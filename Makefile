.PHONY: install seed check bench test demo lint doctor

install:
	python -m pip install -e ".[dev]"

doctor:
	tether doctor

seed:
	python -m seed.emit_ml_layer

seed-dry:
	python -m seed.emit_ml_layer --dry-run

check:
	tether check --diff bench/cases/001-drop-orders-discount-pct/diff.patch --pr-url local --dry-run

bench:
	python bench/run_bench.py

test:
	python -m pytest -q

lint:
	python -m ruff check src tests seed bench

# what a judge runs: quickstart + datapack + ML layer, then the blocked check
demo: install seed check
