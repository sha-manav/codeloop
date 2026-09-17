"""`codeloop version freeze vK` (spec §14, decision D7)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from codeloop import __version__
from codeloop.config import load_project_config
from codeloop.ledger import append_entry, utc_now
from codeloop.llm.prompts import PromptStore
from codeloop.paths import Paths
from codeloop.util.hashing import sha256_file, sha256_text, tree_hash
from codeloop.versioning import git
from codeloop.versioning.freeze import FREEZE_TAG, frozen_scoring_hash


class VersionError(RuntimeError):
    pass


@dataclass
class VersionResult:
    version: str
    commit: str
    tag_commit: str = ""
    sealed_predictions_sha256: str | None = None
    hashes: dict[str, str] = field(default_factory=dict)


def decisions_hash(paths: Paths) -> str:
    config = load_project_config(paths.project_yaml)
    return sha256_text(str(sorted((k, str(v.value)) for k, v in config.decisions.items())))


def collect_hashes(paths: Paths) -> dict[str, str]:
    hashes = {
        "models_yaml": sha256_file(paths.models_yaml),
        "scope_yaml": sha256_file(paths.scope_yaml),
        "tables_yaml": sha256_file(paths.tables_yaml),
        "project_decisions": decisions_hash(paths),
        "scoring_tree": tree_hash(paths.scoring_pkg),
        "config_tree": tree_hash(paths.config),
    }
    for name, h in PromptStore(paths.root / "prompts").hashes().items():
        hashes[f"prompt:{name}"] = h
    return hashes


def render_version_md(version: str, commit: str, hashes: dict[str, str], models_yaml: str, frozen: str | None) -> str:
    lines = [
        f"# {version}",
        "",
        f"- commit: `{commit}`",
        f"- frozen at: {utc_now()}",
        f"- codeloop: {__version__}",
        f"- scoring tree sha256: `{hashes['scoring_tree']}` (freeze: `{frozen}`)",
        "",
        "## Hashes",
        "",
        "| item | sha256 |",
        "|---|---|",
    ]
    lines += [f"| {k} | `{v}` |" for k, v in sorted(hashes.items())]
    lines += ["", "## config/models.yaml", "", "```yaml", models_yaml.rstrip(), "```", ""]
    return "\n".join(lines)


def freeze_version(
    paths: Paths,
    version: str,
    *,
    sealed_predict,
    actor: str | None = None,
    do_git: bool = True,
    require_main: bool = True,
) -> VersionResult:
    """`sealed_predict(version) -> str | None` runs the sealed holdout prediction and returns the ciphertext hash."""
    if not re.fullmatch(r"v\d+", version):
        raise VersionError("version must look like v0, v1, …")
    if do_git:
        if not git.tag_exists(paths.root, FREEZE_TAG):
            raise VersionError("Phase 3 freeze tag missing")
        if git.tag_exists(paths.root, version):
            raise VersionError(f"tag {version} already exists")
        if require_main and git.current_branch(paths.root) != "main":
            raise VersionError("version freezes happen on main")
        if not git.is_clean(paths.root):
            raise VersionError("working tree must be clean: " + ", ".join(git.dirty_paths(paths.root)[:10]))
    frozen = frozen_scoring_hash(paths)
    hashes = collect_hashes(paths)
    if frozen and hashes["scoring_tree"] != frozen:
        raise VersionError("codeloop/scoring tree hash differs from the freeze hash (invariant I3)")
    commit = git.current_commit(paths.root) if do_git else ""
    vdir = paths.versions / version
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "VERSION.md").write_text(
        render_version_md(version, commit, hashes, paths.models_yaml.read_text(encoding="utf-8"), frozen),
        encoding="utf-8",
    )
    result = VersionResult(version=version, commit=commit, hashes=hashes)
    if do_git:
        result.tag_commit = git.commit_all(paths.root, f"{version}: VERSION.md")
        git.create_tag(paths.root, version, f"CodeLoop {version}")
    result.sealed_predictions_sha256 = sealed_predict(version)
    append_entry(
        paths.ledger,
        f"version freeze {version}",
        {
            "commit": result.tag_commit or commit,
            "tag": version,
            **{k: v for k, v in hashes.items() if not k.startswith("prompt:")},
            "prompt_hashes": {k[7:]: v for k, v in hashes.items() if k.startswith("prompt:")},
            "sealed_predictions_sha256": result.sealed_predictions_sha256,
        },
        actor=actor,
    )
    if do_git:
        git.commit_all(paths.root, f"{version}: sealed holdout predictions and ledger")
    return result
