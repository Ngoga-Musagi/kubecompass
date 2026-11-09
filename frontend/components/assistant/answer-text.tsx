import Link from "next/link";
import * as React from "react";

import { sessionHref, speakerHref } from "@/lib/format";
import type { Citation } from "@/types/api";

/**
 * Minimal, safe rendering of model answers: paragraphs, "-"/"*"/"1." lists, **bold**, and
 * [S#]/[P#] citations as links. Built from React elements only (no HTML injection).
 */
export function AnswerText({ text, citations }: { text: string; citations: Citation[] }) {
  const byRef = new Map(citations.map((c) => [c.ref, c]));

  const inline = (line: string, key: string) =>
    line.split(/(\[[SP]\d+\]|\*\*[^*]+\*\*)/g).map((part, i) => {
      const cite = part.match(/^\[([SP]\d+)\]$/);
      if (cite) {
        const c = byRef.get(cite[1]!);
        if (!c) return null; // unverifiable citation: drop
        return (
          <Link
            key={`${key}-${i}`}
            href={c.kind === "session" ? sessionHref(c.id) : speakerHref(c.id)}
            title={c.title}
            className="mx-0.5 inline-flex h-[18px] items-center rounded bg-surface-3 px-1 align-[1px] font-mono text-[10.5px] text-ink-2 no-underline hover:bg-needle-soft hover:text-needle-ink"
          >
            {c.ref}
          </Link>
        );
      }
      const bold = part.match(/^\*\*([^*]+)\*\*$/);
      if (bold) return <strong key={`${key}-${i}`} className="font-semibold">{bold[1]}</strong>;
      return <React.Fragment key={`${key}-${i}`}>{part}</React.Fragment>;
    });

  const blocks: React.ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={`l${blocks.length}`} className={list.ordered ? "list-decimal space-y-1.5 pl-5" : "list-disc space-y-1.5 pl-5"}>
        {list.items.map((it, i) => (
          <li key={i}>{inline(it, `l${blocks.length}-${i}`)}</li>
        ))}
      </Tag>,
    );
    list = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    const numbered = line.match(/^\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const ordered = !!numbered;
      if (!list || list.ordered !== ordered) {
        flush();
        list = { ordered, items: [] };
      }
      list.items.push((bullet ?? numbered)![1]!);
      continue;
    }
    flush();
    if (line) blocks.push(<p key={`p${blocks.length}`}>{inline(line.replace(/^#+\s*/, ""), `p${blocks.length}`)}</p>);
  }
  flush();
  return <div className="space-y-3 text-[14.5px] leading-[1.65] text-ink">{blocks}</div>;
}
