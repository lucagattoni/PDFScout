.PHONY: install lint lint-md fix test test-e2e fixtures coverage ci clean

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
	uv run pytest -m "not e2e"

test-e2e:
ifdef GRP
	uv run pytest tests/integration/ -m "e2e and grp_$(GRP)" -v
else
	uv run pytest tests/integration/ -m e2e -v
endif

fixtures:
ifdef GRP
	uv run python -m tests.fixtures.generators.generate_all grp_$(GRP)
else
	uv run python -m tests.fixtures.generators.generate_all
endif

coverage:
	uv run pytest -m "not e2e" --cov=. --cov-report=term-missing

ci: lint lint-md test

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .coverage htmlcov .pytest_cache node_modules
