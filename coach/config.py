"""Settings from the environment (.env). One place for every knob, injected into the graph through coach.deps."""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


@dataclass(frozen=True)
class Settings:
    model: str = os.environ.get("COACH_MODEL", "gpt-6-luna")
    effort_fast: str = os.environ.get("COACH_EFFORT_FAST", "none")   # high-volume steps: query chain, picker, short replies
    effort_think: str = os.environ.get("COACH_EFFORT_THINK", "low")  # supervisor, writer (routing and safety-following errors)
    embed_model: str = os.environ.get("COACH_EMBED_MODEL", "text-embedding-3-small")
    data_dir: Path = ROOT / "data"
    cache_dir: Path = ROOT / "cache"
    db_path: Path = Path(os.environ.get("COACH_DB", str(ROOT / "data" / "coach.db")))
    top_k: int = 10            # parents shown to the picker per query
    picks_per_query: int = 2   # the picker keeps the 2 best parents per query (diabetes PoC L101)
    rrf_alpha: float = 0.5     # BM25 weight in the dense + BM25 fusion
    max_retries: int = 1       # safety retry cap ...
    time_budget_s: float = 60  # ... and wall-clock cap, whichever comes first (review item 5)
    price_in: float = float(os.environ.get("COACH_PRICE_IN", "0.10"))    # gpt-6-luna $ per 1M tokens (gpt-4o-mini: 0.15)
    price_out: float = float(os.environ.get("COACH_PRICE_OUT", "0.50"))  # (gpt-4o-mini: 0.60); reasoning tokens bill as output
    price_embed: float = 0.02
    excluded_population: str = r"(?i)gestation|pregnan|child|paediatric|pediatric|adolesc|type 1 diabetes|cystic fibrosis"
    extra: dict = field(default_factory=dict)


def langsmith_privacy() -> None:
    """Review item 1: when LangSmith tracing is on, inputs and outputs (profile, questions, answers) are hidden; only the
    graph structure, timings and token counts leave the machine. Set COACH_TRACE_CONTENT=1 only for synthetic test users."""
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true" and os.environ.get("COACH_TRACE_CONTENT") != "1":
        os.environ.setdefault("LANGSMITH_HIDE_INPUTS", "true")
        os.environ.setdefault("LANGSMITH_HIDE_OUTPUTS", "true")
