"""KubeCompass command line: ingestion, refresh, status and evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.config.conferences import get_conference, load_conferences
from app.config.settings import get_settings
from app.infrastructure.logging import configure_logging


def _pipeline(conference_id: str, with_index: bool):  # type: ignore[no-untyped-def]
    from app.infrastructure.elasticsearch import get_es
    from app.infrastructure.embeddings import build_embedding_provider
    from app.ingestion.pipeline import IngestionPipeline
    from app.knowledge_graph.vocabulary import get_vocabulary
    from app.search.indexer import Indexer

    settings = get_settings()
    embeddings = build_embedding_provider(settings)
    indexer = Indexer(get_es(), embeddings.dimensions or None) if with_index else None
    return IngestionPipeline(
        settings, get_conference(conference_id), get_vocabulary(), embeddings, indexer
    )


def cmd_ingest(args: argparse.Namespace) -> int:
    pipeline = _pipeline(args.conference, with_index=not args.no_index)
    result = pipeline.run(remote=args.remote, force=args.force, index=not args.no_index)
    st = result.status
    print(
        json.dumps(
            {
                "state": st.state,
                "version": st.ingestion_version,
                "origin": st.origin,
                "indexed": st.indexed,
                "counts": st.counts,
                "graph": st.graph_stats,
                "changes": st.changes,
                "rejected_records": st.rejected[:10],
                "issues_sample": st.issues[:10],
                "error": st.error,
                "last_successful_version": st.last_successful_version,
            },
            indent=2,
            default=str,
        )
    )
    return 0 if st.state == "succeeded" else 1


def cmd_status(args: argparse.Namespace) -> int:
    from app.ingestion.snapshot import SnapshotStore

    store = SnapshotStore(get_settings().data_dir / "processed", args.conference)
    status = store.load_status()
    print(status.model_dump_json(indent=2) if status else '{"state": "never_ingested"}')
    return 0


def cmd_ensure(args: argparse.Namespace) -> int:
    """Ingest only if Elasticsearch has no index for the conference (container start-up)."""
    from app.infrastructure.elasticsearch import get_es
    from app.knowledge_graph.store import current_version

    if current_version(get_es(), args.conference):
        print(f"{args.conference}: already indexed")
        return 0
    return cmd_ingest(
        argparse.Namespace(remote=False, force=False, no_index=False, conference=args.conference)
    )


def cmd_elastic(args: argparse.Namespace) -> int:
    from app.elastic import setup as elastic

    settings = get_settings()
    if args.action == "create-app-key":
        if not args.output:
            print("--output FILE is required (the key is written there, never printed)")
            return 2
        try:
            key = elastic.create_app_key(args.name, args.expiration)
        except Exception as exc:
            if "derived api keys" not in str(exc):
                raise
            for line in (
                "Cannot create it with an API key: Elasticsearch forbids API keys from minting",
                "keys with privileges. Create it in Kibana instead (logged in as yourself):",
                "  Project settings > API keys > Create API key > Control security privileges",
                "  and paste elasticsearch/security/kubecompass-public-app-role.json",
                "If that dialog only offers other key types, use Kibana Dev Tools (as yourself):",
                '  POST /_security/api_key {"name": "kubecompass-public", "expiration": "90d",',
                '    "role_descriptors": <contents of the role JSON>}  -> copy "encoded"',
            ):
                print(line)
            return 1
        Path(args.output).write_text("KUBECOMPASS_ES_API_KEY=" + key + "\n", encoding="utf-8")
        print(f"Least-privilege key '{args.name}' written to {args.output}")
        return 0
    if args.action == "check":
        rows = elastic.check(settings)
        for name, ok, detail in rows:
            print(f"{'OK  ' if ok else 'FAIL'} {name:28s} {detail}")
        return 0 if all(ok for _, ok, _ in rows) else 1
    report = (
        elastic.teardown(settings)
        if args.action == "teardown"
        else elastic.setup(settings, skip_workflows=args.skip_workflows)
    )
    for line in report.done:
        print("OK  ", line)
    for line in report.failed:
        print("FAIL", line)
    return 0 if report.ok else 1


def cmd_conferences(_: argparse.Namespace) -> int:
    for c in load_conferences().values():
        print(f"{c.id}\t{c.name}\t{c.timezone}\t{c.source.adapter}")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    from app.services.evaluation import run_evaluation

    report = run_evaluation(args.conference, args.dataset, args.output)
    print(json.dumps(report["summary"], indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="kubecompass")
    parser.add_argument("--conference", default=settings.default_conference_id)
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="Validate, normalize, extract and index conference data")
    p.add_argument(
        "--remote",
        action="store_true",
        help="Fetch the configured source endpoints instead of local files",
    )
    p.add_argument(
        "--force", action="store_true", help="Accept a refresh even if it removes many sessions"
    )
    p.add_argument("--no-index", action="store_true", help="Skip Elasticsearch indexing")
    p.set_defaults(func=cmd_ingest)

    sub.add_parser("status", help="Show the last ingestion status").set_defaults(func=cmd_status)
    sub.add_parser("ensure", help="Ingest only if not yet indexed").set_defaults(func=cmd_ensure)
    sub.add_parser("conferences", help="List configured conferences").set_defaults(
        func=cmd_conferences
    )

    el = sub.add_parser(
        "elastic",
        help="Elastic Cloud: check, set up or remove Agent Builder tools/agents and Workflows",
    )
    el.add_argument("action", choices=["check", "setup", "teardown", "create-app-key"])
    el.add_argument("--name", default="kubecompass-public-app", help="create-app-key: key name")
    el.add_argument("--expiration", default=None, help="create-app-key: e.g. 30d")
    el.add_argument("--output", default=None, help="create-app-key: file to write the key to")
    el.add_argument(
        "--skip-workflows",
        action="store_true",
        help="Set up Agent Builder only (e.g. if Workflows is not enabled)",
    )
    el.set_defaults(func=cmd_elastic)

    e = sub.add_parser("evaluate", help="Run the search evaluation dataset")
    e.add_argument("--dataset", default=None)
    e.add_argument("--output", default=None)
    e.set_defaults(func=cmd_evaluate)

    args = parser.parse_args(argv)
    configure_logging(args.log_level, json_output=False)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
