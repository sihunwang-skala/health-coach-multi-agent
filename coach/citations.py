"""Citation contract for the answer screen (docs/HYBRID_UI.md §3).

The writer ends sentences with paper markers such as [PMC6190726]. This module turns them into numbered citations [1], [2]
and, for each one, the passage the picker chose from that paper plus the sentences inside it that support the answer (the
sentences that share the most words with the verified notes). It only re-shapes what the graph already produced: no LLM.

There is no position inside the paper (no HTML anchor, offset or PDF page) in our index, so `location` is always None and the
UI shows the link and the excerpt only.
"""
from __future__ import annotations

import re

from coach.agents.common import stems

MARK = re.compile(r"\s*\[(PMC\d+)\]")
SENT = re.compile(r"(?<=[.!?])\s+")


def _support(passage: str, notes: list[str]) -> list[str]:
    """Sentences of the passage that back the notes: per note, the passage sentence with the largest word overlap."""
    sents = [s for s in SENT.split(passage) if s.strip()]
    out = []
    for n in notes:
        ns = stems(n)
        best = max(sents, key=lambda s: len(stems(s) & ns), default="")
        if best and len(stems(best) & ns) >= 2 and best not in out:
            out.append(best)
    return out


def build(answer: str, evidence: dict, titles: dict | None = None) -> dict:
    """{'statements': [...], 'citations': [...]} for an answer; empty lists when the answer cites nothing."""
    titles = titles or {}
    order: list[str] = []
    for m in MARK.finditer(answer or ""):
        if m.group(1) not in order:
            order.append(m.group(1))
    num = {p: i + 1 for i, p in enumerate(order)}
    statements = []
    for i, s in enumerate(x for x in SENT.split(answer or "") if x.strip()):
        ids = list(dict.fromkeys(num[p] for p in MARK.findall(s)))
        statements.append({"statement_id": f"s{i + 1}", "text": MARK.sub("", s).strip(), "citation_ids": ids})
    citations = []
    for p in order:
        notes = [n["note"] for ev in (evidence or {}).values() for n in ev.get("notes") or [] if n.get("source") == p]
        chunk = None
        for ev in (evidence or {}).values():
            for pk in ev.get("picks") or []:
                for h in (ev.get("results") or {}).get(pk["query"], []):
                    if h["pid"] in pk["best"] and h["pmcid"] == p and chunk is None:
                        chunk = h
        titles.setdefault(p, (chunk or {}).get("title", ""))
        citations.append({
            "citation_id": num[p], "document_id": p, "title": titles.get(p, ""), "authors_year": None,
            "url": f"https://pmc.ncbi.nlm.nih.gov/articles/{p}/",
            "chunk_id": chunk["pid"] if chunk else None, "section": (chunk or {}).get("section"),
            "source_text": (chunk or {}).get("text"), "support_sentences": _support((chunk or {}).get("text", ""), notes),
            "notes": notes, "translated_text": None, "document_version": "PMC open-access full text (scripts/fetch_papers.py)",
            "location": None})
    return {"statements": statements, "citations": citations}
