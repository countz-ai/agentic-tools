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
  6. Every AMOUNT on the Exec Summary links to the cell it was copied from. The Exec
     Summary mints no figure, so each number there has an original on a check's tab; the
     table's title names that tab, and the amount is found by the row's leading label and
     the column's header, both copied verbatim. An amount that matches nothing is
     reported and left — check_workbook.py refuses an unlinked number on the Exec
     Summary, because the fix is copying the label, not linking. These cells take the
     link color and no underline: under a figure, an underline is the accounting rule
     that reads "sum above".

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
    link_workbook.py <workbook.xlsx> [--dry-run] [--json]
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
LINK_COLOR = "0F756D"   # WORKBOOK_STYLE.md § 1a `ACCENT`; the cell keeps its own font
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


# A table on the Exec Summary declares the tab it was copied from by naming that tab in
# its title. Sheet names are distinctive ("q6_ebitda_bridge"), so a substring match is
# unambiguous; a title naming two tabs declares neither.
LABEL_COLS = 4


def declared_source(text: str, sheets) -> str | None:
    # A tab is named `<token> <Title>` (reference/WORKBOOK.md § 2), so a title that names
    # the token alone ("copied from the q6_ebitda_bridge tab") declares that tab too.
    # A declaration says "tab" ("copied from the q6_ebitda_bridge tab"); a row whose
    # leading label merely IS a tab's token declares nothing.
    if re.search(r"\btab\b", text) is None:
        return None
    hits = [t for t in sheets if t != EXEC
            and (t in text or re.search(rf"(?<![\w.]){re.escape(t.split(' ')[0])}(?![\w.])", text))]
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workbook", type=pathlib.Path)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be wired; write nothing")
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

    if not a.dry_run:
        # Every link in this workbook is placed here, so a re-run owns them all: clear
        # first, or a link this pass no longer wants survives, pointing where it did.
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.hyperlink is not None:
                        cell.hyperlink = None
            ws._hyperlinks = []
        for (sheet, coord), (tsheet, tcoord) in targets.items():
            cell = wb[sheet][coord]
            cell.hyperlink = Hyperlink(ref=coord, location=f"'{tsheet}'!{tcoord}",
                                       tooltip=f"{cell.value} — {tsheet}"[:250],
                                       display=str(cell.value)[:250])
            font = copy(cell.font)
            font.color = LINK_COLOR
            # A linked AMOUNT takes color only: under a figure, an underline is the
            # accounting rule that says "sum above", and a link must not draw one.
            if (sheet, coord) not in walk and not isinstance(cell.value, (int, float)):
                font.underline = "single"
            cell.font = font
        wb.save(a.workbook)

    ledgers = (SOURCES, EVIDENCE)
    up = sum(1 for at, t in targets.items() if t[0] in ledgers and at[0] not in ledgers)
    back = sum(1 for at, t in targets.items() if at[0] in ledgers and t[0] not in ledgers)
    rep = {"workbook": str(a.workbook), "ids_seen": len(tokens),
           "links": len(targets), "to_ledgers": up, "back_from_ledgers": back,
           "family_links": fam, "navigation": nav, "walk_amounts": len(walk),
           "unmatched_walk_amounts": [{"cell": c, "row": l, "column": h}
                                      for c, l, h in missed],
           "other": len(targets) - up - back - nav - len(walk),
           "dead_ends": sorted(dead), "internal_refs": sorted(internal),
           "dry_run": a.dry_run}
    if a.json:
        print(json.dumps(rep, indent=2))
        return 0
    verb = "would wire" if a.dry_run else "wired"
    print(f"{a.workbook.name}: {verb} {len(targets)} links over {len(tokens)} ids — "
          f"{up} to {SOURCES}/{EVIDENCE}, {back} back out, {fam} family stems, "
          f"{rep['other'] - fam} to stated homes, {nav} check-tab navigation, "
          f"{len(walk)} {EXEC} amounts.")
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
