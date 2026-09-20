"""Copy a review event store off the Fly volume without `fly ssh` (which needs a working WireGuard tunnel).

    python scripts/fly_pull_events.py --batch batch2 --version v1 [--app codeloop-ui] [--machine ID]

Runs a small read-only snippet on the machine through the Machines API (`fly machine exec`): it serializes a
consistent snapshot of the SQLite database in memory (nothing is written on the machine), and prints its SHA-256 and
the gzip+base64 of the bytes. The copy is verified against that checksum and `PRAGMA integrity_check` before it
replaces runs/<version>/<batch>/events.sqlite. Events hold codes, refs, reasons, grades and timestamps; no encounter
text. Prints counts and hashes only.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

REMOTE = """
import base64, gzip, hashlib, sqlite3, sys
c = sqlite3.connect("file:/data/events/{name}.sqlite?mode=ro", uri=True)
raw = c.serialize()
body = base64.b64encode(gzip.compress(raw, 9)).decode()
sys.stdout.write("BEGIN:" + hashlib.sha256(raw).hexdigest() + ":" + str(len(raw)) + ":" + body + ":END")
"""


def fly(*args: str, timeout: int = 180) -> str:
    out = subprocess.run(["fly", *args], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        sys.exit(f"fly {' '.join(args[:3])} failed: {out.stderr.strip()[:300]}")
    return out.stdout


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--batch", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--app", default="codeloop-ui")
    ap.add_argument("--machine", default=None, help="machine id (default: the app's first machine)")
    ap.add_argument("--root", default=".", help="repository root")
    a = ap.parse_args()
    machine = a.machine or json.loads(fly("machines", "list", "-a", a.app, "--json"))[0]["id"]
    snippet = base64.b64encode(REMOTE.format(name=f"{a.version}_{a.batch}").encode()).decode()
    raw_out = fly("machine", "exec", machine, f"sh -c 'echo {snippet} | base64 -d | /opt/venv/bin/python'", "-a", a.app)
    m = re.search(r"BEGIN:([0-9a-f]{64}):(\d+):([A-Za-z0-9+/=\s]+):END", raw_out)
    if not m:
        sys.exit("no payload in the machine's output (is the store there? " + raw_out.strip()[:200] + ")")
    want, size = m.group(1), int(m.group(2))
    raw = gzip.decompress(base64.b64decode(re.sub(r"\s+", "", m.group(3))))
    got = hashlib.sha256(raw).hexdigest()
    if len(raw) != size or got != want:
        sys.exit(f"checksum mismatch: got {got} ({len(raw)} bytes), machine reported {want} ({size} bytes)")
    dest = Path(a.root) / "runs" / a.version / a.batch / "events.sqlite"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(".pull.sqlite")
    tmp.write_bytes(raw)
    conn = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
    try:
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        n, last = conn.execute("SELECT count(*), max(ts) FROM events").fetchone()
        approved = conn.execute("SELECT count(DISTINCT encounter_id) FROM events WHERE type = 'approve'").fetchone()[0]
    finally:
        conn.close()
    if ok != "ok":
        tmp.unlink()
        sys.exit(f"integrity_check: {ok}")
    tmp.replace(dest)
    print(f"{dest}: {size} bytes, sha256 {got}, {n} events (last {last}), {approved} encounters approved, integrity ok")


if __name__ == "__main__":
    main()
