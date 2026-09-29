#!/usr/bin/env python3
"""A fix pass over a check's own files, as one importable module: snapshot the check before
touching it, and state afterwards what moved in its figures ledger. Edit the files
yourself between the snapshot and the diff.

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from rework import snapshot, diff_ledger

    snap = snapshot(RUN, "a5_bridge")            # rework/a5_bridge/<UTC stamp>/, a copy
    d = diff_ledger(snap, RUN, "a5_bridge")      # {"moved": [...], "added": [...], ...}

**The check's files** are the ones `step_record.py` counts as produced (`own_files`):
`checks/<check>.md`, `checks/<check>-*.csv`, `workpapers/figures-<check>.yaml`,
`workpapers/evidence-<check>.yaml`, `out/tabs/<check>.xlsx`. A check id is
`check_playbook.CHECK_ID` (`[a-z0-9][a-z0-9_]*`); any other is refused.

**Refusals** raise ReworkRefused and write nothing: a check id outside CHECK_ID; a
snapshot of a check with no files, or one whose copy fails part-way (the partial copy is
removed); a diff side that is a path but not a directory; a diff where neither side
holds a figures ledger (so a mistyped check id is refused); a ledger that does not parse,
is not a YAML list, or holds an entry that is not a mapping with a text `id`; and an id
declared twice, within one ledger or, when `check` is None, across ledgers (EVIDENCE.md
§ 0 gives the same quantity one id in every check: diff such checks one at a time). A
ledger is read with PyYAML (YAML 1.1, e.g. `010` is 8 and `1e3` is text).

Command line (exit 0 clean, 1 something moved, 2 refused):

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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_playbook  # noqa: E402  sibling: CHECK_ID, the check-id grammar
import step_record  # noqa: E402  sibling: own_files, the one list of a check's files

__all__ = ["snapshot", "check_files", "diff_ledger", "ReworkRefused"]


class ReworkRefused(RuntimeError):
    """A fix operation refused; nothing was written."""


def _check_id(check) -> str:
    if not isinstance(check, str) or not check_playbook.CHECK_ID.fullmatch(check):
        raise ReworkRefused(f"check id {check!r} is not a check id ([a-z0-9][a-z0-9_]*, no "
                            f"`-`: a `-` in it would name another check's files)")
    return check


def check_files(run_dir, check: str) -> list[pathlib.Path]:
    """The check's own files that exist, relative to the run directory, in
    `step_record.own_files` order. Refuses a check id outside CHECK_ID."""
    rd = pathlib.Path(run_dir)
    return [p.relative_to(rd) for p in step_record.own_files(rd, _check_id(check))]


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def snapshot(run_dir, check: str) -> pathlib.Path:
    """Copy the check's files to `<run_dir>/rework/<check>/<UTC stamp>/`, keeping their
    paths; returns that directory, absolute. The copy lands whole or not at all: it is
    made beside the destination and renamed into place. A check with no files is refused."""
    rd = pathlib.Path(run_dir).resolve()
    files = check_files(rd, check)
    if not files:
        raise ReworkRefused(f"snapshot: {check!r} has no files under {rd} to snapshot")
    stamp = _stamp()
    dest = rd / "rework" / check / stamp
    tmp = rd / "rework" / check / f".{stamp}.tmp"
    try:
        for rel in files:
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rd / rel, tmp / rel)
        if dest.exists():
            raise FileExistsError(f"{dest} exists")
        tmp.rename(dest)
    except OSError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ReworkRefused(f"snapshot: {exc} - nothing was kept") from None
    return dest


def _load(f: pathlib.Path) -> list[dict]:
    import yaml
    try:
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise ReworkRefused(f"{f}: does not parse: {str(exc).splitlines()[0]}") from None
    if doc is None:
        return []
    if not isinstance(doc, list):
        raise ReworkRefused(f"{f}: the ledger is not a YAML list (EVIDENCE.md § 0)")
    for n, e in enumerate(doc, 1):
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not e["id"]:
            raise ReworkRefused(f"{f}: entry {n} is not a mapping with a text `id`")
    return doc


def _figures(where, check: str | None) -> tuple[dict, bool]:
    """({id: entry}, whether any ledger was found) from a FigureSet/dict, or from the
    figures ledgers under a run or snapshot directory (`workpapers/figures-<check>.yaml`,
    all of them when check is None). Refuses an id declared twice."""
    if isinstance(where, dict):
        return dict(where), True
    root = pathlib.Path(where)
    if not root.is_dir():
        raise ReworkRefused(f"{root}: not a directory - a diff side is a run or snapshot "
                            f"directory, or an {{id: entry}} mapping")
    wp = root / "workpapers"
    names = sorted(wp.glob("figures-*.yaml")) if check is None else [wp / f"figures-{check}.yaml"]
    names = [f for f in names if f.is_file()]
    out: dict = {}
    seen: dict[str, str] = {}
    for f in names:
        for e in _load(f):
            if e["id"] in seen:
                raise ReworkRefused(f"{e['id']} is declared in {seen[e['id']]} and {f.name} - "
                                    f"one entry per id per ledger; across ledgers, diff one "
                                    f"check at a time")
            seen[e["id"]] = f.name
            out[e["id"]] = e
    return out, bool(names)


def _family(fid: str) -> str:
    parts = fid.split(".")
    return ".".join(parts[:-1]) if len(parts) >= 4 else fid


def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if math.isnan(a) and math.isnan(b):
            return True
        return math.isclose(a, b, rel_tol=0, abs_tol=1e-9)
    return a == b


def diff_ledger(prior, new, check: str | None = None) -> dict:
    """What a fix pass did to the figures: `moved` [(id, old, new)] (a value or unit that
    changed, the values as stated) with `units` [(id, old unit, new unit)] for the ones
    whose unit changed; `added` and `removed` ids; `unchanged` (a count); `by_family`, the
    moved, added and removed ids grouped by id family (an id of four or more segments less
    its last, `F.a5.nrr` for `F.a5.nrr.fy2025`; a shorter id is its own family); and
    `clean`, true when nothing moved, was added or was removed. A boolean never equals a
    number. `prior` and `new` are run or snapshot directories, or {id: entry} mappings;
    with `check` None every ledger on each side is compared, so a snapshot of one check
    against a run shows the others' figures as added. Refusals: the module docstring."""
    if check is not None:
        _check_id(check)
    (a, found_a), (b, found_b) = _figures(prior, check), _figures(new, check)
    if not (found_a or found_b):
        want = f"workpapers/figures-{check}.yaml" if check else "workpapers/figures-*.yaml"
        raise ReworkRefused(f"neither {prior} nor {new} holds {want} - nothing to compare "
                            f"(is the check id right?)")
    moved, units, unchanged = [], [], 0
    for fid in sorted(a.keys() & b.keys()):
        ea, eb = a[fid], b[fid]
        same_unit = ea.get("unit") == eb.get("unit")
        if _same(ea.get("value"), eb.get("value")) and same_unit:
            unchanged += 1
            continue
        moved.append((fid, ea.get("value"), eb.get("value")))
        if not same_unit:
            units.append((fid, ea.get("unit"), eb.get("unit")))
    added, removed = sorted(b.keys() - a.keys()), sorted(a.keys() - b.keys())
    fam: dict[str, dict] = {}
    for kind, ids in (("moved", [m[0] for m in moved]), ("added", added), ("removed", removed)):
        for fid in ids:
            fam.setdefault(_family(fid), {"moved": [], "added": [], "removed": []})[kind].append(fid)
    return {"moved": moved, "units": units, "added": added, "removed": removed,
            "unchanged": unchanged, "by_family": fam,
            "clean": not (moved or added or removed)}


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
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
