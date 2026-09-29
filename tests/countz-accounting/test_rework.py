#!/usr/bin/env python3
"""Self-test for scripts/rework.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_rework.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import contextlib
import io
import os
import pathlib
import sys
import tempfile

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from rework import ReworkRefused, check_files, diff_ledger, snapshot, main as cli  # noqa: E402


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


def _ledger(rd: pathlib.Path, check: str, entries) -> None:
    import yaml
    (rd / "workpapers").mkdir(parents=True, exist_ok=True)
    (rd / "workpapers" / f"figures-{check}.yaml").write_text(
        entries if isinstance(entries, str) else yaml.safe_dump(entries, sort_keys=False),
        encoding="utf-8")


def _cli(argv: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return cli(argv)


def main() -> int:
    bad: list[str] = []

    def refuses(fn, *args, want: str = "") -> None:
        try:
            fn(*args)
            bad.append(f"{getattr(fn, '__name__', fn)}{args[1:] if len(args) > 1 else ''} did not refuse")
        except ReworkRefused as exc:
            if want and want not in str(exc):
                bad.append(f"refusal lacks {want!r}: {exc}")

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td).resolve()
        rd = td / "run"
        _fixture(rd)
        if [str(p) for p in check_files(rd, "c1")] != [
                "checks/c1.md", "checks/c1-items.csv", "workpapers/figures-c1.yaml",
                "out/tabs/c1.xlsx"]:
            bad.append(f"check_files: {check_files(rd, 'c1')}")
        snap = snapshot(rd, "c1")
        if not (snap / "out/tabs/c1.xlsx").is_file() or not snap.is_absolute():
            bad.append("snapshot did not copy the tab")
        refuses(snapshot, rd, "nope", want="no files")

        # a check id is CHECK_ID; a check's workpapers are named, not globbed by suffix
        (rd / "workpapers" / "figures-a5-c1.yaml").write_text("[]\n", encoding="utf-8")
        (rd / "workpapers" / "notes-c1.yaml").write_text("[]\n", encoding="utf-8")
        (rd / "workpapers" / "evidence-c1.yaml").write_text("[]\n", encoding="utf-8")
        if "workpapers/evidence-c1.yaml" not in [str(p) for p in check_files(rd, "c1")] or \
                any("a5-c1" in str(p) or "notes" in str(p) for p in check_files(rd, "c1")):
            bad.append(f"check_files globbed another file: {check_files(rd, 'c1')}")
        (rd / "workpapers" / "evidence-c1.yaml").unlink()
        for fn, args in ((check_files, (rd, "a5-c1")), (snapshot, (rd, "a5-c1")),
                         (diff_ledger, (snap, rd, "a5-c1"))):
            refuses(fn, *args, want="check id")

        # diff_ledger
        import yaml
        led = rd / "workpapers/figures-c1.yaml"
        doc = yaml.safe_load(led.read_text(encoding="utf-8"))
        doc[1]["value"] = 1001.0
        doc.append({"id": "F.c1.arr.fy2026", "value": 5.0, "unit": "usd"})
        led.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        d = diff_ledger(snap, rd, "c1")
        if [m[0] for m in d["moved"]] != ["F.c1.arr.fy2025"] or d["added"] != ["F.c1.arr.fy2026"] \
                or d["removed"] or d["unchanged"] != 1 or "F.c1.arr" not in d["by_family"] \
                or d["units"] or d["clean"]:
            bad.append(f"diff_ledger: {d}")

        # a mistyped check id or a missing side is refused, never `clean`
        refuses(diff_ledger, snap, rd, "c1_typo", want="nothing to compare")
        refuses(diff_ledger, td / "no-such-dir", rd, "c1", want="not a directory")
        fresh = td / "fresh"
        fresh.mkdir()
        if diff_ledger(fresh, rd, "c1")["added"] != sorted(x["id"] for x in doc):
            bad.append("a side with no ledger (the check had none before) is all added")

        # the same id in two checks: check=None refuses; one check at a time works
        r1, r2 = td / "r1", td / "r2"
        for r, bval in ((r1, 100.0), (r2, 999.0)):
            _ledger(r, "a", [{"id": "F.x.arr.fy2025", "value": 100.0, "unit": "usd"}])
            _ledger(r, "b", [{"id": "F.x.arr.fy2025", "value": bval, "unit": "usd"}])
        refuses(diff_ledger, r1, r2, want="diff one check at a time")
        if [m[0] for m in diff_ledger(r1, r2, "b")["moved"]] != ["F.x.arr.fy2025"] \
                or not diff_ledger(r1, r2, "a")["clean"]:
            bad.append("a per-check diff of a shared id did not see b's move")
        _ledger(r2, "a", [{"id": "F.x.v.y", "value": 1.0}, {"id": "F.x.v.y", "value": 2.0}])
        refuses(diff_ledger, r1, r2, "a", want="declared in")
        for text in ("F.x.v.y: {value: 1}\n", "- id: F.x.v.y\n  value: [1\n", "- value: 3\n",
                     "- id: 12\n  value: 3\n"):
            _ledger(r2, "a", text)
            refuses(diff_ledger, r1, r2, "a")

        # units, booleans and ints: what moved is visible
        _ledger(r1, "c", [{"id": "F.c.n.fy2025", "value": 12, "unit": "count"},
                          {"id": "F.c.flag", "value": 1}, {"id": "F.c.k.x", "value": 12}])
        _ledger(r2, "c", [{"id": "F.c.n.fy2025", "value": 12, "unit": "usd"},
                          {"id": "F.c.flag", "value": True}, {"id": "F.c.k.x", "value": 12.0}])
        d = diff_ledger(r1, r2, "c")
        if d["units"] != [("F.c.n.fy2025", "count", "usd")] or \
                [m[0] for m in d["moved"]] != ["F.c.flag", "F.c.n.fy2025"] or d["unchanged"] != 1:
            bad.append(f"units/booleans: {d}")
        if set(d["by_family"]) != {"F.c.flag", "F.c.n"}:
            bad.append(f"families: {d['by_family']}")

        # a snapshot lands whole or not at all
        if getattr(os, "geteuid", lambda: 0)() != 0:
            (rd / "out" / "tabs" / "c1.xlsx").chmod(0)
            before = sorted(p.name for p in (rd / "rework" / "c1").iterdir())
            refuses(snapshot, rd, "c1", want="nothing was kept")
            if sorted(p.name for p in (rd / "rework" / "c1").iterdir()) != before:
                bad.append("a failed snapshot left a partial copy")
            (rd / "out" / "tabs" / "c1.xlsx").chmod(0o644)
        cwd = os.getcwd()
        try:
            os.chdir(td)
            if not snapshot("run", "c1").is_absolute():
                bad.append("snapshot of a relative run_dir returned a relative path")
        finally:
            os.chdir(cwd)

        # CLI: 0 clean, 1 moved, 2 refused
        if _cli(["diff", str(snap), str(rd), "c1"]) != 1:
            bad.append("CLI diff with moved figures did not exit 1")
        if _cli(["diff", str(r1), str(r1), "c"]) != 0:
            bad.append("CLI diff of a clean ledger did not exit 0")
        if _cli(["snapshot", str(rd), "nope"]) != 2 or _cli(["diff", str(snap), str(rd),
                                                             "c1_typo"]) != 2:
            bad.append("CLI refusal did not exit 2")

    for b in bad:
        print("FAIL", b)
    print("rework.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
