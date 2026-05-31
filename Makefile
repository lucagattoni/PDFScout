.PHONY: install lint fix test coverage ci clean

install:
	uv sync --group dev

lint:
	uv run ruff check .
	uv run ruff format --check .

fix:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

coverage:
	uv run pytest --cov=. --cov-report=term-missing

ci: lint test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .coverage htmlcov .pytest_cache
