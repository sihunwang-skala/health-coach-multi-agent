"""Dataset statistics computed straight from data/users.json and eval/questions.json (single source of truth for the
numbers quoted in README and docs; tests/test_eval_dataset.py compares the docs with these values). Read only.
    .venv/bin/python eval/dataset_stats.py
"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dataset_stats() -> dict:
    users = json.loads((ROOT / "data" / "users.json").read_text())
    q = json.loads((ROOT / "eval" / "questions.json").read_text())
    ages = [u["age"] for u in users]
    health = q["health"]
    return {
        "profiles": len(users),
        "unique_ids": len({u["id"] for u in users}),
        "age_min": min(ages), "age_max": max(ages),
        "aged_65_plus": sum(a >= 65 for a in ages),
        "type2_diabetes": sum("type 2 diabetes" in u["conditions"] for u in users),
        "health_questions": len(health),
        "by_domain": dict(Counter(x["domain"] for x in health)),
        "by_type": dict(Counter(x["type"] for x in health)),
        "service_messages": len(q["routing"]) + len(q.get("refusal", [])),
        "total_messages": len(health) + len(q["routing"]) + len(q.get("refusal", [])),
    }


if __name__ == "__main__":
    print(json.dumps(dataset_stats(), indent=2))
