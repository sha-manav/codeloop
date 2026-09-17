"""Render DECISIONS.md from config/project.yaml."""

from __future__ import annotations

import json

from codeloop.config import ProjectConfig


def _fmt(value) -> str:
    if isinstance(value, str | int | float | bool):
        return f"`{value}`"
    return "`" + json.dumps(value, ensure_ascii=False, sort_keys=True) + "`"


def render_decisions(config: ProjectConfig) -> str:
    lines = [
        "# Decisions register",
        "",
        "Rendered from `config/project.yaml` by `codeloop render-decisions` (`make decisions`).",
        "Edit the YAML, not this file. Status: `default` = builder default awaiting the owner;",
        "`confirmed` / `changed` = owner action; `locked` = frozen at Phase 3.",
        "",
        "| ID | Decision | Value | Status | Change before |",
        "|---|---|---|---|---|",
    ]
    for did, d in config.decisions.items():
        lines.append(f"| {did} | {d.name} | {_fmt(d.value)} | {d.status} | {d.change_before} |")
    lines += ["", "## Rationale", ""]
    for did, d in config.decisions.items():
        lines += [f"### {did} — {d.name}", "", d.rationale.strip() or "(none recorded)", ""]
    lines += [
        "## Seeds and parameters (not numbered decisions)",
        "",
        f"- seeds: `{json.dumps(config.seeds, sort_keys=True)}`",
        f"- holdout: `{config.holdout.model_dump()}`",
        f"- dev split: `{config.dev_split.model_dump()}`",
        "",
    ]
    return "\n".join(lines)
