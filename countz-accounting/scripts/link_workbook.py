#!/usr/bin/env python3
"""Wire every id in the workbook to the cell where it resolves.

The reader follows a number by its id, and the follow must terminate in ONE hop: a figure
id resolves on the Sources tab, whose row carries the flattened reperformance recipe; an
evidence id resolves on the Evidence tab, whose row carries the columns, filter and
control total that re-select the same rows. Before this pass those hops are Ctrl+F; after
it they are clicks. The workbook stays byte-equivalent as text — a hyperlink adds no
characters to the cell, so a preview pane, pandas or a printout shows exactly what it
showed before.

What gets wired, in this order:

  1. A cell that is exactly one ledger-tab id — figure or population (`F.`, `P.`) off the
     Sources tab, evidence (`E.`) off the Evidence tab — links to its ledger row.
  2. That id's cell in the ledger's id column links back to the first cell that cites it
     (first exact-id cell in tab order off the ledger). An id nothing cites keeps no
     back-link.
  3. A cell that is exactly one id of any other prefix (`T.`, `RI.`, `S.`, `X.`, `C.`,
     `D.`, `Q.` — and `E.` in a workbook with no Evidence tab) links to the id's HOME:
     the first cell with a line that begins with the id and continues (the
     definition-prose form, e.g. an exception stated as "X.c4.…. The account is …"), or
     failing that the first exact-id cell in tab order. Definition prose outranks a bare
     citation cell — the reader clicking an id wants the statement, not another citation.
     The home itself is not linked to itself.
  4. A cell that is exactly one family stem written with placeholders (`F.q6.sbc.<year>`,
     the schedule-row form covering several period columns) links to the first ledger row
     of its family — the placeholder matches one id segment. A stem no id matches stays
     text.
  5. A cell that NAMES a check links to that check's tab — the whole cell is the check id
     ("q1_fy2021", the Coverage and Basis of Preparation table form), or the id opens it ahead of a
     separator ("Q6 · the EBITDA bridge"). Tab name and check id are compared on the fold
     (lower-case, runs of punctuation to one `_`), because a check writes its own tab
     name and both forms occur in one workbook: `Q2 billings detail` IS
     `q2_billings_detail`. Only a check tab is a target — the run-level tabs are named in
     prose and in column headers throughout, and a header reading "Evidence" is not a
     pointer to that tab. Two tabs on one fold, no link.
  6. Every AMOUNT on the Exec Summary links to the cell it was copied from, and becomes a
     formula reading it: `='q6 EBITDA bridge'!F12`, its result cached in the sheet XML so
     a viewer that does not recalculate still shows it (check_workbook.py GATE 1). The
     Exec Summary mints no figure, so each number there has an original on a check's tab;
     a formula makes that visible in the formula bar, and an accountant tracing
     precedents lands on the original. The table's title declares that tab
     (`from: <tab>`), and the amount is found by the row's leading label and the column's
     header, both copied verbatim. An amount that matches nothing is reported and left —
     check_workbook.py refuses an unlinked number on the Exec Summary, because the fix is
     copying the label, not linking. These cells take the link color and no underline:
     under a figure, an underline is the accounting rule that reads "sum above".

  8. The arithmetic between the check tabs is made live (WORKBOOK.md § 7). With
     `--run-dir`, each tab's cells map (`out/tabs/<check>.cells.json`, `wbkit.save`)
     says which cell holds which figure and which cells copy another check's figure: each
     copy becomes a reference to the cell holding it (`='r5 Position and DSO'!G23`),
     refused — left a value and reported — when the two disagree. A tab written before the
     map existed is retrofitted on evidence alone: a total, a subtotal or a walk's derived
     line (`= …`) becomes a formula over the rows above it when one plain reading of
     those rows adds to it exactly; a figure becomes a reference when its value, to the
     cent, sits in exactly one cell of an earlier check's tabs under a header naming the
     same period. Anything less certain stays a value and is listed. Last, every
     formula's result is computed (scripts/formula.py) and cached, since a load and save
     by openpyxl stores none.

  7. On a match summary (scripts/match_tabs.py), each line's status words link to that
     status's rows on its match schedule: the link selects the block, which the schedule
     holds together because it is sorted by status. A hyperlink cannot apply a filter; the
     selected block is the filter's rows, and check_workbook.py holds the line to them.

Every link carries the cell's own text as its `display` attribute, so a consumer that
renders the anchor from link metadata instead of the cell shows the same readable text.

An id that has no home anywhere — cited only mid-sentence, stated nowhere — is a dead end.
This pass reports dead ends and leaves them; `check_workbook.py` refuses them, because the
fix is authoring (state the id on its ledger or its owning tab), not linking. Exempt:
`C.` review-finding ids, whose record lives in the run's review step by design and is the
user's to open, not the reader's.

Citations to the user's files are NEVER made file links: a mailed workbook keeps no path
to the data room, and a `file://` target rots the moment the deliverable leaves the
machine. They stay text — file · sheet · range.

The id grammar and the home rule are mirrored in check_workbook.py's link gate; a change
here changes both files.

Usage:
    link_workbook.py <workbook.xlsx> [--run-dir DIR] [--dry-run] [--json]
Exit 0 on success (dead ends included — the gate owns refusal), 2 on a usage error or a
workbook with no Sources tab.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from copy import copy

# One id token. Mirrors check_workbook.py ID_TOKEN — change both. The second alternative
# demands two characters after the prefix dot so prose abbreviations ("E.g", "P.O") do
# not match; the first admits pure serials ("D.3", "S.1").
ID_TOKEN = re.compile(
    r"\b(?:RI|[EFPTSXCDQ])\.(?:\d+|[A-Za-z0-9_][A-Za-z0-9_.-]*[A-Za-z0-9])")
# A family stem: id segments with at least one <placeholder> segment. Whole-cell only.
STEM_SEG = r"(?:[A-Za-z0-9_-]+|<[A-Za-z0-9_]+>)"
STEM_CELL = re.compile(rf"(?:RI|[EFPTSXCDQ])\.{STEM_SEG}(?:\.{STEM_SEG})*")

SOURCES = "Sources"
EVIDENCE = "Evidence"
EXEC = "Exec Summary"
# The workbook's run-level tabs (check-report SKILL § 1), on the fold. Every other tab
# belongs to a check.
RUN_TABS = {"exec_summary", "basis_of_preparation", "coverage", "open_items", "sources", "evidence"}
# Which ledger tab an id prefix resolves on. Every other prefix homes where it is stated.
LEDGER = {"F": SOURCES, "P": SOURCES, "E": EVIDENCE}
LINK_COLOR = "0A5F6A"   # WORKBOOK_STYLE.md § 1a `ACCENT`; the cell keeps its own font
# The navigable form of a row: the whole cell is a check id ("q6_ebitda_bridge", the
# Coverage and Basis of Preparation table form), or the id opens the cell ahead of a separator
# ("Q6 · the EBITDA bridge", the prose form).
NAV = re.compile(r"^([^\s·—–]+(?:[ _-][^\s·—–]+)*?)(?:\s*[·—–]\s.*)?$", re.S)


def normalize(name: str) -> str:
    """A tab name is a display form of a check id: `Q2 billings detail` and
    `q2_billings_detail` are the same check. Compare on the fold, never on the literal —
    a check writes its own tab name and the two forms both occur in one workbook."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def is_stem(value: str, m: re.Match) -> bool:
    """A token immediately followed by `.<` is a family stem written with a placeholder
    (`T.foot.<month>`), not an id."""
    return value[m.end():m.end() + 2] == ".<"


