"""Safety Agent: the exercise rule table applied by code (no LLM) - runs in parallel with the Evidence Agent."""
from coach.agents.common import timed
from coach.safety.rules import applicable_rules


@timed("safety_agent")
async def safety_agent(state, config):
    rules = applicable_rules(state["profile"], state["message"])
    return {"safety_notes": [{"id": r.id, "advice": r.advice, "source": r.source} for r in rules]}
