# Tether — Devpost submission

**Challenge:** Production ML Agents

## Tagline

Tether blocks the pull request that would break a production ML model, and when it misses one,
it finds the lineage edge nobody wrote down, proves it against the feature SQL, writes it back
to DataHub, and stops missing it.

---

## The problem

A broken pipeline throws an error. A broken model does not. It stays technically up and
functionally wrong, serving predictions from a column that someone dropped last Friday, while
every dashboard stays green. Finding which production models still read a deprecated column is,
in the words of the practitioners we researched, "an investigative nightmare."

The reason it is hard is structural. The blast radius you need to trace is
`column → feature → model → deployment`, and that path is almost never populated: only four ML
connectors write it, and the training-data edge is essentially never automatic. So the honest
day-one state of a real DataHub is models whose inputs nobody ever declared. Impact analysis
can't warn you about an edge that isn't there.

## What it does

Tether runs on every pull request that touches a `.sql` file. It parses the diff into
column-level changes, resolves each column to a DataHub dataset, and walks the graph forward,
past the dashboards where everyone else stops, into `mlFeature → mlModel → deployment`. It gets
column precision the graph doesn't store by reading the feature-engineering SQL directly. Then
a deterministic classifier decides, and Tether acts:

- fails the `tether` commit status, which greys out the merge button,
- comments on the PR naming the model, its owner, and the incident,
- raises a `DATA_SCHEMA` incident on the model entity in DataHub.

And here is the part that makes it an agent and not a linter: **when the walk misses because the
edge was never declared, Tether repairs the graph.** It diagnoses the gap, infers the missing
`column → feature` edge from the feature SQL, and writes it back to DataHub tagged
`tether:inferred` with the SQL `file:line` as evidence. The next walk, the next engineer, and
the next agent all inherit it.

## The number

Same PRs, same code, on a live graph. The only difference is whether Tether repaired the
lineage first.

- **Cold graph: 3 of 6 breakages caught.**
- **After Tether repaired the graph: 5 of 6.**
- It repaired 2 edges from SQL evidence and **refused 1** it could not prove.

Delete the repair step and the warm run is byte-identical to the cold run. The write-back is
load-bearing, not decoration. `tether bench` regenerates this end-to-end against a live DataHub.

The one it still misses is a feature computed in a Python transform, with no SQL for Tether to
point at. It refuses to invent an edge it cannot prove, and reports the miss. That refusal is
the honest failure, framed as the design principle it is: **Tether never writes a lineage edge
it cannot cite.**

## How we used DataHub

DataHub is not a step in the middle; it is where the output lives. Tether:

- reads the graph over GraphQL (the relationships API: `DerivedFrom`, then `Consumes`),
- raises real incidents on `mlModel` entities,
- writes `institutionalMemory` links recording each dependency and PR,
- **writes new lineage edges back** (`MLFeatureProperties.sources`), which is the load-bearing
  contribution: the graph is strictly richer after Tether runs than before.

The whole thing only works because `column → feature → model → deployment` lives in one graph in
DataHub and nowhere else. Swap DataHub for a dbt manifest and the ML half of the walk cannot
exist, because dbt's graph has no concept of a model.

## Originality

Two things we did not find anywhere else in the galleries we researched:

1. **The write-back is a repair, not a report.** Most agents write a note a human reads. Tether
   writes the structural edge that makes its own next run better, which is the exact "loop" the
   winners had and the losers didn't.
2. **A stated, tested refusal.** Tether has two determinism boundaries, both unit-tested: the
   LLM can never originate a block, and the repair can never write an edge without SQL evidence.
   The failure number is a feature.

## Challenges we ran into (all real, all in the repo history)

Building against OSS DataHub taught us what the docs don't:
- an `mlFeature` rejects `upstreamLineage`, so ML lineage is dataset-level and column precision
  has to come from the SQL;
- `searchAcrossLineage` won't traverse from a dataset, so the walk uses the relationships API;
- deployment entities and an entity's incidents aren't exposed over OSS GraphQL, so the serving
  signal is a model property and incident idempotency is a local cache;
- GitHub check runs require a GitHub App, so the merge gate is a commit status (works with a
  normal token, gates merge the same way).

Every one of these is fixed in the code and recorded in `results.md`.

## Accomplishments

- A real loop with a real number (3/6 → 5/6) on a live graph, reproducible in one command.
- Four real pull requests on a separate public repo, correctly blocked or passed, each with a
  status, a comment, and a DataHub incident.
- 34 passing tests, including both determinism boundaries.
- Deployable on any repo via a GitHub Action, with a zero-infrastructure `DEMO_MODE` for anyone
  who wants to try it without standing up DataHub.

## Open-source contribution

Tether's incident write-back is a working Python module for raising DataHub incidents over
GraphQL, which the docs currently list as "Python SDK support coming soon." We're offering it
upstream, along with the ML-layer seed as a reusable datapack.

## Try it

- Zero infra: `DEMO_MODE=1 tether check --diff bench/cases/001-drop-orders-discount-pct/diff.patch`
- Full loop: `bash scripts/quickstart.sh` then `tether bench`
- Live PRs: https://github.com/rushibhosalepro/tether-demo-warehouse/pulls

## Built with

Python, DataHub (OSS quickstart, GraphQL + Python SDK), sqlglot, GitHub Actions, Anthropic
(one optional call, fenced so it can never block).

## Repos

- Tool: https://github.com/rushibhosalepro/tether
- Demo warehouse (the PRs): https://github.com/rushibhosalepro/tether-demo-warehouse
