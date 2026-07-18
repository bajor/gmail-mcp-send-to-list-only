.PHONY: test

test:
	.venv/bin/python -m ruff check src tests
	.venv/bin/python -m mypy src
	.venv/bin/python -m pytest -q
