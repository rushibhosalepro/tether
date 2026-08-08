# Tether

**Drop the column, break the model.**

An agent that cannot block on a hunch: Tether parses your unmerged schema diff, walks
DataHub lineage past the dashboards into production ML models, fails the PR check with the
model owner named, and files the dependency back into DataHub as an incident on the model
and a permanent record on the column.

> Built for **Build with DataHub: The Agent Hackathon**, Production ML Agents track.

---

## The problem

A broken pipeline throws. A broken model does not. It stays technically up and functionally
wrong, serving predictions from a column that stopped meaning what it meant, while every
dashboard stays green.

Impact analysis is supposed to catch this, and it stops at the BI layer, because that is
where most metadata graphs stop. Ask a data engineer which production models read
`orders.discount_pct` and the honest answer is usually that finding out is an afternoon of
grep.

## What Tether does

```
PR touches a .sql file
  └─ parse the diff into column-level changes (drop, rename, retype, semantic)
      └─ resolve each column to a DataHub schemaField URN
          └─ walk lineage FORWARD, past datasets, past dashboards
              └─ into mlFeature -> mlModel -> mlModelDeployment
                  └─ deterministic classifier decides BLOCK / WARN / PASS
                      ├─ fail the required GitHub check, owners named
                      ├─ raiseIncident (DATA_SCHEMA) on the model entity
                      └─ institutionalMemory link on the column, pointing at the PR
```

The incident gets resolved when the model is retrained. The link on the column does not go
away, which is the point: the next person to touch that column inherits the dependency
without having to rediscover it.

## The number

Same agent, same PRs, one difference: what it is allowed to look at.

| Arm | Sees | Recall on real breakages |
|---|---|---|
| `datahub` | Full lineage, column → feature → model → deployment | see `bench/results/REPORT.md` |
| `dbt-only` | `manifest.json`, full `child_map` traversal | see `bench/results/REPORT.md` |

The control arm is not a strawman. It walks the entire dbt graph. It finds zero model
dependencies because dbt's graph has no `mlFeature`, `mlModel` or `mlModelDeployment` in it
to find. That structural blindness is the finding.

Every miss is named in the report. `examples/report.html` renders it with no server.

## The determinism boundary

The LLM never decides to block.

The classifier in `src/tether/verdict/classifier.py` is the only thing that can produce
`BLOCK`, from the rules written out in `src/tether/verdict/rules.md`. The model is called in
exactly one place, after a block has already been decided, and asked whether the diff
contains explicit evidence the change is safe. It can turn `BLOCK` into `WARN`. It cannot do
the reverse, it cannot invent an impact, and if it times out or returns prose the block
stands.

That is not a promise in a README. It is `tests/test_llm_cannot_block.py`:

```bash
python -m pytest tests/test_llm_cannot_block.py -v
```

## Quickstart

```bash
bash scripts/quickstart.sh
```

Windows: `powershell -File scripts/quickstart.ps1`

That runs `datahub docker quickstart`, loads `showcase-ecommerce` (1,049 entities), emits
the ML layer this project needs, and installs the CLI. Roughly six minutes, most of it
Docker pulling images.

Then:

```bash
tether check --diff bench/cases/001-drop-orders-discount-pct/diff.patch --pr-url local
```

No Docker? Everything runs from recorded fixtures:

```bash
DEMO_MODE=1 tether check --diff bench/cases/001-drop-orders-discount-pct/diff.patch
```

## Use it on your own repo

```yaml
- uses: ./action
  with:
    datahub-gms-url: ${{ secrets.DATAHUB_GMS_URL }}
    datahub-token: ${{ secrets.DATAHUB_TOKEN }}
```

Mark `tether` as a required status check and the merge button greys out.

## The ML layer

`showcase-ecommerce` ships no ML entities, which is why the Production ML Agents track is
hard to enter at all. `seed/emit_ml_layer.py` emits the missing layer from a declarative
`seed/entities.yaml`: feature tables, features, model groups, models, deployments, owners,
and both dataset-level and column-level lineage edges.

It is written to stand on its own as a datapack, not just as fixture data for this project.

## Layout

| Path | What is in it |
|---|---|
| `src/tether/diff/` | unified diff → `ColumnChange[]`, dbt and DDL |
| `src/tether/graph/` | URN resolution, forward lineage walk into the ML layer |
| `src/tether/verdict/` | the deterministic classifier, the rules, the LLM fence |
| `src/tether/writeback/` | incident, institutional memory, GitHub check |
| `src/tether/arms/` | the two benchmark arms |
| `seed/` | the ML layer, offerable upstream as a datapack |
| `bench/` | replay cases, both arms, published misses |
| `examples/` | real output, readable without running anything |

## "DataHub already has impact analysis"

It does, and it is good. It is also a UI you open after you already suspect something, it
terminates at the dashboard layer, and it cannot read a diff that has not been merged yet.
Tether runs on the change before it exists and ends at a merge decision. Different direction
of travel, different terminus.

## License

Apache 2.0.
