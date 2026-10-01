#!/usr/bin/env python3
"""Refuse a workbook whose figures are invisible, whose ids do not resolve, or whose
figure rows a reader cannot re-perform from.

Seven gates over the stored file, all parsed from the XML rather than through a library so
the check sees what is actually stored, not what a loader reconstructs.

GATE 1 — cached values. An .xlsx cell stores two things: the formula (`<f>`) and the last
computed result (`<v>`). Excel and LibreOffice write both. **openpyxl writes only the
formula** — it never evaluates, so it emits an empty `<v/>`. Excel and LibreOffice
recalculate on open and fill it in, so the author sees a correct workbook. Everything
else — a preview pane, Quick Look, pandas, a mail client, most viewers — reads the stored
value and finds nothing, and renders the cell blank.

Measured on the first live run: 2,306 formula cells, every one blank outside Excel. The
author could not see it, because the author opened it in Excel.

This is a gate, not a repair. It cannot compute the missing values — the author has them,
in the figure ledger. Two ways to satisfy it:

  1. Write the computed VALUE into the cell. Carry the arithmetic as the figure's
     `expression` on the Sources tab. Simplest, and it is what the re-performance trail
     already rests on.
  2. Write a real formula AND cache its result. `xlsxwriter.write_formula(row, col,
     formula, fmt, value)` takes the result as its fifth argument. With openpyxl, write
     the file then substitute `<v/>` for `<v>result</v>` in the sheet XML — verified to
     preserve the formula and render the value.

GATE 8 — live arithmetic (reference/WORKBOOK.md § 7). Every formula in the grammar of
scripts/formula.py is recomputed from the stored values and must agree with its own cached
result. On a sheet a tab script mapped (`wbkit.save` wrote `<tab>.cells.json` naming it,
read beside the workbook and, with --run-dir, from out/tabs/), a subtotal, a total or a
walk's derived line (`= …`) is a formula over the rows it adds, never a typed value.

GATE 4 — the design. Every tab is built to reference/WORKBOOK.md and
WORKBOOK_STYLE.md, read from the stored styles: Arial in the five sizes, column A empty,
the primary table's BAND header on row 4 and BAND on header labels only, freeze panes at B4, no merged cell, every
Excel table's header row reading its column names under a name unique in the workbook and
clear of the sheet's AutoFilter, no
numeric cell left in General, no table cell without its hairline border, prose only in a
wrapped column at least 42 wide or in a cell overflowing an empty row, every row holding
a wrapped cell sized to fit it, no cell cut mid-sentence (nor a label cut mid-word from a
longer statement the workbook carries), gridlines off on deliverable
tabs and on for ledgers,
the tab colour by kind, B1 title, B2 subtitle and B3 the summary, and no cell outside the
id column reading as the run's machine vocabulary (`consistent_late_payer`,
`phone_call: promise_to_pay`) where the reader's words belong. The Exec
Summary's band is rows 1 to 3 (B3 the position), frozen at B4, with no row-4 header rule
(WORKBOOK.md § 6).

GATE 2 — id links. The reader follows a number by its id, and `link_workbook.py` wires
each id cell to where the id resolves: figure and population ids (`F.`, `P.`) on their
Sources row, evidence ids (`E.`) on their Evidence row, every other prefix on the cell
that IS the id, and only failing that on a line of prose opening with it. This gate refuses what the wiring cannot repair and what a skipped
wiring leaves behind:

  - a hyperlink that is external, unparseable, or lands on an empty cell (the deliverable
    is self-contained; a broken jump is worse than none);
  - a cell that is exactly one ledger-tab id, off its ledger, with no link onto the
    ledger row stating it;
  - a cell that is exactly one id of another prefix, unlinked, when the id is stated
    elsewhere;
  - an `E.` id cited in a workbook that has no Evidence tab at all — the evidence records
    belong IN the deliverable, merged from `workpapers/evidence-*.yaml`;
  - a number on the Exec Summary with no link to the cell it was copied from. That tab
    mints no figure; every amount on it is a copy from a check tab (WORKBOOK.md § 6);
  - a DEAD-END id: cited somewhere, stated nowhere — no ledger row, no cell that is it,
    no line beginning with it, so no link can ever resolve it. The fix is authoring, not
    linking. Exempt: family stems written with a placeholder (`T.foot.<month>`) and `C.`
    review-finding ids, whose record lives in the run's review step by design.

  A workbook with no Sources tab is a single check tab staged before assembly: no linker
  has run and the ledger tabs do not exist yet, so this gate holds the statement rules
  (dead ends for non-ledger prefixes) and gate 1 there. Pass `--run-dir` and it holds the
  ledger prefixes too, resolving each cited `F.` / `P.` / `E.` id against the run's own
  `workpapers/*.yaml` records — the files the ledger tabs are later merged FROM. Without
  it, a check that cites an id it never recorded passes its own gate and reaches the
  deliverable, where the report step may not repair a tab it copied. Measured on a live
  run: 17 such ids, invisible to every check, refused at the seal.

  With `--run-dir` the ledgers themselves are gated, at the moment their ids are minted:
  a `workpapers/*.yaml` whose top level is not a list (`resolve_roots.py` reads a
  mapping as its keys — measured: 749 of 1,802 figures reached Sources with no root and
  no recipe), and a declared id outside the id grammar. The grammar admits no space, so
  `id: F.q6.ebit.LTM July 2023` is cited as `F.q6.ebit.LTM` and stated as nothing —
  measured: 38 of 72 dead ends at one seal were that one id family. A period in an id
  is its slug (`fy2025`, `ltm_2026-07`), never the column label (EVIDENCE.md § 0).

GATE 3 — the reperformance contract, on the assembled workbook only (Sources present).
Every figure row on Sources must let the reader re-perform in one hop:

  - Sources carries an `id` header, a `root source` header (the room-file citation ids a
    figure resolves to once passthrough and figure-to-figure hops are collapsed) and a
    `To reperform` header (the flattened recipe: file · sheet · rows · columns · filter ·
    arithmetic · expected value);
  - every `F.` row's `To reperform` cell is non-empty.

Also refused, per tab: a pane frozen deeper than the title band (more than 3 rows or
2 columns). Excel freezes everything above the split, so a preamble stacked over the
header rides into the frozen band — measured on a live run: a 29-row frozen Evidence
header filled a laptop screen and left the data unreachable by scrolling. The preamble
belongs below the data (check-report SKILL § 1). A table header row is never frozen:
the row-4 header belongs to the primary table alone, not to the tables below it.

GATE 5 — the map, on a workbook that has an Exec Summary. The tab strip is the reader's
path (reference/WORKBOOK.md § 2): Exec Summary first; then the lead tabs — the check
tabs the Exec Summary's numbers stand on, in the recipe's `lead` order, by default the
headline family's tab alone; then Basis of Preparation and every other check tab in
roster order; then Coverage, Open Items, Sources, Evidence. A check's match tabs follow
its own tab, together, each summary before its schedule. Without `--run-dir` the gate
holds the shape — Exec Summary first, the tail last. With `--run-dir` it reads
`run.json` (the roster, each check's `params.family`, `plan.recipe`) and the recipe's
frontmatter, and refuses any other strip, naming the one wanted. A check tab it cannot
match to a rostered check is refused too: the name opens with the roster token.

GATE 6 — the match tabs (reference/WORKBOOK.md § 6, scripts/match_tabs.py), on any
workbook that holds them. Every line of a match summary is its schedule filtered on the
line's status: the same count of rows and the same amount, to the cent; the opening line
and the total are the whole schedule; the schedule holds each item once, in one block per
status; the reconciling items foot, and each line's positive and negative items add to
it; and in an assembled workbook each line's words link to its block.

GATE 7 — every reconciliation shows its matching (check-recon § 5), with `--run-dir`. The
tab file of a `recon` check holds a whole set of match tabs — summary, schedule,
reconciling items, rules — whether it matched with `resolve()` or with joins read back
through `from_assignment()`, so the reader finds the schedule on every reconciliation, not
on some. The one reconciliation without them has a side with no item grain, and its check
tab says so on a line opening `No item grain:`. At the seal, every `recon` check with a
tab in the workbook is held to the same.

The id grammar and the home rule mirror link_workbook.py — a change here changes both.

Usage:
    check_workbook.py <workbook.xlsx> [--run-dir DIR] [--json] [--max-report N]
    check_workbook.py --run-dir DIR                # the ledgers alone, no workbook: the
                                                   # gate for a step that writes ledgers
                                                   # and no tab (check-plan)
Exit 0 clean, 1 if any formula cell has no cached value or any link, layout, map or
ledger check fails, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import bisect
import html
import json
import pathlib
import re
import sys
import zipfile

# A cell element carrying an <f> child, capturing its reference and whether a <v> follows
# with anything in it.
CELL = re.compile(r'<c r="([A-Z]+\d+)"[^>]*>(?:(?!</c>).)*?<f[^>]*>.*?</f>\s*(<v\s*/>|<v[^>]*>(.*?)</v>)?',
                  re.S)
# Any cell element, for text extraction: attributes and body.
ANY_CELL = re.compile(r"<c\b([^>]*?)(?:/>|>((?:(?!</c>).)*)</c>)", re.S)
HYPERLINK = re.compile(r"<hyperlink\b[^>]*/?>")
PANE_EL = re.compile(r"<pane\b[^>]*/?>")
# The most a frozen pane may hold: the title band (rows 1-3) and the margin column.
# Never a table header row - the row-4 header describes the primary table alone.
FROZEN_ROWS_MAX = 3
FROZEN_COLS_MAX = 2
# Attribute order in XML is not guaranteed and differs by writer - openpyxl emits
# Target before Id, Excel the reverse. Match each attribute independently.
SHEET_EL = re.compile(r"<sheet\b[^>]*/?>")
REL_EL = re.compile(r"<Relationship\b[^>]*/?>")
ATTR = lambda name: re.compile(rf'\b{name}="([^"]*)"')

# One id token. Mirrors link_workbook.py ID_TOKEN — change both. The second alternative
# demands two characters after the prefix dot so prose abbreviations ("E.g", "P.O") do
# not match; the first admits pure serials ("D.3", "S.1").
ID_TOKEN = re.compile(
    r"\b(?:RI|[EFPTSXCDQ])\.(?:\d+|[A-Za-z0-9_][A-Za-z0-9_.-]*[A-Za-z0-9])")
SOURCES = "Sources"
EVIDENCE = "Evidence"
EXEC = "Exec Summary"
# Which ledger tab an id prefix resolves on. Mirrors link_workbook.py — change both.
LEDGER = {"F": SOURCES, "P": SOURCES, "E": EVIDENCE}
# A link lands on a cell, or selects a range (a match summary's line opens its rows); the
# second group is the cell it lands on, the range's first.
LOCATION = re.compile(r"^'?([^'!]+)'?!\$?([A-Z]+\$?\d+)(?::\$?[A-Z]+\$?\d+)?$")
REF = re.compile(r"^([A-Z]+)(\d+)$")


# A ledger entry's `id:` line, whole value — block style (`- id: F.x` / `  id: F.x`) or
# the head of a flow entry (`- {id: F.x, ...}`); quotes, a trailing comment and flow
# punctuation are stripped by _id_value.
ID_LINE = re.compile(r"^\s*-?\s*\{?\s*id:[ \t]*(.*?)[ \t]*$", re.M)
# What a ledger may DECLARE, whole: any one- or two-letter prefix, then the token body
# above (mirrored from ID_TOKEN — change both). A declared id the token grammar cuts
# short is cited under one spelling and stated under another: every citation dead-ends.
LEDGER_ID = re.compile(r"[A-Z]{1,2}\.(?:\d+|[A-Za-z0-9_][A-Za-z0-9_.-]*[A-Za-z0-9])")


def _id_value(raw: str) -> str:
    """The id as written: a quoted value whole (a space inside the quotes is the
    defect this reads for), an unquoted one up to a trailing comment or, in a flow
    entry (`- {id: F.x, value: 1}`), the next `,` or `}`."""
    v = raw.strip()
    if v[:1] in ("\"", "'"):
        end = v.find(v[0], 1)
        return v[1:end] if end > 0 else v[1:]
    return re.split(r"\s+#|[,}]", v, 1)[0].strip()


def ledger_shape(text: str) -> str:
    """The YAML top level, read as text: `list`, `empty`, `mapping` or `scalar`. The
    first line that is not blank, a comment, a document marker or a directive decides."""
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "%")) or s in ("---", "..."):
            continue
        if s == "-" or s.startswith(("- ", "[")):
            return "list"
        if s.startswith("{") or re.match(r"^[^#]+?:(\s|$)", s):
            return "mapping"
        return "scalar"
    return "empty"


def declared_ids(run_dir: pathlib.Path) -> tuple[set[str] | None, list[str]]:
    """(every id the run's ledgers DECLARE, the ledger failures), read from
    `workpapers/*.yaml`; (None, []) when the directory does not exist.

    A check tab is gated before any ledger tab exists, so on a staged single tab the
    ledger records are the only place a cited `F.`/`P.`/`E.` id can resolve. Without them
    the check-time gate has to skip those prefixes, and a check that cites an id it never
    recorded reaches the deliverable — where the assembler may not repair a copied tab.
    The same read holds the ledger's own shape: a top level that is not a list, and an id
    outside the grammar, are the owning check's defects to fix HERE, at mint time — at
    the seal the report step may not repair them either.
    Read as text: the ledgers are YAML and this script is stdlib-only."""
    wp = run_dir / "workpapers"
    if not wp.is_dir():
        return None, []
    out: set[str] = set()
    fails: list[str] = []
    for f in sorted(wp.glob("*.yaml")):
        text = f.read_text(encoding="utf-8", errors="replace")
        shape = ledger_shape(text)
        if shape not in ("list", "empty"):
            fails.append(f"workpapers/{f.name}: top level is a {shape}, not a list — a "
                         f"ledger is a YAML list, one `- id:` entry per record; "
                         f"resolve_roots.py refuses any other shape (EVIDENCE.md § 0)")
        for m in ID_LINE.finditer(text):
            v = _id_value(m.group(1))
            if LEDGER_ID.fullmatch(v):
                out.add(v)
            else:
                fails.append(f"workpapers/{f.name}: id `{v}` is outside the id grammar — "
                             f"dot-joined segments of [A-Za-z0-9_-], no spaces; a period "
                             f"is its slug (`fy2025`, `ltm_2026-07`), never its label "
                             f"(EVIDENCE.md § 0). Cited, this id reads as "
                             f"`{(ID_TOKEN.match(v) or [''])[0] or '(nothing)'}`")
    return out, fails


def sheet_order(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    """[(worksheet part name, display name)] in TAB ORDER — home resolution depends on it."""
    try:
        wb = z.read("xl/workbook.xml").decode()
        rels = {}
        for el in REL_EL.findall(z.read("xl/_rels/workbook.xml.rels").decode()):
            rid, target = ATTR("Id").search(el), ATTR("Target").search(el)
            if rid and target:
                rels[rid.group(1)] = target.group(1)
    except KeyError:
        return []
    out = []
    for el in SHEET_EL.findall(wb):
        name = ATTR("name").search(el)
        rid = ATTR("r:id").search(el) or ATTR("id").search(el)
        if not (name and rid):
            continue
        target = rels.get(rid.group(1), "")
        part = "xl/" + target.lstrip("/").removeprefix("xl/")
        out.append((part, name.group(1)))
    return out


def shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    sst = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
    return [html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))
            for si in re.findall(r"<si>(.*?)</si>", sst, re.S)]


def sheet_cells(xml: str, shared: list[str]):
    """(texts: {ref: string value}, stored: {ref}) for one worksheet, in document order."""
    texts: dict[str, str] = {}
    stored: set[str] = set()
    for m in ANY_CELL.finditer(xml):
        attrs, body = m.group(1), m.group(2) or ""
        ref = ATTR("r").search(attrs)
        if not ref:
            continue
        ref = ref.group(1)
        t = ATTR("t").search(attrs)
        kind = t.group(1) if t else ""
        if kind == "s":
            v = re.search(r"<v[^>]*>(\d+)</v>", body)
            if v and int(v.group(1)) < len(shared):
                texts[ref] = shared[int(v.group(1))]
        elif kind == "inlineStr":
            texts[ref] = html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", body, re.S)))
        elif kind == "str":
            v = re.search(r"<v[^>]*>(.*?)</v>", body, re.S)
            if v:
                texts[ref] = html.unescape(v.group(1))
        if ref in texts and texts[ref].strip() == "":
            del texts[ref]
        if ref in texts or re.search(r"<v[^>]*>[^<]", body):
            stored.add(ref)
    return texts, stored


def sheet_numbers(xml: str) -> dict[str, float]:
    """{ref: value} for every numeric cell of one worksheet, from the stored XML."""
    out: dict[str, float] = {}
    for m in re.finditer(r"<c\b([^>]*)>(.*?)</c>", xml, re.S):
        attrs, body = m.group(1), m.group(2)
        if re.search(r't="(s|str|inlineStr|b|e)"', attrs):
            continue
        ref = (re.search(r'r="([A-Z]+\d+)"', attrs) or [None, None])[1]
        v = re.search(r"<v>([^<]*)</v>", body)
        if not ref or not v:
            continue
        try:
            out[ref] = float(v.group(1))
        except ValueError:
            pass
    return out


def sheet_links(z: zipfile.ZipFile, part: str, xml: str):
    """[(ref, location or None, external target or None)] for one worksheet."""
    rels = {}
    rel_part = part.replace("worksheets/", "worksheets/_rels/") + ".rels"
    if rel_part in z.namelist():
        for el in REL_EL.findall(z.read(rel_part).decode("utf-8", "replace")):
            rid, target = ATTR("Id").search(el), ATTR("Target").search(el)
            if rid and target and 'TargetMode="External"' in el:
                rels[rid.group(1)] = target.group(1)
    out = []
    for el in HYPERLINK.findall(xml):
        ref = ATTR("ref").search(el)
        loc = ATTR("location").search(el)
        rid = ATTR("r:id").search(el)
        if ref:
            out.append((ref.group(1),
                        loc.group(1) if loc else None,
                        rels.get(rid.group(1)) if rid else None))
    return out


def sheet_tables(z: zipfile.ZipFile, part: str) -> list[tuple[str, str, list[str], str]]:
    """[(display name, ref, column names, style name)] for the Excel tables one worksheet
    carries; the style is empty where the table names none."""
    import html
    import posixpath
    rel_part = part.replace("worksheets/", "worksheets/_rels/") + ".rels"
    if rel_part not in z.namelist():
        return []
    out = []
    for el in REL_EL.findall(z.read(rel_part).decode("utf-8", "replace")):
        typ, target = ATTR("Type").search(el), ATTR("Target").search(el)
        if not (typ and target and typ.group(1).endswith("/table")):
            continue
        path = posixpath.normpath(posixpath.join(posixpath.dirname(part), target.group(1)))
        if path.lstrip("/") not in z.namelist():
            path = path.lstrip("/")
        xml = z.read(path.lstrip("/")).decode("utf-8", "replace")
        head = re.search(r"<table\b[^>]*>", xml)
        name = ATTR("displayName").search(head.group(0)) if head else None
        ref = ATTR("ref").search(head.group(0)) if head else None
        cols = [html.unescape(m.group(1))
                for m in re.finditer(r'<tableColumn\b[^>]*\bname="([^"]*)"', xml)]
        style = re.search(r'<tableStyleInfo\b[^>]*\bname="([^"]+)"', xml)
        out.append((name.group(1) if name else "", ref.group(1) if ref else "", cols,
                    style.group(1) if style else ""))
    return out


def _span(ref: str) -> tuple[int, int, int, int]:
    a, _, b = ref.partition(":")
    ma, mb = re.match(r"([A-Z]+)(\d+)$", a), re.match(r"([A-Z]+)(\d+)$", b or a)
    return (col_index(ma.group(1)), int(ma.group(2)), col_index(mb.group(1)), int(mb.group(2)))


def is_stem(value: str, m: re.Match) -> bool:
    """Mirrors link_workbook.py: a token followed by `.<` is a placeholder family stem."""
    return value[m.end():m.end() + 2] == ".<"


def states(text: str, i: str) -> bool:
    """The cell states the id: it IS the id, or a line of it begins with the id."""
    if text.strip() == i:
        return True
    for line in text.split("\n"):
        line = line.strip()
        m = ID_TOKEN.match(line)
        if m and m.group(0) == i and not is_stem(line, m):
            return True
    return False


def audit_reperform(texts: dict[str, dict[str, str]]) -> list[str]:
    """GATE 3 — the Sources reperformance contract. Header labels are the contract
    (check-report SKILL § 1): `id`, `root source`, `To reperform`, case-insensitive."""
    src = texts.get(SOURCES)
    if src is None:
        return []
    headers: dict[str, str] = {}
    for ref in sorted(src, key=lambda r: (int(REF.match(r).group(2)), REF.match(r).group(1))):
        key = src[ref].strip().lower()
        if key in ("id", "root source", "to reperform"):
            headers.setdefault(key, ref)
    if "id" not in headers or "to reperform" not in headers:
        return [f"{SOURCES}: no header row carrying `id` and `To reperform` columns — "
                f"every figure row must state its flattened recipe "
                f"(check-report SKILL § 1)"]
    fails: list[str] = []
    if "root source" not in headers:
        fails.append(f"{SOURCES}: no `root source` column — the room-file citation ids a "
                     f"figure resolves to belong beside it")
    id_col, hdr_row = REF.match(headers["id"]).groups()
    rep_col = REF.match(headers["to reperform"]).group(1)
    for ref, v in src.items():
        col, row = REF.match(ref).groups()
        if col != id_col or int(row) <= int(hdr_row):
            continue
        m = ID_TOKEN.fullmatch(v.strip())
        if not (m and m.group(0).startswith("F.")):
            continue
        if not src.get(f"{rep_col}{row}", "").strip():
            fails.append(f"{SOURCES}!{rep_col}{row}: figure `{m.group(0)}` has an empty "
                         f"`To reperform` cell — state the recipe from its root reads")
    return fails


def frozen_pane(xml: str) -> tuple[int, int]:
    """(frozen rows, frozen columns) for one worksheet — (0, 0) when nothing is frozen.
    In a frozen pane ySplit/xSplit count rows/columns; in a plain split they are twips,
    so only state="frozen"/"frozenSplit" panes are read."""
    for el in PANE_EL.findall(xml):
        state = ATTR("state").search(el)
        if not state or state.group(1) not in ("frozen", "frozenSplit"):
            continue
        ys, xs = ATTR("ySplit").search(el), ATTR("xSplit").search(el)
        return (int(float(ys.group(1))) if ys else 0,
                int(float(xs.group(1))) if xs else 0)
    return (0, 0)


def audit_links(z: zipfile.ZipFile, declared: set[str] | None = None) -> dict:
    order = sheet_order(z)
    shared = shared_strings(z)
    texts: dict[str, dict[str, str]] = {}
    stored: dict[str, set[str]] = {}
    links: dict[str, list] = {}
    pane_fails: list[str] = []
    numbers: dict[str, dict[str, float]] = {}
    for part, tab in order:
        xml = z.read(part).decode("utf-8", "replace")
        texts[tab], stored[tab] = sheet_cells(xml, shared)
        numbers[tab] = sheet_numbers(xml)
        links[tab] = sheet_links(z, part, xml)
        rows, cols = frozen_pane(xml)
        if rows > FROZEN_ROWS_MAX or cols > FROZEN_COLS_MAX:
            pane_fails.append(
                f"{tab}: frozen pane holds {rows} row(s) x {cols} column(s) — freeze the "
                f"title band only (<= {FROZEN_ROWS_MAX} rows, <= {FROZEN_COLS_MAX} "
                f"columns), never a table header row, and move any preamble below the "
                f"data; a deep frozen band fills a laptop screen and blocks scrolling "
                f"(check-report SKILL § 1)")
    has_sources = SOURCES in texts
    has_evidence = EVIDENCE in texts

    # The same model link_workbook.py builds: exact-id cells, line homes, all tokens.
    exact: dict[str, list[tuple[str, str]]] = {}
    line_home: dict[str, tuple[str, str]] = {}
    tokens: dict[str, tuple[str, str]] = {}
    for _, tab in order:
        for ref, v in texts[tab].items():
            s = v.strip()
            m = ID_TOKEN.fullmatch(s)
            if m:
                exact.setdefault(m.group(0), []).append((tab, ref))
            for line in v.split("\n"):
                line = line.strip()
                lm = ID_TOKEN.match(line)
                if lm and len(line) > len(lm.group(0)) and not is_stem(line, lm):
                    line_home.setdefault(lm.group(0), (tab, ref))
            for tm in ID_TOKEN.finditer(v):
                if not is_stem(v, tm):
                    tokens.setdefault(tm.group(0), (tab, ref))

    linked = {(tab, ref): (loc, ext) for tab in links for ref, loc, ext in links[tab]}
    fails: list[str] = list(pane_fails)
    internal: list[str] = []
    no_evidence_tab: list[str] = []

    # Every hyperlink present must be internal and land on a stored cell.
    for (tab, ref), (loc, ext) in sorted(linked.items()):
        if ext:
            fails.append(f"{tab}!{ref}: external link ({ext}) — the deliverable is "
                         f"self-contained; cite files as text")
            continue
        m = LOCATION.match(loc or "")
        if not m:
            fails.append(f"{tab}!{ref}: unparseable link target ({loc})")
            continue
        tsheet, tref = m.group(1), m.group(2).replace("$", "")
        if tsheet not in texts:
            fails.append(f"{tab}!{ref}: link to missing sheet ({loc})")
        elif tref not in stored[tsheet]:
            fails.append(f"{tab}!{ref}: link lands on an empty cell ({loc})")

    def link_states(at: tuple[str, str], i: str, require_tab: str | None) -> str | None:
        loc, ext = linked.get(at, (None, None))
        if loc is None:
            return f"{at[0]}!{at[1]}: id cell `{i}` has no link"
        m = LOCATION.match(loc)
        if not m:
            return None                       # already failed above
        tsheet, tref = m.group(1), m.group(2).replace("$", "")
        if require_tab and tsheet != require_tab:
            return f"{at[0]}!{at[1]}: `{i}` links to {loc}, not to its {require_tab} row"
        if not states(texts.get(tsheet, {}).get(tref, ""), i):
            return f"{at[0]}!{at[1]}: `{i}` links to {loc}, which does not state it"
        return None

    for i in sorted(tokens):
        cells = exact.get(i, [])
        pfx = i.split(".")[0]
        ledger = LEDGER.get(pfx)
        if ledger:
            if not has_sources:
                # A single check tab staged before assembly: the ledger tab it resolves on
                # does not exist yet, so the run's own records stand in for it.
                if declared is not None and i not in declared:
                    fails.append(
                        f"dead-end id `{i}` — cited at {tokens[i][0]}!{tokens[i][1]}, "
                        f"declared by no workpapers/*.yaml record. Record the read or the "
                        f"figure before citing its id: at assembly the {ledger} tab is "
                        f"merged from those files, and the report step may not repair a "
                        f"tab it copied")
                continue
            if ledger == EVIDENCE and not has_evidence:
                no_evidence_tab.append(i)
                continue
            if not any(c[0] == ledger for c in cells):
                fails.append(f"dead-end id `{i}` — cited at {tokens[i][0]}!{tokens[i][1]}, "
                             f"on no {ledger} row")
                continue
            for at in cells:
                if at[0] != ledger:
                    err = link_states(at, i, require_tab=ledger)
                    if err:
                        fails.append(err)
        else:
            home = (cells[0] if cells else None) or line_home.get(i)
            if home is None:
                if pfx == "C":
                    internal.append(i)
                else:
                    fails.append(f"dead-end id `{i}` — cited at {tokens[i][0]}!"
                                 f"{tokens[i][1]}, stated nowhere: no cell is it and no "
                                 f"line begins with it")
                continue
            if not has_sources:
                continue    # no linker has run on a staged single tab
            for at in cells:
                if at != home:
                    err = link_states(at, i, require_tab=None)
                    if err:
                        fails.append(err)

    # Every number on the Exec Summary is a copy — the tab mints no figure — so it carries
    # a link to the cell it was copied from (link_workbook.py rule 6).
    for ref in sorted(stored.get(EXEC, set()) - set(texts.get(EXEC, {}))):
        if (EXEC, ref) not in linked:
            fails.append(
                f"{EXEC}!{ref}: number with no link to what it was copied from — the "
                f"{EXEC} mints no figure. Put it in a table whose title names the tab "
                f"it comes from, with the row's label and the column's header copied "
                f"verbatim, then re-run link_workbook.py; a number that is not a figure "
                f"(a year in a column header) is written as text (WORKBOOK.md § 6)")

    if no_evidence_tab:
        few = ", ".join(f"`{i}`" for i in no_evidence_tab[:4])
        more = f", … and {len(no_evidence_tab) - 4} more" if len(no_evidence_tab) > 4 else ""
        fails.append(f"workbook cites {len(no_evidence_tab)} evidence id(s) ({few}{more}) "
                     f"but has no '{EVIDENCE}' tab — merge workpapers/evidence-*.yaml "
                     f"into one (check-report SKILL § 1)")
    if has_sources:
        fails.extend(audit_reperform(texts))

    return {"ids": len(tokens), "hyperlinks": len(linked),
            "link_failures": fails, "internal_refs": sorted(internal)}


# GATE 4 — the design (reference/WORKBOOK.md § 8, WORKBOOK_STYLE.md § 10). Parsed from
# styles.xml and each sheet's XML, so the gate sees the stored formatting.
BASIS = "Basis of Preparation"
RUN_LEVEL_TABS = {EXEC, BASIS, "Coverage", "Open Items", SOURCES, EVIDENCE}
LEDGER_TABS = {SOURCES, EVIDENCE}
DESIGN_FONT = "Arial"
DESIGN_SIZES = {9.0, 10.0, 11.0, 12.0, 14.0}
BAND_FILL = "0A5F6A"
TAB_COLOR = {"deliverable": "0A5F6A", "ledger": "5E616A", "review": "8A5A00"}
# Prose: a text cell longer than PROSE_MIN. It sits in a wrapped column at least
# PROSE_WIDTH wide, or overflows a row that is empty to its right (WORKBOOK.md § 4, § 5).
PROSE_MIN = 60
PROSE_WIDTH = 42
# A row holding a wrapped cell carries an explicit height of at least LINE_PT per line
# the cell needs; the viewer does not fit rows on open. lines_needed mirrors the kit's
# fit_rows (WORKBOOK.md § 7) — change both.
LINE_PT = 12.5
# A cell that ends in an ellipsis, or a cell near the retired 240-character cap that ends
# without terminal punctuation, a digit or a percent, was cut. Measured on a sealed QoE
# run: 46 rulings on one tab ended mid-word at 236 characters.
CUT_MIN = 160
CUT_CAP = 228
CUT_END = re.compile(r"""(?:[.!?)\]»”"'’]|\d|%)$""")
CUT_ELLIPSIS = re.compile(r"(?:…|\.\.\.)$")
PREFIX_CUT_MIN = 40
COL_EL = re.compile(r"<col\b([^>]*)/?>")
ROW_EL = re.compile(r"<row\b([^>]*)>")


