"""Synthetic corpus and label fixtures. No real encounter text anywhere in tests."""

from __future__ import annotations

import shutil
from pathlib import Path

from codeloop.config import ProjectConfig, load_project_config
from codeloop.ingest.aci_bench import AciIngestStats
from codeloop.ingest.download import DownloadRecord
from codeloop.ingest.labels import (
    AmazonCodeRow,
    MedCodERData,
    MedCodERDiagnosis,
    MedCodERDoc,
    MedCodEREvidence,
)
from codeloop.paths import Paths
from codeloop.schemas.encounter import Encounter, build_encounter
from codeloop.seal.run import SealInputs

SUBSET_COUNTS = {"aci": 112, "virtassist": 55, "virtscribe": 40}
REAL_ROOT = Path(__file__).resolve().parents[1]


def _split_for(i: int) -> str:
    if i <= 67:
        return "train"
    if i <= 87:
        return "valid"
    if i <= 127:
        return "test1"
    if i <= 167:
        return "test2"
    return "test3"


def synthetic_dialogue(i: int) -> str:
    return (
        f"[doctor] hi , how are you doing today ? this is visit number {i} .\n"
        f"[patient] i'm okay , my knee has been hurting for about {i % 9 + 1} weeks .\n"
        "\n"
        "[doctor] okay . let's take a look .\n"
    )


def synthetic_note(i: int) -> str:
    return (
        "CHIEF COMPLAINT\n\n"
        f"Knee pain, visit number {i}.\n\n"
        "HISTORY OF PRESENT ILLNESS\n\n"
        f"The patient reports right knee pain for {i % 9 + 1} weeks.  Denies fever.\n\n"
        "ASSESSMENT AND PLAN\n\n"
        f"1. Primary osteoarthritis of right knee, visit {i}.\n"
        "- Medical Reasoning: synthetic fixture text.\n"
    )


def synthetic_encounters(counts: dict[str, int] | None = None) -> list[Encounter]:
    counts = counts or SUBSET_COUNTS
    encs: list[Encounter] = []
    i = 0
    for subset, n in counts.items():
        for _ in range(n):
            i += 1
            enc, _ = build_encounter(
                id=f"D2N{i:03d}",
                subset=subset,
                split_orig=_split_for(i),
                dialogue_raw=synthetic_dialogue(i),
                note_raw=synthetic_note(i),
            )
            encs.append(enc)
    return encs


def synthetic_amazon(encs: list[Encounter]) -> list[AmazonCodeRow]:
    rows: list[AmazonCodeRow] = []
    for k, e in enumerate(encs):
        rows.append(AmazonCodeRow(document_id=e.id, code_raw="M17.11", description="Unilateral primary osteoarthritis, right knee", split_orig=e.split_orig))
        if k % 2 == 0:
            rows.append(AmazonCodeRow(document_id=e.id, code_raw="r50.9", description="Fever, unspecified", split_orig=e.split_orig))
    rows.append(AmazonCodeRow(document_id="D2N999", code_raw="Z00.00", description="Encounter for general adult medical examination", split_orig="test"))
    return rows


def _variant(note: str, k: int) -> str:
    if k == 0:
        return note
    if k == 1:
        return note.rstrip()
    return note.replace("  ", " ").replace("\n\n", "\n")


def synthetic_medcoder(encs: list[Encounter], *, skip_last: int = 3) -> MedCodERData:
    data = MedCodERData()
    for k, e in enumerate(encs[: len(encs) - skip_last]):
        text = _variant(e.note_text, k % 3)
        partition = "holdout" if k < 20 else "test"
        doc_id = f"mc{k:05d}xxxxxxxxxxxxxxxx"
        data.docs.append(MedCodERDoc(doc_id=doc_id, text=text, aci_doc_id=f"test_{k + 1}", partition=partition))
        dx = "Primary osteoarthritis of right knee"
        s = text.index(dx)
        data.diagnoses.append(MedCodERDiagnosis(doc_id=doc_id, code_raw="M17.11", diagnosis=dx, start=s, end=s + len(dx), partition=partition))
        ev = "right knee pain"
        s2 = text.index(ev)
        data.evidence.append(MedCodEREvidence(doc_id=doc_id, code_raw="M17.11", text=ev, start=s2 + 1, end=s2 + 1 + len(ev), coordinate=f"({s2}, {s2 + len(ev)})", partition=partition))
    for k in range(2):
        data.docs.append(MedCodERDoc(doc_id=f"unmatched{k}", text=f"Totally unrelated synthetic record {k}.", aci_doc_id=f"test_{900 + k}", partition="test"))
        data.diagnoses.append(MedCodERDiagnosis(doc_id=f"unmatched{k}", code_raw="Z00.00", diagnosis="record", start=0, end=6, partition="test"))
    return data


