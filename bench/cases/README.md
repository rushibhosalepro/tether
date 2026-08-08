# Benchmark cases

One directory per replayed schema change. Each holds:

- `diff.patch` — the unified diff exactly as it would arrive on a PR
- `expected.json` — ground truth per column, `BLOCK` or `PASS`, plus why

Ground truth is derived from `seed/entities.yaml`, which declares which columns feed which
feature and which models are actually deployed. A case is only labelled `BLOCK` when a model
with an `IN_PRODUCTION` deployment reads the column.

Both arms get byte-identical input. Cases are written before the classifier is tuned against
them, and every miss stays in `results/REPORT.md`.
