.PHONY: install test lint type-check format format-check verify-docs clean

install:
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest

test-unit:
	pytest -m unit

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
	rm -rf .coverage htmlcov .mypy_cache .ruff_cache