def synthetic_downloads() -> list[DownloadRecord]:
    return [
        DownloadRecord(source="aci_bench", name="aci-bench-2023.zip", url="https://example.invalid/aci.zip", path="data/raw/aci_bench/aci-bench-2023.zip", bytes=10, sha256="a" * 64, md5="b" * 32, fetched_at="2026-01-01T00:00:00Z", expected_md5="b" * 32),
        DownloadRecord(source="amazon_labels", name="code_train.csv", url="https://example.invalid/code_train.csv", path="data/raw/amazon_labels/code_train.csv", bytes=10, sha256="c" * 64, md5="d" * 32, fetched_at="2026-01-01T00:00:00Z", split_orig="train"),
        DownloadRecord(source="medcoder", name="text.csv", url="https://example.invalid/text.csv", path="data/raw/medcoder/text.csv", bytes=10, sha256="e" * 64, md5="f" * 32, fetched_at="2026-01-01T00:00:00Z", role="text", partition="test"),
    ]


def synthetic_stats(encs: list[Encounter]) -> AciIngestStats:
    st = AciIngestStats(files=["synthetic.csv"])
    for e in encs:
        st.per_split[e.split_orig] = st.per_split.get(e.split_orig, 0) + 1
        st.per_subset[e.subset] = st.per_subset.get(e.subset, 0) + 1
        st.per_split_subset.setdefault(e.split_orig, {})
        st.per_split_subset[e.split_orig][e.subset] = st.per_split_subset[e.split_orig].get(e.subset, 0) + 1
    st.dialogue.turns = 3 * len(encs)
    st.dialogue.speakers = {"doctor": 2 * len(encs), "patient": len(encs)}
    lengths = [len(e.note_text) for e in encs]
    st.note_len_min, st.note_len_max, st.note_len_mean = min(lengths), max(lengths), sum(lengths) / len(lengths)
    return st


def make_inputs(encs: list[Encounter] | None = None) -> SealInputs:
    encs = encs or synthetic_encounters()
    return SealInputs(
        encounters=encs,
        amazon_rows=synthetic_amazon(encs),
        medcoder=synthetic_medcoder(encs),
        downloads=synthetic_downloads(),
        aci_stats=synthetic_stats(encs),
    )


def make_repo(tmp_path: Path) -> tuple[Paths, ProjectConfig]:
    """A throwaway repo root with the real config and an empty layout plus fake raw downloads."""
    root = tmp_path / "repo"
    paths = Paths(root)
    paths.ensure_layout()
    shutil.copy2(REAL_ROOT / "config" / "project.yaml", paths.project_yaml)
    (root / "pyproject.toml").write_text('[project]\nname = "codeloop"\n', encoding="utf-8")
    (root / "codeloop").mkdir(exist_ok=True)
    (paths.raw / ".gitkeep").write_text("", encoding="utf-8")
    (paths.raw / "aci_bench").mkdir(parents=True, exist_ok=True)
    (paths.raw / "aci_bench" / "fake.csv").write_text("dataset,encounter_id,dialogue,note\n", encoding="utf-8")
    (paths.raw / "loose.bin").write_bytes(b"\x00")
    paths.ledger.write_text("# CodeLoop ledger\n", encoding="utf-8")
    return paths, load_project_config(paths.project_yaml)


FAKE_KEY = "synthetic-test-key-not-for-real-use-0123456789"
