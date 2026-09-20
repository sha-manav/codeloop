"""Task diagnostic: for the targeted encounters, show what the extractor decided per problem and what was coded.

Prints encounter ids, basis/status values, ICD-10-CM codes and rule notes only, never descriptions or quotes.
Run inside the task environment (LLM calls are served from the cache after an eval run):
    uv run python tasks/FIND-DX-0010/trace_basis.py [SEED] [ENCOUNTER_ID ...]
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from codeloop.agent.pipeline import RunContext, run_encounter
from codeloop.config import load_project_config
from codeloop.llm.client import build_client
from codeloop.paths import Paths
from codeloop.schemas.encounter import load_encounters_jsonl
from codeloop.scoring import Scope
from codeloop.tables import open_tables
from codeloop.util.hashing import sha256_file

paths = Paths(Path.cwd())
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
wanted = sys.argv[2:]
if not wanted:
    for p in sorted((paths.root / "evals" / "datasets").glob("FIND-DX-00*.yaml")):
        wanted += [c["encounter_id"] for c in yaml.safe_load(p.read_text())["cases"]]
wanted = sorted(set(wanted))
gold = {json.loads(ln)["encounter_id"]: json.loads(ln)["label"] for ln in (paths.root / "data/labels/batch1.jsonl").read_text().splitlines() if ln.strip()}
config = load_project_config(paths.project_yaml)
llm = build_client(paths.root)
ctx = RunContext(
    paths=paths, version="head", run_id="trace-basis", llm=llm, tables=open_tables(paths.root / "data/tables/tables.sqlite"),
    scope=Scope.load(paths.scope_yaml), scope_hash=sha256_file(paths.scope_yaml), evidence_policy=str(config.decisions["D1"].value),
    on_date=datetime.now(UTC).strftime("%Y%m%d"), seed=seed, prompt_hashes=llm.prompts.hashes(),
)
for enc in load_encounters_jsonl(paths.dev_encounters):
    if enc.id not in wanted:
        continue
    trace = run_encounter(enc, ctx)
    stages = {s.name: s for s in trace.stages}
    problems = (stages["extract"].output or {}).get("problems", [])
    mapped = {d["problem_index"]: d for d in (stages["map_dx"].output or [])}
    g = sorted(d["code"] for d in gold[enc.id]["diagnoses"])
    print(f"{enc.id} gold={g}")
    for i, p in enumerate(problems):
        m = mapped.get(i, {})
        code = m.get("code")
        mark = "TP" if code in g else ("FP" if code else "--")
        print(f"    [{i}] basis={p.get('basis'):14} status={p.get('status'):10} -> {str(code):8} {mark} {'; '.join(m.get('notes') or [])[:90]}")
