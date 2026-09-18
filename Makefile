UV ?= uv

.PHONY: install test lint seal data leakage decisions tables eval-targeted eval-regression gate task-env fly-deploy-audit fly-deploy-review fly-pull-audit fly-pull-events

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

# --- Fly.io deployment of the coder UIs (fly.toml, Dockerfile.ui). One-time: fly launch --no-deploy (or fly apps create),
#     fly volumes create codeloop_data --size 1, fly secrets set CODELOOP_UI_USER=... CODELOOP_UI_PASS=...
FLY ?= fly
CODER_ID ?= cpc1

fly-deploy-audit:   ## deploy the audit spot-check UI
	$(FLY) deploy -e CODELOOP_UI_MODE=audit -e CODELOOP_CODER_ID=$(CODER_ID) -e CODELOOP_DATA_DIR=/data

fly-deploy-review:  ## deploy the review UI for BATCH=… VERSION=… (CODER_ID=cpc1)
	@test -n "$(BATCH)" -a -n "$(VERSION)" || (echo "usage: make fly-deploy-review BATCH=batch1 VERSION=v0" && exit 1)
	$(FLY) deploy -e CODELOOP_UI_MODE=review -e CODELOOP_BATCH=$(BATCH) -e CODELOOP_VERSION=$(VERSION) -e CODELOOP_CODER_ID=$(CODER_ID) -e CODELOOP_DATA_DIR=/data

fly-pull-audit:     ## copy the spot-check responses back into runs/audit/
	$(FLY) ssh sftp get /data/audit/spot_check_responses.jsonl runs/audit/spot_check_responses.jsonl

fly-pull-events:    ## copy the review event store for BATCH=… VERSION=… into runs/<version>/<batch>/events.sqlite
	@test -n "$(BATCH)" -a -n "$(VERSION)" || (echo "usage: make fly-pull-events BATCH=batch1 VERSION=v0" && exit 1)
	mkdir -p runs/$(VERSION)/$(BATCH)
	$(FLY) ssh sftp get /data/events/$(VERSION)_$(BATCH).sqlite runs/$(VERSION)/$(BATCH)/events.sqlite
