# What has been built so far

Written 2026-08-08, after the first working session. This is a build log for me, not part
of the submission pitch. It says what exists, what each file does, how data moves through
it, and, importantly, what has and has not actually been run.

---

## Status in one line

The scaffold is complete and the pure-Python logic is tested. **Nothing has touched a live
DataHub yet.** Every module that talks to the graph is written but unverified.

- 51 files, ~2,970 lines
- 18 tests, 18 passing
- 1 commit
- DataHub quickstart is up (GMS and frontend both returning 200), datapack not yet loaded

---

## What I did, in order

1. `git init` in `tether/`, wrote `.gitignore` with `plan.md` excluded.
2. Fetched the real Apache 2.0 text into `LICENSE` (the hackathon requires it detectable at
   the top of the repo page).
3. Wrote the type model first, then everything else against it.
4. Wrote the deterministic classifier and its tests before anything that needs a network.
5. Wrote the DataHub-facing modules (resolve, walk, incident, memory) from the API shapes in
   `../research/01-datahub-platform.md`. These are educated guesses at the GraphQL, not
   verified calls.
6. Wrote the seed, the benchmark harness, the GitHub Action, the docs.
7. Ran the tests. Committed.

**Honest note on ordering:** I wrote a lot of code before running much of it. The tested part
is the part that does not need DataHub. That is the right half to have finished first, but it
also means the risky half is entirely unproven.

---

## The data flow

The whole product is one function, `run()` in `src/tether/pipeline.py`:

```
diff text (from a PR)
   │
   ├─ parse_diff()          diff/parser.py        → list[ColumnChange]
   │                        what changed, at column level: DROP / RENAME / RETYPE / SEMANTIC
   │
   ├─ resolve_column()      graph/resolve.py      → schemaField URN
   │                        "analytics.orders" + "discount_pct" → the URN DataHub knows
   │
   ├─ ml_impacts()          graph/walk.py         → list[Impact]
   │                        forward lineage, past datasets and dashboards, into
   │                        mlFeature → mlModel → mlModelDeployment
   │
   ├─ classify()            verdict/classifier.py → Verdict (BLOCK / WARN / PASS)
   │                        deterministic. the ONLY thing allowed to emit BLOCK
   │
   ├─ soften()              verdict/llm_assist.py → possibly downgrades BLOCK to WARN
   │                        one LLM call, fenced. cannot raise a verdict, ever
   │
   └─ write_back()          writeback/*           → three artifacts
                            incident on the model, link on the column, failing PR check
```

Four types carry everything, all in `verdict/models.py`:

| Type | Is |
|---|---|
| `ColumnChange` | one column-level change read out of the diff |
| `Impact` | one production model reached by walking forward, with deployment status and owners |
| `Verdict` | one change + its level + the impacts that justify it + which rule fired |
| `Report` | all verdicts for one PR, and the roll-up level |

If you read `models.py` and `pipeline.py`, you have read the product. Everything else is
detail hanging off those two.

---

## Every file, and what it is for

### The core (`src/tether/`)

| File | Lines | What it does |
|---|---|---|
| `pipeline.py` | 76 | The whole flow, top to bottom, deliberately readable in one screen. Also `write_back()`, where each of the three artifacts is allowed to fail independently so one broken call cannot take the check down. |
| `verdict/models.py` | 113 | The four types plus the enums. No logic beyond `Report.level` rolling up the worst verdict. |
| `verdict/classifier.py` | 149 | Rules R0–R5. Pure function: change + impacts in, verdict out. No network, no LLM, no I/O. Also `assert_deterministic()`, the guard that raises if a BLOCK ever carries an LLM attribution. |
| `verdict/llm_assist.py` | 96 | The single LLM call and the fence around it. Returns the input verdict unchanged on any failure: no key, timeout, prose instead of JSON, `safe: false`. Fails closed by construction, not by a try/except bolted on. |
| `verdict/rules.md` | 35 | The rules in English, next to the code. Linked from the README so a judge can check the logic without reading Python. |
| `graph/resolve.py` | 66 | Table name as written in SQL → dataset URN, then → schemaField URN. Cached, because the parser asks for the same table repeatedly. Exact `qualifiedName` match wins, then platform match, then suffix match. |
| `graph/walk.py` | 119 | The `searchAcrossLineage` call, DOWNSTREAM, filtered to ML entity types. Pulls the path out of each result so the incident can say *how* the column reaches the model. Second call per model to check whether any deployment is `IN_PRODUCTION`. |
| `diff/parser.py` | 117 | Splits a unified diff per file, reconstructs before/after from the hunks, and routes to the dbt path or the DDL path. Also infers renames (a drop and an add of the same type in the same file). |
| `diff/sqlglot_ddl.py` | 101 | Column extraction. Tries sqlglot, falls back to regex when Jinja makes the SQL unparseable. Falling back rather than crashing is deliberate: a missed column shows up in the benchmark as a miss, a crash shows up as a broken demo. |
| `writeback/incident.py` | 109 | `raiseIncident` GraphQL, type `DATA_SCHEMA`, on the model URN. Checks for an existing open incident with the same title first, so re-running on a PR does not spam the model page. |
| `writeback/memory.py` | 59 | `addLink` for `institutionalMemory` on the column. This is the artifact that outlives the incident. |
| `writeback/github_check.py` | 91 | Creates the check run. Builds the markdown table of column / change / model / deployment / owner / last-trained that the reviewer actually reads. |
| `ledger/store.py` | 49 | Append-only JSONL of every verdict ever issued. |
| `ledger/score.py` | 81 | Precision, recall, F1, and the misses and false alarms as named lists rather than counts. |
| `arms/datahub_arm.py` | 10 | Treatment arm. Thin wrapper on the real walk. |
| `arms/dbt_manifest_arm.py` | 54 | Control arm. Does real `child_map` traversal, then returns zero ML impacts because dbt's graph has no ML entities in it. The comment at the top explains why this is not a strawman. |
| `datahub_client.py` | 90 | One place that talks to GMS. Also the fixture record/replay that makes `DEMO_MODE=1` work with no Docker. |
| `config.py` | 44 | Env loading, a hand-rolled `.env` reader so there is no python-dotenv dependency. |
| `cli.py` | 93 | `tether check | seed | bench | doctor`. argparse, not typer, to keep the dependency list short. Exits 1 on BLOCK, which is what makes the CI check fail. |

