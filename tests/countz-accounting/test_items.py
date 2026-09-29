#!/usr/bin/env python3
"""Self-test for scripts/items.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_items.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import math
import pathlib
import sys

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from items import ItemsError, manifest_md, read_items, write_items  # noqa: E402


def main() -> int:
    import tempfile
    bad: list[str] = []

    def refuses(fn, *a, **k) -> bool:
        try:
            fn(*a, **k)
        except ItemsError:
            return True
        return False

    rows = [
        {"item_id": "X.c4.1", "side": "book", "period": "fy2025", "amount": 1204.404,
         "unit": "usd", "class": "deposit_in_transit", "matched_to": None},
        {"item_id": "X.c4.2", "side": "bank", "period": "fy2025", "amount": -50,
         "unit": "USD", "class": "bank_only", "matched_to": "B.9"},
        {"item_id": "X.c4.3", "side": "bank", "period": "fy2025", "amount": 5000,
         "unit": "eur", "class": "bank_only", "matched_to": None},
        {"item_id": "X.c4.4", "side": "bank", "period": "fy2025", "amount": 120000,
         "unit": "jpy", "class": "matched", "matched_to": "G.1"},
    ]
    kw = dict(extensions=["class", "matched_to"],
              classes=["deposit_in_transit", "bank_only", "matched"], sides=["book", "bank"])
    with tempfile.TemporaryDirectory() as td:
        m = write_items(td, "c4_lockbox", "matches", rows, keys=["deposit_id"],
                        citations={"book": ["E.c4.gl"], "bank": ["E.c4.bank"]},
                        closes="F.c4.unreconciled.fy2025", **kw)
        want_tot = {"book": {"usd": 1204.404}, "bank": {"usd": -50.0, "eur": 5000.0,
                                                       "jpy": 120000.0}}
        if m["row_count"] != 4 or m["sides"] != {"book": 1, "bank": 3} \
                or m["control_total"] != want_tot:
            bad.append(f"manifest {m}")
        if m["table"] != "checks/c4_lockbox-matches.csv":
            bad.append(f"table path {m['table']}")
        back = read_items(td, "c4_lockbox", "matches", **kw)
        if [r["amount"] for r in back] != [1204.404, -50.0, 5000.0, 120000.0] \
                or back[1]["unit"] != "usd" or back[0]["matched_to"] is not None:
            bad.append(f"read back {back}")
        md = manifest_md(m)
        for want in ("$1,204.40", "€5,000.00", "¥120,000", "E.c4.gl", "4 rows",
                     "F.c4.unreconciled.fy2025"):
            if want not in md:
                bad.append(f"manifest_md lacks {want!r}: {md}")
        cases = {
            "undeclared column": [{**rows[0], "memo": "x"}],
            "class outside vocabulary": [{**rows[0], "class": "in_transit"}],
            "repeated item_id": [rows[0], rows[0]],
            "unit outside figures": [{**rows[0], "unit": "dollars"}],
            "side outside sides": [{**rows[0], "side": "ledger"}],
            "amount without unit": [{**rows[0], "unit": None}],
            "unit without amount": [{**rows[0], "amount": None}],
            "empty core": [{**rows[0], "side": ""}],
        }
        for what, rs in cases.items():
            if not refuses(write_items, td, "c4_bad", "matches", rs, **kw):
                bad.append(f"write_items did not refuse: {what}")
        if (pathlib.Path(td) / "checks" / "c4_bad-matches.csv").exists():
            bad.append("a refused table was written")
        # an allocation in thirds closes to its full-precision figure, not to cents
        third = [{"item_id": f"A.{i}", "side": "alloc", "period": None, "amount": 100 / 3,
                  "unit": "usd"} for i in range(3)]
        ma = write_items(td, "c5_alloc", "thirds", third)
        if ma["control_total"] != {"alloc": {"usd": math.fsum([100 / 3] * 3)}} \
                or read_items(td, "c5_alloc", "thirds")[0]["amount"] != 100 / 3:
            bad.append(f"full precision lost: {ma['control_total']}")
        if "$100.00" not in manifest_md(ma):
            bad.append(f"manifest_md does not round for display: {manifest_md(ma)}")
        roster = [{"item_id": "R.1", "side": "gl", "period": None, "amount": None, "unit": None},
                  {"item_id": "R.2", "side": "bank", "period": "", "amount": "", "unit": ""}]
        mr = write_items(td, "c2_roster", "accounts", roster)
        if mr["sides"] != {"gl": 1, "bank": 1} or mr["control_total"] != {"gl": {}, "bank": {}}:
            bad.append(f"a roster with no amount or period: {mr}")
        if [r["amount"] for r in read_items(td, "c2_roster", "accounts")] != [None, None]:
            bad.append("a roster read back with amounts")
        if "none (no amounts)" not in manifest_md(mr):
            bad.append(f"manifest_md of a roster: {manifest_md(mr)}")
        if not refuses(write_items, td, "c4", "a/b", rows, **kw):
            bad.append("a table name with a separator was accepted")
        if not refuses(read_items, td, "c4_lockbox", "matches", extensions=["class"]):
            bad.append("read_items accepted undeclared extensions")
        try:
            import polars  # noqa: F401
            f = read_items(td, "c4_lockbox", "matches", frame=True)
            if f.height != 4:
                bad.append("frame height")
        except ImportError:
            pass
        _hardening(td, bad, refuses)
    for b in bad:
        print("FAIL", b)
    print("items: ok" if not bad else "items: self-check FAILED")
    return 1 if bad else 0


def _row(i, **kw) -> dict:
    return {"item_id": f"I.{i}", "side": "book", "period": "fy2025", "amount": 1.0,
            "unit": "usd", **kw}


def _hardening(td, bad: list[str], refuses) -> None:
    """Each refusal, beside its valid neighbour."""
    import datetime
    import decimal
    import numpy as np
    import polars as pl

    def takes(what, fn, *a, **k):
        try:
            return fn(*a, **k)
        except ItemsError as exc:
            bad.append(f"{what}: refused: {exc}")
            return None

    # the path: a check id has no '-' and a table name no upper case, so no two tables share a file
    for what, check, name in (("check with '-'", "c4-a", "b"), ("upper-case table", "c5", "Matches"),
                              ("upper-case check", "C5", "m"), ("tab in name", "c5", "a\tb"),
                              ("newline in name", "c5", "a\n"), ("colon", "c5", "a:b")):
        if not refuses(write_items, td, check, name, [_row(1)]):
            bad.append(f"table path accepted: {what}")
    if takes("a hyphenated table name", write_items, td, "c4", "book-only", [_row(1)]) is None \
            or read_items(td, "c4", "book-only")[0]["item_id"] != "I.1":
        bad.append("a hyphenated table name under a check id does not round-trip")

    # numpy scalars are written as the number they hold, never as np.float64(...)
    takes("numpy cells", write_items, td, "c6", "np",
          [_row(1, amount=np.float64(2.5), days=np.float64(12.5), n=np.int64(3))],
          extensions=["days", "n"])
    text = (pathlib.Path(td) / "checks" / "c6-np.csv").read_text()
    if "np." in text or "I.1,book,fy2025,2.5,usd,12.5,3" not in text:
        bad.append(f"numpy cells written as {text!r}")

    # a zero-row table read as a frame keeps its columns; the types do not depend on the rows
    write_items(td, "c6", "empty", [], extensions=["class"])
    f = read_items(td, "c6", "empty", frame=True)
    if f.columns != ["item_id", "side", "period", "amount", "unit", "class"] or f.height:
        bad.append(f"a zero-row frame lost its columns: {f.columns}")
    write_items(td, "c6", "roster", [{"item_id": "R1", "side": "gl"}])
    s = dict(read_items(td, "c6", "roster", frame=True).schema)
    if s["amount"] != pl.Float64 or s["period"] != pl.String:
        bad.append(f"a roster frame's types: {s}")

    # amounts: refused where a float would change them; plain numbers of any type accepted
    for what, v in (("int beyond 2**53", 2**53 + 1),
                    ("Decimal beyond a float", decimal.Decimal("12345678901234567.89")),
                    ("too large for a float", 10**400), ("underscores", "1_000"),
                    ("non-ASCII digits", "١٢٣"), ("grouping", "1,000"), ("a word", "nan"),
                    ("a bool", True)):
        if not refuses(write_items, td, "c7", "amt", [_row(1, amount=v)]):
            bad.append(f"amount accepted: {what}")
    ok = [(2**53, 2.0**53), (decimal.Decimal("1204.40"), 1204.4), (" 5e2 ", 500.0),
          (np.int64(7), 7.0), (np.float32(0.5), 0.5), ("-0.10", -0.1)]
    m = takes("plain amounts", write_items, td, "c7", "ok",
              [_row(i, amount=v) for i, (v, _) in enumerate(ok)])
    if m is not None and [r["amount"] for r in read_items(td, "c7", "ok")] != [x for _, x in ok]:
        bad.append(f"plain amounts read back as {[r['amount'] for r in read_items(td, 'c7', 'ok')]}")

    # the vocabulary: a list of non-empty strings; what write accepts, read accepts
    for what, word, kw in (("int classes", 1, dict(classes=[1, 2])),
                           ("classes as a string", "matched", dict(classes="matched")),
                           ("empty word", "", dict(classes=["", "matched"])),
                           ("sides as a string", "matched", dict(sides="book"))):
        if not refuses(write_items, td, "c8", "v", [_row(1, cls=word)], extensions=["cls"],
                       class_column="cls", **kw):
            bad.append(f"vocabulary accepted: {what}")
    vk = dict(extensions=["cls"], class_column="cls", classes=["matched", None], sides=["1", "book"])
    takes("None in classes, an int side", write_items, td, "c8", "v",
          [_row(1, cls=None), {**_row(2, cls="matched"), "side": 1}], **vk)
    back = takes("the same table read back", read_items, td, "c8", "v", **vk)
    if back is not None and [(r["side"], r["cls"]) for r in back] != [("book", None),
                                                                      ("1", "matched")]:
        bad.append(f"vocabulary round trip: {back}")

    # extensions compare as a set; a repeated name is refused
    write_items(td, "c9", "ord", [_row(1, a="x", b="y")], extensions=["a", "b"])
    takes("extensions in another order", read_items, td, "c9", "ord", extensions=["b", "a"])
    if not refuses(read_items, td, "c9", "ord", extensions=["a", "b", "a"]):
        bad.append("read_items accepted a repeated extension")

    # the period: a period key or an ISO date; a date is written as its ISO date
    for what, p in (("not a period", "not a period"), ("a datetime",
                                                       datetime.datetime(2025, 1, 31)),
                    ("upper case", "FY2025"), ("padded", " fy2025"), ("bad date", "2025-02-30"),
                    ("a float", 2025.0)):
        if not refuses(write_items, td, "c10", "p", [{**_row(1), "period": p}]):
            bad.append(f"period accepted: {what}")
    good = ["fy2025", "2025-12", "2026q1", "ltm_2025-12", "2025-01-31",
            datetime.date(2025, 1, 31), None]
    takes("period keys and dates", write_items, td, "c10", "p",
          [{**_row(i), "period": p} for i, p in enumerate(good)])
    if [r["period"] for r in read_items(td, "c10", "p")] != \
            ["fy2025", "2025-12", "2026q1", "ltm_2025-12", "2025-01-31", "2025-01-31", None]:
        bad.append(f"periods read back as {[r['period'] for r in read_items(td, 'c10', 'p')]}")

    # the manifest's stated fields keep their shapes
    for what, kw in (("citations as a string", dict(citations={"book": "E.c11.gl"})),
                     ("a citation that is not an E. id", dict(citations={"book": ["F.c11.x"]})),
                     ("a citation for an undeclared side",
                      dict(citations={"bank": ["E.c11.b"]}, sides=["book"])),
                     ("keys as a string", dict(keys="deposit_id")),
                     ("an empty closes", dict(closes=" "))):
        if not refuses(write_items, td, "c11", "m", [_row(1)], **kw):
            bad.append(f"manifest field accepted: {what}")
    m = takes("stated fields", write_items, td, "c11", "m", [_row(1)], sides=["book", "bank"],
              keys=(k for k in ["deposit_id"]), citations={"bank": ["E.c11.b"]},
              closes="F.c11.total")
    if m is not None and (m["keys"] != ["deposit_id"] or m["citations"] != {"bank": ["E.c11.b"]}):
        bad.append(f"stated fields recorded as {m['keys']} {m['citations']}")
    left = [p.name for p in (pathlib.Path(td) / "checks").iterdir() if p.name.endswith(".tmp")]
    if left:
        bad.append(f"temporary files left in checks/: {left}")


if __name__ == "__main__":
    raise SystemExit(main())
