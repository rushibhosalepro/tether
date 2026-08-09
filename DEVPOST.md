# Tether

**Drop the column, break the model.** Tether blocks the pull request that would break a
production ML model, and when it misses one, it finds the lineage edge nobody wrote down,
proves it against the SQL, writes it back to DataHub, and stops missing it.

Built for **Build with DataHub: The Agent Hackathon**, Production ML Agents track.

*Gallery tagline:* **Blocks the PR that breaks a production ML model, then writes back to
DataHub the lineage edge that let the last one through.**

**My thesis: every model Tether missed was a lineage edge nobody wrote down.** So it writes them
down.

- Tool repo: https://github.com/rushibhosalepro/tether
- Live demo PRs: https://github.com/rushibhosalepro/tether-demo-warehouse/pulls
- Demo video: (coming)

---

## Inspiration

It's 4pm on a Friday. Someone opens a two-line PR that deletes a column called `discount_pct`
from the `orders` table. It's not used in any dashboard, the dbt tests pass, so it gets merged.

Nothing breaks. That's the problem.

Three months ago, a model called `churn_propensity_v4` was trained on a feature built from that
column. It's serving right now, deciding who gets retention emails. The column is gone, so the
feature is null, so the model is quietly wrong. No error. No alert. No red dashboard. Just
predictions that are a little worse every day, and a revenue line that dips for a reason nobody
can find for three weeks.

I kept reading the same sentence in my research: figuring out which production models still
read a deprecated column is "an investigative nightmare." I wanted the nightmare to be a failing
check on the PR that caused it, before anyone hits merge.

## What it does

Tether runs on every pull request that touches a `.sql` file.

1. It parses the diff into column-level changes (drop, rename, retype).
2. It walks DataHub lineage forward from each changed column, past the dashboards where everyone
   else stops, into `mlFeature → mlModel → deployment`.
3. It gets column precision the graph doesn't store by **reading the feature SQL** to see which
   columns each feature actually reads.
4. A deterministic classifier decides BLOCK, WARN, or PASS.
5. If a serving model still reads the column, it **fails the PR's `tether` status** (greying out
   the merge button), comments naming the model and its owner, and **files a `DATA_SCHEMA`
   incident on the affected table, naming the model, in DataHub**.

So the dependency that used to live in one senior engineer's head is now a check on the PR and a
first-class incident the next person inherits.

## The part I'm proudest of: it repairs the graph it just failed on

Here's the honest catch I hit on day one. That `column → feature → model` edge, the thing Tether
needs to walk? **Almost nobody populates it.** Only four ML connectors write it, and the
training-data edge is essentially never automatic. So a real DataHub has models whose inputs were
never declared, and impact analysis can't warn you about an edge that isn't there.

Most tools would shrug. Tether repairs it. When the walk comes up empty, Tether:

- **diagnoses** the miss: a feature's SQL reads the column, but the graph has no edge for it,
- **infers** the missing edge from the feature SQL with sqlglot, keeping the exact `file:line` as
  evidence,
- **writes it back** to DataHub tagged `tether:inferred`, so the next walk catches it,
- **refuses** any edge it can't point at a SQL expression for.

I measured it the only way that means anything: same PRs, same code, on a live graph, with and
without the repair.

- **Cold graph: it caught 3 of 6 breakages.**
- **After it repaired the graph: 5 of 6.**

It wrote back 2 edges from SQL evidence and **refused 1**, a feature computed in a Python
transform with no SQL to cite. Delete the repair step and the second run is identical to the
first. The write-back isn't a receipt; it's the thing that makes the next run better. Run
`tether bench` and you'll watch the number move.

## How this maps to the Production ML Agents track

| The track asks for | Where Tether does it |
|---|---|
| Uses DataHub's end-to-end ML lineage | walks `dataset → mlFeature → mlModel → deployment` over the relationships API |
| Catches silent problems before they cost money | blocks the PR before a serving model loses an input |
| Writes results back so the next person inherits them | files an incident on the affected table naming the model, writes the lineage edge + institutional memory |
| Goes beyond reading metadata | the inferred lineage edge makes the graph strictly richer after it runs |

## How I built it

| Layer | Choice |
|---|---|
| Agent | Python, one readable pipeline: parse → walk → classify → write back |
| DataHub | OSS quickstart; GraphQL for reads/incidents, Python SDK for emitting lineage |
| Lineage precision | sqlglot, to recover a feature's source columns from its SQL |
| Gate | GitHub commit status + PR comment (posted by the agent) |
| LLM | one optional Anthropic call, fenced so it can only ever *downgrade* a block |

