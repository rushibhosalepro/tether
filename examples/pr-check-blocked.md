# The PR comment Tether posts (real, from rushibhosalepro/tether#1)

This is the actual comment on a real GitHub PR that dropped `orders.discount_pct`, plus the
red `tether` commit status that greys out the merge button.

---

## 🔴 Tether: BLOCK

| Column | Change | Model | Deployment | Owner | Last trained |
|---|---|---|---|---|---|
| `orders.discount_pct` | DROP | **churn_propensity_v4** | IN_SERVICE | @aman | 2026-03-14 |

- **orders.discount_pct** (R1): orders.discount_pct is a declared input to 1 model(s) currently in production: churn_propensity_v4.

Filed in DataHub:
- (incident on the model entity)

---
Every BLOCK above was decided by the deterministic classifier. The LLM can only downgrade a verdict, never raise one.