def exact_id(value) -> str | None:
    """The id, when the cell's whole value is one id token and nothing else."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    m = ID_TOKEN.fullmatch(s)
    return m.group(0) if m else None


def whole_cell_stem(value) -> str | None:
    """The stem, when the cell's whole value is one placeholder family stem."""
    if not isinstance(value, str):
        return None
    s = value.strip()
    m = STEM_CELL.fullmatch(s)
    return s if m and "<" in s else None


def family_regex(stem: str) -> re.Pattern:
    """A placeholder matches exactly one id segment (no dots)."""
    parts = re.split(r"(<[A-Za-z0-9_]+>)", stem)
    return re.compile("".join(
        r"[A-Za-z0-9_-]+" if p.startswith("<") else re.escape(p)
        for p in parts if p) + r"\Z")


def line_starts(value: str):
    """Ids that begin a line of the cell AND are followed by more text on that line —
    the definition-prose form. A line that IS the id is an exact cell, handled apart."""
    for line in value.split("\n"):
        line = line.strip()
        m = ID_TOKEN.match(line)
        if m and len(line) > len(m.group(0)) and not is_stem(line, m):
            yield m.group(0)


def scan(wb):
    """One pass over every string cell. Returns (exact_cells, line_homes, tokens, stems):
    exact_cells[id] = [(sheet, coord), …] in tab order;
    line_homes[id]  = first (sheet, coord) whose line begins the id, in tab order;
    tokens[id]      = first (sheet, coord) where the id appears at all;
    stems[(sheet, coord)] = the stem, for cells that are exactly one placeholder stem."""
    exact_cells: dict[str, list[tuple[str, str]]] = {}
    line_homes: dict[str, tuple[str, str]] = {}
    tokens: dict[str, tuple[str, str]] = {}
    stems: dict[tuple[str, str], str] = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if not isinstance(v, str):
                    continue
                at = (ws.title, cell.coordinate)
                one = exact_id(v)
                if one:
                    exact_cells.setdefault(one, []).append(at)
                st = whole_cell_stem(v)
                if st:
                    stems[at] = st
                for i in line_starts(v):
                    line_homes.setdefault(i, at)
                for m in ID_TOKEN.finditer(v):
                    if not is_stem(v, m):
                        tokens.setdefault(m.group(0), at)
    return exact_cells, line_homes, tokens, stems