DataHub isn't a step in the middle here; it's where the output lives. The graph is richer after
Tether runs (new incidents, new lineage edges), and you can see the before/after on the model's
own page.

## Challenges I ran into

Building against OSS DataHub taught me what the docs don't, and every one is a real
commit in the history:

- **An `mlFeature` rejects an `upstreamLineage` aspect.** I assumed I could attach column-level
  lineage to a feature. You can't. ML lineage is dataset-level, so Tether gets column precision from
  the SQL instead. This actually made the story better: reading the code is exactly what a human
  would do.
- **`searchAcrossLineage` returns nothing from a dataset.** The walk looked broken until I
  switched to the relationships API (`DerivedFrom`, then `Consumes`), which is deterministic and
  immediate.
- **Deployment entities and an entity's incidents aren't exposed over OSS GraphQL.** So the
  "serving" signal is a model property and incident de-duplication is a local cache.
- **GitHub check runs require a GitHub App.** A user token gets a flat 403. The fix is a commit
  status, which works with a normal token and greys out merge the same way.
- **A gate must fail closed.** An early version returned PASS when it could not reach DataHub or
  parse a diff, which is the worst failure a merge gate can have: a green check on an unchecked
  PR. Now an unverifiable change is `ERROR`, goes red, and blocks merge, the same direction the
  LLM fence fails.

## What this is NOT

- It does **not** guess. If a feature is computed in Python with no SQL to point at, Tether
  refuses to infer the edge and reports the miss. That's why the number is 5/6, not 6/6.
- The LLM does **not** decide to block. It's called once, only to *downgrade* a block when the
  diff itself proves the change is safe. There's a unit test that fails if it ever blocks.
- It's not a dashboard. The output is a failed PR check and a DataHub incident, not another tab
  to check.
- Serving state comes from a model property, not a deployment entity, because OSS DataHub does
  not expose deployments over GraphQL. Tether reads a configurable property (default `serving`,
  or mlflow's `stage`), and if an instance declares neither, it treats the model as live and
  says so in the reason, rather than silently letting the change through.
- It protects tables DataHub knows about. A change to a table that isn't cataloged is reported
  as un-assessable, not waved through.
- OSS DataHub renders incidents on tables, not on ML models (an `incidents` field exists on
  `Dataset` but not `MLModel`). So Tether files the incident on the affected table and names the
  model it endangers in the title and body, where the next engineer to touch that table sees it.
  The model's own before/after is visible on its Lineage tab.

## Accomplishments I'm proud of

- A real loop with a real before/after number (3/6 → 5/6), reproducible in one command.
- Four real pull requests on a separate public repo, correctly blocked or passed, each with a
  status, a comment, and a DataHub incident.
- 40 passing tests, including both determinism boundaries.
- Deployable on any repo via a GitHub Action, with a zero-setup `DEMO_MODE` for anyone who wants
  to try it without standing up DataHub.

## What I learned

The write-back is the whole game. My first version was a clean pipeline that read the graph and
blocked PRs, and it would have lost, because nothing it wrote made it better at its own job. The
moment I made Tether repair the lineage it failed on, it stopped being a linter and started being
an agent that leaves the graph richer than it found it.

## What's next

- Watch a merged-anyway PR's next scoring run and record whether the model actually broke, to
  score predictions against outcomes over time.
- Promote a `tether:inferred` edge to declared once a human confirms it.
- Ship the incident write-back as the DataHub Python SDK incidents module the docs list as
  "coming soon."

## Open-source contribution

Tether's incident code is a working Python module for raising DataHub incidents over GraphQL,
which the docs currently list as "Python SDK support coming soon." I'm offering it upstream,
plus the ML-layer seed as a reusable datapack.

## Built with

Python, DataHub (OSS, GraphQL + Python SDK), sqlglot, GitHub Actions, Anthropic.

## Try it out

- **Zero setup:** `DEMO_MODE=1 tether check --diff bench/cases/001-drop-orders-discount-pct/diff.patch`
- **The full loop:** `bash scripts/quickstart.sh` then `tether bench`
- **Real PRs:** https://github.com/rushibhosalepro/tether-demo-warehouse/pulls
- **Code:** https://github.com/rushibhosalepro/tether
