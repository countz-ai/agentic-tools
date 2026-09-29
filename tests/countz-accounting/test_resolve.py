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
from resolve import Pass, Rule, chain, from_assignment, resolve, rules  # noqa: E402


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

    # a match built with joins reads back as the same Resolution
    lb = frame([("k1", day(0), 100.0), ("k2", day(0), 40.0), ("k3", day(1), 60.0), ("k4", day(2), 97.0),
                ("k5", day(1), 5.0), ("k6", day(9), 30.0), ("k7", day(9), 12.0)])
    rb = frame([("y1", day(1), 100.0), ("y2", day(2), 100.0), ("y3", day(3), 95.0), ("y4", day(4), 7.0),
                ("y5", day(4), 0.5)])
    asg = pl.DataFrame([("left", "k1", "matched", 1, "cheque", None), ("right", "y1", "matched", 1, "cheque", None),
                        ("left", "k2", "matched", 2, "slip", None), ("left", "k3", "matched", 2, "slip", None),
                        ("right", "y2", "matched", 2, "slip", None),
                        ("left", "k4", "matched", 3, "fee", None), ("right", "y3", "matched", 3, "fee", None),
                        ("left", "k5", "unmatched", None, None, None), ("left", "k6", "unmatched", None, None, None),
                        ("left", "k7", "excluded", None, "void", "voided in the book"),
                        ("right", "y4", "unmatched", None, None, "interest credited"),
                        ("right", "y5", "excluded", None, "void", "bank error, reversed")],
                       orient="row", schema=["side", "id", "status", "group", "pass", "reason"])
    ps = [Pass("cheque", "same cheque number and amount"), Pass("slip", "one deposit slip's lines"),
          Pass("fee", "amount within 3%, the processor's fee", "processor fee"), Pass("void", "voided items")]
    fa = from_assignment(lb, rb, asg, ps, transit=2)
    it = {(r["side"], r["id"]): r for r in fa.items.iter_rows(named=True)}
    expect(fa.engine == "assignment" and res.engine == "resolve", "each Resolution names its engine")
    expect(it["left", "k2"]["matched_to"] == "y2" and it["left", "k2"]["pass"] == "slip"
           and it["right", "y2"]["matched_to"] == "k2;k3" and it["left", "k2"]["type"] == "n:1",
           f"a group's items match what the group holds: {it['left', 'k2']}")
    expect(it["left", "k4"]["difference"] == -2.0, f"a tolerated difference, right less left: {it['left', 'k4']}")
    expect(it["left", "k7"]["reason"] == "excluded by void: voided in the book"
           and it["left", "k5"]["reason"] == "no candidate under any pass"
           and it["right", "y4"]["reason"] == "interest credited", "an unmatched item states why")
    tr = dict(fa.exceptions.filter(pl.col("side") == "left").select("id", "in_transit").iter_rows())
    expect(tr == {"k5": False, "k6": True, "k7": False}, f"in transit by transit=, never an excluded item: {tr}")
    walk = {r["line"]: r["amount"] for r in fa.summary.iter_rows(named=True)}
    expect(walk == {"left_total": 344.0, "left_in_transit": -30.0, "left_unmatched": -17.0,
                    "difference:processor fee": -2.0, "right_unmatched": 7.5, "right_total": 302.5},
           f"the reconciliation, named difference and all: {walk}")
    expect(fa.by_rule["rule"].to_list() == ["cheque", "slip", "fee", "void"]
           and fa.by_rule["matches"].to_list() == [1, 1, 1, 0]
           and fa.by_rule["criteria"][2] == "amount within 3%, the processor's fee", "the passes, in order")
    for kw, what in (({"passes": ps[:3]}, "a pass not among `passes`"),
                     ({"passes": [Pass("fee", "amount within 3%")] + ps[:2] + ps[3:]}, "a difference with no name"),
                     ({"passes": ps + ps[:1]}, "a pass named twice"),
                     ({"assignment": asg.filter(pl.col("id") != "y5")}, "an item not accounted for"),
                     ({"assignment": asg.with_columns(group=pl.when(pl.col("id") == "y1").then(9)
                                                      .otherwise(pl.col("group")))}, "a one-sided group"),
                     ({"transit": -1}, "a negative transit")):
        try:
            from_assignment(**{"left": lb, "right": rb, "assignment": asg, "passes": ps, "transit": 2, **kw})
            bad.append(f"from_assignment did not refuse {what}")
        except ValueError:
            pass
    corner_cases(bad)
    counting_agrees_with_pairs(bad)
    for b in bad:
        print("FAIL", b)
    print("resolve.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


def corner_cases(bad: list[str]) -> None:
    """Inputs inside the documented contract that once matched wrongly, or crashed."""
    import time

    D = dt.date(2024, 3, 1)
    S = lambda **c: pl.DataFrame(c)  # noqa: E731

    def expect(cond, what):
        if not cond:
            bad.append(what)

    def refused(what, fn):
        try:
            fn()
            bad.append(f"accepted {what}")
        except ValueError:
            pass

    def status(res):
        return {(r["side"], r["id"]): (r["status"], r["pass"], r["matched_to"]) for r in res.items.iter_rows(named=True)}

    # a float key is refused (1001.0 would key as `10010`); its text or int form matches
    refused("a float ref", lambda: resolve(S(id=["b1"], date=[D], value=[500.0], ref=[1001.0]),
                                           S(id=["k1"], date=[D], value=[500.0], ref=["1001"])))
    refused("a decimal ref", lambda: resolve(S(id=["b1"], date=[D], value=[5.0], ref=[1001.0]).with_columns(
        pl.col("ref").cast(pl.Decimal(10, 2))), S(id=["k1"], date=[D], value=[5.0], ref=["1001"])))
    refused("a float id", lambda: resolve(S(id=[1.0], date=[D], value=[5.0]), S(id=["k1"], date=[D], value=[5.0])))
    refused("a float entity under same_entity", lambda: resolve(
        S(id=["b1"], date=[D], value=[5.0], entity=[7.0]), S(id=["k1"], date=[D], value=[5.0], entity=[7.0]),
        rules(same_entity=True)))
    res = resolve(S(id=["b1"], date=[D], value=[500.0], ref=[1001]),
                  S(id=["k1"], date=[D], value=[500.0], ref=["01001"]))
    expect(status(res)[("left", "b1")] == ("matched", "reference", "k1"), "an int ref keys with its text form")

    # a zero amount has no direction: a tolerance never pairs it with any amount
    fee = [Rule("fee", (), (0, 2), tolerance=(-50.0, 0.0), difference="processor fee")]
    res = resolve(S(id=["b0"], date=[D], value=[0.0]), S(id=["k9"], date=[D], value=[98765.43]), fee)
    expect(res.matches.height == 0, "a zero left amount matched under a tolerance")
    res = resolve(S(id=["b1"], date=[D], value=[30.0]), S(id=["k0"], date=[D], value=[0.0]), fee)
    expect(res.matches.height == 0, "a zero right amount matched under a tolerance")
    res = resolve(S(id=["b1"], date=[D], value=[1000.0]), S(id=["k1"], date=[D], value=[971.0]), fee)
    expect(res.matches.height == 1, "a tolerance still pairs two amounts within it")
    res = resolve(S(id=["b0"], date=[D], value=[0.0]), S(id=["k0"], date=[D], value=[0.0]))
    expect(res.matches.height == 1, "two zeros still match under an exact rule")

    # a group carries its items' references: never paired with a reference none of them has
    b = S(id=["b1", "b2"], date=[D, D], value=[100.0, 50.0], ref=["1001", "1002"], entity=["ACME", "ACME"])
    res = resolve(b, S(id=["k1"], date=[D], value=[150.0], ref=["9999"], entity=["ACME"]))
    expect(res.matches.height == 0, f"a group overrode its items' references: {res.matches}")
    res = resolve(b, S(id=["k1"], date=[D], value=[150.0], ref=[None], entity=["ACME"]))
    expect(res.matches.height == 1 and res.matches["type"][0] == "n:1", "a group still matches an unreferenced line")
    b2 = S(id=["b1", "b2"], date=[D, D], value=[100.0, 50.0], ref=["1001", None], entity=["ACME", "Acme"])
    res = resolve(b2, S(id=["k1"], date=[D], value=[150.0], ref=["1001"], entity=["acme"]))
    expect(res.matches.height == 1 and res.matches["rule"][0] == "day's items",
           f"a group's one reference agrees; entities group as keys: {res.matches}")

    # a time-zoned datetime's date depends on its zone: refused; naive datetimes are their date
    ts = dt.datetime(2024, 3, 1, 22, 0)
    refused("a time-zoned datetime", lambda: resolve(
        S(id=["b1"], date=[ts], value=[10.0]).with_columns(pl.col("date").dt.replace_time_zone("America/New_York")),
        S(id=["k1"], date=[D], value=[10.0])))
    res = resolve(S(id=["b1"], date=[ts], value=[10.0]), S(id=["k1"], date=[D], value=[10.0]),
                  [Rule("same day", (), (0, 0))])
    expect(res.matches.height == 1, "a naive datetime is its own date")
    for text in ("2024-3-1", "03/01/2024", "2024-02-30", "2024-03-01T10:00:00Z", "2024-03-01+01:00"):
        refused(f"date text {text!r}", lambda: resolve(S(id=["b1"], date=[text], value=[1.0]),
                                                        S(id=["k1"], date=[D], value=[1.0])))
    res = resolve(S(id=["b1"], date=["2024-03-01T10:00:00"], value=[1.0]), S(id=["k1"], date=[D], value=[1.0]))
    expect(res.matches.height == 1, "ISO text with a time and no zone")

    # rules as the engine reads them: named once, ranges forward, percent a fraction
    refused("two rules of one name", lambda: resolve(S(id=["b1"], date=[D], value=[1.0]),
                                                     S(id=["k1"], date=[D], value=[1.0]),
                                                     [Rule("p", ("ref",), (0, 0)), Rule("p", (), (0, 0))]))
    for r in (Rule("x", "ref"), Rule("x", (), (3, 0)), Rule("x", (), (0.5, 2)),
              Rule("x", (), (0, 2), percent=(-3, 0), difference="fee"),
              Rule("x", (), (0, 2), tolerance=(5.0, -5.0), difference="fee"),
              Rule("x", (), (0, 2), tolerance=(-5.0, 0.0)), Rule("x", ("value",)), Rule("x", ("date",)),
              Rule("x", (), (0, 2), group_left=("c",)), Rule("", ())):
        refused(f"rule {r}", lambda: resolve(S(id=["b1"], date=[D], value=[1.0]), S(id=["k1"], date=[D], value=[1.0]), [r]))

    # a column a rule compares that one side lacks is refused; so is same_entity with no entity
    refused("same_entity with no entity on one side", lambda: resolve(
        S(id=["b1"], date=[D], value=[10.0], entity=["X"]), S(id=["k1"], date=[D], value=[10.0]), rules(same_entity=True)))
    refused("same_entity with no entity on either side", lambda: resolve(
        S(id=["b1"], date=[D], value=[10.0]), S(id=["k1"], date=[D], value=[10.0]), rules(same_entity=True)))
    refused("a ref only one side carries", lambda: resolve(
        S(id=["b1"], date=[D], value=[10.0], ref=["1"]), S(id=["k1"], date=[D], value=[10.0])))
    refused("summing by a column the side lacks", lambda: resolve(
        S(id=["b1"], date=[D], value=[10.0]), S(id=["k1"], date=[D], value=[10.0]),
        [Rule("slips", (), (0, 2), group_left=("slip",))]))
    expect(resolve(S(id=["b1"], date=[D], value=[10.0]), S(id=["k1"], date=[D], value=[10.0])).matches.height == 1,
           "neither side carrying ref, entity or batch is fine under the defaults")

    # transit and age are measured at the statement's end when it is given
    b = S(id=["b1", "b2"], date=[D + dt.timedelta(days=23), D + dt.timedelta(days=29)], value=[7.0, 8.0])
    k = S(id=["k1"], date=[D + dt.timedelta(days=24)], value=[99.0])
    quiet = resolve(b, k, transit=2)
    at_end = resolve(b, k, transit=2, end=dt.date(2024, 3, 31))
    tr = lambda r: dict(r.exceptions.filter(pl.col("side") == "left").select("id", "in_transit").iter_rows())  # noqa: E731
    expect(tr(quiet) == {"b1": True, "b2": True} and quiet.end == dt.date(2024, 3, 25),
           f"by default measured at the right side's last date: {tr(quiet)}")
    expect(tr(at_end) == {"b1": False, "b2": True} and at_end.end == dt.date(2024, 3, 31)
           and at_end.exceptions.filter(pl.col("id") == "b1")["age"][0] == 7,
           f"measured at `end`: {tr(at_end)}")
    expect(at_end.decimals == 2 and resolve(b, k, decimals=0).decimals == 0, "the Resolution carries its decimals")
    refused("an end that is not a date", lambda: resolve(b, k, end="31/03/2024"))

    # chain: a reason is the first item's, by id
    inv = S(id=["I1"], date=[D], value=[100.0], ref=["I1"])
    app = S(id=["C1", "C2", "C3"], date=[D, D, D], value=[50.0, 30.0, 20.0], ref=["I1", "I1", "I1"])
    bank = S(id=["K1"], date=[D], value=[50.0])
    r1 = resolve(inv, app, [Rule("ref totals", ("ref",), None, ("ref",), ("ref",))])
    r2 = resolve(app, bank, [Rule("amt", (), (0, 0))])
    ch = chain(r1, r2).row(0, named=True)
    expect(ch["status"] == "partly traced" and ch["stopped"] == 2 and ch["reaches"] == "K1", f"chain: {ch}")

    # many items of one amount: counted, never listed pair by pair
    n = 20_000
    b = pl.DataFrame({"id": [f"b{i}" for i in range(n)], "value": [49.0] * n,
                      "date": [D + dt.timedelta(days=i % 60) for i in range(n)]})
    k = pl.DataFrame({"id": [f"k{i}" for i in range(n)], "value": [49.0] * n,
                      "date": [D + dt.timedelta(days=i % 60 + 1) for i in range(n)]})
    t0 = time.time()
    res = resolve(b, k)
    want = sum(1 for i in range(n) if 0 <= i % 60 + 1 <= 2)        # b0's window: days 0 to 2
    expect(time.time() - t0 < 30 and res.matches.height == 0
           and res.items.filter(pl.col("id") == "b0")["reason"][0] == f"{want} candidates under amount and date",
           f"{n} items of one amount a side: {time.time() - t0:.1f}s, {res.items['reason'][0]}")
    refused("a tolerance rule over too many pairs", lambda: resolve(
        b, k, [Rule("fee", (), None, tolerance=(-1.0, 0.0), difference="fee")]))


def counting_agrees_with_pairs(bad: list[str]) -> None:
    """The counting path (`_reach`) and the pair join (`_pairs`) give every candidate the
    same count and the same partner, over random streams with undated items, repeated
    amounts, zeros, negatives, references that agree, differ or are absent, entities
    and batches, under keyed, dated, undated and grouped rules."""
    import random

    import resolve as engine
    D = dt.date(2024, 3, 1)

    def stream(rng, n, side):
        rows = [(f"{side}{i}", None if rng.random() < 0.1 else D + dt.timedelta(days=rng.randint(0, 12)),
                 rng.choice([10.0, 20.0, 30.0, 0.0, -10.0]), rng.choice([None, "A", "B"]),
                 rng.choice([None, None, "1001", "1002", "01001"]), rng.choice([None, "X1", "X2", "X3"]))
                for i in range(n)]
        df = pl.DataFrame(rows, orient="row", schema={"id": pl.Utf8, "date": pl.Date, "value": pl.Float64,
                                                      "entity": pl.Utf8, "ref": pl.Utf8, "batch": pl.Utf8})
        return engine._stream(df, "left" if side == "b" else "right", 100, {"entity", "ref", "batch"})
    rs = [Rule("r1", ("ref",), (0, 3)), Rule("r2", (), (0, 2)), Rule("r3", (), (-2, 5)), Rule("r4", (), None),
          Rule("r5", ("entity",), (0, 1)), Rule("r6", (), (0, 2), group_right=("batch",)),
          Rule("r7", (), (0, 2), group_left=("entity", "date")),
          Rule("r8", (), (1, 4), group_left=("entity", "date"), group_right=("batch",)),
          Rule("r9", ("ref",), None, ("ref",), ("ref",)), Rule("r10", ("entity", "ref"), (0, 0))]
    seen = {1: 0, 2: 0}
    for seed in range(150):
        rng = random.Random(seed)
        L, R = stream(rng, rng.randint(0, 25), "b"), stream(rng, rng.randint(0, 25), "k")
        for rule in rs:
            fast = engine._candidates(L, R, rule, 100)
            p = engine._pairs(engine._group(L, rule.group_left, rule.on),
                              engine._group(R, rule.group_right, rule.on), rule, 100)
            for got, g, other in ((fast[0], "g", "g_r"), (fast[1], "g_r", "g")):
                want = {r["g"]: (r["n"], r["p"] if r["n"] == 1 else None) for r in
                        p.group_by(g).agg(n=pl.len(), p=pl.col(other).first()).rename({g: "g"}).iter_rows(named=True)}
                have = {r["g"]: (r["n"], r["partner"]) for r in got.iter_rows(named=True) if r["n"]}
                seen[1] += sum(v[0] == 1 for v in want.values())
                seen[2] += sum(v[0] > 1 for v in want.values())
                if have != want:
                    bad.append(f"counting path disagrees with the pairs: seed {seed}, rule {rule.name}")
                    return
    expect_ = seen[1] > 1000 and seen[2] > 1000
    if not expect_:
        bad.append(f"the equivalence fuzz exercised too little: {seen}")


if __name__ == "__main__":
    raise SystemExit(main())
