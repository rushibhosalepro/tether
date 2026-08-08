# Running test log

One line per test, written as it happens, pass or fail. Failures stay in. At submission
time this file is the evidence, not something assembled afterwards.

Format: `date time — what was tested → result`

## 2026-08-08

- 12:40 — `datahub docker quickstart` containers up (gms, frontend, kafka, mysql, opensearch) → PASS
- 12:55 — classifier unit tests, 7 rules R0-R5 → PASS (7/7)
- 12:55 — determinism boundary, LLM cannot raise a verdict to BLOCK → PASS (5/5)
- 12:55 — LLM unreachable / garbage JSON leaves the block standing (fail closed) → PASS

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
