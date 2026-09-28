#!/usr/bin/env python3
"""Self-test for scripts/matching.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_matching.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import pathlib
import sys

import polars as pl

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from matching import MatchError, check_assignment  # noqa: E402


def main() -> int:
    bad: list[str] = []

    def expect(cond, what):
        if not cond:
            bad.append(what)

    def refuses(fn, what):
        try:
            fn()
            bad.append(f"did not refuse: {what}")
        except MatchError:
            pass

    book = pl.DataFrame({"id": ["b1", "b2", "b3", "b4", "b5"],
                         "amt": [100.0, 40.0, 60.0, 75.0, 12.0], "ccy": ["USD"] * 5})
    bank = pl.DataFrame({"id": ["k1", "k2", "k3", "k4"],
                         "amt": [100.0, 100.0, 72.5, 30.0], "ccy": ["USD", "usd", "USD", "EUR"]})
    asg = pl.DataFrame({
        "side": ["left"] * 5 + ["right"] * 4,
        "id": ["b1", "b2", "b3", "b4", "b5", "k1", "k2", "k3", "k4"],
        "status": ["matched", "matched", "matched", "matched", "excluded",
                   "matched", "matched", "matched", "unmatched"],
        "group": [1, 2, 2, 3, None, 1, 2, 3, None],
        "pass": ["ref", "deposit", "deposit", "fee", "void", "ref", "deposit", "fee", None],
        "reason": [None, None, None, None, "voided", None, None, None, None]})
    kw = dict(left_id="id", right_id="id", amount="amt", currency="ccy")
    out = check_assignment(book, bank, asg, tol=None, **kw)
    by = {r["id"]: r for r in out.to_dicts()}
    expect(by["b2"]["matched_to"] == "k2" and by["k2"]["matched_to"] == "b2;b3",
           "matched_to across an n:1 group")
    expect(abs(by["b4"]["diff"] - 2.5) < 1e-9, "the fee group records its 2.5 difference")
    expect(by["k4"]["matched_to"] is None and by["b5"]["diff"] is None, "open items carry no group")
    refuses(lambda: check_assignment(book, bank, asg, tol=1.0, **kw), "a diff beyond tol")
    expect(check_assignment(book, bank, asg, tol=2.5, **kw).height == 9, "a diff within tol")
    refuses(lambda: check_assignment(book, bank, asg.filter(pl.col("id") != "k4"), **kw),
            "an item not accounted for")
    refuses(lambda: check_assignment(book, bank, asg.vstack(asg.head(1)), **kw),
            "an item assigned twice")
    refuses(lambda: check_assignment(book, bank, asg.with_columns(
        reason=pl.lit(None, pl.Utf8)), tol=None, **kw), "an exclusion with no reason")
    refuses(lambda: check_assignment(book, bank, asg.with_columns(
        group=pl.when(pl.col("id") == "k4").then(3).otherwise(pl.col("group")),
        status=pl.when(pl.col("id") == "k4").then(pl.lit("matched")).otherwise("status"),
        **{"pass": pl.when(pl.col("id") == "k4").then(pl.lit("fee")).otherwise("pass")}),
        tol=None, **kw), "a group spanning currencies")
    refuses(lambda: check_assignment(book, bank, asg.with_columns(
        id=pl.when(pl.col("id") == "k4").then(pl.lit("k9")).otherwise("id")), **kw),
        "an id outside the population")

    # a roster: no amounts
    ra = pl.DataFrame({"gl": ["1010", "1020"]})
    rb = pl.DataFrame({"acct": ["x1", "x2"]})
    ros = pl.DataFrame({"side": ["left", "left", "right", "right"],
                        "id": ["1010", "1020", "x1", "x2"],
                        "status": ["matched", "unmatched", "matched", "unmatched"],
                        "group": [1, None, 1, None], "pass": ["gl_account", None, "gl_account", None],
                        "reason": [None] * 4})
    r = check_assignment(ra, rb, ros, left_id="gl", right_id="acct")
    expect(r.filter(pl.col("id") == "1010")["matched_to"][0] == "x1", "roster match")

    for b in bad:
        print("FAIL", b)
    print("matching.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
