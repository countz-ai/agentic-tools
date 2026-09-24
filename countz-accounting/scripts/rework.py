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

Run with no arguments to self-check.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import pathlib
import shutil
import sys
import tempfile

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


def _fixture(rd: pathlib.Path) -> None:
    import yaml
    from openpyxl import Workbook
    (rd / "checks").mkdir(parents=True)
    (rd / "workpapers").mkdir()
    (rd / "out" / "tabs").mkdir(parents=True)
    (rd / "checks" / "c1.md").write_text(
        "# c1\n\n## Conclusion\n\nLogo churn was measured on the in-force basis.\n\n"
        "## Exceptions\n\nNone.\n", encoding="utf-8")
    (rd / "checks" / "c1-items.csv").write_text(
        "id,class,amount\nX.c1.1,logo churn,100\n", encoding="utf-8")
    (rd / "workpapers" / "figures-c1.yaml").write_text(yaml.safe_dump([
        {"id": "F.c1.churn.fy2025", "label": "Logo churn FY2025", "value": 12.0, "unit": "count"},
        {"id": "F.c1.arr.fy2025", "label": "ARR", "value": 1000.5, "unit": "usd"}],
        sort_keys=False), encoding="utf-8")
    wb = Workbook()
    wb.active["B1"] = "c1 · Logo churn"
    wb.active["B5"] = 12
    wb.save(rd / "out" / "tabs" / "c1.xlsx")


def _selfcheck() -> int:
    bad: list[str] = []

    def refuses(fn, *args, want: str = "") -> None:
        try:
            fn(*args)
            bad.append(f"{getattr(fn, '__name__', fn)}{args[1:] if len(args) > 1 else ''} did not refuse")
        except ReworkRefused as exc:
            if want and want not in str(exc):
                bad.append(f"refusal lacks {want!r}: {exc}")

    with tempfile.TemporaryDirectory() as td:
        rd = pathlib.Path(td) / "run"
        _fixture(rd)
        if [str(p) for p in check_files(rd, "c1")] != [
                "checks/c1.md", "checks/c1-items.csv", "workpapers/figures-c1.yaml",
                "out/tabs/c1.xlsx"]:
            bad.append(f"check_files: {check_files(rd, 'c1')}")
        snap = snapshot(rd, "c1")
        if not (snap / "out/tabs/c1.xlsx").is_file():
            bad.append("snapshot did not copy the tab")
        refuses(snapshot, rd, "nope", want="no files")

        # diff_ledger
        import yaml
        led = rd / "workpapers/figures-c1.yaml"
        doc = yaml.safe_load(led.read_text(encoding="utf-8"))
        doc[1]["value"] = 1001.0
        doc.append({"id": "F.c1.arr.fy2026", "value": 5.0, "unit": "usd"})
        led.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        d = diff_ledger(snap, rd, "c1")
        if [m[0] for m in d["moved"]] != ["F.c1.arr.fy2025"] or d["added"] != ["F.c1.arr.fy2026"] \
                or d["removed"] or d["unchanged"] != 1 or "F.c1.arr" not in d["by_family"]:
            bad.append(f"diff_ledger: {d}")

        # CLI
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc_diff = main(["diff", str(snap), str(rd), "c1"])
            rc_snap = main(["snapshot", str(rd), "nope"])
        if rc_diff != 1:
            bad.append("CLI diff with moved figures did not exit 1")
        if rc_snap != 1:
            bad.append("CLI snapshot of no files did not exit 1")

    for b in bad:
        print("FAIL", b)
    print("rework.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else _selfcheck())
