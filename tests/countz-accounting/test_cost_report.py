#!/usr/bin/env python3
"""Self-test for scripts/cost_report.py: the run's cost page, out/cost.html.

Run by check-plugin.py as `uv run --project <plugin> python3 tests/countz-accounting/test_cost_report.py`
from the repository root. Builds a run with a lane worker handed two briefs, a forked
review handed none, the relay's own session and a re-run, then checks that each response
lands on its step, that the totals agree with usage_report.py, that the second dispatch
of a check is a re-run, that the estimate is read, and that the page fetches nothing.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))

FAILS: list[str] = []
SID = "11111111-2222-3333-4444-555555555555"
MODEL = "claude-opus-5-5"


def check(cond: bool, what: str) -> None:
    if not cond:
        FAILS.append(what)


def resp(mid: str, ts: str, out: int) -> str:
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {
        "id": mid, "model": MODEL,
        "usage": {"input_tokens": 1000, "output_tokens": out}}})


def user(ts: str, text: str) -> str:
    return json.dumps({"type": "user", "timestamp": ts, "message": {"content": text}})


def build(root: pathlib.Path) -> pathlib.Path:
    run = root / "run"
    (run / "plan").mkdir(parents=True)
    (run / "out").mkdir()
    (run / "run.json").write_text(json.dumps({
        "run_id": "demo-co.20261029-000000", "goal": "demo",
        "inputs": {"sessions": [{"session_id": SID}]},
        "dispatches": [
            {"seq": 1, "step": "analyze", "check_id": "a1"},
            {"seq": 2, "step": "analyze", "check_id": "a2"},
            {"seq": 3, "step": "review", "check_id": None},
            {"seq": 4, "step": "analyze", "check_id": "a1"},
        ]}))
    ev = [("plan_approved", None, "2026-10-29T00:00:00Z"),
          ("step_start", 1, "2026-10-29T00:01:00Z"), ("step_end", 1, "2026-10-29T00:11:00Z"),
          ("step_start", 2, "2026-10-29T00:12:00Z"), ("step_end", 2, "2026-10-29T00:20:00Z"),
          ("step_start", 3, "2026-10-29T00:21:00Z"), ("step_end", 3, "2026-10-29T00:25:00Z"),
          ("step_start", 4, "2026-10-29T00:26:00Z"), ("step_end", 4, "2026-10-29T00:30:00Z")]
    (run / "events.jsonl").write_text("".join(
        json.dumps({"ts": ts, "event": e, **({"seq": q, "step": "x"} if q else {})}) + "\n"
        for e, q, ts in ev))
    (run / "lanes.json").write_text(json.dumps({"holders": {"1": {"agent": "w1"}}, "retired": []}))
    (run / "plan" / "spend-estimate.json").write_text(json.dumps({
        "steps": [{"id": "a1", "cost_usd": 0.01, "minutes": 5},
                  {"id": "a2", "cost_usd": 0.02, "minutes": 5}],
        "report": {"cost_usd": {"value": 0.05}, "minutes": {"value": 10}},
        "reruns": {"cost_usd": {"value": 0.01}},
        "run": {"cost_usd": {"value": 0.08, "low": 0.06, "high": 0.10},
                "elapsed_minutes": {"value": 20}}}))

    proj = root / "home" / ".claude" / "projects" / "demo"
    subs = proj / SID / "subagents"
    subs.mkdir(parents=True)
    (proj / f"{SID}.jsonl").write_text("\n".join([
        resp("m-relay", "2026-10-29T00:00:30Z", 100)]) + "\n")
    # the lane worker: brief 1, then brief 2 by SendMessage, then brief 4 (a re-run)
    (subs / "agent-w1.jsonl").write_text("\n".join([
        user("2026-10-29T00:01:05Z", "Read dispatch/0001-analyze.md and run it."),
        resp("m1", "2026-10-29T00:02:00Z", 10),
        resp("m1", "2026-10-29T00:02:00Z", 10),        # a second block of one response
        resp("m2", "2026-10-29T00:05:00Z", 20),
        user("2026-10-29T00:12:05Z", "Next: dispatch/0002-analyze.md"),
        resp("m3", "2026-10-29T00:13:00Z", 30),
        user("2026-10-29T00:26:05Z", "Fix: dispatch/0004-analyze.md"),
        resp("m4", "2026-10-29T00:27:00Z", 40),
    ]) + "\n")
    # the forked review: no brief path, active inside step 3's window
    (subs / "agent-r1.jsonl").write_text("\n".join([
        user("2026-10-29T00:21:01Z", "Review the run."),
        resp("m5", "2026-10-29T00:22:00Z", 50),
    ]) + "\n")
    return run


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        run = build(root)
        os.environ["HOME"] = str(root / "home")
        import cost_report
        import usage_report
        rates = json.loads(cost_report.RATES.read_text(encoding="utf-8"))
        rep = cost_report.collect(run, rates)
        by = {r["seq"]: r for r in rep["steps"]}

        check(by[1]["responses"] == 2 and by[1]["output_tokens"] == 30,
              f"step 1 holds m1 once and m2: {by[1]['responses']} responses, {by[1]['output_tokens']} out")
        check(by[2]["output_tokens"] == 30, "step 2 holds m3, after its brief")
        check(by[3]["output_tokens"] == 50 and by[3]["lane"] == "Review",
              "the forked review's responses land on the review step")
        check(by[4]["output_tokens"] == 40 and by[4]["pass"] == "Re-run",
              "the second dispatch of a1 is a re-run and holds m4")
        check(by[1]["lane"] == "Lane 1" and by[1]["pass"] == "First pass", "a1's first pass runs in lane 1")
        check(rep["relay"]["output_tokens"] == 100, "the main session is the relay's")
        check(rep["unattributed"]["responses"] == 0, "every response found a step")
        check(by[1]["est_cost"] == 0.01 and by[4]["est_cost"] is None,
              "the first pass takes its estimate; a re-run takes none")
        check(rep["rerun_count"] == 1 and abs(rep["rerun_cost"] - by[4]["cost"]) < 1e-9, "re-runs summed")

        whole = usage_report.collect(run, rates)
        check(abs(rep["total_cost"] - whole["cost_usd"]) < 1e-9,
              f"total {rep['total_cost']} agrees with usage_report {whole['cost_usd']}")
        check(abs(rep["elapsed_minutes"] - 30) < 1e-9, "elapsed runs from plan approval to the last end")
        check(abs(rep["est_elapsed_minutes"] - 30) < 1e-9, "the estimate's elapsed adds the report's minutes")

        out = cost_report.write(run)
        page = out.read_text(encoding="utf-8")
        check(out == run / "out" / "cost.html", "the page is out/cost.html")
        check("<script src" not in page and "<link" not in page and "http://" not in page
              and "https://" not in page, "the page fetches nothing")
        check(page.count("<tr>") >= 6, "the table carries every step and the relay")

    for f in FAILS:
        print(f"FAIL: {f}")
    print("ok" if not FAILS else f"{len(FAILS)} failed")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