def lines_needed(text: str, width: float) -> int:
    return max(1, -(-len(text) // int(width * 1.1)))


def col_widths(xml: str) -> dict[int, float]:
    widths: dict[int, float] = {}
    for attrs in COL_EL.findall(xml):
        lo, hi, w = ATTR("min").search(attrs), ATTR("max").search(attrs), ATTR("width").search(attrs)
        if lo and hi and w:
            for i in range(int(lo.group(1)), min(int(hi.group(1)), 64) + 1):
                widths[i] = float(w.group(1))
    return widths


def row_heights(xml: str) -> dict[int, float]:
    heights: dict[int, float] = {}
    for attrs in ROW_EL.findall(xml):
        r, ht = ATTR("r").search(attrs), ATTR("ht").search(attrs)
        if r and ht:
            heights[int(r.group(1))] = float(ht.group(1))
    return heights


def col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def get_col(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out

STYLE_CELL = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)
# GATE 5 — the map (reference/WORKBOOK.md § 2): Exec Summary, the lead tabs, Basis of
# Preparation, the other check tabs in roster order, then the tail in this order.
TAIL_TABS = ["Coverage", "Open Items", SOURCES, EVIDENCE]


def style_table(z: zipfile.ZipFile) -> dict:
    """fonts[i] = (name, size); fills[i] = rgb; borders[i] = ruled?;
    xfs[i] = (numFmtId, fontId, fillId, borderId)."""
    try:
        xml = z.read("xl/styles.xml").decode("utf-8", "replace")
    except KeyError:
        return {"fonts": [], "fills": [], "borders": [], "xfs": [], "wraps": [],
                "double_bottom": [], "bold": [], "numfmts": {}}
    # An empty entry is stored self-closing (`<border />`); a parser that reads it as an
    # opening tag swallows the next entry and shifts every index after it.
    def entries(tag: str) -> list[str]:
        return [body or "" for body in re.findall(rf"<{tag}\b(?:[^>]*?/>|[^>]*>(.*?)</{tag}>)", xml, re.S)]

    fonts = []
    for f in entries("font"):
        name = re.search(r'<name val="([^"]*)"', f)
        size = re.search(r'<sz val="([^"]*)"', f)
        fonts.append((name.group(1) if name else "", float(size.group(1)) if size else 0.0))
    fills = []
    for f in entries("fill"):
        rgb = re.search(r'<fgColor rgb="([0-9A-Fa-f]+)"', f)
        fills.append(rgb.group(1)[-6:].upper() if rgb else "")
    border_list = entries("border")
    borders = [re.search(r"<(left|right|top|bottom) style=", b) is not None for b in border_list]
    double_bottom = [re.search(r'<bottom style="double"', b) is not None for b in border_list]
    bold = [re.search(r"<b\s*/>|<b val=\"(?:1|true)\"", f) is not None for f in entries("font")]
    xfs, wraps = [], []
    section = re.search(r"<cellXfs\b[^>]*>(.*?)</cellXfs>", xml, re.S)
    for attrs, body in re.findall(r"<xf\b([^>]*?)(?:/>|>(.*?)</xf>)", section.group(1) if section else "", re.S):
        ids = {k: int(v) for k, v in re.findall(r'(numFmtId|fontId|fillId|borderId)="(\d+)"', attrs)}
        xfs.append((ids.get("numFmtId", 0), ids.get("fontId", 0), ids.get("fillId", 0),
                    ids.get("borderId", 0)))
        wraps.append('wrapText="1"' in body or 'wrapText="true"' in body)
    numfmts = {int(i): html.unescape(code) for i, code in
               re.findall(r'<numFmt numFmtId="(\d+)" formatCode="([^"]*)"', xml)}
    return {"fonts": fonts, "fills": fills, "borders": borders, "xfs": xfs, "wraps": wraps,
            "double_bottom": double_bottom, "bold": bold, "numfmts": numfmts}


# A cell reading as the run's machine vocabulary rather than words (WORKBOOK.md § 3
# Language): a whole cell that is a snake_case code — `consistent_late_payer`,
# `not_supported` — or two joined by a colon (`phone_call: promise_to_pay`). A check id
# (`r5_measures`) names a check and links to its tab, so a cell opening with a roster
# token is not one; nor is an id in the id column, nor a ledger or Basis of Preparation
# cell, where the run's own terms are declared for the reader.
MACHINE_CODE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+(?::\s*[a-z][a-z0-9]*(?:_[a-z0-9]+)*)?$"
                          r"|^[a-z][a-z0-9]*:\s*[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
ROSTER_ID = re.compile(r"^[a-z]{1,3}\d[a-z0-9_]*$")


def audit_design(z: zipfile.ZipFile) -> list[str]:
    """One line per (tab, rule) that fails, with a count and the first cell."""
    styles = style_table(z)
    order = sheet_order(z)
    shared = shared_strings(z)
    fails: list[str] = []
    table_names: set[str] = set()
    cut_candidates: list[tuple[str, str, str]] = []
    all_texts: list[str] = []

    def rule(tab, what, cells, ref):
        n = len(cells)
        fails.append(f"{tab}: {what} — {n} cell(s), first {cells[0]} ({ref})" if n
                     else f"{tab}: {what} ({ref})")

    for part, tab in order:
        xml = z.read(part).decode("utf-8", "replace")
        texts, stored = sheet_cells(xml, shared)
        ledger = tab in LEDGER_TABS
        summary = tab == EXEC       # band rows 1-3, no row-4 header rule, tables anywhere below
        bad_font, col_a, band_cells, general, unstyled, unruled = [], [], [], [], [], []
        cut, narrow, short_rows, coded = [], [], [], []
        widths, heights = col_widths(xml), row_heights(xml)
        by_row: dict[int, list[int]] = {}
        for ref in list(texts) + list(stored):
            m = re.match(r"([A-Z]+)(\d+)$", ref)
            by_row.setdefault(int(m.group(2)), []).append(col_index(m.group(1)))
        need_lines: dict[int, int] = {}
        for m in STYLE_CELL.finditer(xml):
            col, row, attrs, body = m.group(1), int(m.group(2)), m.group(3), m.group(4) or ""
            ref = f"{col}{row}"
            has_value = ref in texts or ref in stored
            if not has_value:
                continue
            if col == "A":
                col_a.append(ref)
            s = ATTR("s").search(attrs)
            xf = styles["xfs"][int(s.group(1))] if s and int(s.group(1)) < len(styles["xfs"]) else None
            if xf is None:
                unstyled.append(ref)
                continue
            num_fmt, font_id, fill_id, border_id = xf
            ruled = border_id < len(styles["borders"]) and styles["borders"][border_id]
            name, size = styles["fonts"][font_id] if font_id < len(styles["fonts"]) else ("", 0.0)
            if name != DESIGN_FONT or size not in DESIGN_SIZES:
                bad_font.append(ref)
            if fill_id < len(styles["fills"]) and styles["fills"][fill_id] == BAND_FILL:
                band_cells.append(ref)
            if ref not in texts and ref in stored and num_fmt == 0:
                general.append(ref)
            if ((row == 4 and not summary) or (ref not in texts and row > 3)) and not ruled:
                unruled.append(ref)                 # a header or a number below the band is a table cell
            if (ref in texts and row > 4 and not ledger and tab != BASIS and col != "B"
                    and MACHINE_CODE.match(texts[ref].strip()) and not ROSTER_ID.match(texts[ref].strip())):
                coded.append(ref)
            if ref in texts and row > 4 and not ledger:
                t = texts[ref].rstrip()
                si = int(s.group(1))
                wrapped = si < len(styles["wraps"]) and styles["wraps"][si]
                width = widths.get(col_index(col), 8.43)
                if wrapped:
                    need_lines[row] = max(need_lines.get(row, 1), lines_needed(t, width))
                if len(t) > PROSE_MIN:
                    right_empty = not any(ci > col_index(col) for ci in by_row.get(row, []))
                    if not (wrapped and width >= PROSE_WIDTH) and not right_empty:
                        narrow.append(ref)
                if len(t) >= CUT_MIN and (CUT_ELLIPSIS.search(t) or
                                          (len(t) >= CUT_CAP and not CUT_END.search(t))):
                    cut.append(ref)
        if unstyled:
            rule(tab, "cells left in the default style (Calibri 11)", unstyled, "WORKBOOK_STYLE.md § 2")
        if bad_font:
            rule(tab, f"font not {DESIGN_FONT} 9/10/11/12/14", bad_font, "WORKBOOK_STYLE.md § 2")
        if col_a:
            rule(tab, "column A is the empty margin", col_a, "WORKBOOK_STYLE.md § 4")
        band_rows = sorted({int(re.sub(r"[A-Z]+", "", c)) for c in band_cells})
        if 4 not in band_rows and not summary:
            rule(tab, f"the primary table's BAND header on row 4 (found rows {band_rows or 'none'})", [], "WORKBOOK_STYLE.md § 4")
        band_figures = [c for c in band_cells if c not in texts]
        if band_figures:
            rule(tab, "BAND fill on a figure — BAND is a table header's fill, never a subtotal's or a total's",
                 band_figures, "WORKBOOK_STYLE.md § 4")
        if general:
            rule(tab, "numeric cell in General format", general, "WORKBOOK_STYLE.md § 3")
        if unruled:
            rule(tab, "table cell with no border — the hairline on every side", unruled, "WORKBOOK_STYLE.md § 4")
        if narrow:
            rule(tab, f"prose in a narrow or unwrapped column with a neighbour — a wrapped column "
                      f"at least {PROSE_WIDTH} wide (description or last), or a row empty to its right", narrow, "WORKBOOK.md § 5")
        for row, lines in sorted(need_lines.items()):
            if lines > 1 and heights.get(row, 0) < LINE_PT * lines:
                short_rows.append(f"row {row} ({lines} lines, height {heights.get(row, 'unset')})")
        if short_rows:
            rule(tab, "row holding a wrapped cell without a height that fits it — kit `fit_rows`", short_rows, "WORKBOOK.md § 7")
        if coded:
            rule(tab, f"the run's machine vocabulary where the reader's words belong (`{texts[coded[0]].strip()[:40]}`) — "
                      f"write the status, class or cause in words, declared beside the code "
                      f"(`consistent_late_payer` shows as `Consistently late payer`)", coded, "WORKBOOK.md § 3")
        if cut:
            rule(tab, "long text cut mid-sentence — split it into a Notes row or the check record, never truncate", cut, "WORKBOOK.md § 4")
        if "<mergeCell " in xml:
            rule(tab, "merged cells", [], "WORKBOOK_STYLE.md § 4")
        # Excel tables (wbkit.excel_tables): Excel repairs, rather than opens, a table whose
        # header cells disagree with its column names, whose name repeats in the workbook,
        # or that overlaps the sheet's own AutoFilter.
        spans, unstyled_tables, crowded_above, crowded_below = [], [], [], []
        last_row = max(by_row) if by_row else 0
        for name, tref, cols, style in sheet_tables(z, part):
            c1, r1, c2, r2 = _span(tref)
            # Spacing (WORKBOOK.md § 4): the row above a header below the band is blank —
            # Google Sheets draws the table's menus there — and two blank rows follow the
            # table, its Total rows included, before anything else on the tab.
            if r1 != 4 and (r1 - 1) in by_row:
                crowded_above.append(tref)
            end = r2
            while (end + 1) in by_row:
                end += 1
            if end < last_row and ((end + 1) in by_row or (end + 2) in by_row):
                crowded_below.append(tref)
            heads = [texts.get(f"{get_col(c)}{r1}", "") for c in range(c1, c2 + 1)]
            if [h.strip() for h in heads] != [c.strip() for c in cols]:
                rule(tab, f"table {name} ({tref}): its header row does not read its column "
                          f"names — rebuild it with wbkit.excel_tables", [], "WORKBOOK.md § 4")
            if not style:
                unstyled_tables.append(tref)
            if name.casefold() in table_names:
                rule(tab, f"table name {name} repeats in the workbook", [], "WORKBOOK.md § 4")
            table_names.add(name.casefold())
            spans.append(_span(tref))
        if crowded_above:
            rule(tab, "a table header with the row above it filled — leave one blank row "
                      "between a Section heading and its table (wbkit.section returns the "
                      "header's row)", crowded_above, "WORKBOOK.md § 4")
        if crowded_below:
            rule(tab, "a table followed within two rows by the next block — leave two blank "
                      "rows under every table, its Total included (wbkit.next_block)",
                 crowded_below, "WORKBOOK.md § 4")
        if unstyled_tables:
            rule(tab, "Excel table naming no table style — Google Sheets imports it as plain "
                      "cells; build it with wbkit.excel_tables", unstyled_tables, "WORKBOOK_STYLE.md § 9")
        sheet_filter = re.search(r"<autoFilter\b[^>]*\bref=\"([^\"]+)\"", xml.split("<tableParts")[0])
        if spans and sheet_filter:
            f1, fr1, f2, fr2 = _span(sheet_filter.group(1))
            if any(not (f2 < a or c < f1 or fr2 < b or d < fr1) for a, b, c, d in spans):
                rule(tab, "the sheet's AutoFilter overlaps an Excel table — each table carries "
                          "its own filter", [], "WORKBOOK.md § 4")
        rows, cols = frozen_pane(xml)
        if (rows, cols) != (3, 1):              # the band alone; never a table header row
            rule(tab, f"freeze panes at B4 — the title band, never a table header "
                      f"(found {rows} row(s) x {cols} column(s))", [],
                 "WORKBOOK.md § 6" if summary else "WORKBOOK_STYLE.md § 4")
        grid_off = re.search(r'<sheetView\b[^>]*showGridLines="0"', xml) is not None
        if grid_off == ledger:
            rule(tab, "gridlines off on a deliverable tab, on for a ledger", [], "WORKBOOK_STYLE.md § 4")
        color = re.search(r'<tabColor[^>]*rgb="([0-9A-Fa-f]+)"', xml)
        want = TAB_COLOR["ledger"] if ledger else TAB_COLOR["review"] if tab == "Open Items" else TAB_COLOR["deliverable"]
        if not color or color.group(1)[-6:].upper() != want:
            rule(tab, f"tab colour {want}", [], "WORKBOOK_STYLE.md § 4")
        if "B1" not in texts:
            rule(tab, "B1 holds the title", [], "WORKBOOK.md § 3")
        if "B2" not in texts:
            rule(tab, "B2 holds the subtitle", [], "WORKBOOK.md § 3")
        if tab not in RUN_LEVEL_TABS and not texts.get("B3", "").strip():
            rule(tab, "B3 holds the summary", [], "WORKBOOK.md § 3")
        if summary and "B3" not in texts:
            rule(tab, "B3 holds the position sentence", [], "WORKBOOK.md § 6")
        for ref, t in texts.items():
            if len(t.rstrip()) >= PREFIX_CUT_MIN and not CUT_END.search(t.rstrip()):
                cut_candidates.append((tab, ref, t.rstrip()))
            all_texts.append(t.rstrip())
    # A label cut to a length: its text is the opening of a longer statement the workbook
    # carries elsewhere. Measured on a sealed revenue run: a leak's name cut at 120
    # characters mid-word ("…has since remov") beside its whole sentence.
    all_texts.sort()
    cut_at: dict[str, list[str]] = {}
    for tab, ref, t in cut_candidates:
        i = bisect.bisect_right(all_texts, t)
        if i < len(all_texts) and all_texts[i].startswith(t) and len(all_texts[i]) > len(t) \
                and all_texts[i][len(t)].isalnum():
            cut_at.setdefault(tab, []).append(ref)
    for tab, refs in cut_at.items():
        rule(tab, "text cut mid-word from a longer statement the workbook carries — write "
                  "the whole claim, never truncate", refs, "WORKBOOK.md § 4")
    return fails


def fold(name: str) -> str:
    """A tab name on the fold — `Q2 billings detail` and `q2_billings_detail` are one
    check. Mirrors link_workbook.py normalize — change both."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def recipe_frontmatter(path: pathlib.Path) -> dict[str, str]:
    """The recipe's frontmatter as flat strings (a flow list stays `[a, b]`), read as
    text: the recipe is markdown and this script is stdlib-only. Mirrors the parser in
    check-plugin.py."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            out[key] = m.group(2).strip()
        elif key and line.startswith((" ", "\t")):
            out[key] += " " + line.strip()
    return out


def fm_list(value: str | None) -> list[str]:
    """`[q6, q5]` or `q6` as a list of bare tokens."""
    if not value:
        return []
    return [v.strip().strip("'\"") for v in value.strip().strip("[]").split(",") if v.strip()]


def lead_families(run: dict) -> list[str] | None:
    """The families whose tabs lead the workbook: the recipe's `lead`, else its
    `headline` alone, else none. None when the run names a recipe this machine cannot
    read — the map is then held on the shape alone."""
    recipe = (run.get("plan") or {}).get("recipe")
    if not recipe:
        return []
    fm = recipe_frontmatter(pathlib.Path(recipe))
    if not fm:
        return None
    return fm_list(fm.get("lead")) or fm_list(fm.get("headline"))


def tab_owners(checks: list[dict], tabs: list[str]) -> tuple[dict[str, str], list[str]]:
    """({check tab: the rostered check it belongs to}, failures). A tab belongs to the check
    whose id its name opens with, or else to the one check of the family its token names."""
    roster = [c["id"] for c in checks]
    family = {c["id"]: (c.get("params") or {}).get("family") for c in checks}
    per_family: dict[str, int] = {}
    for fam in family.values():
        if fam:
            per_family[fam] = per_family.get(fam, 0) + 1
    owner: dict[str, str] = {}
    fails: list[str] = []
    for tab in tabs:
        if tab in RUN_LEVEL_TABS:
            continue
        f, token = fold(tab), fold(tab.split(" ", 1)[0])
        hit = next((cid for cid in roster if f == fold(cid) or f.startswith(fold(cid) + "_")), None)
        if hit is None:      # `q6 EBITDA bridge` for the one check of family q6
            hit = next((cid for cid in roster if family[cid] and token == fold(family[cid])
                        and per_family[family[cid]] == 1), None)
        if hit is None:
            fails.append(f"{tab}: check tab names no check in run.json — the name opens "
                         f"with the roster token, `<token> <Title>` (WORKBOOK.md § 2)")
            continue
        owner[tab] = hit
    return owner, fails


def wanted_order(run_dir: pathlib.Path, tabs: list[str], pairs=()) -> tuple[list[str] | None, list[str], list[str]]:
    """(the tab order the run wants, the lead families, failures). The order is None
    when the run cannot say — no run.json, no checks, a recipe not readable here."""
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, [], []
    checks = [c for c in run.get("checks") or [] if c.get("id")]
    lead = lead_families(run)
    if not checks or lead is None:
        return None, lead or [], []
    roster = [c["id"] for c in checks]
    family = {c["id"]: (c.get("params") or {}).get("family") for c in checks}
    owner, fails = tab_owners(checks, tabs)
    check_tabs = sorted(owner, key=lambda tab: roster.index(owner[tab]))
    # A check's match tabs follow its own tab — summary, schedule, reconciling items,
    # rules — wherever that check sits in the strip: with the lead tabs where it is a
    # lead, in roster order otherwise. The reader reaches a reconciliation's item detail
    # from the reconciliation, not ahead of the story.
    matched = {t for p in pairs for t in p}
    sets: dict[str, list[str]] = {}
    for p in pairs:
        if p[0] in owner:
            sets.setdefault(owner[p[0]], []).extend(p)

    def group(cid: str) -> list[str]:
        return [t for t in check_tabs if owner[t] == cid and t not in matched] + sets.get(cid, [])

    owners = list(dict.fromkeys(owner[t] for t in check_tabs))
    lead_ids = [cid for fam in lead for cid in owners if family[cid] == fam]
    lead_tabs = [t for cid in lead_ids for t in group(cid)]
    rest = [t for cid in owners if cid not in lead_ids for t in group(cid)]
    want = ([EXEC] if EXEC in tabs else []) + lead_tabs + \
        ([BASIS] if BASIS in tabs else []) + rest + [tab for tab in TAIL_TABS if tab in tabs]
    return want, lead, fails


def audit_order(z: zipfile.ZipFile, run_dir: pathlib.Path | None = None) -> list[str]:
    """GATE 5 — the map. Empty on a tab staged before assembly (no Exec Summary)."""
    order = sheet_order(z)
    tabs = [tab for _, tab in order]
    if EXEC not in tabs:
        return []
    fails: list[str] = []
    strip = " · ".join(tabs)
    if tabs[0] != EXEC:
        fails.append(f"{EXEC} is the first tab; the strip opens with `{tabs[0]}` "
                     f"(WORKBOOK.md § 2)")
    tail = [tab for tab in TAIL_TABS if tab in tabs]
    if tail and tabs[-len(tail):] != tail:
        fails.append(f"the strip closes with {' · '.join(tail)}, in that order, after the "
                     f"last check tab; it reads {strip} (WORKBOOK.md § 2)")
    shared = shared_strings(z)
    texts = {tab: sheet_cells(z.read(part).decode("utf-8", "replace"), shared)[0]
             for part, tab in order}
    pairs, _ = match_pairs(texts)
    for p in pairs:                             # each set together, in its own order
        at = [tabs.index(t) for t in p]
        if at != list(range(at[0], at[0] + len(p))):
            fails.append(f"a reconciliation's match tabs sit together — summary, schedule, "
                         f"reconciling items, rules: {' · '.join(p)}; the strip reads {strip} "
                         f"(WORKBOOK.md § 2)")
    want, lead, unnamed = (None, [], []) if run_dir is None else wanted_order(run_dir, tabs, pairs)
    fails.extend(unnamed)
    if want is not None:
        if want != tabs and not unnamed:
            fails.append(f"tab strip reads {strip}; the map wants {' · '.join(want)} — "
                         f"{EXEC}, the lead tabs (families: "
                         f"{', '.join(lead) or 'none'}), "
                         f"{BASIS}, the other checks in roster order — each check's match "
                         f"tabs after its own tab — the tail "
                         f"(WORKBOOK.md § 2)")
        return fails
    return fails


# GATE 6 — the match tabs (reference/WORKBOOK.md § 6, scripts/match_tabs.py). Found by the
# marker their B1 carries after the token; mirrors match_tabs.py — change both.
SUMMARY_MARK = " · Match summary"
SCHEDULE_MARK = " · Match schedule"
RULES_MARK = " · Match rules"
RECON_MARK = " · Reconciling items"


def match_pairs(texts: dict[str, dict[str, str]]) -> tuple[list[tuple[str, ...]], list[str]]:
    """([(summary tab, schedule tab[, reconciling tab][, rules tab])] in tab order,
    failures), paired on the token their B1 opens with."""
    sums: dict[str, str] = {}
    schs: dict[str, str] = {}
    asms: dict[str, str] = {}
    recs: dict[str, str] = {}
    for tab, t in texts.items():
        b1 = t.get("B1", "")
        if SUMMARY_MARK in b1:
            sums[b1.split(SUMMARY_MARK)[0].strip()] = tab
        elif SCHEDULE_MARK in b1:
            schs[b1.split(SCHEDULE_MARK)[0].strip()] = tab
        elif RULES_MARK in b1:
            asms[b1.split(RULES_MARK)[0].strip()] = tab
        elif RECON_MARK in b1:
            recs[b1.split(RECON_MARK)[0].strip()] = tab
    fails = [f"{tab}: a match summary with no match schedule for `{tok}` (match_tabs.py "
             f"writes both)" for tok, tab in sums.items() if tok not in schs]
    fails += [f"{tab}: a match schedule with no match summary for `{tok}`"
              for tok, tab in schs.items() if tok not in sums]
    fails += [f"{tab}: match tab with no match summary for `{tok}`"
              for d_ in (asms, recs) for tok, tab in d_.items() if tok not in sums]
    order = list(texts)
    pairs = sorted(((sums[k], schs[k]) + ((recs[k],) if k in recs else ()) +
                    ((asms[k],) if k in asms else ())
                    for k in sums if k in schs), key=lambda p: order.index(p[0]))
    return pairs, fails


def _rows(texts: dict[str, str], numbers: dict[str, float]) -> dict[int, dict[str, object]]:
    out: dict[int, dict[str, object]] = {}
    for src in (texts, numbers):
        for ref, v in src.items():
            m = REF.match(ref)
            if m:
                out.setdefault(int(m.group(2)), {})[m.group(1)] = v
    return out


def audit_match(z: zipfile.ZipFile, assembled: bool | None = None) -> list[str]:
    """GATE 6. Every line of a match summary is its schedule filtered on the line's status:
    the same count of rows and the same amount, to the cent; the opening line and the total
    are the whole schedule; the schedule holds each id once, sorted into one block per
    status; and, once the workbook is assembled, each line's words link to its block."""
    shared = shared_strings(z)
    texts: dict[str, dict[str, str]] = {}
    numbers: dict[str, dict[str, float]] = {}
    links: dict[str, list] = {}
    for part, tab in sheet_order(z):
        xml = z.read(part).decode("utf-8", "replace")
        texts[tab], _ = sheet_cells(xml, shared)
        numbers[tab] = sheet_numbers(xml)
        links[tab] = sheet_links(z, part, xml)
    if assembled is None:
        assembled = EXEC in texts
    pairs, fails = match_pairs(texts)
    for summ, sched, *_ in pairs:
        rows = _rows(texts[sched], numbers[sched])
        hdr = rows.get(4, {})
        col = {str(v).strip(): c for c, v in hdr.items() if isinstance(v, str)}
        st_col = col.get("Status")
        amt_col = next((c for h, c in col.items() if h.split(" (")[0] == "Amount"), None)
        if not st_col or not amt_col:
            fails.append(f"{sched}: the row-4 header needs `Status` and `Amount` columns")
            continue
        blocks: dict[str, list[int]] = {}
        seen_ids: set[str] = set()
        prev = None
        n_rows, total, foot = 0, 0.0, None
        for r in range(5, max(rows) + 1 if rows else 5):
            row = rows.get(r)
            if not row:
                break
            if row.get("C") == "Total" and "B" not in row:
                foot = float(row.get(amt_col, 0.0))
                break
            word, i = row.get(st_col), row.get("B")
            if not isinstance(word, str) or not word.strip():
                fails.append(f"{sched}!{st_col}{r}: a row with no status")
                continue
            if i in seen_ids:
                fails.append(f"{sched}!B{r}: `{i}` is on the schedule twice")
            seen_ids.add(i)
            if word != prev and word in blocks:
                fails.append(f"{sched}!{st_col}{r}: `{word}` rows are split — the schedule is "
                             f"sorted by status, one block each")
            blocks.setdefault(word, [r, r, 0, 0.0])
            b = blocks[word]
            b[1], b[2], b[3] = r, b[2] + 1, b[3] + float(row.get(amt_col, 0.0))
            prev = word
            n_rows += 1
            total += float(row.get(amt_col, 0.0))
        if foot is not None and abs(foot - total) > 0.005:
            fails.append(f"{sched}: the Total row reads {foot:,.2f}; its rows sum to {total:,.2f}")
        srows = _rows(texts[summ], numbers[summ])
        shown: set[str] = set()
        slinks = {ref: loc for ref, loc, _ in links[summ]}
        for r in range(5, max(srows) + 1 if srows else 5):
            row = srows.get(r)
            if not row:
                break
            word = row.get("C")
            if not isinstance(word, str):
                continue
            n, a = row.get("D"), row.get("E")
            if word.startswith("All ") or word == "Total":
                want = (n_rows, total)
            elif word in blocks:
                want = (blocks[word][2], blocks[word][3])
                shown.add(word)
                if assembled:
                    m = LOCATION.match(slinks.get(f"C{r}") or "")
                    first = int(REF.match(m.group(2).replace("$", "")).group(2)) if m else None
                    if not m or m.group(1) != sched or first != blocks[word][0]:
                        fails.append(f"{summ}!C{r}: `{word}` does not open its rows on {sched} "
                                     f"(row {blocks[word][0]}); link_workbook.py places the link")
            else:
                want = (0, 0.0)
            if n is None or a is None or int(n) != want[0] or abs(float(a) - want[1]) > 0.005:
                fails.append(f"{summ}!C{r}: `{word}` reads {n} for {a}; {sched} filtered on it "
                             f"holds {want[0]} for {want[1]:,.2f}")
        for word in sorted(set(blocks) - shown):
            fails.append(f"{summ}: status `{word}` is on {sched} and not on the summary")
    # the reconciling items foot: the lines above the per-bank total add up to it
    for pair in pairs:
        rec = next((t for t in pair if RECON_MARK in texts[t].get("B1", "")), None)
        if rec is None:
            continue
        rrows = _rows(texts[rec], numbers[rec])
        body = 0.0
        for r in range(5, max(rrows) + 1 if rrows else 5):
            row = rrows.get(r)
            if not row:
                break
            if isinstance(row.get("F"), (int, float)) and isinstance(row.get("G"), (int, float)) and \
                    abs(float(row["F"]) + float(row["G"]) - float(row.get("E", 0.0))) > 0.005:
                fails.append(f"{rec}!E{r}: its positive and negative items add to "
                             f"{float(row['F']) + float(row['G']):,.2f}, the line reads {float(row.get('E', 0.0)):,.2f}")
            if str(row.get("C", "")).endswith("per bank"):
                if abs(body - float(row.get("E", 0.0))) > 0.005:
                    fails.append(f"{rec}!E{r}: the lines above sum to {body:,.2f}, the total "
                                 f"reads {float(row.get('E', 0.0)):,.2f}")
                break
            body += float(row.get("E", 0.0))
    return fails


# GATE 7 — every reconciliation shows its matching (check-recon § 5). The one without match
# tabs has a side with no item grain, and its check tab says so on a line opening with this.
NO_GRAIN_MARK = "No item grain:"


def audit_recon(z: zipfile.ZipFile, stem: str, run_dir: pathlib.Path | None) -> list[str]:
    """GATE 7, with the run's roster. The tab file of a `recon` check (`<check>.xlsx`) holds
    a whole set of match tabs — summary, schedule, reconciling items, rules — however the
    items were matched, or states `No item grain:`; at the seal, so does every `recon`
    check that has a tab in the workbook."""
    if run_dir is None:
        return []
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    checks = [c for c in run.get("checks") or [] if c.get("id")]
    recon = [c["id"] for c in checks if c.get("kind") == "recon"]
    if not recon:
        return []
    shared = shared_strings(z)
    texts = {tab: sheet_cells(z.read(part).decode("utf-8", "replace"), shared)[0]
             for part, tab in sheet_order(z)}
    pairs, _ = match_pairs(texts)
    whole = [p for p in pairs if len(p) == 4]

    def states(tabs) -> bool:
        return any(str(v).strip().startswith(NO_GRAIN_MARK) for t in tabs for v in texts[t].values())
    why = ("write them with scripts/match_tabs.py from resolve() or, for a match built with "
           "joins, from_assignment(); where a side has no item grain, the check tab says so on "
           f"a line opening `{NO_GRAIN_MARK}` (check-recon § 5)")
    if EXEC not in texts:
        if stem in recon and not whole and not states(texts):
            return [f"{stem}: a reconciliation with no " +
                    ("whole set of " if pairs else "") + f"match tabs — {why}"]
        return []
    owner, _ = tab_owners(checks, list(texts))
    fails = []
    for cid in recon:
        mine = [t for t, o in owner.items() if o == cid]
        if mine and not any(owner.get(p[0]) == cid for p in whole) and not states(mine):
            fails.append(f"{cid}: a reconciliation whose tabs ({', '.join(mine)}) carry no whole "
                         f"set of match tabs — {why}")
    return fails


# GATE 8 — live arithmetic (WORKBOOK.md § 7). Every formula the gate can read — a
# reference, a sum, a signed sum, a conditional sum (scripts/formula.py) — is recomputed
# from the stored values and must agree with its own cached result: a stale cache shows a
# viewer one figure and Excel another. And on a sheet its tab script mapped (`wbkit.save`
# wrote a cells map naming it), a subtotal, a total or a walk's derived line (`= …`) is a
# formula over the rows it adds, never a typed value.
SUBTOTAL_FILL = "EDEBE3"     # wbkit's MIST, the Subtotal style's fill
FORMULA_EL = re.compile(r'<c r="([A-Z]+\d+)"[^>]*>\s*<f>(.*?)</f>\s*(?:<v>([^<]*)</v>)?', re.S)


def cell_maps(workbook: pathlib.Path, run_dir: pathlib.Path | None) -> dict[str, set[str]]:
    """{sheet: the cells declared stated} for every sheet a tab script mapped: the cells
    map beside the workbook gated (`<stem>.cells.json`) and, with a run directory, every
    placed tab's."""
    found = [workbook.with_name(workbook.stem + ".cells.json")]
    if run_dir is not None:
        found += sorted((run_dir / "out" / "tabs").glob("*.cells.json"))
    sheets: dict[str, set[str]] = {}
    for f in found:
        try:
            data = json.loads(f.read_text(encoding="utf-8")).get("sheets") or {}
        except (OSError, ValueError, AttributeError):
            continue
        for name, cells in data.items():
            sheets.setdefault(name, set()).update(
                c for c, e in (cells or {}).items() if isinstance(e, dict) and e.get("stated"))
    return sheets


def audit_formulas(z: zipfile.ZipFile, mapped: dict[str, set[str]]) -> list[str]:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import formula as fx  # noqa: PLC0415
    shared = shared_strings(z)
    order = sheet_order(z)
    values: dict[str, dict[str, object]] = {}
    xmls: dict[str, str] = {}
    for part, tab in order:
        tab = html.unescape(tab)
        xml = z.read(part).decode("utf-8", "replace")
        xmls[tab] = xml
        texts, _ = sheet_cells(xml, shared)
        vals: dict[str, object] = dict(sheet_numbers(xml))
        vals.update(texts)
        values[tab] = vals
    get = lambda sh, co: values.get(sh, {}).get(co)  # noqa: E731
    styles = style_table(z) if mapped else None
    fails: list[str] = []
    for tab, xml in xmls.items():
        stale = []
        formulas: set[str] = set()
        for m in FORMULA_EL.finditer(xml):
            ref, text_, cached = m.group(1), html.unescape(m.group(2)), m.group(3)
            formulas.add(ref)
            if cached in (None, ""):
                continue                        # GATE 1 refuses an empty result
            try:
                stored = float(cached)
            except ValueError:
                continue
            got = fx.evaluate(text_, tab, get)
            if got is None:
                continue
            pre = fx.precedents(text_, tab) or []
            terms = [v for v in (get(*c) for c in pre) if isinstance(v, float)]
            if not fx.foots(stored, got, len(pre), terms + [got]):
                stale.append(f"{ref} (={text_[:40]} computes {got:,.2f}; stored {stored:,.2f})")
        if stale:
            fails.append(f"{tab}: a formula whose stored result is not what it computes — "
                         f"{len(stale)} cell(s), first {stale[0]} — write the result its "
                         f"formula computes (wbkit.save caches it)")
        if tab not in mapped or styles is None:
            continue
        rows: dict[int, list[tuple[str, int]]] = {}
        for m in STYLE_CELL.finditer(xml):
            col, row, attrs = m.group(1), int(m.group(2)), m.group(3)
            si = ATTR("s").search(attrs)
            rows.setdefault(row, []).append((col, int(si.group(1)) if si else 0))
        typed = []
        for row, cells in sorted(rows.items()):
            if row < 5:
                continue
            def xf(i):
                return styles["xfs"][i] if i < len(styles["xfs"]) else (0, 0, 0, 0)
            total_row = any(xf(i)[3] < len(styles["double_bottom"]) and styles["double_bottom"][xf(i)[3]]
                            for _, i in cells)
            derived = any(str(values[tab].get(f"{c}{row}", "")).strip().startswith("=")
                          for c in ("B", "C"))
            for col, i in cells:
                ref = f"{col}{row}"
                v = values[tab].get(ref)
                if ref in formulas or not isinstance(v, float):
                    continue
                _, font_id, fill_id, _ = xf(i)
                if ref in mapped.get(tab, set()):
                    continue                    # declared stated (`wbkit.stated`), not a sum
                subtotal = (fill_id < len(styles["fills"]) and styles["fills"][fill_id] == SUBTOTAL_FILL
                            and font_id < len(styles["bold"]) and styles["bold"][font_id])
                if total_row or derived or subtotal:
                    typed.append(ref)
        if typed:
            fails.append(f"{tab}: a subtotal, total or derived line (`= …`) typed as a value — "
                         f"{len(typed)} cell(s), first {typed[0]} — write it with wbkit.total() "
                         f"over the rows it adds (WORKBOOK.md § 7)")
    return fails


def audit(path: pathlib.Path, declared: set[str] | None = None,
          ledger_fails: list[str] | None = None,
          run_dir: pathlib.Path | None = None) -> dict:
    with zipfile.ZipFile(path) as z:
        names = dict(sheet_order(z))
        sheets, formulas, blanks = [], 0, []
        for part in sorted(n for n in z.namelist()
                           if n.startswith("xl/worksheets/") and n.endswith(".xml")):
            xml = z.read(part).decode("utf-8", "replace")
            tab = names.get(part, part.rsplit("/", 1)[-1])
            n_f = n_blank = 0
            for m in CELL.finditer(xml):
                n_f += 1
                ref, whole, inner = m.group(1), m.group(2), m.group(3)
                if whole is None or whole.startswith("<v /") or whole.startswith("<v/") \
                        or (inner is not None and inner.strip() == ""):
                    n_blank += 1
                    blanks.append({"sheet": tab, "cell": ref})
            formulas += n_f
            if n_f:
                sheets.append({"sheet": tab, "formulas": n_f, "uncached": n_blank})
        rep = {"workbook": str(path), "formula_cells": formulas,
               "uncached": len(blanks), "by_sheet": sheets, "cells": blanks,
               "tabs": list(names.values())}
        rep["links"] = audit_links(z, declared)
        rep["design"] = audit_design(z)
        rep["order"] = audit_order(z, run_dir)
        rep["match"] = audit_match(z)
        rep["recon"] = audit_recon(z, path.stem, run_dir)
        rep["formulas"] = audit_formulas(z, cell_maps(path, run_dir))
    if ledger_fails:
        rep["links"]["link_failures"] = list(ledger_fails) + rep["links"]["link_failures"]
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workbook", type=pathlib.Path, nargs="?",
                    help="the workbook to gate; omit it to gate --run-dir's ledgers alone")
    ap.add_argument("--run-dir", type=pathlib.Path,
                    help="the run directory, so a tab staged before assembly resolves its "
                         "ledger ids against workpapers/*.yaml instead of skipping them, "
                         "and the ledgers themselves are gated (shape, id grammar)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-report", type=int, default=15)
    a = ap.parse_args()
    if a.workbook is None and not a.run_dir:
        print("pass a workbook, or --run-dir to gate the ledgers alone", file=sys.stderr)
        return 2
    if a.workbook is not None and not a.workbook.is_file():
        print(f"{a.workbook}: not a file", file=sys.stderr)
        return 2
    declared, ledger_fails = declared_ids(a.run_dir) if a.run_dir else (None, [])
    if a.run_dir and declared is None:
        print(f"{a.run_dir}: no workpapers/ directory", file=sys.stderr)
        return 2
    if a.workbook is None:
        if a.json:
            print(json.dumps({"run_dir": str(a.run_dir), "declared_ids": len(declared),
                              "ledger_failures": ledger_fails}, indent=2))
        elif ledger_fails:
            print(f"{a.run_dir.name}: {len(ledger_fails)} ledger failure(s) over "
                  f"{len(declared)} declared ids.\n")
            for f in ledger_fails[:a.max_report]:
                print(f"    {f}")
            if len(ledger_fails) > a.max_report:
                print(f"    … and {len(ledger_fails) - a.max_report} more")
            print("\n  Fix: rewrite the ledger named - a list at its top level, every id "
                  "inside the grammar (EVIDENCE.md § 0).")
        else:
            print(f"{a.run_dir.name}: {len(declared)} declared ids over workpapers/*.yaml, "
                  f"every ledger a list, every id inside the grammar.")
        return 1 if ledger_fails else 0
    try:
        rep = audit(a.workbook, declared, ledger_fails, a.run_dir)
    except zipfile.BadZipFile:
        print(f"{a.workbook}: not a readable .xlsx", file=sys.stderr)
        return 2
    link_fails = rep["links"]["link_failures"]
    design_fails = rep.get("design", [])
    order_fails = rep.get("order", [])
    match_fails = rep.get("match", [])
    recon_fails = rep.get("recon", [])
    formula_fails = rep.get("formulas", [])
    bad = bool(rep["uncached"] or link_fails or design_fails or order_fails or match_fails
               or recon_fails or formula_fails)

    if a.json:
        print(json.dumps(rep, indent=2))
        return 1 if bad else 0

    if rep["uncached"]:
        print(f"{a.workbook.name}: {rep['uncached']} of {rep['formula_cells']} formula "
              f"cells have NO cached value.\n")
        print("  These render BLANK in anything that does not recalculate — a preview pane,")
        print("  Quick Look, pandas, a mail client. Excel and LibreOffice fill them in on open,")
        print("  which is why they look correct to whoever wrote the file.\n")
        for s in rep["by_sheet"]:
            if s["uncached"]:
                print(f"    {s['sheet']:<34} {s['uncached']:>6} of {s['formulas']:>6}")
        shown = rep["cells"][:a.max_report]
        print("\n  first affected cells: "
              + ", ".join(f"{c['sheet']}!{c['cell']}" for c in shown)
              + (f", … and {rep['uncached'] - len(shown)} more" if rep["uncached"] > len(shown) else ""))
        print("\n  Fix: write the computed value into the cell, or write the formula with its")
        print("  result cached beside it. See this script's header for both recipes.")
        print("  A tab script saves with wbkit.save(wb, path), which caches every formula's result;")
        print("  an assembled workbook gets them from link_workbook.py.\n")
    else:
        print(f"{a.workbook.name}: {rep['formula_cells']} formula cells, all carry a "
              f"cached value — the workbook renders without recalculating.")

    L = rep["links"]
    if link_fails:
        print(f"{a.workbook.name}: {len(link_fails)} link/layout failure(s) over "
              f"{L['ids']} ids and {L['hyperlinks']} hyperlinks.\n")
        for f in link_fails[:a.max_report]:
            print(f"    {f}")
        if len(link_fails) > a.max_report:
            print(f"    … and {len(link_fails) - a.max_report} more")
        print("\n  Fix: run scripts/link_workbook.py after assembly. A dead-end figure or")
        print(f"  population needs its {SOURCES} row, an evidence id its {EVIDENCE} row,")
        print("  any other id a cell or leading line on the tab that owns it; a figure row")
        print("  needs its `To reperform` recipe (check-report SKILL § 1). A ledger failure")
        print("  (`workpapers/...`) is fixed in the ledger, then the tab re-gated.")
    else:
        print(f"{a.workbook.name}: {L['ids']} ids, {L['hyperlinks']} hyperlinks, every id "
              f"resolves — the reader can click from any cited id to where it is stated.")
    if L["internal_refs"]:
        print(f"  run-internal review findings left as text: {', '.join(L['internal_refs'])}")
    if design_fails:
        print(f"{a.workbook.name}: {len(design_fails)} design failure(s) — the tab is not "
              f"built to reference/WORKBOOK.md + WORKBOOK_STYLE.md.\n")
        for f in design_fails[:a.max_report]:
            print(f"    {f}")
        if len(design_fails) > a.max_report:
            print(f"    … and {len(design_fails) - a.max_report} more")
        print("\n  Fix: write the tab from the kit in WORKBOOK.md § 7 — one font, the band on")
        print("  row 4, freeze B4, every number formatted, a claim per cell.")
    else:
        print(f"{a.workbook.name}: every tab built to the design — Arial, the band on row 4, "
              f"freeze B4, no General number, no merged cell, no paragraph in a cell.")
    if order_fails:
        print(f"{a.workbook.name}: {len(order_fails)} map failure(s) — the tab strip is not "
              f"the reader's path.\n")
        for f in order_fails[:a.max_report]:
            print(f"    {f}")
        if len(order_fails) > a.max_report:
            print(f"    … and {len(order_fails) - a.max_report} more")
        print(f"\n  Fix: order the tabs {EXEC}, the lead tabs (the recipe's `lead`, else its")
        print(f"  headline family), {BASIS}, the other check tabs in roster order — each check's")
        print("  match tabs after its own tab — then Coverage, Open Items, Sources, Evidence")
        print("  (WORKBOOK.md § 2). Pass --run-dir and the gate names the strip it wants.")
    elif EXEC in rep.get("tabs", []):
        print(f"{a.workbook.name}: the tab strip is the reader's path — {EXEC}, the lead "
              f"tabs, {BASIS}, the roster, the tail, each check's match tabs after its own.")
    if match_fails:
        print(f"{a.workbook.name}: {len(match_fails)} match-tab failure(s) — a summary line is "
              f"not its schedule filtered on its status.\n")
        for f in match_fails[:a.max_report]:
            print(f"    {f}")
        if len(match_fails) > a.max_report:
            print(f"    … and {len(match_fails) - a.max_report} more")
        print("\n  Fix: write both tabs with scripts/match_tabs.py, and never edit one apart")
        print("  from the other; run link_workbook.py after assembly.")
    if recon_fails:
        print(f"{a.workbook.name}: {len(recon_fails)} reconciliation(s) with no match tabs — "
              f"the reader cannot see what each item matched.\n")
        for f in recon_fails[:a.max_report]:
            print(f"    {f}")
        if len(recon_fails) > a.max_report:
            print(f"    … and {len(recon_fails) - a.max_report} more")
    if formula_fails:
        print(f"{a.workbook.name}: {len(formula_fails)} live-arithmetic failure(s) — a total "
              f"the reader cannot trace to its rows, or a formula whose stored result is stale.\n")
        for f in formula_fails[:a.max_report]:
            print(f"    {f}")
        if len(formula_fails) > a.max_report:
            print(f"    … and {len(formula_fails) - a.max_report} more")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
