"""Deterministic integrity checks for the evaluation data. No API calls. The numbers must match the data files and the
numbers quoted in the docs (docs/DATASET_CARD.md)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from dataset_stats import dataset_stats  # noqa: E402
from mcp_servers.user_server import profile_text  # noqa: E402

USERS = json.loads((ROOT / "data" / "users.json").read_text())
Q = json.loads((ROOT / "eval" / "questions.json").read_text())
S = dataset_stats()


def test_profiles():
    assert S["profiles"] == 10 and S["unique_ids"] == 10
    assert S["type2_diabetes"] == 10


def test_questions():
    assert S["health_questions"] == 60
    assert S["by_domain"] == {"exercise": 20, "diet": 20, "diet_exercise": 20}
    assert S["by_type"] == {"A": 30, "B": 30}
    assert S["total_messages"] == 100


def test_every_question_user_exists():
    ids = {u["id"] for u in USERS}
    for group in ("health", "routing", "refusal"):
        for x in Q.get(group, []):
            assert x["user"] in ids, x["id"]


def test_masking_has_no_name_or_id():
    for u in USERS:
        text = profile_text(u)
        assert u["name"] not in text and u["id"] not in text


def test_age_numbers_match_the_data():
    ages = sorted(u["age"] for u in USERS)
    assert (S["age_min"], S["age_max"], S["aged_65_plus"]) == (ages[0], ages[-1], sum(a >= 65 for a in ages))
    assert (S["age_min"], S["age_max"], S["aged_65_plus"]) == (56, 94, 8)   # the profiles are fixed; evaluation results depend on them


def test_dataset_card_numbers_match():
    card = (ROOT / "docs" / "DATASET_CARD.md").read_text()
    assert f"{S['age_min']} to {S['age_max']}" in card
    assert f"{S['aged_65_plus']} of {S['profiles']}" in card
    assert f"{S['total_messages']} evaluation messages" in card
    assert f"{S['health_questions']} health questions" in card


def test_no_patient_study_claims():
    bad = re.compile(r"(clinically validated|clinical trial was|conducted an experiment with 10|10 diabetes patients|실제 환자 \d+명|당뇨환자 10명)", re.I)
    for f in ("README.md", "docs/DATASET_CARD.md", "docs/EVALUATION.md", "docs/REPORT.md"):
        txt = (ROOT / f).read_text()
        for line in txt.splitlines():
            # the "do not say" list is allowed to quote the forbidden phrases
            if bad.search(line) and "do not" not in line.lower() and "금지" not in line:
                raise AssertionError(f"{f}: {line}")
