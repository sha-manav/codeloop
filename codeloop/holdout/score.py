"""`codeloop holdout verify-scorer` and `codeloop holdout score` (spec §15.2, §15.4, invariant I4)."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from codeloop.config import ProjectConfig
from codeloop.ingest.report import write_text
from codeloop.ledger import append_entry, utc_now
from codeloop.paths import Paths
from codeloop.scoring import Scope, aggregate, canonicalize, score_encounter
from codeloop.scoring.bootstrap import pairwise_version_differences
from codeloop.seal.crypto import decrypt_from_file
from codeloop.util.hashing import sha256_file, tree_hash
from codeloop.util.jsonl import write_json, write_jsonl
from codeloop.versioning.freeze import frozen_scoring_hash


class HoldoutError(RuntimeError):
    pass


def verify_scorer(paths: Paths, *, actor: str | None = None) -> str:
    frozen = frozen_scoring_hash(paths)
    current = tree_hash(paths.scoring_pkg)
    if not frozen:
        raise HoldoutError("no freeze entry in the ledger")
    if current != frozen:
        raise HoldoutError(
            f"scoring tree hash {current[:16]}… differs from the freeze hash {frozen[:16]}… (invariant I3)"
        )
    append_entry(
        paths.ledger,
        "holdout verify-scorer",
        {"scoring_tree_sha256": current, "freeze_hash": frozen, "result": "match"},
        actor=actor,
    )
    return current


def _decrypt_jsonl(path: Path, passphrase: str) -> list[dict[str, Any]]:
    raw = decrypt_from_file(path, passphrase).decode("utf-8")
    return [json.loads(ln) for ln in raw.splitlines() if ln]


def holdout_score(
    paths: Paths,
    config: ProjectConfig,
    *,
    passphrase: str,
    versions: list[str] | None = None,
    actor: str | None = None,
    do_git: bool = True,
    second_coder_seed: int | None = None,
) -> dict[str, Any]:
    lock = paths.sealed / "SCORED.lock"
    if lock.exists():
        raise HoldoutError(
            "the holdout has already been scored (data/sealed/SCORED.lock exists); it is scored exactly once"
        )
    versions = versions or sorted(
        p.name[len("predictions_") : -len(".enc")] for p in paths.sealed.glob("predictions_v*.enc")
    )
    if not versions:
        raise HoldoutError("no sealed predictions found")
    if not paths.holdout_labels_enc.exists():
        raise HoldoutError("no sealed holdout labels (Phase 9 blind labeling not done)")
    scope = Scope.load(paths.scope_yaml)
    labels = _decrypt_jsonl(paths.holdout_labels_enc, passphrase)
    by_coder: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in labels:
        by_coder[r["coder_id"]][r["encounter_id"]] = r["label"]
    coders = sorted(by_coder, key=lambda c: -len(by_coder[c]))
    primary = coders[0]
    gold = by_coder[primary]
    holdout_ids = paths.holdout_ids.read_text().split()
    missing = [i for i in holdout_ids if i not in gold]
    if missing:
        raise HoldoutError(
            f"primary coder {primary} has {len(missing)} unlabeled holdout encounters; label all 40 first"
        )
    preds: dict[str, dict[str, dict]] = {}
    for v in versions:
        recs = _decrypt_jsonl(paths.sealed / f"predictions_{v}.enc", passphrase)
        preds[v] = {r["encounter_id"]: r for r in recs}
    min_n = int(config.decisions["D6"].value)
    results: dict[str, Any] = {
        "scored_at": utc_now(),
        "versions": versions,
        "n": len(holdout_ids),
        "primary_coder": primary,
        "per_version": {},
    }
    agreements: dict[str, dict[str, float]] = {}
    per_version_results = {}
    for v in versions:
        scored = [
            score_encounter(
                eid,
                canonicalize(gold[eid], scope),
                canonicalize(preds[v].get(eid, {"diagnoses": [], "lines": []}), scope),
            )
            for eid in holdout_ids
        ]
        per_version_results[v] = scored
        b = aggregate(scored)
        agreements[v] = {r.encounter_id: r.agreement for r in scored}
        # module-level (lines) results only where evaluable n >= D6
        evaluable = [r for r in scored if any(f.type == "line" for f in r.fields)]
        line_fields = [f for r in evaluable for f in r.fields if f.type in ("line", "modifiers", "units", "pointers")]
        module = (
            f"insufficient (n={len(evaluable)})"
            if len(evaluable) < min_n
            else {
                "n": len(evaluable),
                "line_field_agreement": sum(1 for f in line_fields if f.correct) / len(line_fields)
                if line_fields
                else None,
            }
        )
        results["per_version"][v] = {
            "mean_agreement": b.mean_agreement,
            "mean_hier_agreement": b.mean_hier_agreement,
            "tiers": {k: t.model_dump() for k, t in b.tiers.items()},
            "per_type": b.per_type,
            "no_in_scope_fields": b.no_in_scope_fields,
            "core_lines": module,
            "missing_predictions": sum(1 for eid in holdout_ids if eid not in preds[v]),
        }
    seed = int(config.seeds.get("bootstrap_seed", 0))
    diffs = pairwise_version_differences(
        agreements, n_resamples=int(config.decisions["D9"].value.get("resamples", 10000)), seed=seed
    )
    results["pairwise"] = {k: v.model_dump() for k, v in diffs.items()}
    if len(coders) > 1:
        second = coders[1]
        common = sorted(set(by_coder[second]) & set(gold))
        hh = [
            score_encounter(eid, canonicalize(gold[eid], scope), canonicalize(by_coder[second][eid], scope))
            for eid in common
        ]
        results["human_human"] = {
            "coders": [primary, second],
            "n": len(common),
            "mean_agreement": aggregate(hh).mean_agreement if hh else None,
        }
        if second_coder_seed is not None:
            results["human_human"]["selection_seed"] = second_coder_seed
            random.Random(second_coder_seed)
    write_json(paths.reports / "holdout.json", results)
    write_text(paths.reports / "holdout.md", render_holdout(results, config))
    # plaintext export happens only now (spec §15.4)
    export_dir = paths.runs / "holdout"
    export_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(export_dir / "labels.jsonl", labels)
    for v in versions:
        write_jsonl(export_dir / f"predictions_{v}.jsonl", [preds[v][k] for k in sorted(preds[v])])
    lock.write_text(
        f"scored {results['scored_at']} versions {versions} scorer {tree_hash(paths.scoring_pkg)}\n", encoding="utf-8"
    )
    append_entry(
        paths.ledger,
        "holdout score",
        {
            "versions": versions,
            "n": len(holdout_ids),
            "primary_coder": primary,
            "mean_agreement": {v: results["per_version"][v]["mean_agreement"] for v in versions},
            "report_sha256": sha256_file(paths.reports / "holdout.md"),
            "lock": "data/sealed/SCORED.lock",
        },
        actor=actor,
    )
    if do_git:
        from codeloop.versioning import git

        git.commit_all(paths.root, "Phase 9: holdout scored (single shot)")
    return results


def render_holdout(r: dict[str, Any], config: ProjectConfig) -> str:
    lines = [
        f"# Holdout results (n = {r['n']})",
        "",
        f"Scored once on {r['scored_at']} with the frozen scorer; primary coder `{r['primary_coder']}`.",
        "Primary inferential metric (D9): mean per-encounter field agreement with paired bootstrap 95% CIs; tier shares are descriptive (Wilson intervals).",
        "",
        "| version | mean agreement | hierarchical | ≥75% | ≥90% | 100% | dx recall | line recall | core_lines |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for v, pv in r["per_version"].items():
        t = pv["tiers"]

        def tier(k, t=t):
            return f"{t[k]['share']:.2f} ({t[k]['wilson_low']:.2f}–{t[k]['wilson_high']:.2f})"

        core = (
            pv["core_lines"]
            if isinstance(pv["core_lines"], str)
            else f"n={pv['core_lines']['n']}, line-field agreement {pv['core_lines']['line_field_agreement']}"
        )
        lines.append(
            f"| {v} | {pv['mean_agreement']:.4f} | {pv['mean_hier_agreement']:.4f} | {tier('t75')} | {tier('t90')} | {tier('t100')} | {pv['per_type']['dx']['recall']:.3f} | {pv['per_type']['line']['recall']:.3f} | {core} |"
        )
    lines += [
        "",
        "## Pairwise differences (later − earlier), paired bootstrap",
        "",
        "| pair | diff | 95% CI | n |",
        "|---|---|---|---|",
    ]
    for k, d in r["pairwise"].items():
        lines.append(f"| {k} | {d['diff']:+.4f} | {d['ci_low']:+.4f} … {d['ci_high']:+.4f} | {d['n']} |")
    if "human_human" in r:
        hh = r["human_human"]
        lines += [
            "",
            f"Human–human agreement ({hh['coders'][0]} vs {hh['coders'][1]}, n = {hh['n']}): {hh['mean_agreement']}",
        ]
    lines.append("")
    return "\n".join(lines)
