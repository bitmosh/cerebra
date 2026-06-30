.PHONY: install test test-quick test-unit test-integration lint type-check format format-check verify-docs clean

install:
	pip install -e ".[dev]"
	pre-commit install

# Full suite. Includes integration tests — these load ~1.5 GB of ML models on
# first run and take ~10 min total. Use `test-quick` for fast iteration.
test:
	pytest

# Fast: everything except integration. ~1–2 min on a warm machine. This is
# what CI runs.
test-quick:
	pytest -m "not integration"

# Just the explicitly @pytest.mark.unit tests (subset of test-quick).
test-unit:
	pytest -m unit

# Just the explicitly @pytest.mark.integration tests. Loads ML models.
test-integration:
	pytest -m integration

lint:
	ruff check cerebra tests

type-check:
	mypy cerebra

format:
	black cerebra tests
	ruff check --fix cerebra tests

format-check:
	black --check cerebra tests
	ruff check cerebra tests

verify-docs:
	python scripts/verify_docs.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .coverage htmlcov .mypy_cache .ruff_cache coverage.xml