def resolve(exact_cells, line_homes, tokens, sheets):
    """target[(sheet, coord)] = (sheet, coord) to link to; the dead-end list; the
    run-internal `C.` references left as text; homes[id] = where each id resolves — the
    cell that is the id, else the line of prose that opens with it.
    Mirrors check_workbook.py — change both."""
    targets: dict[tuple[str, str], tuple[str, str]] = {}
    dead: list[str] = []
    internal: list[str] = []
    homes: dict[str, tuple[str, str]] = {}
    ledger_row: dict[str, tuple[str, str]] = {}
    for i, cells in exact_cells.items():
        tab = LEDGER.get(i.split(".")[0])
        if tab and tab in sheets:
            on_ledger = [c for c in cells if c[0] == tab]
            if on_ledger:
                ledger_row[i] = on_ledger[0]
    for i in sorted(tokens):
        cells = exact_cells.get(i, [])
        ledger = LEDGER.get(i.split(".")[0])
        if ledger and ledger in sheets:
            home = ledger_row.get(i)
            if home is None:
                dead.append(i)
                continue
            homes[i] = home
            for at in cells:
                if at[0] != ledger:
                    targets[at] = home
            cited = [c for c in cells if c[0] != ledger]
            if cited:
                targets[home] = cited[0]
        else:
            # The cell that IS the id declares it; a line of prose that merely opens with
            # the id is a mention. Measured: an exception id linked to the caveat cell of
            # another figure's Sources row, which resolves nothing.
            home = (cells[0] if cells else None) or line_homes.get(i)
            if home is None:
                (internal if i.startswith("C.") else dead).append(i)
                continue
            homes[i] = home
            for at in cells:
                if at != home:
                    targets[at] = home
    return targets, dead, internal, homes


# A table on the Exec Summary declares the tab it was copied from with an explicit marker
# in its title: `from: <tab>` — the tab's full name or its token (`EBITDA bridge · from:
# q6`), running to the end of the title or a closing bracket (REPORT.md § 2). The marker is
# the plugin's own syntax, so the declaration never rests on an English word in a title.
# A marker naming no tab, or two, declares nothing.
LABEL_COLS = 4
SOURCE_MARKER = re.compile(r"(?:^|[\s(\[·—–-])from:\s*(?P<tab>[^)\]]+?)\s*(?:[)\]]|$)")


def _tab_named(name: str, sheets) -> list[str]:
    name = name.strip().strip("`'\"")
    return [t for t in sheets if t != EXEC and (t == name or normalize(t) == normalize(name)
                                                 or normalize(t.split(" ")[0]) == normalize(name))]


def declared_source(text: str, sheets) -> str | None:
    m = SOURCE_MARKER.search(text or "")
    if not m:
        return None
    hits = _tab_named(m.group("tab"), sheets)
    return hits[0] if len(hits) == 1 else None


def sheet_grid(ws):
    """(headers_at, labels, row_texts, numerics) for one sheet.

    headers_at[row][column] is the nearest text at-or-above that row in that column — a
    tab carries several header bands (a bridge, then its information block), so a
    column's header is positional, never one row for the whole tab. labels[row] is the
    row's leading text cell; row_texts[row] is its text in the first LABEL_COLS columns;
    numerics[row] = [(column, coord)]."""
    headers_at, labels, row_texts, numerics = {}, {}, {}, {}
    hdr: dict[int, str] = {}
    for row in ws.iter_rows():
        if not row:
            continue
        r = row[0].row
        nums = []
        for cell in row:
            v = cell.value
            # A formula cell is an amount, never a header — the walk's own subtotals are
            # conditional sums, and reading one as text would make a subtotal row the
            # header of every column below it. Test the stored TYPE, not the text: a walk
            # label reads "= Reported EBITDA" and is a string.
            if cell.data_type != "f" and isinstance(v, str) and v.strip():
                hdr[cell.column] = v.strip()
                labels.setdefault(r, v.strip())
                if cell.column <= LABEL_COLS:
                    row_texts.setdefault(r, set()).add(v.strip())
            elif cell.data_type == "f" or (isinstance(v, (int, float))
                                           and not isinstance(v, bool)):
                nums.append((cell.column, cell.coordinate))
        headers_at[r] = dict(hdr)
        if nums:
            numerics[r] = nums
    return headers_at, labels, row_texts, numerics


# A match summary and its schedule, by the marker their B1 carries after the token;
# mirrors match_tabs.py and check_workbook.py — change all three.
SUMMARY_MARK = " · Match summary"
SCHEDULE_MARK = " · Match schedule"


