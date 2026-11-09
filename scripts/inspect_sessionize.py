"""Inspect raw Sessionize payloads before (re)designing schemas or mappings.

Usage:
    python -I -X utf8 scripts/inspect_sessionize.py \
        data/raw/kubecon-all.json data/raw/kubecon-speakers.json

Prints structure, record counts, category/question catalogs and data-quality findings.
Standard library only, so it runs before any dependency is installed.
"""

from __future__ import annotations

import json
import sys
from collections import Counter


def main(all_path: str, speakers_path: str) -> int:
    with open(all_path, encoding="utf-8") as f:
        view = json.load(f)
    with open(speakers_path, encoding="utf-8") as f:
        speakers = json.load(f)

    print("== /view/All ==")
    for key, value in view.items():
        size = len(value) if isinstance(value, list) else "-"
        fields = (
            sorted(value[0])
            if isinstance(value, list) and value and isinstance(value[0], dict)
            else []
        )
        print(f"{key:12s} {type(value).__name__:5s} n={size}  fields={fields}")

    sessions = view.get("sessions", [])
    print("\n== Categories ==")
    item_names = {}
    for cat in view.get("categories", []):
        print(f"[{cat['id']}] {cat['title']} ({len(cat['items'])} items)")
        for item in cat["items"]:
            item_names[item["id"]] = (cat["title"], item["name"])
    usage = Counter(
        item_names.get(i, ("?", str(i))) for s in sessions for i in s.get("categoryItems", [])
    )
    for (title, name), n in sorted(usage.items()):
        print(f"    {title} / {name}: {n}")

    print("\n== Questions ==")
    for q in view.get("questions", []):
        print(f"[{q['id']}] {q['question']} ({q.get('questionType')})")

    print("\n== Data quality ==")
    ids = Counter(s["id"] for s in sessions)
    titles = Counter(s["title"] for s in sessions)
    print("sessions:", len(sessions), "| duplicate ids:", sum(1 for c in ids.values() if c > 1))
    print("titles reused across sessions:", sum(1 for c in titles.values() if c > 1))
    print("missing description:", sum(1 for s in sessions if not s.get("description")))
    print(
        "missing start/end:",
        sum(1 for s in sessions if not s.get("startsAt") or not s.get("endsAt")),
    )
    print("no speakers:", sum(1 for s in sessions if not s.get("speakers")))
    print(
        "days:", dict(sorted(Counter((s.get("startsAt") or "none")[:10] for s in sessions).items()))
    )
    print("status:", dict(Counter(s.get("status") for s in sessions)))

    print("\n== /view/Speakers ==")
    print("speakers:", len(speakers), "| fields:", sorted(speakers[0]) if speakers else [])
    sp_ids = {s["id"] for s in speakers}
    all_sp_ids = {s["id"] for s in view.get("speakers", [])}
    print("same ids as All view:", sp_ids == all_sp_ids)
    print("missing bio:", sum(1 for s in speakers if not s.get("bio")))
    print("missing photo:", sum(1 for s in speakers if not s.get("profilePicture")))
    dangling = sum(1 for s in sessions for p in s.get("speakers", []) if p not in all_sp_ids)
    print("session->speaker refs to unknown speakers:", dangling)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
