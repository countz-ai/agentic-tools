#!/usr/bin/env python3
"""Self-test for scripts/rework.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_rework.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

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
            rc_diff = cli(["diff", str(snap), str(rd), "c1"])
            rc_snap = cli(["snapshot", str(rd), "nope"])
        if rc_diff != 1:
            bad.append("CLI diff with moved figures did not exit 1")
        if rc_snap != 1:
            bad.append("CLI snapshot of no files did not exit 1")

    for b in bad:
        print("FAIL", b)
    print("rework.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
