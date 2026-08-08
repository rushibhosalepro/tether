"""The deterministic classifier.

This is the ONLY module in Tether that is allowed to produce Level.BLOCK.
`llm_assist` runs after this and may downgrade a verdict, never upgrade one.
See rules.md for the rules in English and tests/test_llm_cannot_block.py for the assertion.
"""

from __future__ import annotations

from .models import ChangeKind, ColumnChange, DecidedBy, Impact, Level, Verdict

# Type widenings that cannot break a consumer that already handled the narrow type.
SAFE_WIDENINGS: set[tuple[str, str]] = {
    ("int", "bigint"),
    ("smallint", "int"),
    ("smallint", "bigint"),
    ("float", "double"),
    ("date", "timestamp"),
}

NUMERIC = {"int", "bigint", "smallint", "float", "double", "decimal", "numeric"}
STRINGY = {"varchar", "string", "text", "char"}


def _base_type(t: str | None) -> str:
    if not t:
        return ""
    return t.strip().lower().split("(")[0]


def _type_class(t: str) -> str:
    b = _base_type(t)
    if b in NUMERIC:
        return "numeric"
    if b in STRINGY:
        return "string"
    return b


def classify(change: ColumnChange, impacts: list[Impact]) -> Verdict:
    """Decide a level for one change given everything it reaches in the ML layer."""
    live = [i for i in impacts if i.is_live]
    reached = impacts

    # R0: nothing in the ML layer consumes this column.
    if not reached:
        return Verdict(
            change=change,
            level=Level.PASS,
            impacts=[],
            reason="No production ML feature or model consumes this column.",
            rule_id="R0",
        )

    names = ", ".join(sorted({i.model_name for i in live or reached}))

    # R1: dropping a column a live model is serving from.
    if change.kind is ChangeKind.DROP and live:
        return Verdict(
            change=change,
            level=Level.BLOCK,
            impacts=live,
            reason=(
                f"{change.label()} is a declared input to {len(live)} model(s) currently "
                f"in production: {names}."
            ),
            rule_id="R1",
        )

    # R2: renaming is a drop plus an add as far as a feature definition is concerned.
    if change.kind is ChangeKind.RENAME and live:
        return Verdict(
            change=change,
            level=Level.BLOCK,
            impacts=live,
            reason=(
                f"{change.label()} is renamed to {change.new_name}. Feature definitions bind "
                f"to the old name for {len(live)} live model(s): {names}."
            ),
            rule_id="R2",
        )

    # R3: type change. Widening is survivable, changing class is not.
    if change.kind is ChangeKind.RETYPE and live:
        pair = (_base_type(change.old_type), _base_type(change.new_type))
        if pair in SAFE_WIDENINGS:
            return Verdict(
                change=change,
                level=Level.WARN,
                impacts=live,
                reason=(
                    f"{change.label()} widens {change.old_type} -> {change.new_type}. "
                    f"Survivable, but {names} should be re-validated."
                ),
                rule_id="R3a",
            )
        if _type_class(change.old_type or "") != _type_class(change.new_type or ""):
            return Verdict(
                change=change,
                level=Level.BLOCK,
                impacts=live,
                reason=(
                    f"{change.label()} changes type class "
                    f"{change.old_type} -> {change.new_type} under live model(s): {names}."
                ),
                rule_id="R3b",
            )
        return Verdict(
            change=change,
            level=Level.WARN,
            impacts=live,
            reason=f"{change.label()} narrows within the same type class under {names}.",
            rule_id="R3c",
        )

    # R4: semantics changed silently. This is the case that never throws at runtime.
    if change.kind is ChangeKind.SEMANTIC and live:
        return Verdict(
            change=change,
            level=Level.BLOCK,
            impacts=live,
            reason=(
                f"{change.label()} keeps its name and type but changes meaning. "
                f"{names} will keep scoring and will be silently wrong."
            ),
            rule_id="R4",
        )

    # R5: reaches a model, but nothing is deployed. Real dependency, no live blast radius.
    return Verdict(
        change=change,
        level=Level.WARN,
        impacts=reached,
        reason=(
            f"{change.label()} feeds {len(reached)} model(s) with no active deployment: "
            f"{', '.join(sorted({i.model_name for i in reached}))}."
        ),
        rule_id="R5",
    )


def assert_deterministic(v: Verdict) -> Verdict:
    """Guard used at the boundary. A BLOCK must never carry an LLM attribution."""
    if v.level is Level.BLOCK and v.decided_by is not DecidedBy.DETERMINISTIC:
        raise AssertionError(
            f"BLOCK verdict on {v.change.label()} was attributed to {v.decided_by}. "
            "Only the deterministic classifier may block."
        )
    return v
