"""Task diagnostic: how the head extraction's problem descriptions differ in shape from v0's, for the same encounter.

Prints counts, lengths, similarity scores and codes only; never the descriptions themselves.
    uv run python tasks/FIND-DX-0010/compare_extractions.py [SEED] ENCOUNTER_ID ...
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from codeloop.agent.pipeline import RunContext, run_encounter
from codeloop.config import load_project_config
from codeloop.llm.client import build_client
from codeloop.paths import Paths
from codeloop.schemas.encounter import load_encounters_jsonl
from codeloop.scoring import Scope
from codeloop.tables import open_tables
from codeloop.util.hashing import sha256_file

paths = Paths(Path.cwd())
seed, wanted = int(sys.argv[1]), set(sys.argv[2:])
config = load_project_config(paths.project_yaml)
llm = build_client(paths.root)
ctx = RunContext(
    paths=paths, version="head", run_id="compare", llm=llm, tables=open_tables(paths.root / "data/tables/tables.sqlite"),
    scope=Scope.load(paths.scope_yaml), scope_hash=sha256_file(paths.scope_yaml), evidence_policy=str(config.decisions["D1"].value),
    on_date=datetime.now(UTC).strftime("%Y%m%d"), seed=seed, prompt_hashes=llm.prompts.hashes(),
)
gold = {json.loads(ln)["encounter_id"]: json.loads(ln)["label"] for ln in (paths.root / "data/labels/batch1.jsonl").read_text().splitlines() if ln.strip()}


def toks(p):
    return set((p["description"] + " " + " ".join(p.get("qualifiers", []))).lower().replace(",", " ").split())


def cands(p):
    if p["status"] == "ruled_out":
        return []
    return [c.code for c in ctx.retriever.candidates_for_problem(p["description"], p.get("qualifiers", []), p["laterality"], p["status"])]


for enc in load_encounters_jsonl(paths.dev_encounters):
    if enc.id not in wanted:
        continue
    base_trace = json.loads((paths.runs / "v0" / "batch1" / "traces" / "seed1" / f"{enc.id}.json").read_text())
    stages = {s["name"]: s for s in base_trace["stages"]}
    b_problems = stages["extract"]["output"]["problems"]
    b_codes = {d["problem_index"]: d["code"] for d in stages["map_dx"]["output"]}
    head_trace = run_encounter(enc, ctx)
    h_stages = {s.name: s for s in head_trace.stages}
    h_problems = h_stages["extract"].output["problems"]
    h_codes = {d["problem_index"]: d["code"] for d in h_stages["map_dx"].output}
    g = {d["code"] for d in gold[enc.id]["diagnoses"]}
    print(f"{enc.id}: base problems {len(b_problems)}, head problems {len(h_problems)}; gold {sorted(g)}")
    for i, bp in enumerate(b_problems):
        if b_codes.get(i) not in g:
            continue  # only the problems v0 coded correctly
        best = max(range(len(h_problems)), key=lambda j: len(toks(bp) & toks(h_problems[j])) / max(1, len(toks(bp) | toks(h_problems[j]))))
        hp = h_problems[best]
        jac = len(toks(bp) & toks(hp)) / max(1, len(toks(bp) | toks(hp)))
        bc, hc = cands(bp), cands(hp)
        print(f"   base[{i}] -> {b_codes[i]:8} words={len(bp['description'].split()):2} quals={len(bp.get('qualifiers', []))} lat={bp['laterality']:14} "
              f"| closest head[{best}] sim={jac:.2f} words={len(hp['description'].split()):2} quals={len(hp.get('qualifiers', []))} lat={hp['laterality']:14} basis={hp.get('basis')} "
              f"-> {str(h_codes.get(best)):8} | gold code in base cands: {b_codes[i] in bc}, in head cands: {b_codes[i] in hc}; cands shared {len(set(bc) & set(hc))}/{len(bc)}")
