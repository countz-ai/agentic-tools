#!/usr/bin/env python3
"""Self-test for scripts/step_record.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_step_record.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from step_record import GateRefused, brief, finish, place_tab, main as cli, start  # noqa: E402


def main() -> int:
    import tempfile
    import time
    bad: list[str] = []
    with tempfile.TemporaryDirectory() as d:
        run = pathlib.Path(d) / "run"
        room = pathlib.Path(d) / "room"
        for sub in ("dispatch", "steps", "checks", "workpapers", "out/.staging", "plan"):
            (run / sub).mkdir(parents=True)
        room.mkdir()
        (room / "gl.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (run / "plan" / "p.json").write_text("{}", encoding="utf-8")
        (run / "run.json").write_text(json.dumps({
            "sources": [{"id": "gl", "path": str(room)}],
            "playbook": {"path": "/elsewhere/plan/p.json"}}), encoding="utf-8")
        (run / "dispatch" / "0007-tie.md").write_text(
            "Your arguments:\n\n    run_dir=/x\n    seq=7\n    check=k1\n    sources=gl\n"
            "    goal=(none)\n    params={\"tolerance\": 1}\n    mode=fresh\n", encoding="utf-8")
        (run / "workpapers" / "evidence-k1.yaml").write_text(
            "- id: E.k1.gl\n  kind: span\n  file: gl.csv\n  source: gl\n"
            "  file_role: system_export\n- id: E.k1.a0\n  kind: span\n"
            "  file: checks/k0.md\n  source: null\n  file_role: run_artifact\n", encoding="utf-8")
        (run / "checks" / "k0.md").write_text("k0", encoding="utf-8")
        (run / "checks" / "k1-old.csv").write_text("x", encoding="utf-8")
        old = time.time() - 3600
        for f in ("checks/k1-old.csv", "workpapers/evidence-k1.yaml"):
            os.utime(run / f, (old, old))

        b = brief(run, 7)
        if (b["step"], b["check"], b["args"]["params"], b["args"]["goal"]) != \
                ("tie", "k1", {"tolerance": 1}, None):
            bad.append(f"brief: {b}")
        try:
            finish(run, 7, conclusion="x")
            bad.append("finished with no step_start")
        except ValueError:
            pass
        start(run, 7)
        (run / "checks" / "k1.md").write_text("record", encoding="utf-8")
        (run / "checks" / "k1-ties.csv").write_text("t", encoding="utf-8")
        (run / "out" / ".staging" / "k1.xlsx").write_text("not a workbook", encoding="utf-8")
        try:
            finish(run, 7, conclusion="x")
            bad.append("finished with the tab still staged")
        except ValueError:
            pass
        try:
            place_tab(run, 7)
            bad.append("placed a tab the gates refuse")
        except GateRefused:
            pass
        (run / "out" / ".staging" / "k1.xlsx").unlink()
        for kw in ({"conclusion": ""}, {"conclusion": "x", "outcome": "ok"},
                   {"conclusion": "x", "outcome": "blocked"},
                   {"conclusion": "x", "blockers": [{"what": "gate"}]},
                   {"conclusion": "x", "consumed": {"sources/none.md": "profile"}}):
            try:
                finish(run, 7, **kw)
                bad.append(f"accepted {kw}")
            except (ValueError, FileNotFoundError):
                pass
        rec = finish(run, 7, conclusion="Tied.", consumed={"checks/k0.md": "roster_from"},
                     notes="n")
        if rec["produced"] != ["checks/k1.md", "checks/k1-ties.csv"]:
            bad.append(f"produced: {rec['produced']}")
        got = {pathlib.Path(c["path"]).name: c["used_for"] for c in rec["consumed"]}
        want = {"0007-tie.md": "dispatch brief", "p.json": "step params",
                "gl.csv": "cited as E.k1.gl", "k0.md": "cited as E.k1.a0; roster_from"}
        if got != want:
            bad.append(f"consumed: {got}")
        ev = [json.loads(x) for x in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        if [e["event"] for e in ev] != ["step_start", "step_end"] or \
                ev[1]["duration_s"] < 0 or ev[0]["check"] != "k1":
            bad.append(f"events: {ev}")
        try:
            finish(run, 7, conclusion="again")
            bad.append("wrote a second record for one seq")
        except FileExistsError:
            pass
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            code = cli(["finish", str(run), "7", "--json", str(run / "missing.json")])
        if code == 0:
            bad.append("the CLI finished from a missing file")
    for x in bad:
        print(f"step_record: {x}")
    print("step_record: ok" if not bad else "step_record: self-check FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
