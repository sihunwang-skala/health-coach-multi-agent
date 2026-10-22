"""MCP server 1 - research-paper search (hybrid dense + BM25 RRF over the exercise corpus, population filter).
Holds no user data: it receives search queries only.
    .venv/bin/python mcp_servers/papers_server.py    # stdio server for external MCP clients
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.config import Settings  # noqa: E402
from coach.retrieval.index import Embedder, HybridIndex  # noqa: E402

mcp = FastMCP("coach-papers")


@lru_cache(maxsize=1)
def index() -> HybridIndex:
    s = Settings()
    return HybridIndex(s.data_dir / "papers", Embedder(s.embed_model, s.cache_dir), s.excluded_population, s.rrf_alpha)


def _hit(i: int) -> dict:
    p = index().parents[i]
    return {"pid": i, "pmcid": p["pmcid"], "title": index().meta[p["pmcid"]]["title"], "section": p["section"], "text": p["text"]}


@mcp.tool
def search_papers(queries: list[str], k: int = 10, domain: str = "") -> dict:
    """Top-k paper passages per query (hybrid retrieval, other-population papers filtered out). domain = "diet" or
    "exercise" searches that agent's paper collection only; empty = all papers."""
    # [발표 코드 3-1 | MCP: 논문 검색 기능을 tool로 공개]
    # MCP는 Agent가 논문 검색 기능을 사용하게 해 주는 연결 통로입니다.
    # 실제 논문 검색은 MCP 서버가 담당합니다.
    tops, tokens = index().search(queries, k, domain or None)
    return {"results": {q: [_hit(i) for i in ids] for q, ids in tops.items()}, "embed_tokens": tokens}


@mcp.tool
def search_baseline(question: str, k: int = 5) -> dict:
    """Standard-RAG retrieval for the Before system: the question only, dense top-k, no filter."""
    # [발표 코드 3-2 | MCP: Standard RAG 비교용 tool]
    # 비교 대상인 Standard RAG가 논문을 찾는 방식입니다.
    # 질문 하나로 단순하게 검색합니다.
    ids, tokens = index().dense_only(question, k)
    return {"results": [_hit(i) for i in ids], "embed_tokens": tokens}


@mcp.resource("paper://{pmcid}")
def paper(pmcid: str) -> dict:
    """Title and role of a paper in the corpus."""
    return {"pmcid": pmcid, **index().meta.get(pmcid, {})}


if __name__ == "__main__":
    mcp.run()
