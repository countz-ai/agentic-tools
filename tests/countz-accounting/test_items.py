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
    for b in bad:
        print("FAIL", b)
    print("items: ok" if not bad else "items: self-check FAILED")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
