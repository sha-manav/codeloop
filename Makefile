UV ?= uv

.PHONY: install test lint seal data leakage decisions tables

install:            ## create .venv and install codeloop with dev tools
	$(UV) sync --group dev

test:               ## run the full test suite (includes the holdout leakage test)
	$(UV) run pytest

lint:
	$(UV) run ruff check codeloop tests

seal:               ## Phase 0, once: draw and encrypt the holdout, write dev + public labels
	$(UV) run codeloop seal

data:               ## rebuild data/dev and data/labels_public from upstream using the committed holdout IDs
	$(UV) run codeloop ingest

leakage:            ## scan the repo for holdout IDs or holdout content hashes
	$(UV) run codeloop check-leakage

decisions:          ## re-render DECISIONS.md from config/project.yaml
	$(UV) run codeloop render-decisions

tables:             ## download pinned CMS/CDC tables and build data/tables/tables.sqlite
	$(UV) run codeloop tables fetch
	$(UV) run codeloop tables build
