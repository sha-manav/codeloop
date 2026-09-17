"""Sealed holdout prediction (spec §15.1): decrypt in memory, run the pipeline with the cache off and
content-free logging, encrypt predictions and traces. Nothing about the outputs is displayed."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from codeloop.agent.pipeline import RunContext, run_encounter
from codeloop.config import ProjectConfig
from codeloop.ledger import append_entry, utc_now
from codeloop.llm.client import LLMClient
from codeloop.paths import Paths
from codeloop.schemas.encounter import Encounter
from codeloop.scoring import Scope
from codeloop.seal.crypto import decrypt_from_file, encrypt_to_file
from codeloop.tables import Tables
from codeloop.util.hashing import sha256_file
from codeloop.util.jsonl import dumps_record


class SealedPredictError(RuntimeError):
    pass


def load_holdout_encounters(paths: Paths, passphrase: str) -> list[Encounter]:
    raw = decrypt_from_file(paths.holdout_encounters_enc, passphrase).decode("utf-8")
    return [Encounter.model_validate_json(ln) for ln in raw.splitlines() if ln]


def sealed_predict(
    paths: Paths,
    config: ProjectConfig,
    version: str,
    *,
    llm: LLMClient,
    tables: Tables,
    passphrase: str,
    seed: int = 1,
    concurrency: int = 4,
    actor: str | None = None,
    check_tag: bool = True,
) -> str:
    if llm.cache_enabled:
        raise SealedPredictError("sealed prediction requires the LLM cache to be disabled")
    if check_tag:
        from codeloop.versioning import git

        tag = git.describe_exact_tag(paths.root)
        if tag != version and not (git.is_clean(paths.root) and git.code_matches_tag(paths.root, version)):
            raise SealedPredictError(
                f"working tree is at tag {tag!r}, not {version!r}, and the code differs from the tag"
            )
    out = paths.sealed / f"predictions_{version}.enc"
    if out.exists():
        raise SealedPredictError(f"{out.relative_to(paths.root)} already exists")
    encounters = load_holdout_encounters(paths, passphrase)
    scope = Scope.load(paths.scope_yaml)
    ctx = RunContext(
        paths=paths,
        version=version,
        run_id=f"{version}-holdout-sealed-{utc_now().replace(':', '').replace('-', '')}",
        llm=llm,
        tables=tables,
        scope=scope,
        scope_hash=sha256_file(paths.scope_yaml),
        evidence_policy=str(config.decisions["D1"].value),
        on_date=datetime.now(UTC).strftime("%Y%m%d"),
        seed=seed,
        prompt_hashes=llm.prompts.hashes(),
    )
    failures = 0
    traces = []

    def work(enc: Encounter):
        try:
            return run_encounter(enc, ctx)
        except Exception:  # noqa: BLE001 - content-free: no message, no id
            return None

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        for t in pool.map(work, encounters):
            if t is None:
                failures += 1
            else:
                traces.append(t)
    if failures:
        raise SealedPredictError(f"{failures} holdout encounter(s) failed; nothing written")
    traces.sort(key=lambda t: t.encounter_id)
    plaintext = "".join(dumps_record(t.package) + "\n" for t in traces).encode("utf-8")
    encrypt_to_file(plaintext, out, passphrase, label=f"predictions_{version}")
    trace_text = "".join(t.model_dump_json() + "\n" for t in traces).encode("utf-8")
    encrypt_to_file(trace_text, paths.sealed / f"traces_{version}.enc", passphrase, label=f"traces_{version}")
    digest = sha256_file(out)
    (paths.sealed / f"predictions_{version}.sha256").write_text(
        f"{digest}  predictions_{version}.enc\n", encoding="utf-8"
    )
    tokens_in = sum(c.tokens_in for t in traces for s in t.stages for c in s.llm_calls)
    tokens_out = sum(c.tokens_out for t in traces for s in t.stages for c in s.llm_calls)
    append_entry(
        paths.ledger,
        f"holdout predict {version} (sealed)",
        {
            "n": len(traces),
            "predictions_enc_sha256": digest,
            "traces_enc_sha256": sha256_file(paths.sealed / f"traces_{version}.enc"),
            "models_yaml_sha256": llm.models_hash,
            "scope_sha256": ctx.scope_hash,
            "tables_version": tables.version,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cache": "disabled",
            "seed": seed,
        },
        actor=actor,
    )
    return digest
