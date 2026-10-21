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
