#!/usr/bin/env python3
"""Self-test for scripts/check_playbook.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_check_playbook.py`
from the repository root; it lives outside the plugin so it never ships. check-plugin.py
(8i) runs the validator's command line over fixture files; this covers the params
contract directly.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from check_playbook import CHECK_ID, check_params, validate  # noqa: E402


def main() -> int:
    bad: list[str] = []

    def expect(cond, what):
        if not cond:
            bad.append(what)

    # `params.timezone` is an IANA zone name, as scripts/periods.py converts with it.
    for tz in ("America/New_York", "Asia/Tokyo", "UTC", "Europe/London"):
        got = check_params("cutoff", {"timezone": tz, "period_ends": ["2025-09-30"],
                                      "before": 5, "after": 5})
        expect(got == [], f"timezone {tz!r} accepted, got {got}")
        got = check_params("tieout", {"timezone": tz})
        expect(got == [], f"timezone {tz!r} accepted on a tie, got {got}")
    for tz in ("Mars/Base", "America", "", " UTC", "Asia/Tokyo ", "+05:00", "../etc/passwd",
               5, ["America/New_York"], {"us": "America/New_York"}):
        got = check_params("tieout", {"timezone": tz})
        expect(len(got) == 1 and "`params.timezone`" in got[0]
               and "not an IANA time zone" in got[0],
               f"timezone {tz!r} refused, naming params.timezone, got {got}")
    expect(check_params("tieout", {"timezone": None}) == [],
           "an unset timezone (null) is not a declaration")

    # The step id is the check id its files are named by: no `-`, the whole string.
    for sid in ("c4_lockbox", "a5", "x0", "2026q1_bridge"):
        expect(CHECK_ID.fullmatch(sid) is not None, f"check id {sid!r} accepted")
    for sid in ("a5-bridge", "C4", "_x", "c4 lockbox", "c4\n", ""):
        expect(CHECK_ID.fullmatch(sid) is None, f"check id {sid!r} refused")

    def plan(steps: list[dict]) -> dict:
        return {"schema": "countz-accounting/playbook@1", "name": "p", "title": "t",
                "sources": [{"slot": "a", "name": "A"}, {"slot": "b", "name": "B"}],
                "steps": steps}

    def problems(doc: dict) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            f = pathlib.Path(td) / "p.json"
            f.write_text(json.dumps(doc), encoding="utf-8")
            return validate(f, None)

    step = {"id": "c1_cutoff", "check": "cutoff", "sources": ["a", "b"], "after": [],
            "params": {"period_ends": ["2025-09-30"], "before": 5, "after": 5,
                       "entities": ["us_parent"], "timezone": "America/New_York"}}
    got = problems(plan([step]))
    expect(got == [], f"a plan whose cutoff declares an IANA zone is clean, got {got}")
    got = problems(plan([{**step, "params": {**step["params"], "timezone": "EDT-ish"}}]))
    expect(len(got) == 1 and "step `c1_cutoff`" in got[0] and "`params.timezone`" in got[0],
           f"a plan whose step declares a zone zoneinfo does not know is refused, got {got}")
    got = problems(plan([{**step, "id": "c1-cutoff"}]))
    expect(any("step entry has no valid `id`" in p and "no `-`" in p for p in got),
           f"a step id with `-` is refused, got {got}")

    for b in bad:
        print("FAIL", b)
    print("check_playbook.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
