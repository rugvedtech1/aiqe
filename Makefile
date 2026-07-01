# AIQE — Developer Makefile
# Usage: make <target>
# Run `make help` to see all available commands.

.DEFAULT_GOAL := help
.PHONY: help install install-dev lint format typecheck test test-unit \
        test-integration test-e2e test-security test-performance \
        test-all coverage clean build docs pre-commit-install \
        pre-commit-run setup-dev

PYTHON := python3.12
PIP := pip
VENV := .venv
SRC := src/aiqe
TESTS := tests

# ==================================================
# HELP
# ==================================================

help: ## Show this help message
	@echo ""
	@echo "AIQE — AI Quality Engineering Operating System"
	@echo "================================================"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ==================================================
# ENVIRONMENT SETUP
# ==================================================

setup-dev: ## Complete development environment setup (run once)
	@echo "Setting up AIQE development environment..."
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -e ".[all-dev]"
	$(VENV)/bin/pre-commit install
	$(VENV)/bin/playwright install chromium
	@echo ""
	@echo "Setup complete. Activate with: source $(VENV)/bin/activate"

install: ## Install production dependencies only
	$(PIP) install -e .

install-dev: ## Install all development dependencies
	$(PIP) install -e ".[all-dev]"

pre-commit-install: ## Install pre-commit hooks
	pre-commit install

# ==================================================
# CODE QUALITY
# ==================================================

lint: ## Run ruff linter
	ruff check $(SRC) $(TESTS)

format: ## Run ruff formatter
	ruff format $(SRC) $(TESTS)

format-check: ## Check formatting without applying changes
	ruff format --check $(SRC) $(TESTS)

typecheck: ## Run mypy type checker
	mypy $(SRC)

pre-commit-run: ## Run all pre-commit hooks against all files
	pre-commit run --all-files

check: lint format-check typecheck ## Run all code quality checks (no changes applied)

fix: ## Run linter and formatter with auto-fix
	ruff check --fix $(SRC) $(TESTS)
	ruff format $(SRC) $(TESTS)

# ==================================================
# TESTING
# ==================================================

test: ## Run all tests
	pytest $(TESTS) -v

test-unit: ## Run unit tests only
	pytest $(TESTS)/unit -v -m unit

test-integration: ## Run integration tests only
	pytest $(TESTS)/integration -v -m integration

test-e2e: ## Run end-to-end tests only
	pytest $(TESTS)/e2e -v -m e2e

test-security: ## Run security tests only
	pytest $(TESTS)/security -v -m security

test-performance: ## Run performance tests only
	pytest $(TESTS)/performance -v -m performance

test-fast: ## Run tests excluding slow, browser, and LLM tests
	pytest $(TESTS) -v -m "not slow and not browser and not llm"

test-all: ## Run entire test suite including slow tests
	pytest $(TESTS) -v --timeout=300

coverage: ## Generate coverage report
	pytest $(TESTS) --cov=$(SRC) --cov-report=html --cov-report=term-missing
	@echo "Coverage report: htmlcov/index.html"

# ==================================================
# BUILDING
# ==================================================

build: clean ## Build the package
	$(PYTHON) -m build

clean: ## Remove build artifacts and cache
	rm -rf build/ dist/ *.egg-info/
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	rm -rf htmlcov/ coverage.xml .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	@echo "Cleaned."

# ==================================================
# DOCUMENTATION
# ==================================================

docs: ## Build documentation
	mkdocs build

docs-serve: ## Serve documentation locally
	mkdocs serve

# ==================================================
# AIQE CLI (development)
# ==================================================

scan: ## Run aiqe scan on current directory (dev mode)
	$(PYTHON) -m aiqe.cli.main scan .

version: ## Show aiqe version
	$(PYTHON) -m aiqe.cli.main --version
