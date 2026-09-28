#!/usr/bin/env python3
"""Self-test for scripts/arr_policy.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_arr_policy.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import pathlib
import re
import sys

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from arr_policy import CONVENTIONS, DEC, DECISIONS, POLICIES, PURPOSE_POSITIONS, _derived_at, _valid_value  # noqa: E402


def selftest() -> list[str]:
    """The catalog's own invariants: 31 decisions, ids unique, every derivation runs at
    every position under every purpose, and yields a valid value."""
    bad = []
    if len(DECISIONS) != 31 or len(DEC) != 31:
        bad.append(f"the catalog carries {len(DEC)} decisions, not 31")
    conv = {k: s["default"] for k, s in CONVENTIONS.items()}
    conv["window"] = "trailing_3_months"
    for d in DECISIONS:
        if d["type"] == "policy" and not d["by"]:
            bad.append(f"{d['id']}: a policy decision names no policy that decides it")
        if d["type"] != "policy" and d["by"]:
            bad.append(f"{d['id']}: a {d['type']} is decided by no policy position")
        for purpose, base in PURPOSE_POSITIONS.items():
            for pol in POLICIES:
                for pos in POLICIES[pol]["positions"]:
                    try:
                        v = _derived_at(d, pol, pos, base, conv)
                    except Exception as exc:  # noqa: BLE001
                        bad.append(f"{d['id']}: derivation fails at {pol}={pos} ({exc})")
                        continue
                    if d["id"] == "S2":
                        continue
                    err = _valid_value(d, v)
                    if err:
                        bad.append(f"{d['id']}: derives an invalid value at {pol}={pos}: {err}")
    for k, s in CONVENTIONS.items():
        if s["decision"] not in DEC:
            bad.append(f"convention {k} names decision {s['decision']}, which is not in the catalog")
    return bad + _computing_gaps()


def _computing_gaps() -> list[str]:
    """Every decision has a paragraph in ARR_POLICY.md § Computing ARR, opened by its
    bold id, and that paragraph names every option and field in backticks: an option
    added here without its computing rule fails the selftest."""
    doc = SCRIPTS.parent / "reference" / "ARR_POLICY.md"
    m = re.search(r"^## Computing ARR\n(.*?)(?=^## |\Z)", doc.read_text(), re.S | re.M)
    if not m:
        return ["ARR_POLICY.md carries no § Computing ARR"]
    marks = list(re.finditer(r"^\*\*([SRLVA]\d) ", m.group(1), re.M))
    block = {x.group(1): m.group(1)[x.start():marks[i + 1].start() if i + 1 < len(marks)
                                   else len(m.group(1))] for i, x in enumerate(marks)}
    bad = []
    for d in DECISIONS:
        text = block.get(d["id"])
        if text is None:
            bad.append(f"{d['id']}: no paragraph in ARR_POLICY.md § Computing ARR")
            continue
        names = list(d["options"]) if isinstance(d.get("options"), list) else []
        for f, opts in (d.get("fields") or {}).items():
            names += [f] + (list(opts) if isinstance(opts, list) else [])
        names += [k for k, s in CONVENTIONS.items()
                  if s["decision"] == d["id"] and not isinstance(s.get("options"), list)
                  and "fields" not in s]
        for n in names:
            if f"`{n}`" not in text:
                bad.append(f"{d['id']}: `{n}` has no rule in ARR_POLICY.md § Computing ARR")
    return bad


def main() -> int:
    bad = selftest()
    for b in bad:
        print(b)
    print("arr_policy selftest: " + ("ok" if not bad else f"{len(bad)} defect(s)"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
