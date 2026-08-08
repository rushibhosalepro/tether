"""The LLM's entire job, and the fence around it.

Tether calls a model in exactly one place: when the graph says a change reaches a live
model, but the change might be semantically harmless (a rename that is also aliased in the
same PR, a retype the feature transform already normalises).

The contract, enforced by `soften` and asserted in tests/test_llm_cannot_block.py:

  - it may turn BLOCK into WARN
  - it may attach an explanation to any verdict
  - it may NOT turn PASS or WARN into BLOCK
  - it may NOT invent impacts

If the model is unreachable or returns garbage, the deterministic verdict stands unchanged.
Failing closed is the correct direction here: an unavailable LLM must never unblock a PR.
"""

from __future__ import annotations

import json
import os

from .models import DecidedBy, Level, Verdict

PROMPT = """You are reviewing one column-level schema change against one production ML model.

Change: {change}
Model: {model} (owners: {owners}, last trained: {last_trained})
Deterministic verdict: {level} because {reason}

Question: is there evidence IN THE DIFF BELOW that this change is safe for that model,
for example the column being aliased to its old name, or a backfill that preserves values?

Diff context:
{context}

Answer with JSON only: {{"safe": true|false, "why": "one sentence"}}
Answer false unless the evidence is explicit. Do not speculate.
"""


def soften(verdict: Verdict, diff_context: str, client=None) -> Verdict:
    """Possibly downgrade BLOCK to WARN. Never the reverse."""
    if verdict.level is not Level.BLOCK:
        return verdict
    if os.getenv("TETHER_NO_LLM") == "1":
        return verdict

    try:
        raw = _ask(verdict, diff_context, client)
        parsed = json.loads(raw)
    except Exception:
        return verdict  # fail closed: the block stands

    if not isinstance(parsed, dict) or parsed.get("safe") is not True:
        return verdict

    why = str(parsed.get("why", ""))[:300]
    return Verdict(
        change=verdict.change,
        level=Level.WARN,  # the only transition this function can make
        impacts=verdict.impacts,
        reason=verdict.reason,
        rule_id=verdict.rule_id,
        decided_by=DecidedBy.LLM_SOFTENED,
        llm_note=why,
    )


def _ask(verdict: Verdict, diff_context: str, client) -> str:
    """Single Anthropic call. Kept tiny and swappable so tests can inject a fake."""
    if client is None:
        from anthropic import Anthropic

        client = Anthropic()

    impact = verdict.impacts[0]
    msg = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": PROMPT.format(
                    change=verdict.change.label(),
                    model=impact.model_name,
                    owners=", ".join(impact.owners) or "unowned",
                    last_trained=impact.last_trained or "unknown",
                    level=verdict.level.value,
                    reason=verdict.reason,
                    context=diff_context[:4000],
                ),
            }
        ],
    )
    return msg.content[0].text.strip()
