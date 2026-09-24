#!/usr/bin/env python3
"""A check's item table (EVIDENCE.md § 5) — `checks/<check>-<table>.csv` and the manifest
block that records what built it — as one importable module.

Every step that writes item-level work imports this rather than hand-rolling a CSV writer
and a manifest:

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from items import write_items, read_items, manifest_md

    m = write_items(RUN, "c4_lockbox", "matches", rows,
                    extensions=["class", "matched_to", "match_pass", "note"],
                    classes=["deposit_in_transit", "outstanding_payment", "bank_only",
                             "book_only", "matched"],          # the recipe's vocabulary
                    sides=["book", "bank"], keys=["deposit_id"],
                    citations={"book": ["E.c4.gl_cash"], "bank": ["E.c4.bank_lines"]},
                    closes="F.c4.unreconciled.fy2025")
    record_md += manifest_md(m)                 # the hop from the table to the ledger
    rows = read_items(RUN, "c4_lockbox", "matches")            # a downstream check reads it

**One core, the same in every check.** Every row carries `item_id` (unique in the
table) and `side` (which record the item sits on). `period` (a period key, EVIDENCE.md
§ 0, or an ISO date), `amount` and `unit` (a figures unit — for money, the currency code,
so a table of two currencies states each row's) are always columns but may be empty where
the item has none — a roster member with no amount, an item that belongs to no period;
`amount` and `unit` are filled together or not at all. Everything else is an
**extension**, declared by name when the table is written; a column the call did not
declare is refused, and a declared one missing from a row is written empty.

**The vocabulary is the caller's.** When a `class` column is used, its words come from
`classes` — the recipe's or the kind's SKILL.md list — never from this module; a word
outside the list is refused. `sides` likewise names the sides the table may carry.

**Control totals never cross a currency.** The manifest carries `row_count`, counts per
side, and `control_total` as `{side: {unit: total}}` over the rows that carry an amount:
two currencies are two totals, never one sum. Amounts and totals are stored at full
precision (an FX-translated or allocated item keeps the figure it closes to); only
`manifest_md` rounds, for display.

Run with no arguments to self-check. Stdlib only, except `read_items(..., frame=True)`,
which returns a polars DataFrame.
"""
from __future__ import annotations

import csv
import io
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import figures  # noqa: E402  sibling: units and number formatting

__all__ = ["CORE", "write_items", "read_items", "manifest_md", "table_path",
           "ItemsError"]

CORE = ("item_id", "side", "period", "amount", "unit")
REQUIRED = ("item_id", "side")


class ItemsError(ValueError):
    """A table this module will not write or read as valid."""


def table_path(run_dir, check: str, name: str) -> pathlib.Path:
    """`checks/<check>-<name>.csv` under the run directory."""
    for what, v in (("check", check), ("table", name)):
        if not v or any(ch in v for ch in "/\\ ") or v.startswith("."):
            raise ItemsError(f"{what} {v!r}: a slug, no spaces or path separators")
    return pathlib.Path(run_dir) / "checks" / f"{check}-{name}.csv"


def _rows(rows) -> list[dict]:
    """A list of dicts from a list of dicts or a polars DataFrame."""
    if hasattr(rows, "to_dicts"):
        return rows.to_dicts()
    out = list(rows)
    for i, r in enumerate(out, 1):
        if not isinstance(r, dict):
            raise ItemsError(f"row {i} is a {type(r).__name__}, not a dict keyed by column")
    return out


def _empty(v) -> bool:
    return v is None or str(v).strip() == ""


def _amount(v, unit: str | None, where: str) -> float | None:
    if _empty(v) and _empty(unit):
        return None
    if _empty(v) or _empty(unit):
        raise ItemsError(f"{where}: amount and unit are filled together or both left empty")
    unit = str(unit).lower()
    if isinstance(v, bool):
        raise ItemsError(f"{where}: amount {v!r} is not a number")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ItemsError(f"{where}: amount {v!r} is not a number") from None
    if math.isnan(x) or math.isinf(x):
        raise ItemsError(f"{where}: amount {v!r} is not a finite number")
    if unit == "count":
        if x != round(x):
            raise ItemsError(f"{where}: a count of {v!r} is not whole")
        return float(round(x))
    return x


def _check(rows: list[dict], extensions, classes, class_column, sides) -> list[str]:
    """Validate rows against the core and the declared extensions; return the column list."""
    ext = list(extensions or ())
    clash = [c for c in ext if c in CORE]
    if clash:
        raise ItemsError(f"extension(s) {clash} are core columns; declare only the others")
    if len(set(ext)) != len(ext):
        raise ItemsError(f"extensions repeat a name: {ext}")
    if classes is not None and class_column not in ext:
        raise ItemsError(f"`classes` given but `{class_column}` is not a declared extension")
    columns = [*CORE, *ext]
    allowed = set(columns)
    seen: set[str] = set()
    for i, r in enumerate(rows, 1):
        where = f"row {i} ({r.get('item_id', '?')})"
        extra = sorted(set(r) - allowed)
        if extra:
            raise ItemsError(f"{where}: undeclared column(s) {extra} - declare them in "
                             f"`extensions` or drop them")
        for c in REQUIRED:
            if _empty(r.get(c)):
                raise ItemsError(f"{where}: core column `{c}` is empty")
        iid = str(r["item_id"])
        if iid in seen:
            raise ItemsError(f"{where}: item_id {iid!r} appears twice - one row per item")
        seen.add(iid)
        unit = None if _empty(r.get("unit")) else str(r["unit"]).lower()
        if unit is not None and unit not in figures.UNITS:
            raise ItemsError(f"{where}: unit {r['unit']!r} is not a figures unit "
                             f"(a currency code, or one of {', '.join(figures.OTHER_UNITS)})")
        if sides is not None and r["side"] not in sides:
            raise ItemsError(f"{where}: side {r['side']!r} is not one of {list(sides)}")
        if classes is not None:
            word = r.get(class_column)
            if word not in classes:
                raise ItemsError(f"{where}: {class_column} {word!r} is not in the declared "
                                 f"vocabulary {list(classes)}")
    return columns


