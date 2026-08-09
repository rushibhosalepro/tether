# Tether

**Drop the column, break the model.**

Tether blocks the pull request that would break a production ML model. When it misses one, it
finds the lineage edge nobody ever wrote down, proves it against the feature SQL, writes it
back to DataHub, and stops missing it.

> Built for **Build with DataHub: The Agent Hackathon**, Production ML Agents track.
> Tool repo: this one. Live demo PRs: [tether-demo-warehouse](https://github.com/rushibhosalepro/tether-demo-warehouse/pulls).

---

## The problem

A broken pipeline throws. A broken model does not. It stays technically up and functionally
wrong, serving predictions from a column that was dropped last Friday, while every dashboard
stays green.

Impact analysis is supposed to catch this, and it stops at the BI layer, because that is where
most metadata graphs stop. Worse, the part of the graph you would need, the edge from a column
to the feature to the model, is the part almost nobody populates. Only four ML connectors
populate it at all, and the training-data edge is essentially never automatic. So the honest
day-one state of a real DataHub is: **models whose inputs nobody declared.**

## What Tether does

On every pull request that changes a `.sql` file:

```
parse the diff into column-level changes (drop / rename / retype)
  └─ resolve each column's table to a DataHub dataset
      └─ walk the graph: dataset ─DerivedFrom→ mlFeature ─Consumes→ mlModel ─→ deployment
          └─ column precision: read the feature SQL to see which columns each feature reads
              └─ deterministic classifier decides BLOCK / WARN / PASS
                  ├─ fail the `tether` commit status (greys out merge)
                  ├─ comment on the PR with the model, its owner, and the incident link
                  └─ raise a DATA_SCHEMA incident on the model in DataHub
```

And when the walk misses, because the dataset→feature edge was never declared, Tether repairs
it instead of shrugging:

```
diagnose  the miss: a feature's SQL reads the column, but the graph has no edge for it
  └─ infer   the edge from the feature SQL (sqlglot), with the file:line as evidence
      └─ write it back to DataHub, tagged tether:inferred, so the next walk catches it
          └─ refuse any edge it cannot point at a SQL expression for
```

## The number

Same PRs, same code, on a live graph. The only difference is whether Tether repaired the
lineage first.

| | Breakages caught |
|---|---|
| Cold graph (edges undeclared) | **3 / 6** |
| After Tether repaired the graph | **5 / 6** |

It repaired 2 edges from SQL evidence and **refused 1** it could not prove (a feature computed
in Python, no SQL to cite). Delete the repair step and the warm run equals the cold run: the
write-back is load-bearing, not decoration. Regenerate this yourself with `tether bench`; the
report renders to [`examples/report.html`](examples/report.html).

## Two determinism boundaries, both tested

Tether makes two consequential decisions, and neither is left to an LLM:

1. **The LLM never decides to block.** The classifier ([`verdict/classifier.py`](src/tether/verdict/classifier.py))
   is the only thing that can emit `BLOCK`. The model is called in exactly one place, after a
   block, and can only ever *downgrade* it to a warning. `tests/test_llm_cannot_block.py`.
2. **Tether never writes an edge it cannot prove.** The repair infers edges from SQL only
   ([`repair/infer.py`](src/tether/repair/infer.py)); a feature with no SQL is refused and the
   refusal is published. `tests/test_repair_refuses.py`.

```bash
python -m pytest -q      # 34 tests
```

## See it on real PRs

Four real pull requests on a separate public repo, each judged against a live DataHub:

| PR | Change | Tether |
|---|---|---|
| [#1](https://github.com/rushibhosalepro/tether-demo-warehouse/pull/1) | drop `orders.discount_pct` | 🔴 blocks `churn_propensity_v4` (@aman) |
| [#2](https://github.com/rushibhosalepro/tether-demo-warehouse/pull/2) | drop `orders.quantity` | 🔴 blocks `dynamic_pricing_v2` (@wenjia) |
| [#3](https://github.com/rushibhosalepro/tether-demo-warehouse/pull/3) | drop `products.unit_cost` | 🔴 blocks `dynamic_pricing_v2` |
| [#4](https://github.com/rushibhosalepro/tether-demo-warehouse/pull/4) | drop `orders.status` | 🟢 no ML impact, safe to merge |

## Try it

**Zero infrastructure** (replays recorded DataHub responses, no Docker):

```bash
pip install -e .
DEMO_MODE=1 tether check --diff bench/cases/001-drop-orders-discount-pct/diff.patch
```

**The full thing** (real DataHub, the repair loop, the write-backs):

```bash
bash scripts/quickstart.sh          # datahub quickstart + seed the ML layer, ~6 min
tether bench                        # cold -> repair -> warm, regenerates the report
```

Windows: `powershell -File scripts/quickstart.ps1`.

## Deploy it on your own repo

```yaml
# .github/workflows/tether.yml
on: { pull_request: { paths: ["**/*.sql"] } }
jobs:
  tether:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: rushibhosalepro/tether@v1
        with:
          datahub-gms-url: ${{ secrets.DATAHUB_GMS_URL }}
          datahub-token:   ${{ secrets.DATAHUB_TOKEN }}
```

Mark `tether` a required status check and the merge button greys out on a block. The only real
requirement is a DataHub the runner can reach (DataHub Cloud, a self-hosted runner on your
network, or a tunnel). No DataHub reachable from CI? Leave `datahub-gms-url` empty and it runs
in `DEMO_MODE` off recorded fixtures.

Nothing in Tether is specific to this demo: it resolves every dataset and feature from your
DataHub at runtime and reads your repo's SQL. Two light conventions make the column precision
and the repair work on your repo:

- **Feature SQL is one file per feature**, in `features-dir`, named to match the `mlFeature` in
  DataHub (e.g. `discount_sensitivity.sql` ↔ the `discount_sensitivity` feature).
- **The output column is aliased with the feature name** (`... as discount_sensitivity`), so
  Tether can trace which source columns feed it.

Given those, Tether points at any DataHub and any repo and works unchanged.

## Why this needs DataHub specifically

The blast radius of a dropped column is `column → feature → model → deployment`, and that path
lives in **one graph only in DataHub**. No dbt manifest, no schema file, no other catalog knows
that models exist, let alone which feature feeds which one. Replace DataHub and the product
stops existing.

It is also why the repair matters: DataHub's own impact analysis can only traverse the
dependencies someone already wrote down. Tether writes the missing ones back, so the graph is
strictly richer after it runs, which is the challenge text verbatim: *"writes results back so
the next person or agent inherits the knowledge."*

## Layout

| Path | What is in it |
|---|---|
| `src/tether/diff/` | unified diff → `ColumnChange[]` |
| `src/tether/graph/` | dataset resolution, the relationships-API lineage walk |
| `src/tether/verdict/` | the deterministic classifier, the rules, the LLM fence |
| `src/tether/repair/` | diagnose a gap, infer the edge from SQL, refuse the unprovable |
| `src/tether/writeback/` | incident, institutional memory, inferred edge, PR status |
| `seed/` | the ML layer + `--partial` mode + ground truth |
| `bench/` | the cold→repair→warm benchmark |
| `examples/` | real output, readable without running anything |

## "DataHub already has impact analysis"

It does, and it is good. It is also a UI you open *after* you suspect something, it stops at
dashboards, it cannot read a diff that has not been merged, and **it can only traverse the
dependencies someone already wrote down.** Tether runs on the change before it exists, ends at
a merge decision, and writes back the dependencies it needed to make that decision.

## License

Apache 2.0.
