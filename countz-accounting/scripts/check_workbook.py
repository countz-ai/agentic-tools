#!/usr/bin/env python3
"""Refuse a workbook whose figures are invisible, whose ids do not resolve, or whose
figure rows a reader cannot re-perform from.

Five gates over the stored file, all parsed from the XML rather than through a library so
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

GATE 4 — the design. Every tab is built to reference/WORKBOOK.md and
WORKBOOK_STYLE.md, read from the stored styles: Arial in the five sizes, column A empty,
exactly one BAND header row and it is row 4, freeze panes at B4, no merged cell, no
numeric cell left in General, no table cell without its hairline border, prose only in a
wrapped column at least 42 wide or in a cell overflowing an empty row, every row holding
a wrapped cell sized to fit it, no cell cut mid-sentence, gridlines off on deliverable
tabs and on for ledgers,
the tab colour by kind, B1 title, B2 subtitle and B3 the summary. The Exec
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
roster order; then Coverage, Open Items, Sources, Evidence. Without `--run-dir` the gate
holds the shape — Exec Summary first, the tail last. With `--run-dir` it reads
`run.json` (the roster, each check's `params.family`, `plan.recipe`) and the recipe's
frontmatter, and refuses any other strip, naming the one wanted. A check tab it cannot
match to a rostered check is refused too: the name opens with the roster token.

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
LOCATION = re.compile(r"^'?([^'!]+)'?!\$?([A-Z]+\$?\d+)$")
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


NUM_IN_TEXT = re.compile(r"(?<![\d.,])(\d[\d,]*(?:\.\d+)?)\s*([KMB]|bn|thousand|million|billion)?\b", re.I)
TEXT_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9,
              "billion": 1e9}


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


def sentence_states(text: str, value: float) -> bool:
    """Whether `text` quotes `value`, at the precision the text shows it."""
    for m in NUM_IN_TEXT.finditer(text):
        raw, suffix = m.group(1), (m.group(2) or "").lower()
        scale = TEXT_SCALE.get(suffix, 1.0)
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        try:
            stated = float(raw.replace(",", "")) * scale
        except ValueError:
            continue
        if abs(abs(value) - stated) <= 0.5 * scale * 10 ** -decimals:
            return True
    return False


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
BAND_FILL = "005C53"
TAB_COLOR = {"deliverable": "0F756D", "ledger": "566665", "review": "9A5B00"}
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
        return {"fonts": [], "fills": [], "borders": [], "xfs": [], "wraps": []}
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
    borders = [re.search(r"<(left|right|top|bottom) style=", b) is not None
               for b in entries("border")]
    xfs, wraps = [], []
    section = re.search(r"<cellXfs\b[^>]*>(.*?)</cellXfs>", xml, re.S)
    for attrs, body in re.findall(r"<xf\b([^>]*?)(?:/>|>(.*?)</xf>)", section.group(1) if section else "", re.S):
        ids = {k: int(v) for k, v in re.findall(r'(numFmtId|fontId|fillId|borderId)="(\d+)"', attrs)}
        xfs.append((ids.get("numFmtId", 0), ids.get("fontId", 0), ids.get("fillId", 0),
                    ids.get("borderId", 0)))
        wraps.append('wrapText="1"' in body or 'wrapText="true"' in body)
    return {"fonts": fonts, "fills": fills, "borders": borders, "xfs": xfs, "wraps": wraps}


def audit_design(z: zipfile.ZipFile) -> list[str]:
    """One line per (tab, rule) that fails, with a count and the first cell."""
    styles = style_table(z)
    order = sheet_order(z)
    shared = shared_strings(z)
    fails: list[str] = []

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
        cut, narrow, short_rows = [], [], []
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
        if band_rows != [4] and not summary:
            rule(tab, f"one BAND header row, on row 4 (found rows {band_rows or 'none'})", [], "WORKBOOK_STYLE.md § 4")
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
        if cut:
            rule(tab, "long text cut mid-sentence — split it into a Notes row or the check record, never truncate", cut, "WORKBOOK.md § 4")
        if "<mergeCell " in xml:
            rule(tab, "merged cells", [], "WORKBOOK_STYLE.md § 4")
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


def wanted_order(run_dir: pathlib.Path, tabs: list[str]) -> tuple[list[str] | None, list[str], list[str]]:
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
    check_tabs = sorted(owner, key=lambda tab: roster.index(owner[tab]))
    lead_tabs = [tab for fam in lead for tab in check_tabs if family[owner[tab]] == fam]
    rest = [tab for tab in check_tabs if tab not in lead_tabs]
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
    want, lead, unnamed = (None, [], []) if run_dir is None else wanted_order(run_dir, tabs)
    fails.extend(unnamed)
    if want is not None:
        if want != tabs and not unnamed:
            fails.append(f"tab strip reads {strip}; the map wants {' · '.join(want)} — "
                         f"{EXEC}, the lead tabs (families: {', '.join(lead) or 'none'}), "
                         f"{BASIS}, the other checks in roster order, the tail "
                         f"(WORKBOOK.md § 2)")
        return fails
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
    bad = bool(rep["uncached"] or link_fails or design_fails or order_fails)

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
        print("  result cached beside it. See this script's header for both recipes.\n")
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
        print(f"  headline family), {BASIS}, the other check tabs in roster order, then Coverage,")
        print("  Open Items, Sources, Evidence (WORKBOOK.md § 2). Pass --run-dir and the gate")
        print("  names the strip it wants.")
    elif EXEC in rep.get("tabs", []):
        print(f"{a.workbook.name}: the tab strip is the reader's path — {EXEC}, the lead "
              f"tabs, {BASIS}, the roster, the tail.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
