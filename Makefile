.PHONY: install lint lint-md fix test coverage ci clean

install:
	uv sync --group dev
	npm install

lint:
	uv run ruff check .
	uv run ruff format --check .

lint-md:
	npx markdownlint-cli2 "**/*.md" "#.venv" "#node_modules" "#.pytest_cache" "#plans"

fix:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

coverage:
	uv run pytest --cov=. --cov-report=term-missing

ci: lint lint-md test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .coverage htmlcov .pytest_cache node_modules
