<!--
These go in the Devpost form fields, not the write-up body. Paste the write-up starting at
"## Inspiration" below.
  Project name:   Tether
  Elevator pitch: A column gets dropped, a serving model goes quietly wrong, nobody notices for
                  weeks. Tether blocks that PR. When it misses one, it writes the missing lineage
                  edge to DataHub, and stops missing it.
  Built with:     python, datahub, sqlglot, github-actions, anthropic
  Try it out:     https://github.com/rushibhosalepro/tether
                  https://github.com/rushibhosalepro/tether-demo-warehouse/pulls
-->

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

![A pull request blocked by Tether: the comment names churn_propensity_v4, its owner @aman, and the last training date, and the failing tether check greys out the merge button](https://raw.githubusercontent.com/rushibhosalepro/tether/main/examples/screens/01-pr1-blocked-full.jpeg)

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

![The churn_propensity_v4 model's features in DataHub, with discount_sensitivity carrying a tether:inferred tag, the edge Tether recovered from SQL and wrote back, marked so no one mistakes it for a declared fact](https://raw.githubusercontent.com/rushibhosalepro/tether/main/examples/screens/07-model-features-inferred-tag.png)

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

- It does **not** guess. A feature computed in Python with no SQL to point at gets refused, and
  the miss is reported. That's why the number is 5/6, not 6/6.
- The LLM does **not** decide to block. It's called once, only to *downgrade* a block when the
  diff itself proves the change is safe. A unit test fails if it ever blocks.
- It's not a dashboard. The output is a failed PR check and a DataHub incident, not another tab.
- It works within OSS DataHub's limits, honestly. Serving state comes from a model property
  (OSS hides deployments over GraphQL), unknown means live; incidents are filed on the table,
  not the model (OSS renders them there); an uncatalogued table is reported un-assessable, not
  waved through.

## Results

Four real pull requests on a separate public repo: three drop a column a serving model reads and
get blocked, the one that touches nothing merges clean. And the write-back lands where a human
inherits it, after Tether runs, the `orders` table in DataHub carries two **Critical** incidents,
each naming the model the change would break, each with a Resolve button.

![The orders table's Incidents tab in DataHub showing two Critical incidents: Schema change blocks dynamic_pricing_v2 (orders.quantity) and Schema change blocks churn_propensity_v4 (orders.discount_pct)](https://raw.githubusercontent.com/rushibhosalepro/tether/main/examples/screens/03-orders-incidents-critical.png)

The full set of screenshots is in [`examples/screens/`](https://github.com/rushibhosalepro/tether/tree/main/examples/screens):
the PRs, the model lineage, the table-to-feature edges Tether repaired, and the memory links it wrote.

It ships with 40 passing tests (both determinism boundaries included) and installs on any repo as
a GitHub Action, with a zero-setup `DEMO_MODE` for anyone who wants to try it without DataHub.

## What I learned

The write-back is the whole game. My first version was a clean pipeline that read the graph and
blocked PRs, and it would have lost, because nothing it wrote made it better at its own job. The
moment I made Tether repair the lineage it failed on, it stopped being a linter and started being
an agent that leaves the graph richer than it found it. Every model it missed was a lineage edge
nobody wrote down, so now it writes them down.

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