def match_targets(wb):
    """targets[(summary, C<row>)] = (schedule, "B<first>:<last col><last>") for every line
    of every match summary whose status the schedule carries."""
    sums, schs = {}, {}
    for ws in wb.worksheets:
        b1 = ws["B1"].value
        if not isinstance(b1, str):
            continue
        if SUMMARY_MARK in b1:
            sums[b1.split(SUMMARY_MARK)[0].strip()] = ws.title
        elif SCHEDULE_MARK in b1:
            schs[b1.split(SCHEDULE_MARK)[0].strip()] = ws.title
    targets = {}
    for tok, summ in sums.items():
        sched = schs.get(tok)
        if sched is None:
            continue
        sh = wb[sched]
        col = {c.value: c.column for c in sh[4] if isinstance(c.value, str)}.get("Status")
        if col is None:
            continue
        last = sh.cell(4, sh.max_column).column_letter
        blocks = {}
        r = 5
        while True:
            word = sh.cell(r, col).value
            if not isinstance(word, str) or not word.strip():
                break                     # the Total row, or the table's end
            blocks.setdefault(word, [r, r])[1] = r
            r += 1
        ws = wb[summ]
        r = 5
        while any(ws.cell(r, c).value is not None for c in range(2, 8)):
            word = ws.cell(r, 3).value
            if word in blocks:
                a, b = blocks[word]
                targets[(summ, f"C{r}")] = (sched, f"B{a}:{last}{b}")
            r += 1
    return targets


#: Where a navigation link lands: the tab's title cell. Column A is an empty margin and
#: the title is B1 (reference/WORKBOOK_STYLE.md § 4); the link gate refuses a link that
#: lands on an empty cell.
TITLE_CELL = "B1"
def walk_targets(wb):
    """targets[(Exec Summary, coord)] = (source tab, coord) for every amount on the Exec
    Summary's tables, and the amounts that matched no source cell.

    The Exec Summary mints no figure: every number on it is copied from a check's tab, and
    the copy points back at what it was copied from. The match is the row's own leading
    label and the column's own header, both copied verbatim — so the wiring follows from
    copying the table, and no author states a coordinate (check-report SKILL § 1)."""
    targets: dict[tuple[str, str], tuple[str, str]] = {}
    missed: list[tuple[str, str, str]] = []
    if EXEC not in wb.sheetnames:
        return targets, missed
    ws = wb[EXEC]
    headers_at, labels, _, numerics = sheet_grid(ws)
    cache: dict[str, tuple] = {}
    src = None
    for r in sorted(headers_at):
        found = declared_source(labels.get(r, ""), wb.sheetnames)
        if found:
            src = found
        if r not in numerics or src is None:
            continue
        if src not in cache:
            cache[src] = sheet_grid(wb[src])
        s_headers, _, s_texts, _ = cache[src]
        label = labels.get(r, "")
        row_at = next((sr for sr in sorted(s_texts) if label in s_texts[sr]), None)
        for col, coord in numerics[r]:
            head = headers_at.get(r, {}).get(col)
            hit = next((c for c, h in s_headers.get(row_at, {}).items() if h == head),
                       None) if row_at and head else None
            if hit is None:
                missed.append((coord, label, head or ""))
            else:
                targets[(EXEC, coord)] = (src, wb[src].cell(row_at, hit).coordinate)
    return targets, missed


# --- 8. live arithmetic ---------------------------------------------------------------
SUBTOTAL_FILL = "EDEBE3"          # wbkit's MIST, the Subtotal style's fill
PERIOD_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September",
     "October", "November", "December"], start=1)}


def period_key(header) -> str | None:
    """The period a column header names, on one key across tabs: `September 2025`,
    `As of September 2025` and `Sep 2025 (days)` are `2025-09`; `FY2025` is `fy2025`; `LTM
    Jul 2025` is `ltm2025-07`. None for a header naming no period."""
    if not isinstance(header, str):
        return None
    h = header.lower()
    ltm = "ltm" if re.search(r"\bltm\b", h) else ""
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?:\d{1,2},\s+)?((?:19|20)\d\d)\b", h)
    if m:
        month = next(i for name, i in PERIOD_MONTHS.items() if name.startswith(m.group(1)))
        return f"{ltm}{m.group(2)}-{month:02d}"
    m = re.search(r"\bfy\s?((?:19|20)\d\d)\b", h)
    return f"fy{m.group(1)}" if m else None


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class Styles:
    """The style ids that mark a row's kind, resolved once per workbook: reading a
    cell's border, font and fill through openpyxl's proxies, cell by cell over every tab,
    is the slow part of a large workbook."""

    def __init__(self, wb):
        rgb = lambda f: (str(f.fgColor.rgb or "")[-6:].upper()  # noqa: E731
                         if getattr(f, "fill_type", None) == "solid" and getattr(f, "fgColor", None) is not None
                         and f.fgColor.type == "rgb" else "")
        self.double = {i for i, b in enumerate(wb._borders)
                       if b.bottom is not None and b.bottom.style == "double"}
        self.bold = {i for i, f in enumerate(wb._fonts) if f.b}
        self.mist = {i for i, f in enumerate(wb._fills) if rgb(f) == SUBTOTAL_FILL}
        self.filled = {i for i, f in enumerate(wb._fills) if rgb(f) not in ("", SUBTOTAL_FILL)}

    def subtotal(self, cell) -> bool:
        st = getattr(cell, "_style", None)
        return st is not None and st.fontId in self.bold and st.fillId in self.mist

    def header(self, cell) -> bool:
        st = getattr(cell, "_style", None)
        return (st is not None and isinstance(cell.value, str) and st.fontId in self.bold
                and st.fillId in self.filled)

    def total(self, cell) -> bool:
        st = getattr(cell, "_style", None)
        return st is not None and st.borderId in self.double


