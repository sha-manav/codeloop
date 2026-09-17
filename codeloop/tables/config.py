"""config/tables.yaml: pinned releases, URLs, hashes and parser versions of every external table."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from codeloop.util.hashing import sha256_file

HEADER = """# Pinned external tables (spec §2.1, §3). `codeloop tables fetch` downloads every file into
# data/tables/raw/ (gitignored), verifies or records sha256/bytes/downloaded_at here, and
# `codeloop tables build` parses them into data/tables/tables.sqlite (gitignored, rebuilt on demand).
# CPT descriptor text (AMA-licensed) is discarded at parse time wherever a file carries it (I6).
"""


class TableFile(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    url: str
    members: list[str] = Field(default_factory=list)
    sha256: str | None = None
    bytes: int | None = None
    downloaded_at: str | None = None


class TableSpec(BaseModel):
    model_config = ConfigDict(extra="allow")
    release: str
    effective: str | None = None
    license: str = ""
    parser: str
    note: str = ""
    files: list[TableFile]


class TablesConfig(BaseModel):
    parser_version: str = "1"
    tables: dict[str, TableSpec]
    source_sha256: str | None = None


def load_tables_config(path: Path) -> TablesConfig:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    cfg = TablesConfig.model_validate(raw)
    cfg.source_sha256 = sha256_file(path)
    return cfg


def save_tables_config(path: Path, cfg: TablesConfig) -> None:
    data = cfg.model_dump(mode="json", exclude={"source_sha256"}, exclude_none=True)
    text = HEADER + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120)
    Path(path).write_text(text, encoding="utf-8", newline="\n")
