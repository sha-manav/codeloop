"""Download pinned source files, verify hashes, record what was fetched."""

from __future__ import annotations

import shutil
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from codeloop.config import ProjectConfig, Source
from codeloop.ledger import utc_now
from codeloop.util.hashing import md5_file, sha256_file

USER_AGENT = "codeloop-ingest/0.1"


class DownloadError(RuntimeError):
    pass


@dataclass
class DownloadRecord:
    source: str
    name: str
    url: str
    path: str  # relative to the repo root
    bytes: int
    sha256: str
    md5: str
    fetched_at: str
    expected_md5: str | None = None
    expected_sha256: str | None = None
    split_orig: str | None = None
    role: str | None = None
    partition: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def fetch_url(url: str, dest: Path, *, retries: int = 3, timeout: int = 180) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as out:
                shutil.copyfileobj(resp, out)
            return
        except (urllib.error.URLError, OSError) as e:  # includes HTTPError and timeouts
            last = e
            if attempt < retries:
                time.sleep(2 * attempt)
    raise DownloadError(f"failed to download {url}: {last}")


def verify_hashes(path: Path, expected_md5: str | None, expected_sha256: str | None) -> None:
    if expected_md5 and md5_file(path) != expected_md5.lower():
        raise DownloadError(f"{path.name}: md5 mismatch (expected {expected_md5})")
    if expected_sha256 and sha256_file(path) != expected_sha256.lower():
        raise DownloadError(f"{path.name}: sha256 mismatch (expected {expected_sha256})")


def _record(source_id: str, name: str, url: str, path: Path, root: Path, **extra) -> DownloadRecord:
    return DownloadRecord(
        source=source_id,
        name=name,
        url=url,
        path=path.relative_to(root).as_posix(),
        bytes=path.stat().st_size,
        sha256=sha256_file(path),
        md5=md5_file(path),
        fetched_at=utc_now(),
        **extra,
    )


def download_source(source_id: str, source: Source, raw_dir: Path, root: Path) -> list[DownloadRecord]:
    out: list[DownloadRecord] = []
    sdir = raw_dir / source_id
    sdir.mkdir(parents=True, exist_ok=True)
    for f in source.files:
        dest = sdir / f.name
        fetch_url(f.url, dest)
        verify_hashes(dest, f.expected_md5, f.expected_sha256)
        out.append(
            _record(
                source_id, f.name, f.url, dest, root,
                expected_md5=f.expected_md5, expected_sha256=f.expected_sha256,
                split_orig=f.split_orig, role=f.role or ("archive" if f.kind == "zip" else None),
                partition=f.partition,
            )
        )
        if f.kind == "zip":
            with zipfile.ZipFile(dest) as zf:
                names = set(zf.namelist())
                for m in f.members:
                    if m.member not in names:
                        raise DownloadError(f"{f.name}: member {m.member} not in archive")
                    target = sdir / Path(m.member).name
                    with zf.open(m.member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    out.append(
                        _record(
                            source_id, target.name, f"{f.url}#{m.member}", target, root,
                            split_orig=m.split_orig, role="member",
                        )
                    )
    return out


def download_all(config: ProjectConfig, raw_dir: Path, root: Path) -> list[DownloadRecord]:
    records: list[DownloadRecord] = []
    for source_id, source in config.sources.items():
        records.extend(download_source(source_id, source, raw_dir, root))
    return records