def _cell(v) -> str:
    return "" if v is None else repr(v) if isinstance(v, float) else str(v)


def _totals(rows: list[dict]) -> tuple[dict, dict]:
    """Rows per side and `{side: {unit: total}}`, each total an exact float sum (`fsum`),
    never rounded."""
    counts: dict[str, int] = {}
    parts: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        side = str(r["side"])
        counts[side] = counts.get(side, 0) + 1
        by = parts.setdefault(side, {})
        if r["amount"] is not None:
            by.setdefault(str(r["unit"]).lower(), []).append(r["amount"])
    totals = {side: {u: math.fsum(xs) for u, xs in by.items()} for side, by in parts.items()}
    return counts, totals


def write_items(run_dir, check: str, name: str, rows, *, extensions=(), classes=None,
                class_column: str = "class", sides=None, keys=None, citations=None,
                closes=None) -> dict:
    """Write `checks/<check>-<name>.csv` atomically and return its manifest (EVIDENCE.md
    § 5): `table`, `columns`, `row_count`, `sides` (rows per side), `control_total`
    (`{side: {unit: total}}`), and `keys`, `citations` (`{side: [E. ids]}`) and `closes`
    (what the table closes to: a figure id or a sentence) as the call states them.
    Refuses, writing nothing, on an undeclared column, an empty `item_id` or `side`, a
    repeated `item_id`, an amount without a unit or a unit without an amount, a unit
    outside figures.UNITS, a side outside `sides` or a class outside
    `classes`."""
    rows = _rows(rows)
    columns = _check(rows, extensions, classes, class_column, sides)
    clean = []
    for i, r in enumerate(rows, 1):
        c = {k: r.get(k) for k in columns}
        c["amount"] = _amount(r.get("amount"), r.get("unit"), f"row {i} ({r['item_id']})")
        c["unit"] = None if c["amount"] is None else str(r["unit"]).lower()
        clean.append(c)
    path = table_path(run_dir, check, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    for c in clean:
        w.writerow({k: _cell(v) for k, v in c.items()})
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8")
    tmp.replace(path)
    counts, totals = _totals(clean)
    rel = path.relative_to(pathlib.Path(run_dir)).as_posix()
    return {"table": rel, "columns": columns, "row_count": len(clean), "sides": counts,
            "control_total": totals, "keys": list(keys or []),
            "citations": dict(citations or {}), "closes": closes}


def read_items(run_dir, check: str, name: str, *, extensions=None, classes=None,
               class_column: str = "class", sides=None, frame: bool = False):
    """The rows of `checks/<check>-<name>.csv`, validated as `write_items` writes them:
    the core columns present, `item_id` and `side` filled, `item_id` unique, amounts
    numbers. `extensions`, when
    given, must be exactly the table's other columns; `classes` / `sides` re-check the
    vocabulary. `frame=True` returns a polars DataFrame."""
    path = table_path(run_dir, check, name)
    if not path.is_file():
        raise ItemsError(f"{path}: no such item table")
    with path.open(encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        header = list(rd.fieldnames or [])
        raw = list(rd)
    missing = [c for c in CORE if c not in header]
    if missing:
        raise ItemsError(f"{path.name}: core column(s) {missing} missing - not an item table")
    ext = [c for c in header if c not in CORE]
    if extensions is not None and list(extensions) != ext:
        raise ItemsError(f"{path.name}: extensions {ext} are not the declared {list(extensions)}")
    rows = [{k: (v if v != "" else None) for k, v in r.items()} for r in raw]
    _check(rows, ext, classes, class_column, sides)
    for i, r in enumerate(rows, 1):
        r["amount"] = _amount(r["amount"], r["unit"], f"{path.name} row {i}")
        r["unit"] = None if r["amount"] is None else r["unit"].lower()
    if frame:
        import polars as pl
        return pl.DataFrame(rows, infer_schema_length=None)
    return rows


def manifest_md(m: dict) -> str:
    """The manifest block for `checks/<check>.md`: the table, its keys, rows per side, the
    control total per side and currency, the citations behind each side, what it closes to."""
    lines = [f"**Item table** `{m['table']}` — {m['row_count']:,} rows; columns "
             f"{', '.join(f'`{c}`' for c in m['columns'])}."]
    if m.get("keys"):
        lines.append(f"- Keys: {', '.join(f'`{k}`' for k in m['keys'])}")
    for side in sorted(m.get("sides") or {}):
        totals = "; ".join(figures.fmt(v, u, "cell")
                           for u, v in sorted((m.get("control_total") or {}).get(side, {}).items())) \
            or "none (no amounts)"
        cites = ", ".join((m.get("citations") or {}).get(side, [])) or "none stated"
        lines.append(f"- Side `{side}`: {m['sides'][side]:,} rows; control total {totals}; "
                     f"cites {cites}")
    if m.get("closes"):
        lines.append(f"- Closes to: {m['closes']}")
    return "\n".join(lines) + "\n"


# --- self-check -----------------------------------------------------------------------
def _selfcheck() -> int:
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
    raise SystemExit(_selfcheck())