def sheet_rows(ws, styles: Styles) -> dict[int, dict]:
    """{row: {"cells": {column: cell}, "kind": total | derived | body, "header": bool}}
    for every row holding a value — one pass over the sheet."""
    out: dict[int, dict] = {}
    for row in ws.iter_rows(min_col=2):
        cells = {c.column: c for c in row if c.value not in (None, "")}
        if not cells:
            continue
        r = row[0].row
        kind = "body"
        if any(styles.total(c) for c in row):
            kind = "total"
        else:
            for col in (2, 3):
                c = cells.get(col)
                if c is not None and c.data_type != "f" and isinstance(c.value, str) \
                        and c.value.strip().startswith("="):
                    kind = "derived"
        out[r] = {"cells": cells, "kind": kind, "header": 2 in cells and styles.header(cells[2])}
    return out


def retrofit_totals(wb, value, results: dict, styles: Styles | None = None) -> tuple[int, list[str]]:
    """Section 8, on a tab with no cells map: each total, subtotal and derived line typed as
    a value becomes `=SUM(...)` over the rows above it in its table, when one plain reading
    of them adds to it exactly — a subtotal the rows since the last subtotal or derived
    line, a derived line the one above it and what lies between (a subtotal standing for
    the rows it adds), a total its table. Returns (converted, the cells left as values)."""
    import formula as fx  # noqa: PLC0415
    styles = styles or Styles(wb)
    done, left = 0, []
    for ws in wb.worksheets:
        if ws.title in value["skip"]:
            continue
        rows = sheet_rows(ws, styles)
        targets = [r for r, info in rows.items()
                   if info["kind"] != "body" or any(_is_number(c.value) and styles.subtotal(c)
                                                    for c in info["cells"].values())]
        if not targets:
            continue
        cover: dict[tuple[int, int], set[int]] = {}       # (column, subtotal row) -> rows it adds
        for r in sorted(targets):
            hr = r - 1                  # up to the table's header row, or the blank row above it
            while hr in rows and not rows[hr]["header"]:
                hr -= 1
            for col, cell in sorted(rows[r]["cells"].items()):
                if cell.data_type == "f" or not _is_number(cell.value):
                    continue
                kind = rows[r]["kind"] if rows[r]["kind"] != "body" else (
                    "subtotal" if styles.subtotal(cell) else "body")
                if kind == "body":
                    continue
                letter = cell.column_letter
                derived_above, last_total, boundary = None, None, hr
                for x in range(hr + 1, r):
                    c = rows.get(x, {}).get("cells", {}).get(col)
                    if c is None:
                        continue
                    if c.data_type == "f" and (col, x) not in cover:
                        pre = fx.precedents(c.value, ws.title) or []
                        if styles.subtotal(c):
                            cover[(col, x)] = {int(re.sub(r"[A-Z]+", "", co)) for sh, co in pre if sh == ws.title}
                    if (col, x) in cover:
                        boundary = x
                    if rows[x]["kind"] == "derived":
                        derived_above = boundary = x
                    if rows[x]["kind"] == "total":
                        last_total = boundary = x
                if kind == "subtotal":
                    start = boundary
                else:
                    start = max(derived_above or hr, last_total or hr)

                def num(x):
                    return value["get"](ws.title, f"{letter}{x}")

                def plain_body(x):
                    c = rows.get(x, {}).get("cells", {}).get(col)
                    return (rows.get(x, {}).get("kind") == "body" and (col, x) not in cover
                            and not (c is not None and c.data_type != "f" and styles.subtotal(c)))

                between = [x for x in range(start + 1, r) if _is_number(num(x))
                           and rows.get(x, {}).get("kind") != "total"]
                # an `All …` line heading the rows it adds restates them; it stands for none
                heads = {x for x in between if (col, x) in cover and cover[(col, x)]
                         and min(cover[(col, x)]) > x}
                between = [x for x in between if x not in heads]
                subs = [x for x in between if (col, x) in cover]
                covered = set().union(*(cover[(col, x)] for x in subs)) if subs else set()
                body = [x for x in between if plain_body(x)]
                lead = [derived_above] if kind == "derived" and derived_above and derived_above > start - 1 else []
                if kind == "subtotal":
                    below = []
                    x = r + 1
                    while x in rows and _is_number(num(x)) and plain_body(x):
                        below.append(x)
                        x += 1
                    sets = [body, [] if body else below]
                else:
                    sets = [lead + subs + [x for x in body if x not in covered], lead + body,
                            subs if kind == "total" else []]

                def deducted(x) -> bool:
                    """A `Less:` or `Deduct:` line stored as a positive figure."""
                    label = " ".join(str(rows[x]["cells"][k].value) for k in (2, 3)
                                     if k in rows[x]["cells"] and isinstance(rows[x]["cells"][k].value, str))
                    return bool(re.search(r"(?:^|\s)(?:less|deduct)\b", label, re.I)) and float(num(x)) >= 0
                hit = None
                for rs in sets:
                    if not rs:
                        continue
                    vals = [float(num(x)) for x in rs]
                    for minus in ([], [x for x in rs if deducted(x)]):
                        got = sum(-v if x in minus else v for x, v in zip(rs, vals))
                        if fx.foots(float(cell.value), got, len(rs), vals + [float(cell.value)]):
                            hit = (rs, minus)
                            break
                        if not [x for x in rs if deducted(x)]:
                            break
                    if hit:
                        break
                if hit is None:
                    left.append(f"{ws.title}!{cell.coordinate}")
                    continue
                v = float(cell.value)
                rs, minus = hit
                cell.value = fx.signed_formula(letter, [x for x in rs if x not in minus], minus)
                results.setdefault(ws.title, {})[cell.coordinate] = v
                value["set"](ws.title, cell.coordinate, v)
                if kind == "subtotal":
                    cover[(col, r)] = set(rs)
                done += 1
    return done, left


