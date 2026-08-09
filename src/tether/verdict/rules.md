# The rules

Every rule below is deterministic. Given the same change and the same graph, the same
verdict comes out. The LLM is not consulted until after a rule has fired, and it can only
downgrade `BLOCK` to `WARN`.

Read `classifier.py` alongside this. If the two ever disagree, the code is right and this
file is a bug.

| Rule | Condition | Level | Why |
|---|---|---|---|
| R0 | No `mlFeature` or `mlModel` downstream of the column | PASS | Nothing to protect. Most changes land here, and that matters: a gate that blocks everything gets turned off. |
| R1 | `DROP`, and a model with an `IN_SERVICE` deployment reads the column | **BLOCK** | The feature transform will fail or null out. This is the case the whole project exists for. |
| R2 | `RENAME`, same condition | **BLOCK** | A feature definition binds to a column name. A rename is a drop with extra steps. |
| R3a | `RETYPE` that widens (`int`→`bigint`, `float`→`double`, `date`→`timestamp`) | WARN | Anything that handled the narrow type handles the wide one. Worth a look, not worth a block. |
| R3b | `RETYPE` that crosses type class (numeric ↔ string) | **BLOCK** | The transform either throws or coerces silently, and the silent coercion is worse. |
| R3c | `RETYPE` that narrows within a class | WARN | Truncation risk, dependent on data, not decidable from the graph. |
| R4 | `SEMANTIC`, declared by the author with `-- tether: semantic <table>.<column>` | **BLOCK** | Same name, same type, different meaning. Nothing throws, ever. The model keeps scoring and is quietly wrong. This is the failure mode DataHub's ML lineage is uniquely able to catch. |
| R5 | Reaches a model, but no deployment is serving | WARN | A real dependency with no live blast radius. Flag it, do not stop the merge. |
| R-untracked | The table is reachable in DataHub but not cataloged | PASS, reason recorded | Tether can only protect what DataHub knows. A genuinely untracked staging table should not block every PR. |
| R-error | Tether could **not** verify: unreachable DataHub, a walk that threw, a parse failure | **ERROR (fails the check)** | A gate must fail closed. A green check on a PR Tether never actually checked is the worst outcome, so an unverifiable change goes red and blocks merge. |

## PASS vs ERROR: the difference is knowledge

R0 and R-untracked are PASS because Tether *successfully determined* there is nothing to
protect. R-error is not PASS, because Tether *could not determine anything*. A checker that
blocks when it is merely unsure gets disabled within a week; a checker that shows green when it
failed to run is a liability. So Tether blocks only on positive evidence of a live consumer, and
fails closed only when it could not look. The cost of the first choice shows up honestly in the
benchmark as false negatives, and those are published.

## Serving state

`IN_SERVICE` above is read from a model property (OSS DataHub does not expose deployment
entities over GraphQL): a configurable `TETHER_SERVING_PROPERTY` (default `serving`), or mlflow's
`stage`. If neither is present, the model is treated as **live** and the verdict says so, because
a false negative on a serving model is the expensive error.

## Where the LLM sits

After a rule fires, and only on `BLOCK`. It is asked one question: does the diff itself
contain explicit evidence this is safe, for example the column being aliased back to its old
name in the same PR. It answers with JSON. Anything other than an explicit `{"safe": true}`
leaves the block standing, including a timeout, a missing API key, or prose instead of JSON.

Asserted in `tests/test_llm_cannot_block.py`.
