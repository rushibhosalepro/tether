# Screenshots

Real captures from a live run. Nothing staged.

## On the pull request (GitHub)

- **[01-pr1-blocked-full.jpeg](01-pr1-blocked-full.jpeg)** — PR #1 in full: Tether's BLOCK
  comment (model, owner, incident link), the failed `tether` check, the merge button gated.
- **[01b-pr1-checks-failed.png](01b-pr1-checks-failed.png)** — "All checks have failed", the
  `tether` status naming the model.
- **[01c-pr1-comment.png](01c-pr1-comment.png)** — the comment close up.
- **[02-prs-list-3red-1green.png](02-prs-list-3red-1green.png)** — four PRs, three blocked (red
  ✗), the safe one passed (green ✓).

## In DataHub (the write-backs)

- **[03-orders-incidents-critical.png](03-orders-incidents-critical.png)** — the `orders`
  table's Incidents tab: two **Critical** incidents Tether filed, naming `churn_propensity_v4`
  and `dynamic_pricing_v2`, each with a Resolve button.
- **[04-model-lineage.png](04-model-lineage.png)** — `churn_propensity_v4` lineage: its four
  features and its model group.
- **[05-orders-lineage-features.png](05-orders-lineage-features.png)** — from the `orders`
  table forward to the four features, including the two edges Tether repaired.
- **[06-orders-columns-memory.png](06-orders-columns-memory.png)** — the institutional-memory
  links Tether wrote on the table ("consumed by churn_propensity_v4 / dynamic_pricing_v2").
- **[07-model-features-inferred-tag.png](07-model-features-inferred-tag.png)** —
  `discount_sensitivity` carrying the **`tether:inferred`** tag, the repaired edge, marked as
  inferred so no one mistakes it for declared truth.
