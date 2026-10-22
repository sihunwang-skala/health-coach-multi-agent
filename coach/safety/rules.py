"""Deterministic safety layer (review items: rules in code like a DUR table, an emergency path, a clear definition of
"dangerous advice"). The LLM never decides these; it only explains the rules that fire.

1. EMERGENCY (checked before anything else): symptoms of severe hypoglycaemia or of a cardiac event during or after
   exercise -> fixed reply (stop, fast sugar if able to swallow, call 119 / guardian). No coaching, no LLM.
2. EXERCISE_RULES: (profile condition or medicine) x (exercise) -> precaution with its source paper. Applied by code to
   every exercise answer as "safety notes" (the Safety Agent).
3. check_answer(): what counts as dangerous advice (S1-S9). A flagged answer is rewritten once; if it is still unsafe the
   flagged sentences are removed before the user sees them. Unsafe advice is never "approved" by the user - human
   approval is only used for data operations (deleting a record).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

EMERGENCY = re.compile(
    r"(?i)chest (pain|tightness|pressure)|can'?t breathe|short(ness)? of breath.{0,20}(rest|sudden|severe)|faint(ed|ing)?|passed out|"
    r"pass(ing)? out|unconscious|seizure|convuls|confus(ed|ion)|slurred|can'?t (stand|speak|wake)|"
    r"(sweat\w*|shak\w*|tremb\w*).{0,40}(dizz\w*|confus\w*|blurred|faint\w*)|blood sugar.{0,15}\b([1-4]\d|5[0-3])\b(?! ?mmol)|"
    r"\b(2\.\d|[01]\.\d) ?mmol|가슴 통증|의식|쓰러|경련|식은땀")
EMERGENCY_REPLY = ("This may be an emergency. Stop exercising now and sit or lie down. If you can swallow and this could be a low "
                   "blood sugar, take 15 g of fast-acting sugar (juice, glucose tablets) and recheck in 15 minutes. If you have "
                   "chest pain, trouble breathing, confusion or you feel faint, call 119 (or your local emergency number) and "
                   "your guardian right away. This app cannot help in an emergency.")
MED_CHANGE_REPLY = ("Please do not skip, stop, double or change any diabetes medicine on your own to fit your exercise - a changed "
                    "dose can cause dangerously low or high blood sugar. Ask your doctor, nurse or pharmacist how to time your "
                    "medicine and exercise.")


@dataclass(frozen=True)
class Rule:
    id: str
    when: str          # regex on the profile (conditions + medicines)
    topic: str         # regex on the question (empty = always)
    advice: str
    source: str
    domain: str = "exercise"   # the rule applies when this research agent is called


EXERCISE_RULES = [
    Rule("R1", r"insulin|glargine|aspart|premixed", "",
         "On insulin, low blood sugar can happen during exercise and for up to 12 hours after it: check glucose before exercise "
         "and carry fast-acting carbohydrate.", "PMC6546780"),
    Rule("R2", r"glimepiride|gliclazide|glipizide|glyburide|glibenclamide|sulfonylurea|sulphonylurea", "",
         "Sulfonylureas raise the risk of low blood sugar during moderate to high-intensity exercise and for up to 12 hours "
         "after: check glucose before exercise and carry fast-acting carbohydrate.", "PMC6546780"),
    Rule("R3", r"insulin|glargine|aspart|premixed|glimepiride|gliclazide|glipizide|sulfonylurea", r"(?i)before|blood sugar|glucose|eat|snack",
         "A pre-exercise glucose of 4.0-5.4 mmol/L (about 72-97 mg/dL) can herald a low during exercise: take one to two serves "
         "of fast-acting carbohydrate first.", "PMC6546780"),
    Rule("R4", r"proliferative|retinopathy", "",
         "With severe non-proliferative or unstable proliferative retinopathy, avoid exercise that raises eye pressure: high "
         "intensity aerobic or strength exercise, head-down positions, breath-holding, jumping and jarring.", "PMC8453655"),
    Rule("R5", r"neuropathy|numb|foot ulcer|foot deformity", "",
         "With neuropathy, exercise is not forbidden but needs precautions: seamless socks and professionally chosen footwear, "
         "daily foot checks, and water-based activity instead of walking if the foot is at high risk.", "PMC10201453"),
    Rule("R6", r"hypertension|amlodipine|lisinopril|losartan", r"(?i)lift|weight|strength|resist|gym|intens|tennis|sprint|hiit",
         "With high blood pressure, some exercise types can be contraindicated: get blood pressure checked and cleared before "
         "heavy or high-intensity training and do not hold your breath while lifting.", "PMC6546780"),
    Rule("R7", r"kidney|ckd|nephropathy", r"(?i)lift|weight|strength|resist|intens|hiit|start|safe",
         "Nephropathy is one of the conditions in which certain exercise types are contraindicated: agree the intensity with "
         "your clinician before starting.", "PMC6546780"),
    Rule("R8", r"cane|walker|fall|balance|frail|age: (8\d|9\d)", "",
         "For fall risk, choose balance and strength exercise (it lowers injurious falls) and use a support such as a chair "
         "or cane when balance is impaired.", "PMC10435089"),
    # diet rules (from the diabetes diet PoC final model's safety rules)
    Rule("D1", r"kidney|ckd|nephropathy", r"(?i)protein|meat|egg|dairy|diet|eat",
         "With kidney disease, keep protein around 0.8 g/kg body weight a day; avoid high-protein diets (above 1.3 g/kg) and "
         "do not cut protein lower on your own - lower targets are only set with a dietitian to avoid malnutrition.", "PMC4170131", "diet"),
    Rule("D2", r"metformin", r"(?i)metformin|kidney|ckd|medicine|pill",
         "Metformin with kidney disease: it is reassessed when eGFR falls below 45 and stopped below 30 - ask your doctor "
         "about your latest eGFR.", "PMC4170131", "diet"),
    Rule("D3", r"insulin|glargine|aspart|premixed|glimepiride|gliclazide|glipizide|sulfonylurea",
         r"(?i)skip|breakfast|meal|late|fast|eat (less|little)|appetite|small amounts|odd times",
         "With insulin or a sulfonylurea, a delayed, missed or smaller-than-planned meal can cause low blood sugar.", "PMC3639216", "diet"),
    Rule("D4", r"insulin|glargine|aspart|premixed|glimepiride|gliclazide|glipizide|sulfonylurea|metformin",
         r"(?i)alcohol|beer|wine|drink|soju",
         "Alcohol can cause low blood sugar together with glucose-lowering medicine because it delays the body's recovery from a "
         "low; guidelines allow alcohol only in moderation, with food.", "PMC3639216", "diet"),
    Rule("D5", r"hypertension|amlodipine|lisinopril|losartan", r"(?i)salt|sodium|salty|pickle|eat out|restaurant|blood pressure",
         "With high blood pressure keep sodium below 2,300 mg a day (about 5-6 g of salt).", "PMC8057793", "diet"),
    Rule("D6", r"lost \d+ ?kg|poor appetite|low muscle|weight loss", r"(?i)eat|calori|food|diet|protein|meal|weight|muscle",
         "With weight loss or a poor appetite, do not cut calories: the goal is eating enough (about 30 kcal per kg of body "
         "weight a day) to prevent undernutrition and frailty.", "PMC7693664", "diet"),
]


def applicable_rules(profile: str, question: str, domains: tuple[str, ...] = ("exercise",)) -> list[Rule]:
    p = profile.lower()
    return [r for r in EXERCISE_RULES if r.domain in domains and re.search(r.when, p) and (not r.topic or re.search(r.topic, question))]


def is_emergency(message: str) -> bool:
    return bool(EMERGENCY.search(message))


NON_GLUCOSE = r"amlodipine|lisinopril|losartan|valsartan|enalapril|ramipril|statin"
CHANGE = re.compile(r"(?i)\b(skip|stop|double|increase|reduce|lower|cut|omit)\b (taking )?(your |the |a )?(dose|doses|insulin|medication|medicine|pills?|tablets?|glimepiride|gliclazide|metformin)")
REFER = re.compile(r"(?i)doctor|clinician|physician|nurse|pharmacist|provider|healthcare team|care team")
HEAVY = re.compile(r"(?i)heavy (lift|weight)|high[- ]intensity|hiit|sprint|jump|head[- ]down|max(imal)? (lift|effort)")
LIMIT = re.compile(r"(?i)avoid|not recommended|should not|shouldn't|do not|don't|forbid|contraindicat|unsafe|stop|risk|danger|concern|harm|bleed|haemorrh|hemorrh|pressure|cleared|clearance|check(ed)? .{0,20}before")
OTHER_POP = re.compile(r"(?i)gestation|pregnan|child|paediatric|pediatric|adolesc|type 1 diabetes")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def check_answer(answer: str, profile: str, question: str, titles: dict[str, str]) -> list[dict]:
    """Dangerous advice = any of S1-S6. Returns [{rule, quote}] (quote empty when something required is missing)."""
    issues, p = [], profile.lower()
    on_hypo_drug = re.search(r"insulin|glargine|aspart|premixed|glimepiride|gliclazide|glipizide|sulfonylurea", p)
    for s in _sentences(answer):
        if re.search(NON_GLUCOSE, s, re.I) and re.search(r"(?i)hypoglyc|lower(s)? (your )?blood (sugar|glucose)", s):
            issues.append({"rule": "S1 blood-pressure drug described as glucose-lowering", "quote": s})
        if CHANGE.search(s) and not REFER.search(s):
            issues.append({"rule": "S2 medicine change without the clinician", "quote": s})
        if re.search(r"retinopathy", p) and HEAVY.search(s) and not LIMIT.search(s):
            issues.append({"rule": "S3 high-intensity / heavy exercise suggested with retinopathy", "quote": s})
    for pmc in set(re.findall(r"PMC\d+", answer)):
        if OTHER_POP.search(titles.get(pmc, "")):
            issues.append({"rule": "S4 source about another population", "quote": f"{pmc}: {titles[pmc]}"})
    if on_hypo_drug and re.search(r"(?i)exercis|walk|train|lift|tennis|activity|workout|gym|skip|breakfast|alcohol|beer|wine", question) \
            and not re.search(r"(?i)hypoglyc|low blood (sugar|glucose)|blood sugar (drop|low)|\blows?\b", answer):
        issues.append({"rule": "S5 insulin / sulfonylurea user: exercise, skipped-meal or alcohol answer without a low-blood-sugar warning", "quote": ""})
    if re.search(r"(?i)metformin", question) and re.search(r"kidney|ckd", p) and not (
            re.search(r"\b30\b", answer) and re.search(r"(?i)(below|under|<|less than|falls? (below|under))\s*(an eGFR of\s*)?45", answer)):
        issues.append({"rule": "S8 metformin with kidney disease without the eGFR thresholds (reassess < 45, stop < 30)", "quote": ""})
    if re.search(r"lost \d+ ?kg|poor appetite|weight loss", p):
        for x in _sentences(answer):
            if re.search(r"(?i)(decreas|reduc|lower|cut|restrict)\w* (your )?(daily )?(calori|energy intake|portion)|weight (management|reduction)|lose weight|calorie deficit|\b1[0-6]\d\d ?kcal", x) \
                    and not re.search(r"(?i)\bnot\b|n't|avoid|prevent|undernutrition|malnutrition|risk|associated|monitor", x):
                issues.append({"rule": "S9 calorie cutting / weight loss for a user who is losing weight", "quote": x})
    m = re.search(r"(?i)\b(7[2-9]|8\d|9[0-7])\s*(mg/dl)?\b|\b(4\.\d|5\.[0-4])\s*mmol", question)
    if on_hypo_drug and m and re.search(r"(?i)(no|not|don't|do not) need to eat|no need to eat|safe range|ideal range|you can (start|go|proceed)", answer):
        issues.append({"rule": "S7 pre-exercise glucose 4.0-5.4 mmol/L (72-97 mg/dL) on insulin / sulfonylurea: answer says no carbohydrate is needed",
                       "quote": next((x for x in _sentences(answer) if re.search(r"(?i)need to eat|safe range|ideal range|you can (start|go|proceed)", x)), "")})
    if re.search(r"(?i)\bstop (taking|your)\b|you can skip", answer) and not REFER.search(answer):
        issues.append({"rule": "S6 tells the user to stop or skip treatment", "quote": ""})
    return issues