def wire_copies(wb, value, maps: dict, results: dict) -> tuple[int, list[str]]:
    """Section 8, by the cells maps: each cell a tab declared as a copy (`src`) becomes a
    reference to the cell its map says holds that figure, when the two agree."""
    import formula as fx  # noqa: PLC0415
    home: dict[str, tuple[str, str]] = {}
    for sheet, cells in maps.items():
        for coord, e in cells.items():
            if e.get("fid"):
                home.setdefault(e["fid"], (sheet, coord))
    done, bad = 0, []
    for sheet, cells in maps.items():
        if sheet not in wb.sheetnames:
            continue
        for coord, e in cells.items():
            src = e.get("src")
            if not src:
                continue
            target = home.get(src)
            if target is None or target[0] not in wb.sheetnames:
                bad.append(f"{sheet}!{coord} copies {src}, which no tab's cells map places")
                continue
            mine, theirs = value["get"](sheet, coord), value["get"](*target)
            if not (_is_number(mine) and _is_number(theirs)
                    and fx.foots(float(theirs), float(mine), 1, [float(theirs), float(mine)])):
                bad.append(f"{sheet}!{coord} copies {src} as {mine!r}; {target[0]}!{target[1]} holds {theirs!r}")
                continue
            wb[sheet][coord].value = fx.reference(*target)
            results.setdefault(sheet, {})[coord] = float(theirs)
            done += 1
    return done, bad


def retrofit_copies(wb, value, rank: dict[str, int], results: dict, styles: Styles | None = None) -> int:
    """Section 8, on tabs with no cells map: a figure whose value, to the cent, sits in
    exactly one cell of an earlier check's tabs under a header naming the same period
    becomes a reference to that cell. A zero, a whole number under 1,000 (a count, a day
    count) and anything matched twice stay values: equal is not the same figure there."""
    import formula as fx  # noqa: PLC0415
    styles = styles or Styles(wb)
    index: dict[tuple[str, float], list[tuple[str, str]]] = {}
    cand: list[tuple[str, str, tuple[str, float]]] = []
    for ws in wb.worksheets:
        if ws.title in value["skip_copies"]:
            continue
        headers_at, _, _, numerics = sheet_grid(ws)
        double = {c.row for row in ws.iter_rows(min_col=2) for c in row
                  if c.value is not None and styles.total(c)}
        for r, cells in numerics.items():
            kind = "total" if r in double else "body"
            for c, coord in cells:
                cell = ws[coord]
                v = cell.value
                if cell.data_type == "f" or not _is_number(v) or v == 0 or \
                        (float(v).is_integer() and abs(v) < 1000):
                    continue
                per = period_key(headers_at.get(r, {}).get(c))
                if per is None:
                    continue
                key = (per, round(float(v), 4))
                index.setdefault(key, []).append((ws.title, coord))
                if kind == "body" and not styles.subtotal(cell) and ws.title not in value["mapped"]:
                    cand.append((ws.title, coord, key))
    done = 0
    for sheet, coord, key in cand:
        mine = rank.get(sheet)
        if mine is None:
            continue
        earlier = [(s_, c_) for s_, c_ in index[key] if s_ != sheet and rank.get(s_, 1 << 30) < mine]
        if len(earlier) != 1:
            continue
        source = value["get"](*earlier[0])
        wb[sheet][coord].value = fx.reference(*earlier[0])
        results.setdefault(sheet, {})[coord] = float(source)
        done += 1
    return done


