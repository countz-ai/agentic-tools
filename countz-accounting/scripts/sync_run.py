#!/usr/bin/env python3
"""Sync a run home - the whole run directory, never a chosen subset.

Three modes:

    sync_run.py <run_dir>                       refresh <run_dir>/out/run_sync.tar.gz
    sync_run.py <run_dir> --dest <result_root>  copy the run to <result_root>/<name>.<stamp>/
    sync_run.py <archive.tar.gz> --dest <result_root>
                                                land a pulled archive at the same layout

The third mode is the receiving side of the first: an archive pulled off a cloud
container lands whole at `<result_root>/<name>.<stamp>/`, where the top folder - name,
stamp and all - comes from the archive itself, so `--name` is refused there. It refuses
a target that already exists and an archive that is not a single-folder run archive.

Either way the run travels whole under one top-level folder `<name>.<stamp>` - `--name`
overrides the short name, which defaults to the run directory's own (`<skill>-<company>`
from a minted `run_id`, so the copy is recognisably the same run), then to the run's
goal; the stamp is UTC
`YYYYMMDD-HHMMSS` - with a `sync.json` at its top recording the run id, every session id
from `run.json.inputs.sessions`, the plugin name and version the run executed under, the
source path and the sync time. The session ids are
what `usage_report.py` prices a run from and what locate the session that produced the
run when a result needs triage or resuming; `sync.json` puts them where a reader finds
them without opening the state file.

The run's own code comes back with the data - run-local code and scripts, `dispatch/`
(each sub-agent's entire launch instruction), `events.jsonl`, `steps/*.json`,
`out/usage.json`: what a later performance analysis reads, none of it recoverable from
the deliverable alone. `sync.json` also carries `plugin_executed` - the version and tree
digest of the plugin the run registered under, so a triage reads a finished run against
the instructions that produced it rather than the checkout on its own disk. Excluded:
`__pycache__/`, `*.pyc`, `*.tmp`, `.DS_Store`, and the archive itself.

`--transcripts` additionally copies each session's `.jsonl` into `<run>/transcripts/`. It
is the only record of which instruction files a worker opened. It carries client data, so
it is opt-in: pass it on a debug run, not on a client sync.

Stdlib only. Exit 0 on success, 2 on refusal (no run.json; --dest target already exists).
"""
from __future__ import annotations

import argparse
import fnmatch
import io
import json
import os
import pathlib
import re
import shutil
import sys
import tarfile
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from setup_run import slug  # noqa: E402  sibling: the one slug rule

ARCHIVE_NAME = "run_sync.tar.gz"
EXCLUDE_DIRS = {"__pycache__"}
# `<run_dir>/cache/` is the extract step's typed copy of the data room (the file table in
# RUN_CONTRACT.md): rebuilt by re-running the extract step's script, cited by nothing, and
# the size of the room. Skipped at the run root only.
EXCLUDE_ROOT_DIRS = {"cache"}
EXCLUDE_FILES = ("*.pyc", "*.tmp", ".DS_Store")


def _excluded(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_FILES)


def _slug(text: str) -> str:
    """setup_run.py's slug (accents folded, a non-Latin name to `co-<hash>`), so a synced
    copy is named as its run directory is."""
    return slug(text) or "run"


def _short_name(run: dict) -> str | None:
    """`<skill>-<company>` from a minted run_id (`<skill>-<company>.<YYYYMMDD-HHMMSS>`)."""
    m = re.fullmatch(r"(.+)\.\d{8}-\d{6}", str(run.get("run_id") or ""))
    return m.group(1) if m else None


def _plugin() -> dict:
    # This script ships at <plugin>/scripts/, so the manifest beside it names the plugin
    # version the run executed under - the one fact a synced run cannot recover later.
    pj = pathlib.Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
    try:
        doc = json.loads(pj.read_text(encoding="utf-8"))
        return {"name": doc.get("name"), "version": doc.get("version")}
    except Exception:
        return {"name": None, "version": None}


def _manifest(run: dict, run_dir: pathlib.Path, top: str, now_iso: str) -> bytes:
    doc = {
        "schema": "run-sync@1",
        "name": top,
        "synced_at": now_iso,
        "source_run_dir": str(run_dir),
        "plugin": _plugin(),
        # The plugin the run actually EXECUTED under, stamped at registration. A triage
        # compares this tree digest with the checkout it is reading; they differ, the
        # instructions differed, and `files` in run.json names which.
        "plugin_executed": {k: v for k, v in (run.get("plugin") or {}).items()
                            if k != "files"},
        "run_schema": run.get("schema"),
        "run_id": run.get("run_id"),
        "goal": run.get("goal"),
        "sessions": (run.get("inputs") or {}).get("sessions") or [],
    }
    return (json.dumps(doc, indent=2) + "\n").encode()


def _collect_transcripts(run: dict, run_dir: pathlib.Path) -> int:
    """Copy this run's session transcripts into <run_dir>/transcripts/.

    Claude Code writes one `<session_id>.jsonl` per session under ~/.claude/projects/<cwd
    slug>/ and ~/.claude/traces/. Nothing under the run directory records which instruction
    files a worker opened, so without these a question like "did the report worker read
    REPORT.md § 3" has no answer after the fact."""
    ids = [s.get("session_id") for s in ((run.get("inputs") or {}).get("sessions") or [])
           if s.get("session_id")]
    if not ids:
        return 0
    dest = run_dir / "transcripts"
    dest.mkdir(exist_ok=True)
    n = 0
    home = pathlib.Path.home() / ".claude"
    if not (home / "projects").is_dir() and not (home / "traces").is_dir():
        print(f"sync_run: no transcript directory under {home} - this host keeps session "
              f"transcripts elsewhere (or not at all); none copied, which is not the same "
              f"as none existing", file=sys.stderr)
        return 0
    for sid in ids:
        for src in list(home.glob(f"projects/*/{sid}.jsonl")) + list(
                home.glob(f"traces/{sid}.jsonl")):
            out = dest / f"{src.parent.name}-{src.name}"
            if not out.exists():
                shutil.copy2(src, out)
                n += 1
    return n


