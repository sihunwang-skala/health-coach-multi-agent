"""Download the corpus (PubMed Central open-access XML) into data/raw/ and convert it to data/papers/<PMCID>.json.
Papers already on disk (any XML under the --local dirs) are copied instead of downloaded.
    .venv/bin/python scripts/fetch_papers.py [--local DIR ...]
"""
import json
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coach.retrieval.parse import parse_pmc_xml  # noqa: E402

RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "papers"


def wanted() -> dict[str, str]:
    ids = json.loads((ROOT / "data" / "paper_ids.json").read_text())
    roles = {p: "core" for p in ids["core"]}
    roles.update({p: "distractor_exercise_other_topic" for p in ids["distractor_exercise_other_topic"]})
    for p in (ROOT / "data" / "diet_shelf_ids.txt").read_text().split():
        roles.setdefault(p, "distractor_diabetes_diet_shelf")
    return roles


def local_index(dirs) -> dict[str, Path]:
    idx = {}
    for d in dirs:
        for f in Path(d).rglob("*.xml"):
            m = re.search(r'pub-id-type="(?:pmc|pmcid)"[^>]*>(?:PMC)?(\d+)<', f.read_text(errors="ignore")[:20000])
            if m:
                idx.setdefault("PMC" + m.group(1), f)
    return idx


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    a = sys.argv
    dirs = [a[i + 1] for i, x in enumerate(a) if x == "--local"]
    roles, local = wanted(), local_index(dirs)
    meta = {}
    for pmc, role in roles.items():
        raw = RAW / f"{pmc}.xml"
        if not raw.exists():
            if pmc in local:
                shutil.copy(local[pmc], raw)
            else:
                url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id={pmc[3:]}&rettype=xml"
                raw.write_bytes(urllib.request.urlopen(url, timeout=60).read())
                time.sleep(0.4)
        doc = parse_pmc_xml(raw.read_text(errors="ignore"))
        doc.update(pmcid=pmc, role=role)
        (OUT / f"{pmc}.json").write_text(json.dumps(doc, ensure_ascii=False))
        meta[pmc] = {"title": doc["title"], "role": role, "chars": sum(len(s["text"]) for s in doc["sections"])}
        print(pmc, role, meta[pmc]["chars"], doc["title"][:80])
    (ROOT / "data" / "corpus_meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(f"papers {len(meta)} | core {sum(v['role'] == 'core' for v in meta.values())}")


if __name__ == "__main__":
    main()
