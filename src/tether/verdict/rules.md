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
| R5 | Reaches a model, but no deployment is `IN_SERVICE` | WARN | A real dependency with no live blast radius. Flag it, do not stop the merge. |
| R-unresolved | The column cannot be resolved to a DataHub URN | PASS, with the reason recorded | Tether does not block on ignorance. An unresolvable column is a gap in the graph, and saying so is more useful than guessing. |

## Why R0 and R-unresolved are PASS

A checker that blocks when it is unsure gets disabled within a week, and then it protects
nothing. Tether blocks only on positive evidence of a live consumer. The cost of that choice
shows up honestly in the benchmark as false negatives, and those are published.

## Where the LLM sits

After a rule fires, and only on `BLOCK`. It is asked one question: does the diff itself
contain explicit evidence this is safe, for example the column being aliased back to its old
name in the same PR. It answers with JSON. Anything other than an explicit `{"safe": true}`
leaves the block standing, including a timeout, a missing API key, or prose instead of JSON.

Asserted in `tests/test_llm_cannot_block.py`.
