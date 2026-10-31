"""Korean output for the Korean-first UI (lang="ko").

The agents, the paper search and the dangerous-advice check S1-S9 all work in English, as evaluated on 2026-10-22. Korean is
added only at the very end: fixed replies use reviewed Korean text (no LLM); LLM answers are translated by one extra call
AFTER the safety check. The Korean text itself is not re-checked by S1-S9 (English rules) - a known, documented limit.
"""
from __future__ import annotations

import asyncio
import re

from coach.safety import rules

FIXED_KO = {
    rules.EMERGENCY_REPLY: ("응급 상황일 수 있습니다. 지금 운동을 멈추고 앉거나 누우세요. 삼킬 수 있고 저혈당일 수 있다면 빠르게 흡수되는 당 "
                            "15 g(주스, 포도당 정제)을 먹고 15분 뒤 혈당을 다시 재세요. 가슴 통증, 숨쉬기 어려움, 혼란, 정신이 흐려지는 "
                            "느낌이 있으면 바로 119(또는 지역 응급 번호)와 보호자에게 연락하세요. 이 앱은 응급 상황에 도움을 드릴 수 없습니다."),
    rules.MED_CHANGE_REPLY: ("운동에 맞추려고 당뇨약을 스스로 거르거나, 끊거나, 두 배로 먹거나, 바꾸지 마세요. 용량이 바뀌면 혈당이 위험할 "
                             "만큼 낮아지거나 높아질 수 있습니다. 약과 운동 시간을 어떻게 맞출지는 의사, 간호사, 약사에게 물어보세요."),
    rules.HANDOFF_REPLY: ("의료진과 연결해 드릴게요. 아래 '의료진 상담 전화' 버튼을 누르거나, 다니는 병원의 간호사·약사에게 직접 문의하세요. "
                          "급하거나 지금 몸이 좋지 않다면 119에 전화하세요."),
    rules.OTHER_USER_REPLY: "본인의 건강 정보만 보여 드릴 수 있습니다. 다른 사람의 기록은 개인정보라서 찾아보거나 알려 드릴 수 없습니다.",
    rules.PRIVACY_INFO_REPLY: ("프로필과 기록은 이 앱의 자체 데이터베이스에 저장됩니다. 건강 질문을 하면 이름은 지우고 답변에 필요한 건강 정보만 "
                               "AI 모델에 보냅니다. 논문 검색에는 개인정보가 전달되지 않습니다. 기록은 본인이 확인한 뒤에만 삭제됩니다."),
    "There is no record to delete.": "삭제할 기록이 없습니다.",
    "Okay, nothing was deleted.": "알겠습니다. 아무것도 삭제하지 않았습니다.",
}

TRANSLATE = """You translate the final answer of a diabetes diet-and-exercise coaching assistant into natural, plain Korean for
an older adult reader.

Goal: the Korean text must say exactly what the English says - no added advice, no removed warning, no softened or stronger
wording - so the safety-checked English answer and the Korean answer mean the same thing.

Task:
- Translate every sentence. Keep numbers, units (mg/dL, mmol/L, minutes, g) and medicine names exactly.
- Keep every citation marker such as [PMC1234567] unchanged, at the end of the same sentence.
- Use polite, simple sentences (존댓말). Do not add a greeting or a summary.
Return JSON: {{"answer": "<Korean text>"}}

English answer:
{answer}"""

MARK = re.compile(r"\[PMC\d+\]")


def fixed_ko(answer: str) -> str | None:
    if answer in FIXED_KO:
        return FIXED_KO[answer]
    if answer.startswith("Deleted: "):
        return "삭제했습니다: " + answer[len("Deleted: "):]
    if answer.startswith("Delete this record? "):
        return "이 기록을 삭제할까요? " + answer[len("Delete this record? "):]
    return None


async def to_korean(deps, usage, answer: str) -> dict:
    """{'answer': Korean text, 'translated': bool}. Falls back to the English answer if the translation dropped a
    citation marker (the Korean text would no longer be traceable to its evidence)."""
    if not answer:
        return {"answer": answer, "translated": False}
    ko = fixed_ko(answer)
    if ko is not None:
        return {"answer": ko, "translated": True}
    j = await asyncio.to_thread(deps.llm.json, "translate_ko", [("user", TRANSLATE.format(answer=answer))], usage)
    out = str(j.get("answer", "")).strip()
    if not out or sorted(MARK.findall(out)) != sorted(MARK.findall(answer)):
        return {"answer": answer, "translated": False}
    return {"answer": out, "translated": True}
