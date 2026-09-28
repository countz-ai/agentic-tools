#!/usr/bin/env python3
"""A fix pass over a check's own files, as one importable module: snapshot the check before
touching it, and state afterwards what moved in its figures ledger. Edit the files
yourself between the snapshot and the diff.

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from rework import snapshot, diff_ledger

    snap = snapshot(RUN, "a5_bridge")            # rework/a5_bridge/<UTC stamp>/, a copy
    d = diff_ledger(snap, RUN, "a5_bridge")      # {"moved": [...], "added": [...], ...}

**The check's files** are the ones `step_record.py` counts as produced: `checks/<check>.md`,
`checks/<check>-*.csv`, `workpapers/*-<check>.yaml`, `out/tabs/<check>.xlsx`.

Command line:

    rework.py snapshot <run_dir> <check>
    rework.py diff <prior_dir> <run_dir> <check>
"""
from __future__ import annotations

import datetime as dt
import json
import math
import pathlib
import shutil
import sys

__all__ = ["snapshot", "check_files", "diff_ledger", "ReworkRefused"]


class ReworkRefused(RuntimeError):
    """A fix operation refused; nothing was written."""


def check_files(run_dir, check: str) -> list[pathlib.Path]:
    """The check's own files that exist, relative to the run directory."""
    rd = pathlib.Path(run_dir)
    pats = [f"checks/{check}.md", f"checks/{check}-*.csv", f"workpapers/*-{check}.yaml",
            f"out/tabs/{check}.xlsx"]
    out: list[pathlib.Path] = []
    for pat in pats:
        out.extend(p.relative_to(rd) for p in sorted(rd.glob(pat)) if p.is_file())
    return out


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def snapshot(run_dir, check: str) -> pathlib.Path:
    """Copy the check's files to `<run_dir>/rework/<check>/<UTC stamp>/`, keeping their
    paths; returns that directory. A check with no files is refused."""
    rd = pathlib.Path(run_dir)
    files = check_files(rd, check)
    if not files:
        raise ReworkRefused(f"snapshot: {check!r} has no files under {rd} to snapshot")
    dest = rd / "rework" / check / _stamp()
    for rel in files:
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rd / rel, dest / rel)
    return dest


def _figures(where, check: str | None) -> dict:
    """{id: entry} from a FigureSet/dict, or from the figures ledgers under a run or
    snapshot directory (`workpapers/figures-<check>.yaml`, all of them when check is None)."""
    if isinstance(where, dict):
        return dict(where)
    import yaml
    wp = pathlib.Path(where) / "workpapers"
    names = sorted(wp.glob("figures-*.yaml")) if check is None else [wp / f"figures-{check}.yaml"]
    out: dict = {}
    for f in names:
        if not f.is_file():
            continue
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or []
        for e in doc if isinstance(doc, list) else []:
            if isinstance(e, dict) and isinstance(e.get("id"), str):
                out.setdefault(e["id"], e)
    return out


def _family(fid: str) -> str:
    parts = fid.split(".")
    return ".".join(parts[:-1]) if len(parts) >= 4 else fid


def _same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        if math.isnan(a) and math.isnan(b):
            return True
        return math.isclose(a, b, rel_tol=0, abs_tol=1e-9)
    return a == b


def diff_ledger(prior, new, check: str | None = None) -> dict:
    """What a fix pass did to the figures: `moved` [(id, old, new)] — a value or unit that
    changed — `added` and `removed` ids, `unchanged` (a count), and `by_family`, the same
    grouped by id family (the id less its last segment: `F.a5.nrr` for `F.a5.nrr.fy2025`).
    `prior` and `new` are run or snapshot directories, or {id: entry} mappings."""
    a, b = _figures(prior, check), _figures(new, check)
    moved, unchanged = [], 0
    for fid in sorted(a.keys() & b.keys()):
        ea, eb = a[fid], b[fid]
        if _same(ea.get("value"), eb.get("value")) and ea.get("unit") == eb.get("unit"):
            unchanged += 1
        else:
            moved.append((fid, ea.get("value"), eb.get("value")))
    added, removed = sorted(b.keys() - a.keys()), sorted(a.keys() - b.keys())
    fam: dict[str, dict] = {}
    for kind, ids in (("moved", [m[0] for m in moved]), ("added", added), ("removed", removed)):
        for fid in ids:
            fam.setdefault(_family(fid), {"moved": [], "added": [], "removed": []})[kind].append(fid)
    return {"moved": moved, "added": added, "removed": removed, "unchanged": unchanged,
            "by_family": fam, "clean": not (moved or added or removed)}


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="rework.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("run_dir")
    s.add_argument("check")
    d = sub.add_parser("diff")
    d.add_argument("prior")
    d.add_argument("run_dir")
    d.add_argument("check")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "snapshot":
            print(snapshot(a.run_dir, a.check))
        else:
            out = diff_ledger(a.prior, a.run_dir, a.check)
            print(json.dumps(out, indent=2, default=str))
            return 0 if out["clean"] else 1
    except ReworkRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
