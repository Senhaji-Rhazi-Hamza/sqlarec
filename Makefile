.PHONY: install install-prod test lint typecheck format clean-cache clean-dist clean

install:
	uv sync

install-prod:
	uv sync --no-dev

test:
	uv run pytest

lint:
	uv run ruff check src/ tests/

typecheck:
	uv run ty check

format:
	uv run ruff format src/ tests/

clean-cache:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .mypy_cache .pytest_cache .ruff_cache

clean-dist:
	rm -rf dist

clean: clean-cache clean-dist
