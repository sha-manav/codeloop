"""`codeloop freeze` (Phase 3): difficulty index, dev split with blind subsets, hashes, tag `freeze`.

Difficulty index = z-scored sum of note length (chars), number of Amazon gold ICD codes, and number of
audit-flagged candidate services. The 167 dev encounters are split into seed (20), batch1-3 (45 each)
and spare (12), stratified-random on subset × difficulty tercile with `split_seed`; five blind
encounters per batch are pre-selected (decision D8). The scoring package tree hash recorded here is
the frozen hash checked by tests/test_scoring_frozen.py.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeloop import __version__
from codeloop.config import load_project_config
from codeloop.decisions import render_decisions
from codeloop.ledger import append_entry, utc_now
from codeloop.paths import Paths
from codeloop.schemas.encounter import Encounter, load_encounters_jsonl
from codeloop.scoring import Scope
from codeloop.util.hashing import sha256_file, tree_hash
from codeloop.util.jsonl import read_json, read_jsonl, write_json
from codeloop.versioning import git

SET_ORDER = ("seed", "batch1", "batch2", "batch3", "spare")
FREEZE_TAG = "freeze"


class FreezeError(RuntimeError):
    pass


def _z(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0 for _ in values]
    mean = statistics.fmean(values)
    sd = statistics.pstdev(values)
    return [((v - mean) / sd) if sd > 0 else 0.0 for v in values]


def difficulty_index(
    encounters: list[Encounter], amazon_codes: dict[str, int], flag_counts: dict[str, int]
) -> dict[str, dict[str, float]]:
    ids = [e.id for e in encounters]
    note_len = [float(len(e.note_text)) for e in encounters]
    n_codes = [float(amazon_codes.get(i, 0)) for i in ids]
    n_flags = [float(flag_counts.get(i, 0)) for i in ids]
    z_len, z_codes, z_flags = _z(note_len), _z(n_codes), _z(n_flags)
    return {
        i: {
            "note_len": note_len[k],
            "n_amazon_codes": n_codes[k],
            "n_audit_flags": n_flags[k],
            "z_note_len": z_len[k],
            "z_amazon_codes": z_codes[k],
            "z_audit_flags": z_flags[k],
            "difficulty": z_len[k] + z_codes[k] + z_flags[k],
        }
        for k, i in enumerate(ids)
    }


def _terciles(values: dict[str, float]) -> dict[str, int]:
    ordered = sorted(values, key=lambda i: (values[i], i))
    n = len(ordered)
    out: dict[str, int] = {}
    for rank, i in enumerate(ordered):
        out[i] = min(2, rank * 3 // n) if n else 0
    return out


def _largest_remainder(total_by_set: dict[str, int], stratum_size: int, grand_total: int) -> dict[str, int]:
    """Allocate a stratum of `stratum_size` across sets proportionally to set sizes."""
    raw = {s: total_by_set[s] * stratum_size / grand_total for s in total_by_set}
    alloc = {s: int(raw[s]) for s in raw}
    remainder = stratum_size - sum(alloc.values())
    for s in sorted(raw, key=lambda s: (-(raw[s] - alloc[s]), s))[:remainder]:
        alloc[s] += 1
    return alloc


def stratified_split(
    encounters: list[Encounter],
    difficulty: dict[str, dict[str, float]],
    *,
    sizes: dict[str, int],
    blind_per_batch: int,
    seed: int,
) -> dict[str, Any]:
    ids = sorted(e.id for e in encounters)
    if sum(sizes.values()) != len(ids):
        raise FreezeError(f"split sizes {sizes} sum to {sum(sizes.values())}, but there are {len(ids)} dev encounters")
    subset_of = {e.id: e.subset for e in encounters}
    tercile = _terciles({i: difficulty[i]["difficulty"] for i in ids})
    strata: dict[tuple[str, int], list[str]] = defaultdict(list)
    for i in ids:
        strata[(subset_of[i], tercile[i])].append(i)
    rng = random.Random(seed)
    assignment: dict[str, str] = {}
    # allocate quotas per stratum with largest remainder, then fix rounding so every set hits its size
    quotas: dict[tuple[str, int], dict[str, int]] = {}
    for key in sorted(strata):
        quotas[key] = _largest_remainder(sizes, len(strata[key]), len(ids))
    totals = {s: sum(q[s] for q in quotas.values()) for s in sizes}
    keys = sorted(strata, key=lambda k: -len(strata[k]))
    for s in SET_ORDER:
        while totals[s] > sizes[s]:
            donor = next(k for k in keys if quotas[k][s] > 0)
            receiver = next(t for t in SET_ORDER if totals[t] < sizes[t])
            quotas[donor][s] -= 1
            quotas[donor][receiver] += 1
            totals[s] -= 1
            totals[receiver] += 1
    for key in sorted(strata):
        members = sorted(strata[key])
        rng.shuffle(members)
        cursor = 0
        for s in SET_ORDER:
            for i in members[cursor : cursor + quotas[key][s]]:
                assignment[i] = s
            cursor += quotas[key][s]
    sets = {s: sorted(i for i in ids if assignment[i] == s) for s in SET_ORDER}
    blind = {b: sorted(rng.sample(sets[b], min(blind_per_batch, len(sets[b])))) for b in ("batch1", "batch2", "batch3")}
    summary = {}
    for s, members in sets.items():
        subsets: dict[str, int] = defaultdict(int)
        for i in members:
            subsets[subset_of[i]] += 1
        summary[s] = {
            "n": len(members),
            "mean_difficulty": statistics.fmean(difficulty[i]["difficulty"] for i in members) if members else 0.0,
            "mean_note_len": statistics.fmean(difficulty[i]["note_len"] for i in members) if members else 0.0,
            "mean_amazon_codes": statistics.fmean(difficulty[i]["n_amazon_codes"] for i in members) if members else 0.0,
            "mean_audit_flags": statistics.fmean(difficulty[i]["n_audit_flags"] for i in members) if members else 0.0,
            "subsets": dict(sorted(subsets.items())),
        }
    return {"seed": seed, "sizes": sizes, "sets": sets, "blind": blind, "summary": summary, "tercile": tercile}


@dataclass
class FreezeResult:
    commit: str
    tag: str
    scoring_tree_sha256: str
    config_tree_sha256: str
    splits_tree_sha256: str
    dev_split_sha256: str
    summary: dict[str, Any] = field(default_factory=dict)


def load_split_inputs(paths: Paths) -> tuple[list[Encounter], dict[str, int], dict[str, int]]:
    encounters = load_encounters_jsonl(paths.dev_encounters)
    amazon: dict[str, int] = {}
    if paths.amazon_labels.exists():
        for r in read_jsonl(paths.amazon_labels):
            amazon[r["encounter_id"]] = len(r.get("codes", []))
    flags: dict[str, int] = {}
    fc = paths.runs / "audit" / "flag_counts.json"
    if fc.exists():
        flags = {k: int(v) for k, v in read_json(fc).items()}
    return encounters, amazon, flags


def validate_scope(scope_path: Path) -> Scope:
    scope = Scope.load(scope_path)
    if "core_dx" not in scope.modules or not scope.modules["core_dx"].on:
        raise FreezeError("scope.yaml: core_dx must be on")
    if "core_lines" not in scope.modules:
        raise FreezeError("scope.yaml: core_lines module missing")
    for name, m in scope.modules.items():
        if m.on and name != "core_dx" and not m.code_ranges and not m.modifiers:
            raise FreezeError(f"scope.yaml: module {name} is on but has no code ranges or modifiers")
    return scope


def supersede_freeze(paths: Paths, *, reason: str, actor: str | None = None, do_git: bool = True) -> dict[str, str]:
    """Retire the current freeze: tag `freeze` -> `freeze-provisional`, dev_split.json -> a .provisional copy,
    and a correction entry in the ledger. The caller then proceeds as a fresh freeze."""
    info: dict[str, str] = {"reason": reason}
    if do_git and git.tag_exists(paths.root, FREEZE_TAG):
        info["previous_commit"] = git.tag_commit(paths.root, FREEZE_TAG)
        info["renamed_tag"] = git.rename_tag(paths.root, FREEZE_TAG, f"{FREEZE_TAG}-provisional")
    if paths.dev_split.exists():
        stamp = utc_now().replace(":", "").replace("-", "")
        moved = paths.splits / f"dev_split.provisional-{stamp}.json"
        paths.dev_split.rename(moved)
        info["previous_dev_split"] = moved.relative_to(paths.root).as_posix()
        info["previous_dev_split_sha256"] = sha256_file(moved)
    prev = frozen_scoring_hash(paths)
    if prev:
        info["previous_scoring_tree_sha256"] = prev
    append_entry(paths.ledger, "freeze superseded (correction)", info, actor=actor)
    return info


def perform_freeze(
    paths: Paths,
    *,
    actor: str | None = None,
    require_clean: bool = True,
    do_git: bool = True,
    supersede: bool = False,
    reason: str = "superseded by the owner",
) -> FreezeResult:
    config = load_project_config(paths.project_yaml)
    validate_scope(paths.scope_yaml)
    if not paths.holdout_ids.exists():
        raise FreezeError("holdout not sealed; run Phase 0 first")
    if do_git and not git.is_repo(paths.root):
        raise FreezeError("not a git repository")
    if do_git and require_clean and not git.is_clean(paths.root):
        dirty = ", ".join(git.dirty_paths(paths.root)[:10])
        raise FreezeError(f"working tree must be clean before freezing: {dirty}")
    if supersede:
        supersede_freeze(paths, reason=reason, actor=actor, do_git=do_git)
    if paths.dev_split.exists():
        raise FreezeError(
            f"{paths.dev_split.relative_to(paths.root)} exists; the freeze happens once (use --supersede)"
        )
    if do_git and git.tag_exists(paths.root, FREEZE_TAG):
        raise FreezeError(f"tag {FREEZE_TAG!r} already exists (use --supersede)")
    encounters, amazon, flags = load_split_inputs(paths)
    holdout = set(paths.holdout_ids.read_text().split())
    if any(e.id in holdout for e in encounters):
        raise FreezeError("dev encounters contain holdout ids")
    if not flags:
        raise FreezeError("runs/audit/flag_counts.json missing; run `codeloop audit report` (Phase 2) first")
    if not amazon:
        raise FreezeError("data/labels_public/amazon.jsonl missing")
    difficulty = difficulty_index(encounters, amazon, flags)
    ds = config.dev_split
    sizes = {
        "seed": ds.seed,
        "batch1": ds.batch_size,
        "batch2": ds.batch_size,
        "batch3": ds.batch_size,
        "spare": ds.spare,
    }
    split = stratified_split(
        encounters, difficulty, sizes=sizes, blind_per_batch=ds.blind_per_batch, seed=int(config.seeds["split_seed"])
    )
    split["frozen_at"] = utc_now()
    split["difficulty"] = {i: difficulty[i] for i in sorted(difficulty)}
    write_json(paths.dev_split, split)

    # lock decisions and re-render
    _lock_decisions(paths.project_yaml)
    config = load_project_config(paths.project_yaml)
    paths.decisions_md.write_text(render_decisions(config), encoding="utf-8", newline="\n")

    scoring_hash = tree_hash(paths.scoring_pkg)
    config_hash = tree_hash(paths.config)
    splits_hash = tree_hash(paths.splits)
    fields = {
        "codeloop_version": __version__,
        "split_seed": config.seeds["split_seed"],
        "sizes": sizes,
        "blind_per_batch": ds.blind_per_batch,
        "set_summary": {
            s: {k: (round(v, 3) if isinstance(v, float) else v) for k, v in split["summary"][s].items()}
            for s in SET_ORDER
        },
        "dev_split_sha256": sha256_file(paths.dev_split),
        "scope_yaml_sha256": sha256_file(paths.scope_yaml),
        "scope_status": _scope_status(paths.scope_yaml),
        "project_yaml_sha256": sha256_file(paths.project_yaml),
        "models_yaml_sha256": sha256_file(paths.models_yaml) if paths.models_yaml.exists() else None,
        "config_tree_sha256": config_hash,
        "splits_tree_sha256": splits_hash,
        "scoring_tree_sha256": scoring_hash,
        "decisions": "D0–D10 locked",
    }
    append_entry(paths.ledger, "freeze", fields, actor=actor)
    commit = ""
    if do_git:
        commit = git.commit_all(paths.root, "Phase 3: freeze (dev split, locked decisions, scoring hash)")
        git.create_tag(paths.root, FREEZE_TAG, f"CodeLoop freeze; scoring tree {scoring_hash}")
    return FreezeResult(
        commit=commit,
        tag=FREEZE_TAG if do_git else "",
        scoring_tree_sha256=scoring_hash,
        config_tree_sha256=config_hash,
        splits_tree_sha256=splits_hash,
        dev_split_sha256=sha256_file(paths.dev_split),
        summary=split["summary"],
    )


def _scope_status(scope_path: Path) -> str:
    extra = Scope.load(scope_path).model_extra or {}
    return str((extra.get("audit_provenance") or {}).get("status", "final"))


def _lock_decisions(project_yaml: Path) -> None:
    """Set every decision's status to `locked` in place, preserving the rest of the file."""
    import re

    text = project_yaml.read_text(encoding="utf-8")
    text = re.sub(r"^(    status: )(default|confirmed|changed)$", r"\1locked", text, flags=re.M)
    project_yaml.write_text(text, encoding="utf-8")


def frozen_scoring_hash(paths: Paths) -> str | None:
    """The scoring tree hash recorded by the most recent `freeze` ledger entry, if any."""
    from codeloop.ledger import read_entries

    if not paths.ledger.exists():
        return None
    for entry in reversed(read_entries(paths.ledger)):
        if entry.event == "freeze":
            return entry.fields.get("scoring_tree_sha256")
    return None


def load_dev_split(paths: Paths) -> dict[str, Any]:
    if not paths.dev_split.exists():
        raise FreezeError("data/splits/dev_split.json missing; run `codeloop freeze` (Phase 3)")
    return read_json(paths.dev_split)


def batch_ids(paths: Paths, name: str) -> list[str]:
    split = load_dev_split(paths)
    if name not in split["sets"]:
        raise FreezeError(f"unknown batch {name!r}; known: {list(split['sets'])}")
    return list(split["sets"][name])
