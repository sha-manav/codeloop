"""`codeloop findings package FIND-…` (spec §11, §13.1): targeted dataset + suites + task folder."""

from __future__ import annotations

from pathlib import Path

import yaml

from codeloop.config import ProjectConfig
from codeloop.evals.suites import EvalCase, EvalDataset, EvalSuite
from codeloop.findings.extract import field_refs_for, load_existing, save_finding
from codeloop.paths import Paths
from codeloop.review_ui.store import EventStore
from codeloop.scoring import Scope
from codeloop.util.jsonl import read_jsonl
from codeloop.versioning import git

WRITABLE = [
    "codeloop/agent/",
    "codeloop/schemas/",
    "codeloop/mappers/",
    "codeloop/rules/",
    "codeloop/tools/",
    "prompts/",
]
SIGN_OFF = ["evals/graders/"]
READ_ONLY = [
    "codeloop/scoring/",
    "codeloop/compliance/",
    "codeloop/scrubber/",
    "config/",
    "data/",
    "runs/",
    "evals/datasets/",
    "evals/suites/",
    "findings/",
]


def labeled_batches(paths: Paths) -> list[str]:
    return sorted(p.stem for p in paths.labels.glob("batch*.jsonl"))


def package_finding(
    paths: Paths, config: ProjectConfig, finding_id: str, *, store: EventStore | None = None
) -> dict[str, str]:
    finding = next((f for f in load_existing(paths) if f.id == finding_id), None)
    if finding is None:
        raise RuntimeError(f"unknown finding {finding_id}")
    if finding.status not in ("accepted", "eligible"):
        raise RuntimeError(
            f"{finding_id} has status {finding.status}; only accepted (or eligible) findings are packaged"
        )
    batch = finding.batch_discovered
    labels = read_jsonl(paths.labels_file(batch))
    version = labels[0]["version_reviewed"]
    scope = Scope.load(paths.scope_yaml)
    # a finding seen in several batches has occurrences in each batch's event store; every occurrence becomes a case
    batches = [batch] + [b for b in finding.batches_seen if b != batch and paths.labels_file(b).exists()]
    cases: list[EvalCase] = []
    for b in batches:
        if store is not None and b == batch:
            b_store = store
        else:
            b_version = read_jsonl(paths.labels_file(b))[0]["version_reviewed"]
            b_store = EventStore.from_jsonl(paths.review_dir(b_version, b) / "events.jsonl")
        refs = field_refs_for(b_store, finding, scope)
        cases += [
            EvalCase(encounter_id=eid, gold=f"data/labels/{b}.jsonl#{eid}", field_refs=refs.get(eid, []))
            for eid in sorted(refs)
        ]
    dataset = EvalDataset(finding=finding.id, cases=cases)
    ds_path = paths.evals / "datasets" / f"{finding.id}.yaml"
    dataset.save(ds_path)
    runs = int(config.decisions["D4"].value.get("runs", 3))
    seeds = list(config.decisions["D4"].value.get("seeds", [1, 2, 3]))
    targeted = EvalSuite(
        name=f"targeted-{finding.id}",
        kind="targeted",
        dataset=ds_path.relative_to(paths.root).as_posix(),
        runs=runs,
        seeds=seeds,
        finding=finding.id,
    )
    t_path = paths.evals / "suites" / f"targeted-{finding.id}.yaml"
    targeted.save(t_path)
    batches = labeled_batches(paths)
    reg_name = f"regression-through-{batches[-1]}"
    regression = EvalSuite(
        name=reg_name,
        kind="regression",
        gold=[f"data/labels/{b}.jsonl" for b in batches],
        base_version=version,
        runs=runs,
        seeds=seeds,
    )
    r_path = paths.evals / "suites" / f"{reg_name}.yaml"
    regression.save(r_path)
    task_dir = paths.tasks / finding.id
    task_dir.mkdir(parents=True, exist_ok=True)
    base_commit = git.current_commit(paths.root) if git.is_repo(paths.root) else ""
    d5 = config.decisions["D5"].value
    task = {
        "finding": finding.id,
        "title": finding.title,
        "base_commit": base_commit,
        "base_version": version,
        "writable": WRITABLE + [f"tasks/{finding.id}/"],
        "writable_with_sign_off": SIGN_OFF,
        "read_only": READ_ONLY,
        "not_mounted": ["data/sealed/"],
        "network": "LLM provider API host(s) only, via docker/allowlist proxy",
        "commands": [f"make eval-targeted TASK={finding.id}", "make eval-regression", f"make gate TASK={finding.id}"],
        "targeted_suite": t_path.relative_to(paths.root).as_posix(),
        "regression_suite": r_path.relative_to(paths.root).as_posix(),
        "success_criteria": d5,
        "definition_of_done": [
            "RESULTS.md complete: targeted before/after, regression before/after, scrubber delta, escalations, diff summary",
            "gate PASS, or an explicit ambiguity note",
            f"branch codeloop/{finding.id} pushed",
        ],
        "prohibited": [
            "changing scope",
            "touching codeloop/scoring",
            "adding CPT descriptors",
            "reading holdout material",
            "weakening the compliance policy",
            "editing config/, findings/, evals/datasets/, evals/suites/",
        ],
    }
    (task_dir / "task.yaml").write_text(yaml.safe_dump(task, sort_keys=False), encoding="utf-8")
    (task_dir / "EXEC_PLAN.md").write_text(
        f"# EXEC_PLAN — {finding.id}\n\n_Written by the improvement agent._\n\n## Root cause\n\n(fill in)\n\n"
        "## pipeline_cause\n\n(one of: extraction_miss, mapper_gap, tool_data_gap, rule_bug, grader_bug, model_reasoning)\n\n## Plan\n\n(fill in)\n",
        encoding="utf-8",
    )
    (task_dir / "RESULTS.md").write_text(
        f"# RESULTS — {finding.id}\n\n_Written by the improvement agent._\n\n"
        "| metric | before (base) | after (head) |\n|---|---|---|\n| targeted error rate | | |\n| regression mean agreement | | |\n"
        "| dx recall | | |\n| line recall | | |\n| scrubber errors | | |\n| escalation failures | | |\n\n"
        "grader_changed: false\n\n## Diff summary\n\n(fill in)\n",
        encoding="utf-8",
    )
    finding.targeted_eval = ds_path.relative_to(paths.root).as_posix()
    finding.task = f"tasks/{finding.id}/"
    save_finding(paths, finding)
    return {
        "dataset": finding.targeted_eval,
        "targeted_suite": targeted.name,
        "regression_suite": reg_name,
        "task": finding.task,
    }


def packaged_paths(paths: Paths, finding_id: str) -> tuple[Path, Path, Path]:
    task_dir = paths.tasks / finding_id
    with open(task_dir / "task.yaml", encoding="utf-8") as fh:
        task = yaml.safe_load(fh)
    return task_dir, paths.root / task["targeted_suite"], paths.root / task["regression_suite"]
