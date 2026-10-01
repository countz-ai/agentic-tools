#!/usr/bin/env python3
"""The formulas a workbook of this plugin carries, read, evaluated and cached.

A schedule's arithmetic is live in the workbook: a subtotal, a total and a walk's
derived line (`= …`) are formulas over the rows they add, a figure copied from another
check's tab is a reference to the cell it came from, and the Exec Summary's copies are
references too (WORKBOOK.md § 7). Body rows stay values — they come from the data room,
which the workbook does not hold, and their reperformance is the Sources tab's.

Three callers, one grammar: `wbkit.total()` checks the formula it writes against the
figure the tab script computed, `link_workbook.py` writes references and footing formulas
at assembly, and `check_workbook.py` recomputes every formula it can read from the stored
results and refuses one whose cached result disagrees. The grammar is the forms those
writers produce, and nothing wider:

    ='q6 EBITDA bridge'!F12          a reference, on this sheet or another
    =SUM(G5:G9)  =SUM(G5,G7:G8)      a sum of cells and ranges
    =G5+G6-G7                        a signed sum of references
    =SUMIFS(G10:G11,$N$10:$N$11,"supported")+SUMIFS(…)   a conditional sum over a column

`evaluate()` returns None for anything outside it; a caller never guesses.

openpyxl saves a formula with an empty result, which a viewer that does not recalculate
shows blank (check_workbook.py GATE 1). `cache_results()` writes the results into the
saved file. Stdlib only, so the gates import it.
"""
from __future__ import annotations

import html
import pathlib
import re
import zipfile

COORD = re.compile(r"^\$?([A-Z]{1,3})\$?(\d+)$")
_SHEET = r"(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_.]*))!"
_CELL = r"\$?[A-Z]{1,3}\$?\d+"
TOKEN = re.compile(
    rf"\s*(?:(?P<func>SUMIFS|SUM)\(|(?P<ref>(?:{_SHEET})?{_CELL}(?::{_CELL})?)"
    rf"|(?P<num>\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)|(?P<str>\"(?:[^\"]|\"\")*\")|(?P<op>[-+,)]))")


