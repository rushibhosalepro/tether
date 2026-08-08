# Running test log

One line per test, written as it happens, pass or fail. Failures stay in. At submission
time this file is the evidence, not something assembled afterwards.

Format: `date time — what was tested → result`

## 2026-08-08 — scaffold and first tests

**Environment**

- 12:38 — Docker Desktop up, `datahub docker quickstart` containers running: gms, frontend, kafka, mysql, opensearch → PASS
- 12:41 — GMS `/health` returned 000 (still booting at 48s) → FAIL, expected, retried
- 13:05 — GMS `http://localhost:8080/health` → 200, frontend `http://localhost:9002` → 200 → PASS
- 13:06 — `datahub` CLI not on PATH in this Python env → FAIL, install pending before datapack load

**Classifier, rules R0–R5 (9 tests, `tests/test_classifier.py`)**

- 12:55 — R0 no ML consumer downstream → PASS (returns PASS, does not block)
- 12:55 — R1 DROP under a model with IN_PRODUCTION deployment → PASS (returns BLOCK)
- 12:55 — R2 RENAME under a live model → PASS (returns BLOCK)
- 12:55 — R4 SEMANTIC change under a live model → PASS (returns BLOCK)
- 12:55 — R3a widening int→bigint → PASS (returns WARN, not BLOCK)
- 12:55 — R3a widening float→double → PASS (returns WARN)
- 12:55 — R3a widening date→timestamp → PASS (returns WARN)
- 12:55 — R3b type class change int→varchar(32) → PASS (returns BLOCK)
- 12:55 — R5 model reached but nothing deployed → PASS (returns WARN, not BLOCK)

**Determinism boundary (5 tests, `tests/test_llm_cannot_block.py`)**

- 12:55 — LLM cannot raise a PASS verdict to BLOCK → PASS
- 12:55 — LLM may downgrade BLOCK to WARN when the diff proves it safe → PASS
- 12:55 — LLM raises an exception (no API key) → block stands → PASS (fails closed)
- 12:55 — LLM returns prose instead of JSON → block stands → PASS (fails closed)
- 12:55 — a BLOCK forged with an LLM attribution is rejected by `assert_deterministic` → PASS

**Diff parser (4 tests, `tests/test_parser.py`)**

- 13:10 — dbt model diff, dropped column detected on the real case file → PASS
- 13:10 — same diff produces exactly one change, no phantom columns → PASS
- 13:10 — DDL `ALTER TABLE ... RENAME COLUMN` and `ALTER COLUMN ... TYPE` both parsed → PASS
- 13:10 — non-SQL files in the diff are ignored → PASS

**Totals so far: 18 tests, 18 pass, 0 fail.** Nothing here touches DataHub yet, so none of it
is the headline number. It is the floor under the headline number.

<!-- append below as you go. suggested next entries:
- datapack showcase-ecommerce loaded, N entities visible
- resolve_dataset("orders") returns a URN
- emit_ml_layer --dry-run, all source tables resolve
- emit_ml_layer live, mlModel page renders
- forward lineage from orders.discount_pct reaches churn_propensity_v4  <- the go/no-go
- raiseIncident against a model URN returns an incident urn
- incident visible on the model page in the UI
- addLink writes institutionalMemory on the column
- diff parser on case 001 finds exactly one DROP
- end to end: tether check on case 001 returns BLOCK
- GitHub check run appears red on a real PR
- bench both arms, N cases
-->

## Tricky cases, deliberately trying to break it

<!-- these are worth more to a judge than twenty easy passes:
- column dropped that NO model reads → must PASS, not block (a gate that blocks everything gets disabled)
- column renamed AND aliased back in the same PR → LLM should downgrade to WARN
- model exists but has no deployment → WARN not BLOCK
- column that cannot be resolved in DataHub at all → PASS with the reason recorded, no crash
- DataHub unreachable mid-run → the check must not pass silently
- same PR run twice → exactly one incident, not two
-->
