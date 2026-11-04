# Dataset Card: evaluation profiles and messages

This card describes the data used to evaluate the system. Every number below is computed from `data/users.json` and `eval/questions.json` by `eval/dataset_stats.py`, and `tests/test_eval_dataset.py` fails if this card and the data disagree.

## Purpose
To compare four system designs on identical inputs (see `docs/EVALUATION.md`). It is a system evaluation, not a clinical study or a patient trial.

## What the profiles are
- 10 fictional synthetic profiles. They are not real patients and contain no real patient data. Names are invented.
- All 10 include type 2 diabetes.
- Age range: 56 to 94. 8 of 10 profiles are aged 65 or older (the other two are in their fifties).
- Other conditions: chronic kidney disease stage 3 (3 profiles), hypertension (3), peripheral neuropathy (1), low muscle mass (1), proliferative diabetic retinopathy (1).
- Medications: metformin (7), amlodipine (2), glimepiride (2), insulin glargine (2), gliclazide (1), lisinopril (1), premixed insulin (1), insulin aspart (1). Insulin and sulfonylurea use drive the hypoglycemia rules.
- Each profile also has a short activity, mobility, diet and goal description written by the authors.

## What the 100 evaluation messages are
- 60 health questions: 20 exercise, 20 diet, 20 diet plus exercise. In each domain, 10 are personalized (type A) and 10 are general (type B), so 30 personalized and 30 general.
- 40 service messages: 10 about the user's information and records, 10 chat, 10 safety (emergency 5, changing medicine alone 5), 10 service and privacy.
- Total: 100 evaluation messages.
- Personalized question: asks about the user's own health, so the profile must shape the answer. General question: asks a literature question; personalized retrieval is limited, but the Safety Agent still applies profile-based rules.

## Where the profile is used in the pipeline
`run_eval.py` passes each question's `user` to the graph. `guard()` loads that user's profile through the user MCP server. For personalized questions the profile feeds the Supervisor, Evidence Agent, Safety Agent and Writer. Conditions and medications (insulin, sulfonylurea, hypoglycemia, kidney disease, neuropathy, retinopathy, hypertension) are used by the rules in `coach/safety/rules.py`.

## De-identification
Before any profile text goes to an LLM, `profile_text()` (`mcp_servers/user_server.py`) sends health fields only. Name and ID are never included. A test checks this.

## Limitations
- Synthetic profiles were designed by the authors, so they carry selection bias: they cover the risk cases the authors thought of (insulin, kidney disease, retinopathy) and may miss real-world mixtures.
- Ten profiles and 100 messages are small. Scores cannot be generalized to a population.
- Answers were graded by an LLM (Claude) against author-written key points. There was no clinician review.
- Nothing here supports a claim of clinical validity, safety in real patients, or effectiveness for older adults.
- Wording: describe this as a system evaluation on fictional profiles. Do not say "conducted an experiment with 10 diabetes patients" or "clinically validated the system on elderly patients".
- Ages were not changed to fit any claim; results depend on the fixed profiles.

## Needed before any real user study
Clinician review of the safety rules and of a sample of answers, ethics (IRB) approval and informed consent, a contract with zero data retention for any external model, a larger and independently built profile set, and a prospective evaluation with real users.
