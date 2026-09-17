"""reports/ingest.md — content-free ingest and crosswalk report.

Never writes encounter text. Never lists holdout IDs (the leakage test scans this file).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from codeloop.config import ProjectConfig
from codeloop.ingest.aci_bench import AciIngestStats
from codeloop.ingest.download import DownloadRecord
from codeloop.ingest.labels import CrosswalkStats


def _ids_line(ids: Iterable[str], holdout: set[str]) -> str:
    listed = [i for i in ids if i not in holdout]
    hidden = sum(1 for i in ids if i in holdout)
    parts = []
    if listed:
        parts.append(", ".join(listed))
    if hidden:
        parts.append(f"plus {hidden} holdout encounter(s), not listed")
    return "; ".join(parts) if parts else "none"


def render_ingest_report(
    *,
    command: str,
    generated_at: str,
    config: ProjectConfig,
    downloads: list[DownloadRecord],
    aci_stats: AciIngestStats,
    amazon_stats: CrosswalkStats,
    medcoder_stats: CrosswalkStats,
    holdout_ids: list[str],
    allocation: dict[str, int],
    seed: int,
) -> str:
    holdout = set(holdout_ids)
    a = aci_stats.to_dict()
    lines: list[str] = []
    lines += [
        "# Ingest report",
        "",
        f"Generated {generated_at} by `codeloop {command}`. This report contains counts and hashes only;",
        "it never contains encounter text and never lists holdout encounter IDs.",
        "",
        "## Sources",
        "",
        "| Source | Title | License | Landing | Pinned |",
        "|---|---|---|---|---|",
    ]
    for sid, s in config.sources.items():
        lines.append(f"| {sid} | {s.title} | {s.license} | {s.landing_url} | {s.pinned_commit or 'release as linked'} |")
    lines += ["", "## Downloads", "", "| Source | File | Bytes | SHA-256 | MD5 | Verified against |", "|---|---|---|---|---|---|"]
    for d in downloads:
        verified = "md5" if d.expected_md5 else ("sha256" if d.expected_sha256 else "—")
        lines.append(f"| {d.source} | {d.name} | {d.bytes} | `{d.sha256}` | `{d.md5}` | {verified} |")
    lines += [
        "",
        "## ACI-Bench encounters",
        "",
        f"- files parsed: {', '.join(a['files'])}",
        f"- encounters: {sum(a['per_split'].values())} (expected {config.expected_encounter_count})",
        f"- per original split: {a['per_split']}",
        f"- per subset: {a['per_subset']}",
        f"- per split × subset: {a['per_split_subset']}",
        f"- dialogue turns: {a['dialogue']['turns']}; speaker tags: {a['dialogue']['speakers']}",
        f"- untagged continuation lines (appended to previous turn): {a['dialogue']['continuation_lines']}; "
        f"leading untagged lines (speaker `unknown`): {a['dialogue']['leading_untagged_lines']}; blank lines dropped: {a['dialogue']['blank_lines']}",
        f"- notes with trailing whitespace (kept as released): {a['notes_with_trailing_ws']}; texts containing CR (normalized): {a['texts_with_cr']}",
        f"- note length (chars) min/mean/max: {a['note_len']['min']}/{a['note_len']['mean']}/{a['note_len']['max']}",
        "- not ingested: `*_metadata.csv` (patient age/sex, chief complaint) and `src_experiment_data/` (ASR variants);"
        " the agent must take patient facts from the note/dialogue with spans (spec §6).",
        "",
        "## Holdout",
        "",
        f"- n = {len(holdout_ids)}, seed = {seed}, stratified on subset; allocation: {allocation}",
        "- IDs: `data/splits/holdout_ids.txt`; content hashes: `data/sealed/holdout_content_hashes.json`;"
        " encrypted content: `data/sealed/holdout_encounters.enc`",
        "",
        "## Amazon ICD-10-CM labels (calibration only)",
        "",
        f"- documents: {amazon_stats.documents}; code rows: {amazon_stats.rows}",
        f"- matched by encounter ID: {amazon_stats.matched_documents}; unmatched documents: {amazon_stats.unmatched_documents} ({amazon_stats.unmatched_rows} rows)",
        f"- code strings not shaped like ICD-10-CM: {amazon_stats.extra.get('invalid_code_shapes', 0)}",
        f"- encounters without an Amazon record: {_ids_line(amazon_stats.encounters_without_record, holdout)}",
        f"- committed after holdout removal: {amazon_stats.matched_documents - sum(1 for i in holdout if i not in amazon_stats.encounters_without_record)} records in `data/labels_public/amazon.jsonl`",
        "",
        "## MedCodER labels (calibration only)",
        "",
        f"- documents: {medcoder_stats.documents} (partition test: {medcoder_stats.extra.get('docs_partition_test')}, "
        f"MedCodER's own 'holdout' partition: {medcoder_stats.extra.get('docs_partition_holdout')} — unrelated to the CodeLoop holdout)",
        f"- diagnosis rows: {medcoder_stats.extra.get('diagnosis_rows')}; supporting-evidence rows: {medcoder_stats.extra.get('evidence_rows')}",
        f"- matched to encounters by note text: {medcoder_stats.matched_documents} ({medcoder_stats.matched_by}); unmatched documents: {medcoder_stats.unmatched_documents} ({medcoder_stats.unmatched_rows} rows dropped); duplicate matches: {medcoder_stats.duplicate_matches}",
        f"- MedCodER's own offsets verified against MedCodER's text: diagnoses {medcoder_stats.extra.get('medcoder_diagnosis_offsets_verified')}/{medcoder_stats.extra.get('diagnosis_rows')}, evidence {medcoder_stats.extra.get('medcoder_evidence_offsets_verified')}/{medcoder_stats.extra.get('evidence_rows')}",
        f"- snippets re-located uniquely in our note_text: diagnoses {medcoder_stats.extra.get('diagnoses_located_in_note')} located / {medcoder_stats.extra.get('diagnoses_not_located')} not; evidence {medcoder_stats.extra.get('evidence_located_in_note')} located / {medcoder_stats.extra.get('evidence_not_located')} not",
        f"- code strings not shaped like ICD-10-CM: {medcoder_stats.extra.get('invalid_code_shapes', 0)}",
        f"- encounters without a MedCodER record: {_ids_line(medcoder_stats.encounters_without_record, holdout)}",
        "",
        "## License notes (owner review before any publication)",
        "",
        "- ACI-Bench: CC BY 4.0. Normalized encounter text in `data/dev/` is gitignored by default and rebuilt by `make data`; committing it is an owner decision.",
        "- Amazon annotations: CC BY-NC 4.0 (non-commercial). Committed as a filtered derivative for calibration.",
        "- MedCodER: CC BY-NC-ND 4.0 (non-commercial, no derivatives). The committed file is a row-filtered, reformatted subset;"
        " confirm that this counts as permitted redistribution before publishing the repository.",
        "",
    ]
    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