def col_num(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def col_letters(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def split(coord: str) -> tuple[int, int]:
    """(column, row) of `G23` (or `$G$23`)."""
    m = COORD.match(coord.strip())
    if not m:
        raise ValueError(f"not a cell reference: {coord!r}")
    return col_num(m.group(1)), int(m.group(2))


def quote(sheet: str) -> str:
    """A sheet name as a formula writes it: always quoted, inner quotes doubled."""
    return "'" + sheet.replace("'", "''") + "'"


def reference(sheet: str, coord: str) -> str:
    return f"={quote(sheet)}!{coord}"


def sum_formula(col: str, rows: list[int]) -> str:
    """`=SUM(G5:G9)` over one contiguous run of rows, `=SUM(G5,G7,G9)` otherwise."""
    rows = sorted(set(rows))
    if not rows:
        raise ValueError("a sum over no rows")
    if rows == list(range(rows[0], rows[-1] + 1)) and len(rows) > 1:
        return f"=SUM({col}{rows[0]}:{col}{rows[-1]})"
    return "=SUM(" + ",".join(f"{col}{r}" for r in rows) + ")"


def signed_formula(col: str, plus: list[int], minus: list[int] = ()) -> str:
    """`=G5+G6-G7`: a walk whose deductions are stored as positive figures. A plain sum
    when nothing is deducted."""
    if not minus:
        return sum_formula(col, plus)
    terms = [(r, "+") for r in plus] + [(r, "-") for r in minus]
    terms.sort()
    out = "".join(f"{sign}{col}{r}" for r, sign in terms)
    return "=" + out.lstrip("+")


def _tokens(text: str):
    pos = 0
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip() == "":
                return
            raise ValueError(f"cannot read the formula at {text[pos:pos + 20]!r}")
        pos = m.end()
        if m.group("func"):
            yield "func", m.group("func")
        elif m.group("ref"):
            yield "ref", m.group("ref")
        elif m.group("num"):
            yield "num", float(m.group("num"))
        elif m.group("str"):
            yield "str", m.group("str")[1:-1].replace('""', '"')
        else:
            yield "op", m.group("op")


def _cells(ref: str, sheet: str) -> list[tuple[str, str]]:
    """[(sheet, coord)] a reference or a range names."""
    m = re.match(rf"^(?:{_SHEET})?({_CELL})(?::({_CELL}))?$", ref)
    if not m:
        raise ValueError(f"not a reference: {ref!r}")
    sh = (m.group(1).replace("''", "'") if m.group(1) else m.group(2)) or sheet
    a = m.group(3).replace("$", "")
    b = (m.group(4) or m.group(3)).replace("$", "")
    (c1, r1), (c2, r2) = split(a), split(b)
    return [(sh, f"{col_letters(c)}{r}") for r in range(min(r1, r2), max(r1, r2) + 1)
            for c in range(min(c1, c2), max(c1, c2) + 1)]


def _num(v) -> float:
    """A cell as a sum reads it: a number counts, text and blanks are nothing."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def evaluate(formula: str, sheet: str, get) -> float | None:
    """The value of `formula` on `sheet`, reading every cell it names through
    `get(sheet, coord)` (a number, a string or None); None for a formula outside the
    grammar this module writes."""
    text = formula.strip()
    if text.startswith("="):
        text = text[1:]
    try:
        toks = list(_tokens(text))
    except ValueError:
        return None
    i = 0

    def args() -> list[list]:
        nonlocal i
        out, cur = [], []
        while i < len(toks):
            kind, v = toks[i]
            i += 1
            if kind == "op" and v == ")":
                out.append(cur)
                return out
            if kind == "op" and v == ",":
                out.append(cur)
                cur = []
                continue
            cur.append((kind, v))
        raise ValueError("unclosed call")

    def term():
        nonlocal i
        kind, v = toks[i]
        i += 1
        if kind == "num":
            return v
        if kind == "ref":
            cells = _cells(v, sheet)
            if len(cells) != 1:
                raise ValueError("a range outside a sum")
            return _num(get(*cells[0]))
        if kind == "func":
            parts = args()
            if v == "SUM":
                total = 0.0
                for p in parts:
                    if len(p) != 1:
                        raise ValueError("SUM takes cells, ranges and numbers")
                    pk, pv = p[0]
                    if pk == "num":
                        total += pv
                    elif pk == "ref":
                        total += sum(_num(get(*c)) for c in _cells(pv, sheet))
                    else:
                        raise ValueError("SUM of text")
                return total
            if len(parts) < 3 or len(parts) % 2 == 0 or any(len(p) != 1 for p in parts):
                raise ValueError("SUMIFS(sum range, criteria range, criterion, …)")
            values = _cells(parts[0][0][1], sheet)
            keep = [True] * len(values)
            for k in range(1, len(parts), 2):
                crit = _cells(parts[k][0][1], sheet)
                want = parts[k + 1][0][1]
                if len(crit) != len(values):
                    raise ValueError("SUMIFS ranges of different sizes")
                keep = [kp and str(get(*c) if get(*c) is not None else "").strip().lower()
                        == str(want).strip().lower() for kp, c in zip(keep, crit)]
            return sum(_num(get(*c)) for c, kp in zip(values, keep) if kp)
        if kind == "op" and v in "+-":
            t = term()
            return -t if v == "-" else t
        raise ValueError(f"unexpected {v!r}")

    try:
        total = term()
        while i < len(toks):
            kind, v = toks[i]
            i += 1
            if kind != "op" or v not in "+-":
                return None
            t = term()
            total = total + t if v == "+" else total - t
        return total
    except (ValueError, IndexError):
        return None


def precedents(formula: str, sheet: str) -> list[tuple[str, str]] | None:
    """Every (sheet, coord) `formula` reads, or None outside the grammar."""
    text = formula.strip().lstrip("=")
    try:
        return [c for kind, v in _tokens(text) if kind == "ref" for c in _cells(v, sheet)]
    except ValueError:
        return None


def decimals(v) -> int:
    """The decimals a stored number carries (`2316941.25` two, `0.6154252322` ten), at
    most nine."""
    r = repr(float(v))
    if "e" in r or "E" in r:
        return 9
    return min(len(r.split(".")[1].rstrip("0")) if "." in r else 0, 9)


def foots(expected: float, got: float, n_terms: int, values=()) -> bool:
    """Whether a total agrees with what its terms add to. A writer may have rounded each
    term and the total at the precision they are stored to — cents for `2316941.25`,
    nothing for whole numbers — so the allowance is half that unit per term, and float
    noise; never more. `values` are the terms and the total as stored."""
    d = max([decimals(v) for v in list(values) + [expected] if v] or [0])
    slack = 0.5 * 10.0 ** -d * (n_terms + 1) if 0 < d < 9 else 0.0
    return abs(expected - got) <= slack + 1e-9 * max(1.0, abs(expected))


def compute_results(wb, known: dict[str, dict[str, float]] | None = None,
                    fallback=None) -> dict[str, dict[str, float]]:
    """{sheet: {coord: result}} for every formula of an openpyxl workbook `wb` loaded with
    formulas, computed from its values — a formula reading another formula's cell, on any
    sheet, is computed after it. `known` seeds results already established (the kit's);
    `fallback` is the same workbook loaded with `data_only=True`, whose cached result
    stands for a formula outside this module's grammar. A formula neither computes nor
    falls back on is left out: check_workbook.py GATE 1 names it."""
    pending: dict[tuple[str, str], str] = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.data_type == "f" and isinstance(c.value, str):
                    pending[(ws.title, c.coordinate)] = c.value
    done: dict[tuple[str, str], float] = {}
    for sh, cells in (known or {}).items():
        for co, v in cells.items():
            if (sh, co) in pending and isinstance(v, (int, float)):
                done[(sh, co)] = float(v)
    names = set(wb.sheetnames)

    class _Pending(Exception):
        pass

    def get(sh, co):
        if (sh, co) in pending:
            if (sh, co) in done:
                return done[(sh, co)]
            raise _Pending
        if sh not in names:
            return None
        return wb[sh][co].value

    changed = True
    while changed:
        changed = False
        for key, f in pending.items():
            if key in done:
                continue
            try:
                got = evaluate(f, key[0], get)     # a getter's _Pending passes through it
            except _Pending:
                continue
            if got is not None:
                done[key] = got
                changed = True
    out: dict[str, dict[str, float]] = {}
    for (sh, co) in pending:
        v = done.get((sh, co))
        if v is None and fallback is not None and sh in fallback.sheetnames:
            fv = fallback[sh][co].value
            v = float(fv) if isinstance(fv, (int, float)) and not isinstance(fv, bool) else None
        if v is not None:
            out.setdefault(sh, {})[co] = v
    return out


# --- results into a saved workbook ----------------------------------------------------
_REL = re.compile(r"<Relationship\b[^>]*/?>")
_ATTR = lambda name: re.compile(rf'\b{name}="([^"]*)"')  # noqa: E731


def sheet_parts(z: zipfile.ZipFile) -> dict[str, str]:
    """{sheet name: worksheet part} in the stored workbook."""
    wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
    rels = {}
    for el in _REL.findall(z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "replace")):
        rid, target = _ATTR("Id").search(el), _ATTR("Target").search(el)
        if rid and target:
            rels[rid.group(1)] = target.group(1)
    out = {}
    for el in re.findall(r"<sheet\b[^>]*/?>", wb):
        name, rid = _ATTR("name").search(el), _ATTR("r:id").search(el)
        if name and rid and rid.group(1) in rels:
            out[html.unescape(name.group(1))] = "xl/" + rels[rid.group(1)].lstrip("/").removeprefix("xl/")
    return out


_FCELL = re.compile(r'(<c\b[^>]*\br="([A-Z]+\d+)"[^>]*>)<f>(.*?)</f>(?:<v\s*/>|<v>[^<]*</v>)?</c>', re.S)


def cache_results(path: pathlib.Path, results: dict[str, dict[str, float]]) -> int:
    """Write each formula's result into its cell's `<v>`, per sheet name. The zip is
    rewritten whole, every other part as it was. Returns the cells written."""
    path = pathlib.Path(path)
    results = {k: v for k, v in results.items() if v}
    if not results:
        return 0
    with zipfile.ZipFile(path) as z:
        parts = {p: results[name] for name, p in sheet_parts(z).items() if name in results}
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    written = 0

    def filler(values: dict[str, float]):
        def fill(m: re.Match) -> str:
            nonlocal written
            ref = m.group(2)
            if ref not in values:
                return m.group(0)
            written += 1
            return f"{m.group(1)}<f>{m.group(3)}</f><v>{float(values[ref])!r}</v></c>"
        return fill

    tmp = path.with_suffix(".caching.xlsx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for info, data in items:
            if info.filename in parts:
                data = _FCELL.sub(filler(parts[info.filename]), data.decode("utf-8")).encode("utf-8")
            out.writestr(info, data)
    tmp.replace(path)
    return written
