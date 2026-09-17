UV ?= uv

.PHONY: install test lint seal data leakage decisions tables eval-targeted eval-regression gate task-env

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

# --- improvement-agent commands (spec §13.1); TASK=FIND-XX-0001
eval-targeted:      ## run the targeted suite of a finding at the current commit
	$(UV) run codeloop eval run --suite evals/suites/targeted-$(TASK).yaml

eval-regression:    ## run the latest regression suite at the current commit
	$(UV) run codeloop eval run --suite $$(ls evals/suites/regression-through-*.yaml | sort | tail -1)

gate:               ## merge gate for a task: BASE and HEAD default to the task's base commit and HEAD
	$(UV) run codeloop gate check --task tasks/$(TASK) --base $${BASE:-$$(uv run python -c "import yaml;print(yaml.safe_load(open('tasks/$(TASK)/task.yaml'))['base_commit'])")} --head $${HEAD:-$$(git rev-parse HEAD)}

task-env:           ## open the bounded task environment (docker compose)
	docker compose -f docker/compose.yaml run --rm task
