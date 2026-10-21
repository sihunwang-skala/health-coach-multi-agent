"""Chunk the corpus and embed the children once (cached in cache/)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coach.config import Settings  # noqa: E402
from coach.retrieval.index import Embedder, HybridIndex  # noqa: E402

s = Settings()
idx = HybridIndex(s.data_dir / "papers", Embedder(s.embed_model, s.cache_dir), s.excluded_population)
print(f"papers {len(idx.meta)} | parents {len(idx.parents)} | children {len(idx.children)} | excluded parents {len(idx.excluded)}")
