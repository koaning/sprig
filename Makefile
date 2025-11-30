.PHONY: install setup lint test check

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
