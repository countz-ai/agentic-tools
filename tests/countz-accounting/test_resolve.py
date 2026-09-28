#!/usr/bin/env python3
"""Self-test for scripts/resolve.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_resolve.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import polars as pl

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from resolve import Rule, chain, resolve, rules  # noqa: E402


def main() -> int:
    bad: list[str] = []

    def expect(cond, what):
        if not cond:
            bad.append(what)
    D = dt.date(2024, 3, 1)
    cols = ("id", "date", "value", "entity", "ref", "text", "batch")
    frame = lambda rows: pl.DataFrame([tuple(r) + (None,) * (len(cols) - len(r)) for r in rows], orient="row",  # noqa: E731
                                      schema={c: pl.Date if c == "date" else pl.Float64 if c == "value"
                                              else pl.Utf8 for c in cols})
    day = lambda n: D + dt.timedelta(days=n)  # noqa: E731
    book = frame([("b1", day(0), 100.37, "OPER", "1001"),          # its cheque number on the bank
                  ("b2", day(0), 250.13, "OPER"),                  # same amount, a day later
                  ("b3", day(1), 75.25, "OPER"), ("b4", day(1), 75.25, "OPER"),   # twins
                  ("b5", day(2), 40.00, "OPER"), ("b6", day(2), 60.01, "OPER"),   # one slip
                  ("b7", day(3), 500.00, "OPER"),                  # credited on two lines
                  ("b8", day(4), 1000.00, "MERCH"),                # net of a fee
                  ("b9", day(30), 99.99, "OPER"),                  # after the statement
                  ("b10", None, 12.34, "OPER")])                   # undated
    bank = frame([("x1", day(5), 100.37, "OPER", None, "CHECK 1001"),
                  ("x2", day(1), 250.13, "OPER"),
                  ("x3", day(1), 75.25, "OPER"), ("x4", day(2), 75.25, "OPER"),
                  ("x5", day(3), 100.01, "OPER"),
                  ("x6", day(4), 200.00, "OPER", None, None, "D7"), ("x7", day(4), 300.00, "OPER", None, None, "D7"),
                  ("x8", day(5), 971.00, "MERCH"),
                  ("x9", day(9), -35.00, "OPER", None, "SERVICE CHARGE")])
    fee = Rule("card fee", ("entity",), (0, 3), percent=(-0.035, -0.015), difference="card fee")
    rs = rules(window=(0, 2), same_entity=True) + [fee]
    res = resolve(book, bank, rs)
    it = {(r["side"], r["id"]): r for r in res.items.iter_rows(named=True)}
    expect(it[("left", "b1")]["pass"] == "quoted" and it[("left", "b1")]["matched_to"] == "x1",
           f"a number the bank quotes matches whatever the dates: {it[('left', 'b1')]}")
    expect(it[("left", "b2")]["pass"] == "amount and date", "an amount the only one within the window matches")
    expect(it[("left", "b3")]["status"] == it[("left", "b4")]["status"] == "unmatched"
           and "candidates" in (it[("left", "b3")]["reason"] or ""), "twins are left for a person, with the count")
    expect(it[("left", "b5")]["pass"] == "day's items" and it[("left", "b5")]["type"] == "n:1",
           f"a day's items against one line, n:1: {it[('left', 'b5')]}")
    expect(it[("left", "b7")]["pass"] == "deposit lines" and it[("left", "b7")]["type"] == "1:n",
           f"a deposit's lines against one item, 1:n: {it[('left', 'b7')]}")
    expect(it[("left", "b8")]["pass"] == "card fee" and it[("left", "b8")]["difference"] == -29.0,
           f"a tolerated difference is matched and named: {it[('left', 'b8')]}")
    expect(it[("left", "b10")]["status"] == "unmatched" and it[("right", "x9")]["status"] == "unmatched",
           "what no rule reaches stays open")
    walk = {r["line"]: r for r in res.summary.iter_rows(named=True)}
    expect(walk["left_in_transit"]["amount"] == -99.99 and walk["difference:card fee"]["amount"] == -29.0
           and abs(walk["right_unmatched"]["amount"] - (75.25 * 2 - 35.00)) < 1e-9,
           f"the reconciliation's lines: {walk}")
    expect(abs(walk["right_unmatched"]["plus"] - 150.50) < 1e-9 and walk["right_unmatched"]["minus"] == -35.00,
           f"each line shows its gross beside its net: {walk['right_unmatched']}")
    tr = dict(res.exceptions.select("id", "in_transit").iter_rows())
    expect(tr["b9"] and not tr["b10"] and not tr["b3"], f"only a late item is in transit: {tr}")
    near = resolve(frame([("n1", day(8), 10.0), ("n2", day(7), 20.0)]), frame([("y1", day(9), 5.0)]),
                   rules(window=(0, 2)))
    tr = dict(near.exceptions.filter(pl.col("side") == "left").select("id", "in_transit").iter_rows())
    expect(tr == {"n1": True, "n2": False}, f"in transit: within the window of the statement's end: {tr}")
    qt = resolve(frame([("q1", day(0), 10.0, None, "7777")]), frame([("z1", day(40), 10.0, None, "7777")]),
                 [Rule("quoted", ("quote",), None)])
    expect(qt.matches.height == 0, "quoted reads the bank's text, never its reference")
    guard = resolve(frame([("g1", day(0), 10.0, None, "1001")]), frame([("z1", day(0), 10.0, None, "1002")]))
    expect(guard.matches.height == 0, "an amount never pairs two items whose references differ")
    solo = resolve(frame([("g1", day(0), 10.0, None, "1001")]), frame([("z1", day(0), 10.0)]))
    expect(solo.matches.height == 1, "a reference on one side only does not stop an amount")
    redep = resolve(frame([("orig", day(0), 100.0), ("again", day(19), 100.0, None, "INV7")]),
                    frame([("lbx", day(0), 100.0, None, None, "LOCKBOX INV7"),
                           ("dep", day(20), 100.0, None, None, "DEPOSIT")]), rules(window=(-5, 5)))
    got = dict(redep.items.filter(pl.col("side") == "left").select("id", "matched_to").iter_rows())
    expect(got == {"orig": "lbx", "again": "dep"},
           f"a cheque banked again meets its own line, not the first banking that quoted its invoice: {got}")
    undated = resolve(frame([("u1", None, 50.0, None, "5555"), ("w1", day(0), 70.0, None, "INV9")]),
                      frame([("z1", day(3), 50.0, None, "5555"), ("z2", day(-30), 70.0, None, None, "ACH REF INV9")]))
    got = dict(undated.items.filter(pl.col("side") == "left").select("id", "pass").iter_rows())
    expect(got == {"u1": "reference, any date", "w1": "quoted, any date"},
           f"what no dated rule can pair, a reference pairs at any date, last: {got}")
    far = resolve(frame([("p1", day(0), -10.0)]), frame([("y1", day(9), -5.0)]), rules(window=(0, 2)), transit=10)
    expect(far.exceptions.filter(pl.col("side") == "left")["in_transit"].to_list() == [True],
           "transit= sets how long an item may take to reach the bank")
    try:
        resolve(book, bank, transit=-1)
        bad.append("did not refuse a negative transit")
    except ValueError:
        pass
    inv = frame([("i1", day(0), 100.0, "C1"), ("i2", day(0), 50.0, "C2"), ("i3", day(0), 70.0, "C3"),
                 ("i4", day(0), 90.0, "C4")])
    app = frame([("a1", day(3), 100.0, "C1"), ("a2", day(3), 50.0, "C2"),
                 ("a3", day(4), 60.0, "C4"), ("a4", day(4), 30.0, "C4")])
    rec = frame([("r1", day(3), 150.0, "C1"), ("r2", day(4), 60.0)])
    by_c = [Rule("customer", ("entity",), (0, 5)), Rule("customer lines", ("entity",), (0, 5), group_right=("entity",))]
    ch = chain(resolve(inv, app, by_c), resolve(app, rec, [Rule("day", (), (0, 0), group_left=("date",)),
                                                           Rule("amount", (), (0, 1))]))
    ch = {r["id"]: r for r in ch.iter_rows(named=True)}
    expect(ch["i1"]["status"] == "traced" and ch["i1"]["reaches"] == "r1" and ch["i1"]["rules"] == "customer > day",
           f"a chain traces an invoice to its receipt: {ch['i1']}")
    expect(ch["i3"]["status"] == "open" and ch["i3"]["stopped"] == 1 and ch["i3"]["reaches"] is None,
           f"a chain stops where its first step is open: {ch['i3']}")
    expect(ch["i4"]["status"] == "partly traced" and ch["i4"]["stopped"] == 2 and ch["i4"]["reaches"] == "r2"
           and ch["i4"]["rules"] == "customer lines > amount" and ch["i4"]["reason"] == "no candidate under any rule",
           f"a chain says where part of it stops: {ch['i4']}")
    expect(res.by_rule.filter(pl.col("rule") == "quoted")["matches"][0] == 1, "each rule's count")
    for a, b in ((book.reverse(), bank.reverse()), (book.sample(fraction=1, shuffle=True, seed=3), bank)):
        expect(resolve(a, b, rs).items.equals(res.items, null_equal=True), "row order does not matter")
    for bad_left, what in ((book.with_columns(date=pl.lit("03/04/2024")), "a date not ISO"),
                           (book.with_columns(value=pl.lit(1.005)), "a value finer than cents"),
                           (book.with_columns(id=pl.lit("x")), "repeated ids")):
        try:
            resolve(bad_left, bank)
            bad.append(f"did not refuse {what}")
        except ValueError:
            pass
    try:
        from matching import check_assignment
        check_assignment(book, bank, res.items, left_id="id", right_id="id", amount="value", tol=None)
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        bad.append(f"check_assignment refused the output: {e}")
    for b in bad:
        print("FAIL", b)
    print("resolve.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
