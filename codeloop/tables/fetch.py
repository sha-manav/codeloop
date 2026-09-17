"""`codeloop tables fetch`: download pinned table files into data/tables/raw/ and record hashes."""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from codeloop.ingest.download import DownloadError, fetch_url
from codeloop.ledger import utc_now
from codeloop.tables.config import TablesConfig, load_tables_config, save_tables_config
from codeloop.util.hashing import sha256_file


class TableFetchError(RuntimeError):
    pass


@dataclass
class FetchRecord:
    table: str
    name: str
    path: str
    bytes: int
    sha256: str
    status: str  # "downloaded" | "verified" | "recorded" | "cached"


def raw_dir(root: Path) -> Path:
    return root / "data" / "tables" / "raw"


def member_path(root: Path, table: str, member: str) -> Path:
    return raw_dir(root) / table / Path(member).name


def fetch_tables(
    root: Path, tables_yaml: Path, *, only: set[str] | None = None, update: bool = False
) -> list[FetchRecord]:
    cfg: TablesConfig = load_tables_config(tables_yaml)
    records: list[FetchRecord] = []
    for table, spec in cfg.tables.items():
        if only and table not in only:
            continue
        tdir = raw_dir(root) / table
        tdir.mkdir(parents=True, exist_ok=True)
        for f in spec.files:
            dest = tdir / f.name
            status = "cached"
            if not (dest.exists() and f.sha256 and sha256_file(dest) == f.sha256):
                try:
                    fetch_url(f.url, dest)
                except DownloadError as e:
                    raise TableFetchError(str(e)) from e
                status = "downloaded"
            digest = sha256_file(dest)
            if f.sha256 and digest != f.sha256:
                if not update:
                    raise TableFetchError(
                        f"{table}/{f.name}: sha256 {digest[:16]}… differs from pinned {f.sha256[:16]}… "
                        "(pass --update to re-pin)"
                    )
                status = "re-pinned"
            elif f.sha256:
                status = "verified" if status == "downloaded" else status
            else:
                status = "recorded"
            f.sha256, f.bytes, f.downloaded_at = digest, dest.stat().st_size, f.downloaded_at or utc_now()
            if status in ("downloaded", "re-pinned", "recorded"):
                f.downloaded_at = utc_now()
            if f.members and zipfile.is_zipfile(dest):
                with zipfile.ZipFile(dest) as zf:
                    names = {n.lower(): n for n in zf.namelist()}
                    by_base = {Path(n).name.lower(): n for n in zf.namelist()}
                    for m in f.members:
                        actual = names.get(m.lower()) or by_base.get(Path(m).name.lower())
                        if actual is None:
                            raise TableFetchError(
                                f"{table}/{f.name}: member {m!r} not in archive ({sorted(by_base.values())})"
                            )
                        target = tdir / Path(m).name
                        with zf.open(actual) as src, open(target, "wb") as out:
                            shutil.copyfileobj(src, out)
            records.append(FetchRecord(table, f.name, dest.relative_to(root).as_posix(), f.bytes, digest, status))
    save_tables_config(tables_yaml, cfg)
    return records
