"""Copy the Phase 9 holdout labels (ciphertext) and the holdout event store off the codeloop-holdout volume.

    python scripts/fly_pull_holdout.py [--app codeloop-holdout] [--machine ID] [--root .]

Runs a read-only snippet on the machine through the Machines API (`fly machine exec`): for each file it prints the
SHA-256, the size and the gzip+base64 of the bytes; the copy is verified against the checksum before it is written.
Destinations: data/sealed/holdout_labels.enc (+ .meta.json) and data/sealed/holdout_events.sqlite. Nothing is
decrypted and no content is printed: sizes, hashes and counts only.
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

FILES = ("holdout_labels.enc", "holdout_labels.enc.meta.json", "holdout_events.sqlite")

REMOTE = """
import base64, gzip, hashlib, sqlite3, sys
name = "{name}"
path = "/data/sealed/" + name
if name.endswith(".sqlite"):
    raw = sqlite3.connect("file:" + path + "?mode=ro", uri=True).serialize()
else:
    raw = open(path, "rb").read()
sys.stdout.write("BEGIN:" + hashlib.sha256(raw).hexdigest() + ":" + str(len(raw)) + ":"
                 + base64.b64encode(gzip.compress(raw, 9)).decode() + ":END")
"""


def fly(*args: str, timeout: int = 180) -> str:
    out = subprocess.run(["fly", *args], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        sys.exit(f"fly {' '.join(args[:3])} failed: {out.stderr.strip()[:300]}")
    return out.stdout


def pull(app: str, machine: str, name: str) -> bytes:
    snippet = base64.b64encode(REMOTE.format(name=name).encode()).decode()
    raw_out = fly("machine", "exec", machine, f"sh -c 'echo {snippet} | base64 -d | /opt/venv/bin/python'", "-a", app)
    m = re.search(r"BEGIN:([0-9a-f]{64}):(\d+):([A-Za-z0-9+/=\s]+):END", raw_out)
    if not m:
        sys.exit(f"{name}: no payload in the machine's output (is the file there?)")
    want, size = m.group(1), int(m.group(2))
    raw = gzip.decompress(base64.b64decode(re.sub(r"\s+", "", m.group(3))))
    got = hashlib.sha256(raw).hexdigest()
    if len(raw) != size or got != want:
        sys.exit(f"{name}: checksum mismatch (got {got}, machine reported {want})")
    print(f"{name}: {size} bytes, sha256 {got}")
    return raw


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--app", default="codeloop-holdout")
    ap.add_argument("--machine", default=None)
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    machine = a.machine or json.loads(fly("machines", "list", "-a", a.app, "--json"))[0]["id"]
    sealed = Path(a.root) / "data" / "sealed"
    sealed.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        raw = pull(a.app, machine, name)
        dest = sealed / name
        if dest.exists() and dest.read_bytes() == raw:
            print(f"{name}: unchanged")
            continue
        tmp = dest.with_name("." + name + ".pull")
        tmp.write_bytes(raw)
        if name.endswith(".sqlite"):
            conn = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
            try:
                ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
                n = conn.execute("SELECT count(*) FROM events").fetchone()[0]
                labeled = conn.execute(
                    "SELECT count(DISTINCT encounter_id) FROM events WHERE type='blind_submit'"
                ).fetchone()[0]
            finally:
                conn.close()
            if ok != "ok":
                tmp.unlink()
                sys.exit(f"{name}: integrity_check {ok}")
            print(f"{name}: {n} events, {labeled} encounters labeled, integrity ok")
        tmp.replace(dest)
    print(f"written under {sealed}")


if __name__ == "__main__":
    main()