### Everything else

| Path | What it is |
|---|---|
| `seed/entities.yaml` | The ML layer declared in data: 2 feature tables, 6 features, 2 model groups, 3 models, 2 deployments. Also the benchmark answer sheet, because `source_columns` says which columns feed which feature. |
| `seed/emit_ml_layer.py` | Reads that YAML and emits it with the Python SDK. Emits lineage two ways: `fineGrainedLineages` for column→feature, and dataset-level `sources` plus a `source_columns` custom property as fallback. |
| `bench/run_bench.py` | Loads cases, runs both arms on identical input, writes JSON + `REPORT.md`. |
| `bench/render_report.py` | The only "frontend". One self-contained HTML file, theme-aware, no CDN, no server. For the judge who will not start Docker. |
| `bench/cases/001-.../` | One case so far: dropping `orders.discount_pct`. `diff.patch` + `expected.json`. |
| `demo/warehouse/` | A 4-model dbt project. This is what PRs get opened against, so the demo is a real PR in a real repo. |
| `.github/workflows/tether.yml` | Runs on PRs touching SQL. Computes the diff, runs the check, uploads the verdict. |
| `action/action.yml` | Composite action so someone else can drop this into their own repo. |
| `scripts/quickstart.{sh,ps1}` | Nothing to blocked-PR-check in one command. |
| `tests/` | 18 tests across 3 files. |
| `results.md` | The running log. |
| `README.md` | The submission front door. |

---

## What is actually tested

All 18 passing tests are pure logic. No network, no DataHub, no LLM.

**`test_classifier.py`, 9 tests.** One per rule, plus three parametrised widening cases.
Covers: no consumer passes, drop blocks, rename blocks, semantic change blocks, widening
warns instead of blocking, type-class change blocks, undeployed model warns.

**`test_llm_cannot_block.py`, 5 tests.** This is the one that matters for credibility.
A PASS cannot be raised to BLOCK. A BLOCK can be downgraded to WARN. An LLM exception leaves
the block standing. Prose instead of JSON leaves the block standing. A BLOCK forged with an
LLM attribution is rejected by the guard.

**`test_parser.py`, 4 tests.** Runs against the real `bench/cases/001` patch file, not a
fixture invented for the test. Detects the drop, finds exactly one change (no phantom
columns), parses DDL rename and retype, ignores non-SQL files.

---

## What is NOT tested, and is therefore the risk

Everything with a network call in it:

| Unverified | Why it matters |
|---|---|
| `graph/resolve.py` | The search query shape and the matching heuristic are guesses. If `qualifiedName` is not what I think, nothing resolves. |
| `graph/walk.py` | **The go/no-go.** Does `searchAcrossLineage` from a `schemaField` URN actually traverse into `mlFeature`? If it only works from the dataset URN, the walk needs a fallback path. |
| `seed/emit_ml_layer.py` | Never run, not even `--dry-run`. Class names and constructor args come from the research doc, not from the installed SDK. |
| `writeback/incident.py` | `RaiseIncidentInput` field names are from the docs. The `incidents` query on `MLModel` may not exist in this OSS build. |
| `writeback/memory.py` | Whether `addLink` accepts a `schemaField` URN as `resourceUrn` is unknown. It may only take dataset-level URNs, in which case the link goes on the dataset with the column named in the label. |
| `writeback/github_check.py` | Needs a real PR to test. |
| `bench/run_bench.py` | Cannot run until the walk works. |

The pattern is clear: **the half that needs DataHub is the half that is unproven**, and it is
also the half the entire submission rests on.

---

## Design decisions worth remembering

**The classifier is a pure function.** Change plus impacts in, verdict out. That is why it
could be fully tested before DataHub was even reachable, and why the rules are checkable by
reading one file.

**The LLM fence is structural, not a promise.** `soften()` can only ever construct a WARN.
There is no code path in it that produces a BLOCK, so the guarantee holds even if someone
edits the prompt. `assert_deterministic()` at the pipeline boundary catches it if that ever
stops being true.

**Blocking requires positive evidence.** Unresolvable column, no ML consumer, unreachable
graph: all PASS, with the reason recorded. A checker that blocks when unsure gets switched
off inside a week and then protects nothing. The cost shows up honestly in the benchmark as
false negatives, and those get published.

**Write-backs fail independently.** A failed `addLink` must not take down the PR check.

**The seed is declarative.** All the ML entities live in YAML, so changing the scenario is a
data edit, and the same file is the benchmark ground truth.

---

## Next, in order

1. Install the `datahub` CLI, load `showcase-ecommerce`, see what the real table names are.
2. `python -m seed.emit_ml_layer --dry-run` and fix whatever the SDK actually calls things.
3. Emit for real, open a model page, confirm it renders.
4. **The go/no-go:** walk forward from `orders.discount_pct` and see whether
   `churn_propensity_v4` comes back.
5. One `raiseIncident` call by hand before wiring it up.
6. Then, and only then, more benchmark cases.

Log every one of those in `results.md` as it happens, not afterwards.