def _walk_files(run_dir: pathlib.Path, skip: set):
    for dirpath, dirnames, filenames in os.walk(run_dir):
        at_root = pathlib.Path(dirpath) == pathlib.Path(run_dir)
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS
                             and not (at_root and d in EXCLUDE_ROOT_DIRS))
        for fn in sorted(filenames):
            p = pathlib.Path(dirpath) / fn
            if _excluded(fn) or p in skip:
                continue
            yield p


def _land(archive: pathlib.Path, dest: str | None, name: str | None) -> int:
    if not dest:
        print("sync_run: landing an archive needs --dest <result_root>", file=sys.stderr)
        return 2
    if name:
        print("sync_run: --name does not apply to an archive - its top folder already "
              "carries the name and stamp", file=sys.stderr)
        return 2
    try:
        tar = tarfile.open(archive, "r:gz")
    except Exception as exc:
        print(f"sync_run: {archive} did not open as a tar.gz ({exc})", file=sys.stderr)
        return 2
    with tar:
        names = tar.getnames()
        tops = {n.split("/", 1)[0] for n in names}
        if len(tops) != 1 or any(n.startswith("/") or ".." in n.split("/")
                                 for n in names):
            print(f"sync_run: {archive} is not a single-folder run archive",
                  file=sys.stderr)
            return 2
        top = tops.pop()
        if f"{top}/run.json" not in names:
            print(f"sync_run: {archive} carries no {top}/run.json - not a run archive",
                  file=sys.stderr)
            return 2
        dest_root = pathlib.Path(dest).expanduser().resolve()
        target = dest_root / top
        if target.exists():
            print(f"sync_run: {target} already exists - refusing to overwrite",
                  file=sys.stderr)
            return 2
        dest_root.mkdir(parents=True, exist_ok=True)
        try:
            tar.extractall(dest_root, filter="data")
        except TypeError:  # Python without extraction filters; names checked above
            tar.extractall(dest_root)
    print(f"LANDED:\t{target}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sync a run home - the whole run directory, never a chosen subset.")
    ap.add_argument("run_dir", metavar="run_dir|archive.tar.gz")
    ap.add_argument("--dest", help="result root to copy or land the run into")
    ap.add_argument("--name",
                    help="short name for the synced copy (default: the run's goal)")
    ap.add_argument("--transcripts", action="store_true",
                    help="also copy each session transcript into <run>/transcripts/ before "
                         "syncing - the only record of which instruction files a worker "
                         "read. Carries client data, so it is opt-in and for a debug run")
    a = ap.parse_args()

    run_dir = pathlib.Path(a.run_dir).expanduser().resolve()
    if run_dir.is_file():
        return _land(run_dir, a.dest, a.name)
    run_json = run_dir / "run.json"
    if not run_json.is_file():
        print(f"sync_run: {run_dir} carries no run.json - not a run directory",
              file=sys.stderr)
        return 2
    try:
        run = json.loads(run_json.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"sync_run: {run_json} did not parse ({exc}) - syncing with an empty "
              f"manifest", file=sys.stderr)
        run = {}

    if a.transcripts:
        n = _collect_transcripts(run, run_dir)
        print(f"transcripts:\t{n} copied into {run_dir / 'transcripts'}")

    now = datetime.now(timezone.utc)
    short = a.name or _short_name(run) or run.get("goal") or "run"
    top = f"{_slug(short)}.{now.strftime('%Y%m%d-%H%M%S')}"
    manifest = _manifest(run, run_dir, top, now.isoformat(timespec="seconds"))

    if a.dest:
        dest_root = pathlib.Path(a.dest).expanduser().resolve()
        target = dest_root / top
        if target.exists():
            print(f"sync_run: {target} already exists - refusing to overwrite",
                  file=sys.stderr)
            return 2
        archive_dir = run_dir / "out"

        def ignore(dirpath, names):
            out = [n for n in names if n in EXCLUDE_DIRS or _excluded(n)]
            if pathlib.Path(dirpath) == archive_dir:
                out.append(ARCHIVE_NAME)
            return out

        shutil.copytree(run_dir, target, symlinks=True, ignore=ignore)
        (target / "sync.json").write_bytes(manifest)
        print(f"SYNCED:\t{target}")
        return 0

    out_dir = run_dir / "out"
    out_dir.mkdir(exist_ok=True)
    final = out_dir / ARCHIVE_NAME
    tmp = out_dir / (ARCHIVE_NAME + ".tmp")  # *.tmp, so the walk's pattern skips it too
    with tarfile.open(tmp, "w:gz") as tar:
        info = tarfile.TarInfo(f"{top}/sync.json")
        info.size = len(manifest)
        info.mtime = int(now.timestamp())
        tar.addfile(info, io.BytesIO(manifest))
        for p in _walk_files(run_dir, skip={final, tmp}):
            tar.add(p, arcname=f"{top}/{p.relative_to(run_dir)}", recursive=False)
    tmp.replace(final)
    print(f"ARCHIVE:\t{final}")
    print(f"EXTRACT:\ttar -xzf {ARCHIVE_NAME} -C <result_root>    "
          f"# lands at <result_root>/{top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
