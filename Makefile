.PHONY: install setup lint test check clean

install:
	uv sync --dev

setup: install

lint:
	uv run ruff check src

test:
	uv run pytest

check:
	@echo "Checking project..."
	@$(MAKE) lint
	@$(MAKE) test

clean:
	rm -rf .uv-cache .venv .pytest_cache tmp-repo-test
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
