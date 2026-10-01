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
§ 0, or an ISO date `YYYY-MM-DD`, or a `datetime.date`, written as its ISO date),
`amount` and `unit` (a figures unit — for money, the currency code, so a table of two
currencies states each row's) are always columns but may be empty where the item has
none (e.g. a roster member with no amount); `amount` and `unit` are filled together or
not at all. Everything else is an **extension**, declared
by name when the table is written; a column the call did not declare is refused, and a
declared one missing from a row is written empty. Every cell is written as text (a float
as its shortest round-trip form, numpy scalars included) and read back as text, except
`amount`, read back as a float.

**The path is unambiguous.** `check` is a check id (`check_playbook.CHECK_ID`:
`[a-z0-9][a-z0-9_]*`, no `-`) and the table name a lower-case slug
(`[a-z0-9][a-z0-9_-]*`), so `<check>-<name>` splits one way only and no two tables share
a file on a case-insensitive disk.

**The vocabulary is the caller's.** When a `class` column is used, its words come from
`classes` — the recipe's or the kind's SKILL.md list — never from this module; a word
outside the list is refused. `sides` likewise names the sides the table may carry. A
vocabulary is a list of non-empty strings (`classes` may also hold None: a row may leave
its class empty); a bare string, a non-string word or an empty word is refused. Cells are
compared as the text they are written as, so `read_items` accepts what `write_items`
wrote.

**Amounts are float64, refused where a float would change them.** An amount is an int, a
float, a Decimal, a numpy scalar or a plain decimal string (`-1234.5`, `1e+16`; no
grouping, underscores, non-ASCII digits or words). A value a float cannot hold exactly
(an integer beyond 2**53, a Decimal or string with more significant digits than a float
keeps) is refused: round it to the precision it closes to, or give the float.

**Control totals never cross a currency.** The manifest carries `row_count`, counts per
side, and `control_total` as `{side: {unit: total}}` over the rows that carry an amount:
two currencies are two totals. Amounts are stored as the float given (an
FX-translated or allocated item keeps the figure it closes to) and each total is the
correctly rounded sum of those floats (`math.fsum`); only `manifest_md` rounds, for
display.

Stdlib and sibling modules only, except `read_items(..., frame=True)`,
which returns a polars DataFrame.
"""
from __future__ import annotations

import csv
import datetime
import decimal
import io
import math
import os
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import figures  # noqa: E402  sibling: units and number formatting
import periods  # noqa: E402  sibling: the period-key grammar (EVIDENCE.md § 0)
from check_playbook import CHECK_ID  # noqa: E402  sibling: the check-id grammar

__all__ = ["CORE", "write_items", "read_items", "manifest_md", "table_path",
           "ItemsError"]

CORE = ("item_id", "side", "period", "amount", "unit")
REQUIRED = ("item_id", "side")
TABLE = re.compile(r"[a-z0-9][a-z0-9_-]*")        # a table name; matched with fullmatch
# A plain decimal number as a string: sign, digits, point, exponent - nothing else.
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)


class ItemsError(ValueError):
    """A table this module will not write or read as valid."""


def table_path(run_dir, check: str, name: str) -> pathlib.Path:
    """`checks/<check>-<name>.csv` under the run directory. `check` must be a check id
    (`[a-z0-9][a-z0-9_]*`, no `-`) and `name` a lower-case slug (`[a-z0-9][a-z0-9_-]*`),
    each the whole string; anything else is refused."""
    if not isinstance(check, str) or not CHECK_ID.fullmatch(check):
        raise ItemsError(f"check {check!r}: a check id, [a-z0-9][a-z0-9_]* - lower case, "
                         f"no '-', spaces or path separators")
    if not isinstance(name, str) or not TABLE.fullmatch(name):
        raise ItemsError(f"table {name!r}: a lower-case slug, [a-z0-9][a-z0-9_-]* - no "
                         f"spaces, path separators or upper case")
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


def _scalar(v):
    """A numpy scalar as the Python value it holds; anything else unchanged."""
    if not isinstance(v, (str, bytes, int, float)) and hasattr(v, "item"):
        return v.item()
    return v


def _amount(v, unit: str | None, where: str) -> float | None:
    if _empty(v) and _empty(unit):
        return None
    if _empty(v) or _empty(unit):
        raise ItemsError(f"{where}: amount and unit are filled together or both left empty")
    unit = str(unit).lower()
    v = _scalar(v)
    if isinstance(v, bool):
        raise ItemsError(f"{where}: amount {v!r} is not a number")
    if isinstance(v, str):
        if not NUMBER.fullmatch(v.strip()):
            raise ItemsError(f"{where}: amount {v!r} is not a plain decimal number (digits, "
                             f"an optional sign, point and exponent - no grouping, "
                             f"underscores or words)")
        exact = decimal.Decimal(v.strip())
    elif isinstance(v, (int, decimal.Decimal)):
        exact = decimal.Decimal(v)
    elif isinstance(v, float):
        exact = None                               # the float is the value
    else:
        raise ItemsError(f"{where}: amount {v!r} is not a number")
    try:
        x = float(exact) if exact is not None else v
    except (OverflowError, ValueError):
        x = math.inf
    if math.isnan(x) or math.isinf(x):
        raise ItemsError(f"{where}: amount {v!r} is not a finite number")
    if exact is not None and decimal.Decimal(repr(x)) != exact:
        raise ItemsError(f"{where}: amount {v!r} has more digits than a float holds (it "
                         f"would be stored as {x!r}); round it to the precision it closes "
                         f"to, or give the float")
    if unit == "count":
        if x != round(x):
            raise ItemsError(f"{where}: a count of {v!r} is not whole")
        return float(round(x))
    return x


def _period(v, where: str) -> str | None:
    """The period as written: a period key (EVIDENCE.md § 0) or an ISO date; a
    `datetime.date` becomes its ISO date. A datetime, padded text or anything else is
    refused."""
    v = _scalar(v)
    if _empty(v):
        return None
    if isinstance(v, datetime.datetime):
        raise ItemsError(f"{where}: period {v!r} is a datetime - give its date or a period "
                         f"key")
    if isinstance(v, datetime.date):
        return v.isoformat()
    if isinstance(v, str) and v == v.strip():
        if ISO_DATE.fullmatch(v):
            try:
                datetime.date.fromisoformat(v)
                return v
            except ValueError:
                pass
        else:
            try:
                periods.check_key(v)
                return v
            except ValueError:
                pass
    raise ItemsError(f"{where}: period {v!r} is neither a period key ({periods.GRAMMAR}) nor "
                     f"an ISO date (`YYYY-MM-DD`)")


def _vocab(v, what: str, allow_none: bool = False) -> set | None:
    """A declared vocabulary as a set of words; a bare string, a non-string word or an
    empty word is refused (None, for `classes`, lets a row leave the column empty)."""
    if v is None:
        return None
    if isinstance(v, (str, bytes, dict)) or not hasattr(v, "__iter__"):
        raise ItemsError(f"`{what}` is a list of words, got {v!r}")
    words = list(v)
    bad = [w for w in words if not ((w is None and allow_none)
                                    or (isinstance(w, str) and w.strip() == w and w))]
    if bad:
        raise ItemsError(f"`{what}` holds {bad}: each word is a non-empty string with no "
                         f"surrounding spaces" + (" (or None: a row may leave it empty)"
                                                  if allow_none else ""))
    return set(words)


def _check(rows: list[dict], extensions, classes, class_column, sides) -> list[str]:
    """Validate rows against the core and the declared extensions; return the column list."""
    ext = list(extensions or ())
    clash = [c for c in ext if c in CORE]
    if clash:
        raise ItemsError(f"extension(s) {clash} are core columns; declare only the others")
    if len(set(ext)) != len(ext):
        raise ItemsError(f"extensions repeat a name: {ext}")
    bad = [c for c in ext if not isinstance(c, str) or not c.strip()]
    if bad:
        raise ItemsError(f"extension names are non-empty strings: {bad}")
    if classes is not None and class_column not in ext:
        raise ItemsError(f"`classes` given but `{class_column}` is not a declared extension")
    class_words = _vocab(classes, "classes", allow_none=True)
    side_words = _vocab(sides, "sides")
    columns = [*CORE, *ext]
    allowed = set(columns)
    seen: set[str] = set()
    for i, r in enumerate(rows, 1):
        where = f"row {i} ({r.get('item_id', '?')})"
        extra = sorted(map(str, set(r) - allowed))
        if extra:
            raise ItemsError(f"{where}: undeclared column(s) {extra} - declare them in "
                             f"`extensions` or drop them")
        for c in REQUIRED:
            if _empty(r.get(c)):
                raise ItemsError(f"{where}: core column `{c}` is empty")
        iid = _cell(r["item_id"])
        if iid in seen:
            raise ItemsError(f"{where}: item_id {iid!r} appears twice - one row per item")
        seen.add(iid)
        unit = None if _empty(r.get("unit")) else str(r["unit"]).lower()
        if unit is not None and unit not in figures.UNITS:
            raise ItemsError(f"{where}: unit {r['unit']!r} is not a figures unit "
                             f"(a currency code, or one of {', '.join(figures.OTHER_UNITS)})")
        _period(r.get("period"), where)
        if side_words is not None and _cell(r["side"]) not in side_words:
            raise ItemsError(f"{where}: side {r['side']!r} is not one of {list(sides)}")
        if class_words is not None:
            word = None if _empty(r.get(class_column)) else _cell(r.get(class_column))
            if word not in class_words:
                raise ItemsError(f"{where}: {class_column} {r.get(class_column)!r} is not in "
                                 f"the declared vocabulary {list(classes)}")
    return columns


def _cell(v) -> str:
    """A cell as it is written: a float (numpy's included) as its shortest round-trip
    form, a date as its ISO date, anything else as `str`."""
    v = _scalar(v)
    return "" if v is None else repr(float(v)) if isinstance(v, float) else str(v)


def _totals(rows: list[dict]) -> tuple[dict, dict]:
    """Rows per side and `{side: {unit: total}}`, each total the correctly rounded sum of
    the amounts' floats (`fsum`), never rounded further."""
    counts: dict[str, int] = {}
    parts: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        side = _cell(r["side"])
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
    Refuses, writing nothing, on a check id or table name outside their grammars
    (`table_path`), an undeclared column, an empty `item_id` or `side`, a repeated
    `item_id` (as written), an amount that is not a number a float holds as given, an
    amount without a unit or a unit without an amount, a unit outside figures.UNITS, a
    period that is neither a period key nor an ISO date, a vocabulary that is not a list
    of words, a side outside `sides`, a class outside `classes`, `keys` that are not a
    list of names, `citations` that are not `{side: [E. ids]}` (a side outside `sides`
    included), or a `closes` that is not a non-empty string."""
    path = table_path(run_dir, check, name)
    rows = _rows(rows)
    columns = _check(rows, extensions, classes, class_column, sides)
    if keys is not None:
        if isinstance(keys, (str, bytes, dict)) or not hasattr(keys, "__iter__"):
            raise ItemsError(f"`keys` is a list of the column names matched on, got {keys!r}")
        keys = list(keys)
        if not all(isinstance(k, str) and k.strip() for k in keys):
            raise ItemsError(f"`keys` is a list of the column names matched on, got {keys!r}")
    cites = {} if citations is None else citations
    if not isinstance(cites, dict) or not all(
            isinstance(s, str) and s and isinstance(ids, (list, tuple))
            and all(isinstance(x, str) and x.startswith("E.") and x == x.strip() for x in ids)
            for s, ids in cites.items()):
        raise ItemsError(f"`citations` is {{side: [E. ids]}}, got {citations!r}")
    side_words = _vocab(sides, "sides")
    if side_words is not None and set(cites) - side_words:
        raise ItemsError(f"`citations` names side(s) {sorted(set(cites) - side_words)} "
                         f"outside `sides` {list(sides)}")
    if closes is not None and (not isinstance(closes, str) or not closes.strip()):
        raise ItemsError(f"`closes` is a figure id or a sentence, got {closes!r}")
    clean = []
    for i, r in enumerate(rows, 1):
        where = f"row {i} ({r['item_id']})"
        c = {k: r.get(k) for k in columns}
        c["period"] = _period(r.get("period"), where)
        c["amount"] = _amount(r.get("amount"), r.get("unit"), where)
        c["unit"] = None if c["amount"] is None else str(r["unit"]).lower()
        if classes is not None and _empty(c.get(class_column)):
            c[class_column] = None                 # an empty class is written empty
        clean.append(c)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    for c in clean:
        w.writerow({k: _cell(v) for k, v in c.items()})
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    tmp = pathlib.Path(tmpname)
    try:
        tmp.write_text(buf.getvalue(), encoding="utf-8")
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    counts, totals = _totals(clean)
    rel = path.relative_to(pathlib.Path(run_dir)).as_posix()
    return {"table": rel, "columns": columns, "row_count": len(clean), "sides": counts,
            "control_total": totals, "keys": list(keys or []),
            "citations": {s: list(ids) for s, ids in cites.items()}, "closes": closes}


def read_items(run_dir, check: str, name: str, *, extensions=None, classes=None,
               class_column: str = "class", sides=None, frame: bool = False):
    """The rows of `checks/<check>-<name>.csv`, validated as `write_items` writes them:
    the core columns present once each, `item_id` and `side` filled, `item_id` unique,
    amounts numbers, periods period keys or ISO dates. `extensions`, when given, must be
    the table's other columns (in any order, each once); `classes` / `sides` re-check the
    vocabulary. Every cell is text, or None where empty, and `amount` a float.
    `frame=True` returns a polars DataFrame with every column of the table — `amount`
    Float64, the rest String — whatever its row count."""
    path = table_path(run_dir, check, name)
    if not path.is_file():
        raise ItemsError(f"{path}: no such item table")
    with path.open(encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        header = list(rd.fieldnames or [])
        raw = list(rd)
    if len(set(header)) != len(header):
        raise ItemsError(f"{path.name}: the header repeats a column: {header}")
    missing = [c for c in CORE if c not in header]
    if missing:
        raise ItemsError(f"{path.name}: core column(s) {missing} missing - not an item table")
    ext = [c for c in header if c not in CORE]
    if extensions is not None:
        want = list(extensions)
        if len(set(want)) != len(want) or set(want) != set(ext):
            raise ItemsError(f"{path.name}: extensions {ext} are not the declared {want}")
    rows = [{k: (v if v != "" else None) for k, v in r.items()} for r in raw]
    _check(rows, ext, classes, class_column, sides)
    for i, r in enumerate(rows, 1):
        r["amount"] = _amount(r["amount"], r["unit"], f"{path.name} row {i}")
        r["unit"] = None if r["amount"] is None else r["unit"].lower()
    if frame:
        import polars as pl
        return pl.DataFrame(rows, schema={c: pl.Float64 if c == "amount" else pl.String
                                          for c in header})
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
