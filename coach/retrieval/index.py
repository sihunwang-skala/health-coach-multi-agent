"""Hybrid retrieval index (same design as the diabetes PoC final model): section-aware parent chunks (~800 chars) with
child chunks (~300 chars) for matching; dense (OpenAI embeddings) + BM25 on the children, fused with RRF (weight 0.5),
mapped to parents. Papers about another population (pregnancy, children, type 1) are filtered out at query time.
Embeddings are cached on disk, so a rebuild or a rerun of the evaluation does not pay twice."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(s: str) -> list[str]:
    return TOKEN.findall(s.lower())


def _split(text: str, size: int) -> list[str]:
    paras, out, cur = [p.strip() for p in text.split("\n") if p.strip()], [], ""
    for p in paras:
        while len(p) > size * 1.5:  # very long paragraph: cut at a sentence end near `size`
            cut = p.rfind(". ", 0, size) + 1 or size
            out.append((cur + " " + p[:cut]).strip()) if cur else out.append(p[:cut].strip())
            cur, p = "", p[cut:].strip()
        if len(cur) + len(p) > size and cur:
            out.append(cur.strip())
            cur = ""
        cur += (" " if cur else "") + p
    if cur.strip():
        out.append(cur.strip())
    return out


def build_chunks(papers_dir: Path, parent_size=800, child_size=300):
    parents, children, meta = [], [], {}
    for f in sorted(papers_dir.glob("PMC*.json")):
        d = json.loads(f.read_text())
        meta[d["pmcid"]] = {"title": d["title"], "role": d["role"]}
        for sec in d["sections"]:
            header = f"{d['title']} > {sec['title']}"
            for ptext in _split(sec["text"], parent_size):
                pi = len(parents)
                parents.append({"pmcid": d["pmcid"], "section": sec["title"], "text": ptext})
                for ctext in _split(ptext, child_size):
                    children.append((pi, f"{header}\n{ctext}"))
    return parents, children, meta


class Embedder:
    def __init__(self, model: str, cache_dir: Path):
        self.model, self.cache_dir = model, cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.qcache_path = cache_dir / f"query_vectors_{model}.json"
        self.qcache = json.loads(self.qcache_path.read_text()) if self.qcache_path.exists() else {}
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def _embed(self, texts: list[str]) -> tuple[np.ndarray, int]:
        vecs, tokens = [], 0
        for i in range(0, len(texts), 512):
            r = self.client.embeddings.create(model=self.model, input=texts[i:i + 512])
            vecs += [d.embedding for d in r.data]
            tokens += r.usage.total_tokens
        v = np.array(vecs, dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True), tokens

    def documents(self, texts: list[str]) -> np.ndarray:
        key = hashlib.sha1(("\n".join(texts) + self.model).encode()).hexdigest()[:16]
        path = self.cache_dir / f"children_{key}.npy"
        if path.exists():
            return np.load(path)
        v, tokens = self._embed(texts)
        np.save(path, v)
        print(f"embedded {len(texts)} children, {tokens} tokens (${tokens * 0.02 / 1e6:.4f})", flush=True)
        return v

    def queries(self, texts: list[str]) -> tuple[np.ndarray, int]:
        """Returns vectors and the number of tokens actually paid (0 when cached)."""
        todo = [t for t in dict.fromkeys(texts) if t not in self.qcache]
        tokens = 0
        if todo:
            v, tokens = self._embed(todo)
            self.qcache.update({t: x.tolist() for t, x in zip(todo, v)})
            self.qcache_path.write_text(json.dumps(self.qcache))
        return np.array([self.qcache[t] for t in texts], dtype=np.float32), tokens


class HybridIndex:
    def __init__(self, papers_dir: Path, embedder: Embedder, excluded_population: str | None = None, alpha: float = 0.5):
        self.parents, self.children, self.meta = build_chunks(papers_dir)
        self.embedder, self.alpha = embedder, alpha
        self.cv = embedder.documents([t for _, t in self.children])
        self.cpar = np.array([pi for pi, _ in self.children])
        self.bm = BM25Okapi([tokenize(t) for _, t in self.children])
        pat = re.compile(excluded_population) if excluded_population else None
        self.excluded = {i for i, p in enumerate(self.parents) if pat and pat.search(self.meta[p["pmcid"]]["title"])}
        self.words = {}  # pmcid -> set of words, for the note check
        for p in self.parents:
            self.words.setdefault(p["pmcid"], set()).update(tokenize(p["text"]))
        self.all_words = set().union(*self.words.values())

    def _rrf(self, lists: list[list[int]], weights: list[float], k: int = 60) -> list[int]:
        score: dict[int, float] = {}
        for lst, w in zip(lists, weights):
            for r, x in enumerate(lst):
                score[x] = score.get(x, 0.0) + w / (k + r + 1)
        return sorted(score, key=lambda x: -score[x])

    def search_vec(self, query: str, qvec: np.ndarray, k: int = 10, filter_population: bool = True) -> list[int]:
        d = list(np.argsort(-(self.cv @ qvec))[:120])
        b = list(np.argsort(-self.bm.get_scores(tokenize(query)))[:120])
        fused = self._rrf([d, b], [1 - self.alpha, self.alpha])
        out = []
        for j in fused:
            pi = int(self.cpar[j])
            if pi in out or (filter_population and pi in self.excluded):
                continue
            out.append(pi)
            if len(out) == k:
                break
        return out

    def search(self, queries: list[str], k: int = 10) -> tuple[dict[str, list[int]], int]:
        vecs, tokens = self.embedder.queries(queries)
        return {q: self.search_vec(q, v, k) for q, v in zip(queries, vecs)}, tokens

    def dense_only(self, query: str, k: int = 5) -> tuple[list[int], int]:
        """Baseline retrieval: the question alone, dense top-k, no fusion, no filter (standard RAG)."""
        vecs, tokens = self.embedder.queries([query])
        order, out = np.argsort(-(self.cv @ vecs[0])), []
        for j in order:
            pi = int(self.cpar[j])
            if pi not in out:
                out.append(pi)
            if len(out) == k:
                break
        return out, tokens