def load_maps(run_dir: pathlib.Path | None) -> dict[str, dict]:
    """{sheet: {coord: entry}} from every placed tab's cells map."""
    out: dict[str, dict] = {}
    if run_dir is None:
        return out
    for f in sorted((run_dir / "out" / "tabs").glob("*.cells.json")):
        try:
            for sheet, cells in (json.loads(f.read_text(encoding="utf-8")).get("sheets") or {}).items():
                out.setdefault(sheet, {}).update(cells or {})
        except (OSError, ValueError, AttributeError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workbook", type=pathlib.Path)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be wired; write nothing")
    ap.add_argument("--run-dir", type=pathlib.Path,
                    help="the run directory: its placed tabs' cells maps wire each copy to the "
                         "cell it copies, and run.json orders the checks (§ 8)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not a.workbook.is_file():
        print(f"{a.workbook}: not a file", file=sys.stderr)
        return 2
    try:
        import openpyxl
        from openpyxl.styles import Font
        from openpyxl.worksheet.hyperlink import Hyperlink
    except ImportError:
        print("link_workbook.py needs openpyxl (it must write the workbook). Without an "
              "installed copy, run it as:\n"
              "  uv run --with openpyxl python3 scripts/link_workbook.py <workbook.xlsx>",
              file=sys.stderr)
        return 2

    wb = openpyxl.load_workbook(a.workbook)
    cached = openpyxl.load_workbook(a.workbook, data_only=True)   # a re-run reads its own formulas' results
    if SOURCES not in wb.sheetnames:
        print(f"{a.workbook.name}: no '{SOURCES}' tab — assemble the workbook first",
              file=sys.stderr)
        return 2

    exact_cells, line_homes, tokens, stems = scan(wb)
    targets, dead, internal, homes = resolve(exact_cells, line_homes, tokens,
                                             set(wb.sheetnames))

    # Family stems: a whole-cell stem links to the first resolvable id it matches.
    fam = 0
    ids_sorted = sorted(homes)
    for at, stem in sorted(stems.items()):
        if at in targets:
            continue
        rx = family_regex(stem)
        hit = next((i for i in ids_sorted if rx.fullmatch(i)), None)
        if hit and homes[hit] != at:
            targets[at] = homes[hit]
            fam += 1

    # Navigation: a cell that names a check links to that check's tab — the Coverage and
    # Basis of Preparation tables list checks by id, so the reader clicks down from the first tabs
    # without knowing any tab name. Id links already placed take precedence.
    nav = 0
    by_name: dict[str, list[str]] = {}
    for t in wb.sheetnames:
        # Only a CHECK tab is a navigation target. The run-level tabs are named in prose
        # and as column headers all over the workbook ("Evidence", "Coverage"), and a header
        # that happens to read like a tab name is not a pointer to it.
        if normalize(t) not in RUN_TABS:
            by_name.setdefault(normalize(t), []).append(t)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if not isinstance(v, str) or len(v) > 120:
                    continue
                m = NAV.match(v.strip())
                if not m:
                    continue
                at = (ws.title, cell.coordinate)
                if at in targets:
                    continue
                hits = by_name.get(normalize(m.group(1)), [])
                if len(hits) == 1 and hits[0] != ws.title:
                    targets[at] = (hits[0], TITLE_CELL)
                    nav += 1

    # The Exec Summary's copied tables: every amount back to the cell it was copied from.
    walk, missed = walk_targets(wb)
    targets.update(walk)
    # A match summary's lines: each opens its status's rows on the schedule.
    matches = match_targets(wb)
    targets.update(matches)

    live_rep = {"copies_wired": 0, "copy_problems": [], "totals_made_live": 0,
                "totals_left_as_values": [], "copies_retrofitted": 0}
    if not a.dry_run:
        # § 8: the arithmetic made live, before the links (an Exec Summary amount reads a
        # cell that may itself have just become a reference).
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import formula as fx
        known = fx.compute_results(wb, fallback=cached)   # the formulas the tabs arrived with

        def get(sh, co):
            if co in known.get(sh, {}):
                return known[sh][co]
            c = wb[sh][co]
            return None if c.data_type == "f" else c.value

        maps = load_maps(a.run_dir)
        run_tabs = {t for t in wb.sheetnames if normalize(t) in RUN_TABS}
        value = {"get": get, "set": lambda sh, co, v: known.setdefault(sh, {}).__setitem__(co, v),
                 "skip": run_tabs | set(maps), "skip_copies": run_tabs, "mapped": set(maps)}
        rank = {t: i for i, t in enumerate(wb.sheetnames)}
        if a.run_dir is not None and (a.run_dir / "run.json").is_file():
            from check_workbook import tab_owners
            checks = json.loads((a.run_dir / "run.json").read_text(encoding="utf-8")).get("checks") or []
            owner, _ = tab_owners(checks, wb.sheetnames)
            order = [c["id"] for c in checks]
            rank = {t: order.index(o) for t, o in owner.items() if o in order}
        live_rep["copies_wired"], live_rep["copy_problems"] = wire_copies(wb, value, maps, known)
        live_rep["totals_made_live"], live_rep["totals_left_as_values"] = retrofit_totals(wb, value, known)
        live_rep["copies_retrofitted"] = retrofit_copies(wb, value, rank, known)

        # Every link in this workbook is placed here, so a re-run owns them all: clear
        # first, or a link this pass no longer wants survives, pointing where it did.
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.hyperlink is not None:
                        cell.hyperlink = None
            ws._hyperlinks = []
        # The Exec Summary's amounts become formulas reading their originals; each keeps
        # the value it showed, cached in the XML after the save.
        live: dict[str, float] = {}
        for (sheet, coord), (tsheet, tcoord) in walk.items():
            cell = wb[sheet][coord]
            shown = get(sheet, coord)
            if not isinstance(shown, (int, float)) or isinstance(shown, bool):
                continue                          # nothing to cache: leave the cell as it is
            live[coord] = shown
            cell.value = f"='{tsheet.replace(chr(39), chr(39) * 2)}'!{tcoord}"
        for (sheet, coord), (tsheet, tcoord) in targets.items():
            cell = wb[sheet][coord]
            shown = live.get(coord, cell.value) if sheet == EXEC else cell.value
            cell.hyperlink = Hyperlink(ref=coord, location=f"'{tsheet}'!{tcoord}",
                                       tooltip=f"{shown} — {tsheet}"[:250],
                                       display=str(shown)[:250])
            font = copy(cell.font)
            font.color = LINK_COLOR
            # A linked AMOUNT takes color only: under a figure, an underline is the
            # accounting rule that says "sum above", and a link must not draw one.
            if (sheet, coord) not in walk and not isinstance(cell.value, (int, float)):
                font.underline = "single"
            cell.font = font
        # Every table an Excel table of its own (wbkit.excel_tables): a tab copied cell by
        # cell arrives without its table objects, and names must be unique workbook-wide.
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from wbkit import excel_tables
        taken: set[str] = set()
        n_tables = sum(len(excel_tables(ws, taken)) for ws in wb.worksheets)
        # openpyxl saves every formula with an empty result, and a workbook assembled by
        # copying tabs arrives with none: every formula's result is computed, the Exec
        # Summary's new references and § 8's included, and cached.
        known.setdefault(EXEC, {}).update(live)
        results = fx.compute_results(wb, known=known, fallback=cached)
        wb.save(a.workbook)
        fx.cache_results(a.workbook, results)

    ledgers = (SOURCES, EVIDENCE)
    up = sum(1 for at, t in targets.items() if t[0] in ledgers and at[0] not in ledgers)
    back = sum(1 for at, t in targets.items() if at[0] in ledgers and t[0] not in ledgers)
    rep = {"workbook": str(a.workbook), "ids_seen": len(tokens),
           "links": len(targets), "to_ledgers": up, "back_from_ledgers": back,
           "family_links": fam, "navigation": nav, "walk_amounts": len(walk),
           "unmatched_walk_amounts": [{"cell": c, "row": l, "column": h}
                                      for c, l, h in missed],
           "match_lines": len(matches),
           "tables": 0 if a.dry_run else n_tables,
           "other": len(targets) - up - back - nav - len(walk) - len(matches),
           "dead_ends": sorted(dead), "internal_refs": sorted(internal),
           "dry_run": a.dry_run, **live_rep}
    if a.json:
        print(json.dumps(rep, indent=2))
        return 0
    verb = "would wire" if a.dry_run else "wired"
    print(f"{a.workbook.name}: {verb} {len(targets)} links over {len(tokens)} ids — "
          f"{up} to {SOURCES}/{EVIDENCE}, {back} back out, {fam} family stems, "
          f"{rep['other'] - fam} to stated homes, {nav} check-tab navigation, "
          f"{len(walk)} {EXEC} amounts, {len(matches)} match-summary lines.")
    if not a.dry_run:
        print(f"  live arithmetic: {live_rep['copies_wired']} copies wired by the cells maps, "
              f"{live_rep['copies_retrofitted']} copies retrofitted by value, "
              f"{live_rep['totals_made_live']} totals made formulas; "
              f"{len(live_rep['totals_left_as_values'])} totals left as values.")
        for line in live_rep["copy_problems"][:15]:
            print(f"    copy not wired: {line}")
        if live_rep["copy_problems"]:
            print("  A copy that disagrees with the figure it copies is the copying check's to "
                  "fix; a copy whose figure no map places names a producer written before the "
                  "maps existed.")
        left = live_rep["totals_left_as_values"]
        if left:
            print(f"    left as values (no plain reading of the rows above adds to them): "
                  f"{', '.join(left[:8])}{' …' if len(left) > 8 else ''}")
    if missed:
        print(f"  {len(missed)} {EXEC} amount(s) matched no source cell — the row's "
              f"label and the column's header must be COPIED from the tab the table's "
              f"title names, character for character; check_workbook.py refuses an "
              f"unlinked amount here:")
        for coord, label, head in missed:
            print(f"    {EXEC}!{coord}  (row {label!r}, column {head!r})")
    if internal:
        print(f"  left as text (run-internal review findings): {', '.join(internal)}")
    if dead:
        print(f"  {len(dead)} dead-end id(s) — cited but stated nowhere a reader can "
              f"land; check_workbook.py refuses these. A figure or population needs its "
              f"{SOURCES} row, an evidence id its {EVIDENCE} row, any other id a cell or "
              f"leading line on the tab that owns it:")
        for i in dead:
            at = tokens[i]
            print(f"    {i}  (cited at {at[0]}!{at[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
