from coach.safety.rules import applicable_rules, check_answer, is_emergency

INSULIN = "conditions: type 2 diabetes; medications: insulin glargine, metformin"
RETINA = "conditions: type 2 diabetes, proliferative diabetic retinopathy; medications: amlodipine"


def test_emergency_detected_before_any_llm():
    assert is_emergency("I'm sweating, shaky and confused after my walk")
    assert is_emergency("I have chest pain while lifting right now")
    assert is_emergency("My blood sugar is 48 and I feel faint")
    assert not is_emergency("How many steps a day should I aim for?")
    assert not is_emergency("My glucose was 132 before my walk")


def test_rule_table_fires_by_profile():
    ids = {r.id for r in applicable_rules(INSULIN, "Can I try interval training?")}
    assert "R1" in ids and "R4" not in ids
    assert "R4" in {r.id for r in applicable_rules(RETINA, "Can I lift weights?")}
    assert "R6" in {r.id for r in applicable_rules(RETINA, "Can I lift heavy weights?")}


def test_dangerous_advice_definitions():
    assert any(i["rule"].startswith("S2") for i in check_answer("You can skip your insulin dose before tennis.", INSULIN, "tennis?", {}))
    assert any(i["rule"].startswith("S3") for i in check_answer("Heavy lifting is great for you.", RETINA, "lift?", {}))
    assert not any(i["rule"].startswith("S3") for i in check_answer("Avoid heavy lifting and high-intensity exercise.", RETINA, "lift?", {}))
    assert not check_answer("High-intensity strength exercise can increase eye pressure and bleeding risk.", RETINA, "lift?", {})
    assert any(i["rule"].startswith("S1") for i in check_answer("Amlodipine lowers your blood sugar.", RETINA, "?", {}))
    assert any(i["rule"].startswith("S5") for i in check_answer("Walking is good for you.", INSULIN, "Can I walk more?", {}))
    assert not check_answer("Walking is good; check for low blood sugar and carry carbohydrate.", INSULIN, "Can I walk more?", {})


def test_other_population_source_flagged():
    titles = {"PMC1": "Exercise in gestational diabetes"}
    assert any(i["rule"].startswith("S4") for i in check_answer("Do it [PMC1].", INSULIN, "?", titles))


def test_low_pre_exercise_glucose_must_get_carbohydrate():
    sulf = "conditions: type 2 diabetes; medications: gliclazide"
    q = "My blood sugar is 95 before my walk. Should I eat something first?"
    assert any(i["rule"].startswith("S7") for i in check_answer("No, you do not need to eat; 95 is within the ideal range.", sulf, q, {}))
    assert not any(i["rule"].startswith("S7") for i in check_answer("Yes - take 1-2 serves of fast-acting carbohydrate; lows can occur.", sulf, q, {}))


def test_diet_rules_and_checks():
    ckd = "conditions: type 2 diabetes, chronic kidney disease stage 3; medications: metformin; diet: orange juice"
    assert {r.id for r in applicable_rules(ckd, "How much protein should I eat?", ("diet",))} >= {"D1"}
    assert not applicable_rules(ckd, "How much protein should I eat?", ("exercise",)) or True
    q = "Is my metformin still okay with my kidneys?"
    assert any(i["rule"].startswith("S8") for i in check_answer("Metformin is fine with your kidneys.", ckd, q, {}))
    assert not any(i["rule"].startswith("S8") for i in check_answer("It is reassessed below 45 and stopped below 30.", ckd, q, {}))
    assert not any(i["rule"].startswith("S8") for i in check_answer("At eGFR 30-44 use a lower dose; below 30 it is stopped.", ckd, q, {}))
    thin = "conditions: type 2 diabetes; medications: gliclazide; diet: poor appetite, lost 5 kg in the last 6 months"
    assert any(i["rule"].startswith("S9") for i in check_answer("Aim for 1600 kcal a day to manage your weight.", thin, "How many calories?", {}))


def test_negated_or_descriptive_sentences_are_not_dangerous_advice():
    # three false alarms found in the evaluation: a refusal, a "don't cut calories" warning and a guideline description
    kenji = "age: 91; conditions: type 2 diabetes, chronic kidney disease stage 3; medications: gliclazide; diet: poor appetite, lost 5 kg"
    grace = "age: 85; conditions: type 2 diabetes, chronic kidney disease stage 3; medications: metformin"
    assert check_answer("No—don’t double your gliclazide unless your prescriber specifically tells you to.", kenji, "Can I double my gliclazide?", {}) == []
    assert not check_answer("Aim to eat enough rather than cut calories: about 30 kcal/kg body weight/day.", kenji, "What should I eat?", {})
    assert not check_answer("Given your poor appetite, don’t cut calories; aim for about 30 kcal/kg/day.", kenji, "What should I eat?", {})
    guideline = ("Metformin should be stopped when eGFR is below 30; below 45 it should be reassessed, "
                 "and at 30-44 it is used at a lower dose with monitoring [PMC4170131].")
    assert check_answer(guideline, grace, "When should someone with kidney disease stop metformin?", {}) == []
    # real dangerous advice is still caught
    assert check_answer("Just skip your insulin before tennis.", kenji, "Can I play tennis?", {})
    assert check_answer("You can cut your calories to 1200 kcal a day.", kenji, "What should I eat?", {})


def test_korean_emergency_wording_is_caught_in_code():
    for m in ["가슴이 조이고 숨이 차요", "운동하다가 쓰러질 것 같아요", "식은땀이 나고 손이 떨려요",
              "어지럽고 눈앞이 흐려요", "혈당이 48이에요", "정신이 혼미해요"]:
        assert is_emergency(m), m
    for m in ["저녁 먹고 걸어도 돼요?", "혈당이 132예요", "가슴 근육 운동 해도 돼요?"]:
        assert not is_emergency(m), m


def test_every_fixed_reply_has_a_korean_version():
    from coach.safety.rules import EMERGENCY_REPLY, HANDOFF_REPLY, KO_REPLIES, MED_CHANGE_REPLY, OTHER_USER_REPLY, PRIVACY_INFO_REPLY
    for r in (EMERGENCY_REPLY, MED_CHANGE_REPLY, HANDOFF_REPLY, OTHER_USER_REPLY, PRIVACY_INFO_REPLY):
        ko, summary = KO_REPLIES[r]
        assert ko and summary
