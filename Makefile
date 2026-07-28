.PHONY: install install-prod test lint typecheck format clean-cache clean

install:
	uv sync

install-prod:
	uv sync --no-dev

test:
	uv run pytest

lint:
	uv run ruff check src/ tests/

typecheck:
	uv run mypy

format:
	uv run ruff format src/ tests/

clean-cache:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache

clean: clean-cache
