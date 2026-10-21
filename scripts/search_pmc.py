"""Candidate exercise papers from PubMed Central (open access subset), by topic. Free NCBI E-utilities, no key."""
import json
import sys
import time
import urllib.parse
import urllib.request

TOPICS = {
    "hypoglycemia_insulin": 'exercise AND "type 2 diabetes" AND hypoglycemia AND (insulin OR sulfonylurea) AND review[pt]',
    "position_statement": '"physical activity" AND exercise AND diabetes AND ("position statement" OR guideline OR consensus)',
    "resistance_older": '"resistance training" AND "type 2 diabetes" AND (older OR elderly) AND (meta-analysis OR review)',
    "postprandial_walking": '(walking OR "light activity") AND postprandial AND glucose AND "type 2 diabetes"',
    "falls_balance": '(balance OR "fall prevention") AND exercise AND older adults AND (meta-analysis OR review)',
    "neuropathy_foot": 'exercise AND ("peripheral neuropathy" OR "diabetic foot") AND diabetes AND (review OR trial)',
    "retinopathy": 'exercise AND "diabetic retinopathy" AND (risk OR safety)',
    "ckd_exercise": 'exercise AND "chronic kidney disease" AND (older OR elderly) AND review',
    "hypertension_exercise": 'exercise AND hypertension AND "blood pressure" AND (older OR elderly) AND meta-analysis',
    "sarcopenia_exercise": 'sarcopenia AND "resistance exercise" AND older adults AND review',
    "steps_glycemic": '(steps OR walking) AND HbA1c AND "type 2 diabetes" AND meta-analysis',
    "hiit_older_t2d": '"high-intensity interval" AND "type 2 diabetes" AND (older OR safety)',
}
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def main():
    out = {}
    for k, q in TOPICS.items():
        term = urllib.parse.quote(f'({q}) AND "open access"[filter] AND 2012:2025[pdat]')
        ids = get(f"{BASE}esearch.fcgi?db=pmc&retmode=json&retmax=8&sort=relevance&term={term}")["esearchresult"]["idlist"]
        time.sleep(0.4)
        summ = get(f"{BASE}esummary.fcgi?db=pmc&retmode=json&id={','.join(ids)}")["result"] if ids else {}
        time.sleep(0.4)
        out[k] = [{"pmcid": "PMC" + i, "title": summ[i]["title"], "year": summ[i].get("pubdate", "")[:4],
                   "journal": summ[i].get("source", "")} for i in ids if i in summ]
        for x in out[k]:
            print(k, x["pmcid"], x["year"], x["title"][:110])
    json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "candidates.json", "w"), indent=1)


if __name__ == "__main__":
    main()
