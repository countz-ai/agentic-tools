#!/usr/bin/env python3
"""Refuse a report deck that says something the workbook does not.

The deck (`out/report.pptx`) is the decider's surface and the workbook is the trail. The
two are one set of figures: `build_report.py` copies every table and resolves every
figure reference from the workbook, so by construction the deck mints nothing. This gate
reads the RESULT — the stored slide XML, never the builder's memory of it — and holds
three mechanical things (reference/REPORT.md § 5). What the deck says, and in what
order, is the author's (§ 1); this gate has no view on it.

GATE 1 — the figures. Every number on a slide — in a sentence, a stat, a table cell, a
chart's cached values — is backed: by a numeric cell of the workbook within the rounding
tolerance of the precision shown, by a number stated in a workbook text cell, or by a
value the run's `workpapers/*.yaml` ledgers carry (the same admission check_prose.py
makes). Page numbers and bare one- or two-digit counts are outside the
rule; a year attached to a period label (`FY2023`) is text. A number that matches
nothing was typed, and typed numbers are what this gate exists to refuse.

GATE 2 — the sources. A page that states a figure — in a table, a chart, a stat or a
sentence — names the workbook tabs it stands on in its footer, every one a tab the
workbook has, and every table on the page comes from a tab the footer names. A referenced
figure names its own tab; a page whose figures are typed declares `source:`.

GATE 3 — the cover. The cover is four strings and each fact is on it once: the title names
the work — never the period — the subtitle the entity detail and the period, the kicker
and the prepared line the company and the date. That the title and subtitle name no
company is the critic's judgment (skills/check-review), not a pattern: a company's name
in any language and legal form is not something a regex holds.

GATE 4 — the message. Every page title is a headline — at most 80 characters and no
full stop (`(continued)` on a flowed page is not counted) — and every sentence the
builder set as prose (the `message` under a headline, a `text` block) is complete: it
ends with a full stop, a question mark or an exclamation. And the deck has at least one
page beyond its cover.

GATE 5 — the recipe's schedules. On a plan-driven run whose recipe declares `## Report`
schedules (RECIPE_FORMAT.md § Report), each is on the deck as a table from its family's
tab carrying every declared column and period, at the full population its `where` and
`through` leave: every row's identity is on the deck, none is trimmed. A check whose
declared periods scripts/periods.py refuses fails this gate by name. A run with no
recipe, or a recipe with no `## Report`, is not held to it. On every deck, a table whose
rows read the same in every column shown is refused: the reader cannot tell them apart.

GATE 6 — the structure (REPORT.md § 1). The recipe decides it; this gate holds the deck
to what the recipe declares. The first page after the cover is the executive summary —
headed `Executive summary`, its message a sentence, at least one stat tile, table or
chart on it. On a recipe run the second page is the key-metrics page, headed as the
recipe's `metrics.title`, carrying a figure block; the first schedule placed `lead` sits
at most one page after it and no other page stands between two `lead` schedules; every
page carrying a schedule placed `appendix` has the kicker `Appendix`, as does every page
after the first `Appendix` page; and where the recipe declares `narrative`, every
narrative page carries one of its sections as its kicker, in the declared order.

GATE 7 — the reader's words (REPORT.md § 3). No ledger id, step token or run working word
anywhere on a slide, a copied table's cells included; and no working-paper term (`walk`,
`as supported`, `candidate`, `boundary`, `ruled`, `routed`, `standing`) in what the
author writes — a term opening its own definition and a tab's name are not read.

Parsed from the .pptx zip with the standard library only, like check_workbook.py.

Usage:
    check_report.py <report.pptx> [--workbook <workbook.xlsx>] [--run-dir DIR] [--json] [--max-report N]
--workbook defaults to workbook.xlsx beside the deck; --run-dir to the nearest ancestor
holding workpapers/ (the ledger admission is skipped when there is none).
Exit 0 clean, 1 on any refusal, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from check_prose import admitted_values  # noqa: E402
from check_workbook import sheet_cells, sheet_numbers, sheet_order, shared_strings  # noqa: E402
from recipe_format import APPENDIX, report_metrics, report_narrative, report_schedules  # noqa: E402
import style  # noqa: E402

TITLE_MAX = 80                          # build_report.TITLE_MAX — a headline, not a sentence
# The cover's budgets and patterns, restated from build_report.py (the SoT): this gate
# reads the stored deck with the standard library only and imports nothing from it.
COVER_TITLE_MAX, COVER_SUB_MAX = 60, 72
MONTHS = style.MONTHS
PERIOD_TOKEN = re.compile(
    rf"\b(?:FY|CY)\s?(?:19|20)?\d\d\b|\b(?:19|20)\d\d\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b"
    rf"|\b(?:{'|'.join(m[:3] for m in MONTHS)})[a-z]*\.?\s+\d{{1,4}}\b", re.I)
CONTINUED = " (continued)"
PROSE_SHAPES = {"message", "body-text"}  # the shapes the builder sets as sentences
SENTENCE_END = re.compile(r"[.?!][)\]\"'”’]*$")
# Shapes whose numbers are navigation, not figures. A chart's ticks and category labels
# are its scale: the plotted values are audited from the shape names CHARTVAL matches.
SKIP_SHAPES = {"kicker", "footer-page", "footer-left", "footer-source", "table-more", "cover-prepared",
               "chart-axis", "chart-cat", "chart-legend"}
# build_report.py draws a chart as shapes so it stays vector in every viewer, and carries
# each plotted value on its shape's name: `chartval:<tab>:<value>`.
CHARTVAL = re.compile(r"^chartval:(.+):(-?[\d.eE+-]+)$")

# A schedule of money is shown at a scale, its table's title stating it (REPORT.md § 4) in
# any currency — `$ in thousands`, `€ in millions`; the figure behind such a cell is the
# workbook's, times that scale. The patterns are scripts/style.py's, the table the
# builder writes with, so the two cannot drift.
COL_SCALE = style.COL_SCALE
NUM = style.NUM
_SUF = style.SUFFIX_RE
_CUR_CHARS = "".join(sorted({ch for c in style.CURRENCIES.values() for ch in c.symbol}))
TOKEN = re.compile(
    rf"(?:{style.MONEY_TOKEN})"                                       # $9.4M  €1,204  EUR 5,000
    rf"|\((?P<neg>{NUM})\s*(?P<nsuf>{_SUF})?(?P<npct>%)?\)"            # (1,234)  (3.1%)
    rf"|(?<![\d.,\-–+{re.escape(_CUR_CHARS)}])(?P<days>{NUM})[\s-]days?\b"
    rf"|(?<![\d.,])(?P<pct>{NUM})\s?%"
    rf"|(?<![\d.,])(?P<mult>{NUM})x\b"
    rf"|(?<![\w.,{re.escape(_CUR_CHARS)}])(?P<plain>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+\.\d+|\d{{3,}})"
    rf"(?![\w.,%]|\s?days?\b)")
YEAR = re.compile(r"^(?:19|20)\d\d$")
ATTR = lambda name: re.compile(rf'\b{name}="([^"]*)"')
REL_EL = re.compile(r"<Relationship\b[^>]*/?>")


# --- the deck as stored ---------------------------------------------------------------
def slide_parts(z: zipfile.ZipFile) -> list[str]:
    """Slide part names in presentation order."""
    try:
        pres = z.read("ppt/presentation.xml").decode("utf-8", "replace")
        rels = {}
        for el in REL_EL.findall(z.read("ppt/_rels/presentation.xml.rels").decode("utf-8", "replace")):
            rid, target = ATTR("Id").search(el), ATTR("Target").search(el)
            if rid and target:
                rels[rid.group(1)] = target.group(1)
    except KeyError:
        return []
    out = []
    for el in re.findall(r"<p:sldId\b[^>]*/?>", pres):
        rid = ATTR("r:id").search(el)
        if rid and rid.group(1) in rels:
            out.append("ppt/" + rels[rid.group(1)].lstrip("/").removeprefix("ppt/"))
    return out


def para_text(xml: str) -> str:
    """The paragraphs of a text body, one line each, runs joined."""
    lines = []
    for p in re.findall(r"<a:p\b.*?</a:p>", xml, re.S):
        lines.append(html.unescape("".join(re.findall(r"<a:t>(.*?)</a:t>", p, re.S))))
    return "\n".join(lines)


OFF = re.compile(r"<a:off\b[^>]*\bx=\"(-?\d+)\"[^>]*\by=\"(-?\d+)\"")
# A table's title is the `table-title` shape drawn above it at the same left edge (EMU).
TITLE_X_SLACK = 12700


def offset(xml: str) -> tuple[int, int]:
    """A shape's top-left corner in EMU, from its first `<a:off>`."""
    m = OFF.search(xml)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def read_slide(z: zipfile.ZipFile, part: str) -> dict:
    xml = z.read(part).decode("utf-8", "replace")
    name = ""
    m = re.search(r"<p:cSld\b[^>]*\bname=\"([^\"]*)\"", xml)
    if m:
        name = html.unescape(m.group(1))
    shapes: list[tuple[str, str]] = []
    titles: list[tuple[int, int, str]] = []            # (x, y, text) of each table title
    for sp in re.findall(r"<p:sp\b.*?</p:sp>", xml, re.S):
        nm = re.search(r"<p:cNvPr\b[^>]*\bname=\"([^\"]*)\"", sp)
        shapes.append((html.unescape(nm.group(1)) if nm else "", para_text(sp)))
        if shapes[-1][0] == "table-title":
            titles.append((*offset(sp), shapes[-1][1]))
    tables: list[tuple[str, list[list[str]]]] = []
    table_titles: list[str] = []                       # the title drawn above each table
    charts: list[tuple[str, list[float]]] = []
    rel_part = part.replace("slides/", "slides/_rels/") + ".rels"
    rels = {}
    if rel_part in z.namelist():
        for el in REL_EL.findall(z.read(rel_part).decode("utf-8", "replace")):
            rid, target = ATTR("Id").search(el), ATTR("Target").search(el)
            if rid and target:
                rels[rid.group(1)] = target.group(1)
    drawn: dict[str, list[float]] = {}
    for nm, _ in shapes:
        m = CHARTVAL.match(nm)
        if m:
            try:
                drawn.setdefault(f"chart:{m.group(1)}", []).append(float(m.group(2)))
            except ValueError:
                pass
    charts += sorted(drawn.items())
    for gf in re.findall(r"<p:graphicFrame\b.*?</p:graphicFrame>", xml, re.S):
        nm = re.search(r"<p:cNvPr\b[^>]*\bname=\"([^\"]*)\"", gf)
        gname = html.unescape(nm.group(1)) if nm else ""
        if "<a:tbl>" in gf:
            rows = []
            for tr in re.findall(r"<a:tr\b.*?</a:tr>", gf, re.S):
                rows.append([para_text(tc) for tc in re.findall(r"<a:tc\b.*?</a:tc>", tr, re.S)])
            tables.append((gname, rows))
            tx, ty = offset(gf)
            above = [(y, t) for x, y, t in titles if abs(x - tx) <= TITLE_X_SLACK and y <= ty]
            table_titles.append(max(above)[1] if above else "")
        cm = re.search(r"<c:chart\b[^>]*r:id=\"([^\"]+)\"", gf)
        if cm and cm.group(1) in rels:
            cpart = "ppt/" + rels[cm.group(1)].lstrip("/").replace("../", "")
            if cpart in z.namelist():
                cxml = z.read(cpart).decode("utf-8", "replace")
                vals = []
                for cache in re.findall(r"<c:numCache>.*?</c:numCache>", cxml, re.S):
                    vals += [float(v) for v in re.findall(r"<c:v>(-?[\d.eE+-]+)</c:v>", cache)]
                charts.append((gname, vals))
    return {"part": part, "name": name, "shapes": shapes, "tables": tables, "charts": charts,
            "table_titles": table_titles,
            "kicker": next((t for n, t in shapes if n == "kicker"), ""),
            "title": next((t for n, t in shapes if n == "title"), ""),
            "footer_source": next((t for n, t in shapes if n == "footer-source"), "")}


# GATE 7 — the reader's words. A slide is written to the company's executives, never in
# the run's machine vocabulary (WORKBOOK.md § 3 Language, DOCTRINE.md § Voice): no ledger
# id (`Q.r4.ar_movement`, `LK.terms_not_enforced`) in a sentence or a cell, and no step
# token mid-text (`as R4 measured it`). Footers name tabs by design and are not read.
MACHINE_ID = re.compile(r"(?<![\w.])(?:F|P|E|T|RI|S|X|C|D|Q|H|LK|A)\.[a-z][a-z0-9_]*(?:\.[\w<>-]+)*")
RUN_TAB_NAMES = {"exec summary", "basis of preparation", "coverage", "open items", "sources",
                 "evidence"}
# A token shaped like a period (`Q1`, `H2`) is read in lower case only: in upper case it is
# the quarter or the half a sentence names.
PERIOD_LIKE = re.compile(r"^[qh]\d$", re.I)


# The run's working words, refused anywhere on a slide: in what the author writes, and in a
# table copied from a tab — a row carrying them stays off the deck (REPORT.md § 3).
MACHINE_PHRASE = re.compile(
    r"\b(?:mint(?:ed|s|ing)?|recipe|skill|this run|the run(?:'s)?|rule \d+|"
    r"hypothes(?:is|es) (?:departed|held)|departed hypothes(?:is|es))\b", re.I)

# The working papers' own terms, refused in what the author writes on a slide (REPORT.md
# § 3 Working-paper terms): the deck says what happened to an item in its area's own
# terms, which no list here can hold. A copied table's cells keep the tab's words.
# A term opening its own definition (`Candidate: …`, `candidate — …`) is the status note
# REPORT.md § 3 asks for, and a tab's name (`b9 Debt walk`) is a pointer, so neither counts.
WORKING_PAPER = re.compile(
    r"(?<![\w-])(?:walk(?:s|ed|ing)?|candidates?|as supported|boundary|boundaries|"
    r"rul(?:ed|ing|ings)|routed|routing|standing|(?:cause|item|account|line) grain|"
    r"beside the walk|review step)(?![\w-])(?!\s*[:—–])", re.IGNORECASE)
AUTHORED_SHAPES = {"title", "message", "body-text", "body-bullets", "body-note", "body-heading",
                   "stat-label", "stat-value", "stat-note", "kv-label", "kv-value", "chart-title",
                   "chart-cat", "footer-tagline", "cover-title", "cover-subtitle"}


def working_paper_words(text: str, tabs: list[str]) -> list[str]:
    for t in sorted(tabs, key=len, reverse=True):
        name = t.split(" ", 1)[1] if " " in t else t
        for n in (t, name):
            text = re.sub(rf"(?<!\w){re.escape(n)}(?!\w)", " ", text, flags=re.IGNORECASE)
    return [m.group(0) for m in WORKING_PAPER.finditer(text)]


def step_tokens(tabs: list[str]) -> list[str]:
    """The roster tokens the workbook's check tabs open with (`r4 Position and DSO`)."""
    out = set()
    for t in tabs:
        if t.strip().lower() in RUN_TAB_NAMES or " " not in t.strip():
            continue
        tok = t.split()[0]
        if re.fullmatch(r"[A-Za-z]{1,3}\d[\w]*", tok):
            out.add(tok)
    return sorted(out, key=len, reverse=True)


def machine_words(text: str, tokens: list[str]) -> list[str]:
    hits = [m.group(0) for m in MACHINE_ID.finditer(text)]
    for tok in tokens:
        flags = 0 if PERIOD_LIKE.match(tok) else re.I
        for m in re.finditer(rf"(?<![\w.]){re.escape(tok)}(?![\w.])", text, flags):
            if m.start() > 0:                  # a cell OPENING with the token names a tab
                hits.append(m.group(0))
    return hits


# --- the workbook as stored --------------------------------------------------------
CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


def fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def col_num(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def workbook_texts(path: pathlib.Path) -> dict[str, dict[int, dict[int, str]]]:
    """{tab: {row: {col: text}}} — every text cell of every tab, as stored."""
    out: dict[str, dict[int, dict[int, str]]] = {}
    with zipfile.ZipFile(path) as z:
        shared = shared_strings(z)
        for part, tab in sheet_order(z):
            texts, _ = sheet_cells(z.read(part).decode("utf-8", "replace"), shared)
            grid: dict[int, dict[int, str]] = {}
            for ref, txt in texts.items():
                m = CELL_REF.match(ref)
                if m:
                    grid.setdefault(int(m.group(2)), {})[col_num(m.group(1))] = txt
            out[html.unescape(tab)] = grid
    return out


def tab_block(grid: dict[int, dict[int, str]], title: str | None) -> tuple[list[str], list[list[str]]]:
    """(headers, rows of text) for a tab's primary table — the header on row 4 — or the
    block under `title`: the header is the first populated row after the title, the body
    runs to the first empty row. Numeric cells read as empty text; the gate needs the
    label and status columns only."""
    headers, rows, _ = tab_block_at(grid, title)
    return headers, rows


def tab_block_at(grid: dict[int, dict[int, str]], title: str | None) -> tuple[list[str], list[list[str]], int]:
    """tab_block, with the sheet row of the header: body row k sits on row header + 1 + k."""
    if title is None:
        hr = 4
    else:
        heads = [r for r in sorted(grid) if r >= 4 and len(grid[r]) == 1]

        def text(r: int) -> str:
            return next(iter(grid[r].values()))
        # the heading that reads exactly as the title wins over one it merely opens
        # (`Obligations due` over `Obligations due by class, …`)
        hr = next((r for r in heads if text(r).strip() == title.strip()), None) or \
            next((r for r in heads if fold(text(r)).startswith(fold(title))), None)
        if hr is None:
            return [], [], 0
        hr = next((r for r in sorted(grid) if r > hr and len(grid[r]) >= 2), None)
        if hr is None:
            return [], [], 0
    if hr not in grid or len(grid[hr]) < 2:
        return [], [], 0
    cols = sorted(grid[hr])
    headers = [grid[hr][c] for c in cols]
    rows = []
    r = hr + 1
    while r in grid:
        rows.append([grid[r].get(c, "") for c in cols])
        r += 1
    return headers, rows, hr


def workbook_numbers(path: pathlib.Path) -> dict[str, dict[int, dict[int, float]]]:
    """{tab: {row: {col: value}}} — every numeric cell of every tab, as stored."""
    out: dict[str, dict[int, dict[int, float]]] = {}
    with zipfile.ZipFile(path) as z:
        for part, tab in sheet_order(z):
            grid: dict[int, dict[int, float]] = {}
            for ref, val in sheet_numbers(z.read(part).decode("utf-8", "replace")).items():
                m = CELL_REF.match(ref)
                if m:
                    grid.setdefault(int(m.group(2)), {})[col_num(m.group(1))] = val
            out[html.unescape(tab)] = grid
    return out


def squash(s: str) -> str:
    """A header word on its letters and digits only: `sub-group` and `subgroup` are one."""
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def header_at(headers: list[str], word: str) -> int | None:
    """The column headed `word`: exact, squashed, or the one header containing it — the
    match build_report.py's `column_index` makes."""
    hits = [i for i, h in enumerate(headers) if h == word] or \
           [i for i, h in enumerate(headers) if squash(h) == squash(word)]
    if not hits:
        part = [i for i, h in enumerate(headers) if squash(word) in squash(h)]
        hits = part if len(part) == 1 else []
    return hits[0] if hits else None


SCHEDULE_ROWS = 25   # build_report.py's: past it, a schedule shows its largest rows (REPORT.md § 1)


def schedule_gate(schedules: list[dict], tabs: list[str], texts: dict[str, dict[int, dict[int, str]]],
                  slides: list[dict], plan: list | None = None,
                  nums: dict[str, dict[int, dict[int, float]]] | None = None) -> list[str]:
    """GATE 5 — the recipe's schedules (RECIPE_FORMAT.md § Report): each is on the deck as
    a table from its family's tab, carrying every declared column and period, at the
    full population the schedule's `where` / `through` leave — every row's identity
    (the first declared column) present, none trimmed. A period column is one naming a
    period the plan declares (`plan`, scripts/periods.py); on a run that declares none,
    one whose header reads as a period. `latest` is the latest by the plan's dates, else
    the last such column."""
    fails: list[str] = []
    # every table on the deck, grouped by its tab and its header row: a table continued
    # over pages is one schedule, and two schedules from one tab differ in their headers
    groups: dict[tuple[str, tuple[str, ...]], list[list[str]]] = {}
    trimmed: set[tuple[str, tuple[str, ...]]] = set()
    for s in slides:
        for tname, rows in s["tables"]:
            if ":" not in tname or not rows:
                continue
            key = (tname.split(":", 1)[1], tuple(h.strip() for h in rows[0]))
            groups.setdefault(key, []).extend(rows[1:])
            if any(n == "table-more" for n, _ in s["shapes"]):
                trimmed.add(key)
    for sc in schedules:
        title, fam = str(sc.get("title", "")), fold(str(sc.get("from", "")))
        tab = next((t for t in tabs if fold(t.split(" ", 1)[0]) == fam), None)
        if tab is None:
            fails.append(f"schedule `{title}`: the workbook has no `{fam}` tab to draw it from")
            continue
        words = [str(w) for w in sc.get("columns", [])]
        headers, rows, hr = tab_block_at(texts.get(tab, {}), sc.get("block"))
        if not headers:
            fails.append(f"schedule `{title}`: `{tab}` has no "
                         + (f"block titled `{sc['block']}`" if sc.get("block") else "primary table"))
            continue
        if plan:
            dated = [(h, period_of(h, plan)) for h in headers]
            dated = [(h, p.end) for h, p in dated if p is not None]
        else:
            dated = [(h, None) for h in headers if PERIOD_TOKEN.search(h)]
        periods = [h for h, _ in dated]
        want = list(words)
        if sc.get("periods") == "all":
            want += periods
        elif sc.get("periods") == "latest" and periods:
            known = [(h, d) for h, d in dated if d is not None]
            want.append(max(known, key=lambda x: x[1])[0] if known else periods[-1])
        candidates = [(k, body) for k, body in groups.items() if k[0] == tab]
        if not candidates and sc.get("place") == "appendix" and not sc.get("required"):
            continue                           # an appendix schedule is the author's to include unless `required` (REPORT.md § 1)
        if not candidates:
            fails.append(f"schedule `{title}`: no page carries a table from `{tab}` — the recipe "
                         f"places it `{sc.get('place', 'lead')}`{' and `required`' if sc.get('required') else ''} (REPORT.md § 1)")
            continue
        # two schedules from one tab can carry the same columns (a transactions walk and a
        # balances walk): the table is the one showing this schedule's own rows
        ident0 = header_at(headers, words[0]) if words else None
        labels = {r[ident0].strip() for r in rows if ident0 is not None and ident0 < len(r) and r[ident0].strip()}

        def overlap(kb, words=words, labels=labels) -> int:
            di_ = header_at(list(kb[0][1]), words[0]) if words else None
            return sum(1 for r in kb[1] if di_ is not None and di_ < len(r) and r[di_].strip() in labels)
        if (sc.get("place") == "appendix" and not sc.get("required") and labels
                and not any(overlap(kb) for kb in candidates)):
            continue                           # its rows are on no page: the author left it to the workbook
        full = [(k, body) for k, body in candidates
                if not [w for w in want if header_at(list(k[1]), w) is None]]
        match = max(full, key=lambda kb: (overlap(kb), len(kb[1]))) if full else None
        if match is None:
            # name what the nearest table lacks: the candidate missing the fewest columns,
            # and of those the one carrying the most of the declared (non-period) columns
            missing = min(([w for w in want if header_at(list(k[1]), w) is None] for k, _ in candidates),
                          key=lambda ms: (len(ms), sum(1 for w in ms if w in words)))
            fails.append(f"schedule `{title}`: no table from `{tab}` carries the column(s) "
                         f"{', '.join(f'`{m}`' for m in missing)} the recipe declares")
            continue
        (_, deck_headers), body = match
        ident = header_at(headers, words[0])
        if ident is None:
            fails.append(f"schedule `{title}`: `{tab}` has no column headed `{words[0]}`")
            continue
        keep = list(range(len(rows)))
        for header, wanted in (sc.get("where") or {}).items():
            ci = header_at(headers, str(header))
            if ci is None:
                fails.append(f"schedule `{title}`: `{tab}` has no column headed `{header}`")
                keep = []
                break
            allowed = {fold(x) for x in (wanted if isinstance(wanted, list) else [wanted])}
            keep = [j for j in keep if not rows[j][ci].strip() or fold(rows[j][ci]) in allowed]
        through = sc.get("through")
        if through:
            stop = next((n for n, j in enumerate(keep)
                         if any(c.strip() == str(through).strip() or fold(c) == fold(str(through))
                                for c in rows[j][:2] if c)), None)
            if stop is None:
                fails.append(f"schedule `{title}`: `{tab}` has no row labelled `{through}`")
                continue
            keep = keep[:stop + 1]
        di = header_at(list(deck_headers), words[0])
        shown = {r[di].strip() for r in body if di is not None and di < len(r)}
        # a row nil in every period column shown is dropped from the deck (`nonzero`) and
        # a derived line (`= …`) is never one of them; a schedule declaring no period reads
        # every numeric column the deck shows, as the builder's `nonzero` does
        if nums is not None:
            cols = sorted((texts.get(tab, {}).get(hr) or {}))
            grid = nums.get(tab, {})
            if periods:
                pcols = [cols[i] for i, h in enumerate(headers) if h in want and h in periods and i < len(cols)]
            else:
                on_deck = {i for i in (header_at(headers, h) for h in deck_headers) if i is not None}
                pcols = [cols[i] for i in sorted(on_deck) if i < len(cols)
                         and any(cols[i] in grid.get(hr + 1 + j, {}) for j in range(len(rows)))]
            def nil(j):
                if any(c.strip().startswith("=") for c in rows[j][:2]):
                    return False
                vals = grid.get(hr + 1 + j, {})
                return bool(pcols) and all(round(vals.get(c, 0.0), 2) == 0 for c in pcols)
            keep = [j for j in keep if not nil(j)]
        wanted_rows = [rows[j][ident].strip() for j in keep if rows[j][ident].strip()]
        absent = [x for x in wanted_rows if x not in shown]
        closing = str(through).strip() if through else (wanted_rows[-1] if wanted_rows else "")
        reaches = any(closing and (c.strip() == closing or fold(c) == fold(closing)) for r in body for c in r[:2])
        if absent and len(wanted_rows) > SCHEDULE_ROWS and (
                (match[0] in trimmed and len(wanted_rows) - len(absent) >= min(SCHEDULE_ROWS, len(wanted_rows)) // 2)
                or reaches):
            # a long list shows its largest rows and states the rest; a long walk is shown at
            # cause grain, reaching its closing line — the builder holds it to footing
            absent = []
        elif absent:
            named = "; ".join(a[:44] for a in absent[:3])
            fails.append(f"schedule `{title}`: {len(absent)} of {len(wanted_rows)} rows on `{tab}` are not "
                         f"on the deck ({'…; ' if len(absent) > 3 else ''}{named}) — a recipe schedule of up "
                         f"to {SCHEDULE_ROWS} rows is shown whole; a longer one shows its largest rows "
                         f"(`largest`) and states the rest")
        if not absent and match[0] in trimmed and len(wanted_rows) <= SCHEDULE_ROWS:
            fails.append(f"schedule `{title}`: a table from `{tab}` states rows left on the tab — "
                         f"a schedule of {SCHEDULE_ROWS} rows or fewer is shown whole")
    return fails


EXEC_TITLE = "executive summary"
MATTERS_TITLE = "Matters for your attention"
OPENING_MAX_EXTRA = 1     # pages allowed between the key-metrics page and the first lead schedule


def has_figures(s: dict) -> bool:
    """Whether a slide carries a figure block — a stat tile, a table copied from a tab or
    a drawn chart — as against prose alone."""
    return (any(n == "stat-value" for n, _ in s["shapes"]) or bool(s["tables"])
            or any(CHARTVAL.match(n) for n, _ in s["shapes"]))


def schedule_tab(sc: dict, tabs: list[str]) -> str | None:
    fam = fold(str(sc.get("from", "")))
    return next((x for x in tabs if fold(x.split(" ", 1)[0]) == fam), None)


def carries(s: dict, sc: dict, tabs: list[str]) -> bool:
    """Whether a slide carries schedule `sc`'s own table: from its tab, its header
    carrying every declared column."""
    tab = schedule_tab(sc, tabs)
    words = [str(w) for w in sc.get("columns", [])]
    return tab is not None and any(
        ":" in n and n.split(":", 1)[1] == tab and rows
        and all(header_at([h.strip() for h in rows[0]], w) is not None for w in words)
        for n, rows in s["tables"])


def structure_gate(metrics: dict | None, schedules: list[dict] | None, narrative: list[str] | None,
                   tabs: list[str], slides: list[dict]) -> list[str]:
    """GATE 6 — the structure (REPORT.md § 1), as the recipe declares it. The first page
    after the cover is the executive summary: headed `Executive summary`, carrying its
    message as a sentence and at least one figure block. On a recipe run the second page is
    the key-metrics page, headed as the recipe's `metrics.title`, carrying a figure block.
    Then each schedule's place: `lead` directly after the opening, the lead schedules in
    one run; `appendix` under the `Appendix` kicker, after every other page. Where the
    recipe declares `narrative`, the narrative's pages carry its sections as kickers, in
    order. Slide numbers in the messages count the cover as slide 1."""
    fails: list[str] = []
    body = [s for s in slides if s["name"] != "cover"]
    if not body:
        return fails
    first = body[0]
    if fold(first["title"].strip()) != fold(EXEC_TITLE):
        fails.append(f"slide 2: the first page after the cover is headed `Executive summary`, "
                     f"not `{first['title'].strip()[:50]}` — the elevator pitch opens the deck")
    if not any(n == "message" and txt.strip() for n, txt in first["shapes"]):
        fails.append("slide 2: the executive summary carries its message as a sentence under the headline")
    if not has_figures(first):
        fails.append("slide 2: the executive summary carries no stat tile, table or chart — "
                     "not prose alone (REPORT.md § 1)")
    if not metrics:
        return fails
    want = str(metrics.get("title") or "").strip()
    if len(body) < 2:
        fails.append(f"the deck has no key-metrics page headed `{want}` after the executive summary")
        return fails
    second = body[1]
    if fold(second["title"].strip().removesuffix(CONTINUED)) != fold(want):
        fails.append(f"slide 3: the key-metrics page is headed `{want}` (the recipe's `metrics.title`), "
                     f"not `{second['title'].strip()[:50]}`")
    if not has_figures(second):
        fails.append(f"slide 3: the key-metrics page `{want}` carries no stat tile, table or chart")
    # the opening runs to the key-metrics page and its continuations
    opening_end = 1
    while (opening_end + 1 < len(body)
           and fold(body[opening_end + 1]["title"].strip().removesuffix(CONTINUED)) == fold(want)
           and body[opening_end + 1]["title"].strip().endswith(CONTINUED.strip())):
        opening_end += 1
    # `Matters for your attention` (REPORT.md § 1) closes the opening where the run raised
    # an integrity pattern
    while (opening_end + 1 < len(body)
           and fold(body[opening_end + 1]["title"].strip().removesuffix(CONTINUED)) == fold(MATTERS_TITLE)):
        opening_end += 1
    schedules = schedules or []
    lead = [sc for sc in schedules if sc.get("place", "lead") == "lead"]
    appendix = [sc for sc in schedules if sc.get("place") == "appendix"]
    is_appx = [fold(s["kicker"].strip()) == fold(APPENDIX) for s in body]
    # The lead schedules run together from the first page carrying one: that run of pages
    # is where every lead schedule sits. A later page copying a few of a schedule's rows is
    # the narrative's (and is the author's to justify), not the schedule's place.
    lead_at: list[int] = []
    head = next((i for i, s in enumerate(body) if any(carries(s, sc, tabs) for sc in lead)), None)
    if head is not None:
        i = head
        while i < len(body) and any(carries(body[i], sc, tabs) for sc in lead):
            lead_at.append(i)
            i += 1
        if head > opening_end + 1 + OPENING_MAX_EXTRA:
            fails.append(f"slide {head + 2}: the first lead schedule (`{lead[0].get('title')}`) sits "
                         f"{head - opening_end - 1} pages after the key-metrics page; at most "
                         f"{OPENING_MAX_EXTRA} (REPORT.md § 1)")
        for sc in lead:
            if not any(carries(body[j], sc, tabs) for j in lead_at):
                at = next((j for j, s in enumerate(body) if carries(s, sc, tabs)), None)
                if at is not None:
                    fails.append(f"slide {at + 2}: a page stands between the lead schedules — `{sc.get('title')}` "
                                 f"runs on from the one before it, directly after the opening (REPORT.md § 1)")
    for sc in appendix:
        at = [i for i, s in enumerate(body) if carries(s, sc, tabs)]
        if at and not any(is_appx[i] for i in at):
            fails.append(f"slide {at[0] + 2}: the schedule `{sc.get('title')}` is placed `appendix` by the "
                         f"recipe; it sits in the appendix, on pages with the kicker `{APPENDIX}` after the "
                         f"narrative, not under `{body[at[0]]['kicker'].strip()[:30]}`")
    first_appx = next((i for i, a in enumerate(is_appx) if a), None)
    if first_appx is not None:
        stray = next((i for i in range(first_appx, len(body)) if not is_appx[i]), None)
        if stray is not None:
            fails.append(f"slide {stray + 2}: a page (`{body[stray]['title'].strip()[:40]}`) follows the "
                         f"appendix — the appendix closes the deck (REPORT.md § 1)")
    if narrative:
        order = [fold(x) for x in narrative]
        start = (lead_at[-1] + 1) if lead_at else opening_end + 1
        last, last_name = -1, ""
        for i in range(start, len(body)):
            if is_appx[i] or i in lead_at:
                continue
            k = fold(body[i]["kicker"].strip())
            if k not in order:
                fails.append(f"slide {i + 2}: kicker `{body[i]['kicker'].strip()[:30]}` is not a narrative "
                             f"section the recipe declares ({', '.join(narrative)})")
                continue
            if order.index(k) < last:
                fails.append(f"slide {i + 2}: the section `{body[i]['kicker'].strip()[:30]}` comes after "
                             f"`{last_name}` — the recipe orders the narrative {' · '.join(narrative)}")
            if order.index(k) >= last:
                last, last_name = order.index(k), body[i]["kicker"].strip()[:30]
    return fails


def twin_rows(slides: list[dict]) -> list[str]:
    """Every table on the deck — a table continued over pages read as one — whose body
    holds two rows that read the same in every column shown. The reader cannot tell them
    apart; the owning check names each row distinctly, or the page shows the column that
    separates them."""
    fails: list[str] = []
    groups: dict[tuple[str, tuple[str, ...]], list[tuple[int, list[str]]]] = {}
    for n, s in enumerate(slides, 1):
        for tname, rows in s["tables"]:
            if not rows:
                continue
            key = (tname, tuple(h.strip() for h in rows[0]))
            groups.setdefault(key, []).extend((n, r) for r in rows[1:])
    for (tname, _), rows in groups.items():
        seen: dict[tuple[str, ...], int] = {}
        for n, r in rows:
            sig = tuple(c.strip() for c in r)
            if not any(sig):
                continue
            if sig in seen:
                tab = tname.split(":", 1)[1] if ":" in tname else tname
                fails.append(f"slide {n}: two rows of the table from `{tab}` read the same in every column "
                             f"shown (`{sig[0][:50]}`) — show the column that tells them apart, or the check "
                             f"that wrote `{tab}` names each row distinctly")
                break
            seen[sig] = n
    return fails


def workbook_values(path: pathlib.Path) -> tuple[list[str], list[float], list[float]]:
    """(tab names, numeric cell values, numbers stated in text cells)."""
    nums: list[float] = []
    text_nums: list[float] = []
    with zipfile.ZipFile(path) as z:
        order = sheet_order(z)
        shared = shared_strings(z)
        for part, tab in order:
            xml = z.read(part).decode("utf-8", "replace")
            texts, _ = sheet_cells(xml, shared)
            for m in re.finditer(r"<c\b([^>]*?)(?:/>|>((?:(?!</c>).)*)</c>)", xml, re.S):
                attrs, body = m.group(1), m.group(2) or ""
                t = ATTR("t").search(attrs)
                if t and t.group(1) in ("s", "str", "inlineStr", "b"):
                    continue
                v = re.search(r"<v[^>]*>(-?[\d.eE+-]+)</v>", body)
                if v:
                    try:
                        nums.append(float(v.group(1)))
                    except ValueError:
                        pass
            for txt in texts.values():
                for _, value, _, _ in tokenize(txt):
                    text_nums.append(value)
    # sheet names come off the XML attribute escaped (`P&amp;L`); the deck's footer
    # carries them as written
    return [html.unescape(tab) for _, tab in order], nums, text_nums


def tokenize(text: str):
    """Yield (token, value, tolerance, variants) for every figure-looking number. `value` is
    the magnitude: a written sign is not checked. A bare year (1900–2099) is a period, not
    a figure."""
    for m in TOKEN.finditer(text):
        g = m.groupdict()
        raw = g["money"] or g["money2"] or g["neg"] or g["days"] or g["pct"] or g["mult"] or g["plain"]
        if raw is None:
            continue
        raw = raw.rstrip(",")
        if g["plain"] and YEAR.match(raw):
            continue
        if g["neg"] and re.fullmatch(r"\d{1,2}", raw) and not (g["nsuf"] or g["npct"]):
            continue                       # "(3)" is a count in a heading, not a negative
        suffix = (g["suffix"] or g["suffix2"] or g["nsuf"] or "").strip()
        scale = style.scale_of(suffix)
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        value = float(raw.replace(",", "")) * scale
        tol = 0.5 * scale * 10 ** -decimals
        is_pct = bool(g["pct"]) or bool(g["npct"])
        variants = (1.0, 100.0) if is_pct else (1.0,)
        yield m.group(0).strip().rstrip(","), value, tol, variants


# A title that states the scale alone, a multi-currency table's form: `(in thousands)`.
BARE_SCALE = re.compile(r"\bin (thousands|millions|billions)\b", re.I)


def table_scale(title: str) -> float | None:
    """The factor a table's title states (`EBITDA bridge ($ in thousands)` → 1e-3), else
    None. The currency's own form first (scripts/style.py COL_SCALE), then the bare
    `in thousands` of a table in more than one currency."""
    if not title:
        return None
    hit = next((f for pat, f in COL_SCALE if pat.search(title)), None)
    if hit is not None:
        return hit
    m = BARE_SCALE.search(title)
    return {"thousands": 1e-3, "millions": 1e-6, "billions": 1e-9}[m.group(1).lower()] if m else None


def backed(value: float, tol: float, variants, pool: list[float]) -> bool:
    """Whether a magnitude on the deck is the magnitude of a value of the pool."""
    for av in pool:
        for f in variants:
            if abs(abs(av) * f - value) <= tol:
                return True
    return False


# --- the plan's periods ------------------------------------------------------------------
def plan_periods(run_dir: pathlib.Path | None, defects: list[str] | None = None) -> list | None:
    """Every period the run's checks declare (`params.columns`, scripts/periods.py), or
    None when the run declares none — the gate then reads periods off the headers. A
    check whose periods scripts/periods.py refuses (mixed calendar forms, a zone that is
    not IANA, a blank label, ...) adds a line to `defects` naming it and the refusal;
    its periods are missing from the plan."""
    if run_dir is None or not (run_dir / "run.json").is_file():
        return None
    try:
        from periods import Periods  # noqa: PLC0415
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (ImportError, OSError, ValueError):
        return None
    out, seen = [], set()
    for c in run.get("checks") or []:
        if not (c.get("params") or {}).get("columns") or not c.get("id"):
            continue
        try:
            # periods.py resolves the check's own columns, year end, calendar and labels
            ps = Periods.load(run_dir, c["id"])
        except (ValueError, TypeError, KeyError) as exc:
            if defects is not None:
                defects.append(f"check `{c['id']}` declares periods scripts/periods.py refuses "
                               f"({exc}) - the recipe's schedules cannot be held to them; fix "
                               f"the check's params and re-run it")
            continue
        for p in ps:
            if p.key not in seen:
                seen.add(p.key)
                out.append(p)
    return out or None


def period_names(p) -> set[str]:
    """The folded forms a header may name period `p` by: its key, its labels, and each with
    month names long or short (`LTM July 2025` / `LTM Jul 2025`)."""
    names = {p.key}
    for basis in ("flow", "snapshot"):
        try:
            names.add(p.label(basis))
        except (TypeError, ValueError):
            names.add(p.label())
    more = set()
    for n in names:
        for full, short in zip(style.MONTHS, style.MONTHS_SHORT):
            if full in n:
                more.add(n.replace(full, short))
    return {fold(n) for n in names | more if n}


def period_of(header: str, periods: list) -> object | None:
    """The plan period a column header names, or None."""
    h = fold(header)
    hits = [p for p in periods for n in period_names(p)
            if re.search(rf"(?:^|_){re.escape(n)}(?:_|$)", h)]
    if not hits:
        return None
    return max(hits, key=lambda p: max(len(n) for n in period_names(p)))


# --- the audit -------------------------------------------------------------------------
def audit(deck: pathlib.Path, workbook: pathlib.Path, run_dir: pathlib.Path | None) -> dict:
    with zipfile.ZipFile(deck) as z:
        slides = [read_slide(z, p) for p in slide_parts(z)]
    tabs, nums, text_nums = workbook_values(workbook)
    pool = nums + text_nums
    ledger_pool: list[float] = []
    if run_dir is not None and (run_dir / "workpapers").is_dir():
        ledger_pool = [v for v, _ in admitted_values(run_dir, [])]
    pool += ledger_pool
    # A figure the builder computed from cells (`{= …}`, REPORT.md § 2) is admitted when its
    # terms are workbook values and they add to it; a sidecar that does not hold is a failure.
    computed_fails: list[str] = []
    side = deck.with_name(deck.stem + ".computed.json")
    if side.is_file():
        try:
            entries = json.loads(side.read_text(encoding="utf-8")) or []
        except ValueError:
            entries, computed_fails = [], [f"{side.name}: not valid JSON — rebuild the deck"]
        for e in entries:
            terms = e.get("terms") or []
            vals = [float(t.get("value", 0)) for t in terms]
            total = sum(-v if t.get("sign") == "-" else v for t, v in zip(terms, vals))
            unknown = [t.get("ref") for t, v in zip(terms, vals)
                       if not any(abs(v - x) <= max(0.005, abs(v) * 1e-9) for x in nums)]
            if unknown or abs(total - float(e.get("value", 0))) > 0.01:
                computed_fails.append(f"{side.name}: `{e.get('expression', '')[:60]}` does not rest on "
                                      f"workbook cells that add to it ({', '.join(map(str, unknown)) or 'sum'})")
            else:
                pool.append(float(e["value"]))
    period_defects: list[str] = []
    plan = plan_periods(run_dir, period_defects)
    fails: list[str] = list(computed_fails)
    if not slides:
        return {"slides": 0, "failures": ["the deck holds no slides"], "numbers": 0, "unbacked": []}
    body = [s for s in slides if s["name"] != "cover"]
    if not body:
        fails.append("the deck has no page beyond its cover")

    # GATE 3 — the cover.
    cover = next((s for s in slides if s["name"] == "cover"), None)
    if cover is not None:
        shp = {n: t.strip() for n, t in cover["shapes"]}
        ctitle, csub = shp.get("cover-title", ""), shp.get("cover-subtitle", "")
        # That neither names the company is the critic's judgment (skills/check-review):
        # a name in any language and legal form is not a pattern this gate can hold.
        if len(ctitle) > COVER_TITLE_MAX:
            fails.append(f"the cover title is {len(ctitle)} characters; it names the work, "
                         f"at most {COVER_TITLE_MAX}")
        m = PERIOD_TOKEN.search(ctitle)
        if m:
            fails.append(f"the cover title carries the period (`{m.group(0)}`) — the period is the "
                         f"subtitle's, the date the prepared line's")
        if len(csub) > COVER_SUB_MAX:
            fails.append(f"the cover subtitle is {len(csub)} characters; the entity and the period, "
                         f"at most {COVER_SUB_MAX}")

    # GATE 1 — the figures; GATE 2 — the sources; GATE 4 — the message.
    total = 0
    unbacked: list[dict] = []
    for n, s in enumerate(slides, 1):
        if s["name"] == "cover":
            continue
        figures_here = 0
        for shape_name, text in s["shapes"]:
            if shape_name in SKIP_SHAPES:
                continue
            for token, value, tol, variants in tokenize(text):
                total += 1
                figures_here += 1
                if not backed(value, tol, variants, pool):
                    unbacked.append({"slide": n, "where": shape_name or "text", "token": token})
        for (tname, rows), ttitle in zip(s["tables"], s.get("table_titles") or [""] * len(s["tables"])):
            # The scale is stated once, in the table's title (REPORT.md § 4).
            title_scale = table_scale(ttitle)
            for r, row in enumerate(rows):
                if r == 0:
                    continue                       # the header row: period labels, counts of columns
                for cell in row:
                    for token, value, tol, variants in tokenize(cell):
                        total += 1
                        if title_scale is not None and "%" not in token:
                            # a title scale covers the money columns; a count or a
                            # multiple in the same table is read at face value
                            variants = tuple(variants) + tuple(v * title_scale for v in variants)
                        if not backed(value, tol, variants, pool):
                            unbacked.append({"slide": n, "where": tname, "token": token})
        for cname, vals in s["charts"]:
            for v in vals:
                total += 1
                if not backed(abs(v), 0.5, (1.0,), pool):     # a magnitude, as every figure
                    unbacked.append({"slide": n, "where": cname, "token": f"{v:g}"})
        has_figures = bool(s["tables"] or s["charts"] or figures_here
                           or any(n_ in ("stat-value", "kv-value") for n_, _ in s["shapes"]))
        if has_figures:
            src = s["footer_source"]
            listed = src.split(" / ", 1)[1] if src.startswith("Source:") and " / " in src else ""
            named = [t.strip() for t in listed.split("·") if t.strip()]
            if not named:
                fails.append(f"slide {n} (`{s['title'][:50]}`) states a figure and names no source tab "
                             f"in its footer — declare `source:` on the page")
            else:
                titles = {style.tab_title(t) for t in tabs}
                for t in named:
                    if t not in titles:
                        fails.append(f"slide {n}: footer names `{t}`, no tab of the workbook")
                for tname, _ in s["tables"] + s["charts"]:
                    tab = tname.split(":", 1)[1] if ":" in tname else ""
                    if tab and style.tab_title(tab) not in named:
                        fails.append(f"slide {n}: a table from `{tab}` on a page whose footer does not name it")
        title = s["title"].strip().removesuffix(CONTINUED)
        if len(title) > TITLE_MAX:
            fails.append(f"slide {n}: title is {len(title)} characters; a headline, at most {TITLE_MAX}")
        if title.endswith("."):
            fails.append(f"slide {n}: title `{title[:50]}` ends with a full stop — a headline, not a sentence")
        for shape_name, text in s["shapes"]:
            if shape_name in PROSE_SHAPES and text.strip() and not SENTENCE_END.search(text.strip()):
                fails.append(f"slide {n}: {shape_name} `{text.strip()[:50]}` does not end with a full stop — "
                             f"a complete sentence")
    # GATE 7 — the reader's words.
    tokens = step_tokens(tabs)
    jargon: dict[int, list[str]] = {}
    for n, s in enumerate(slides, 1):
        authored = [t for nm, t in s["shapes"] if nm not in SKIP_SHAPES]
        texts_here = authored + [c for _, rows in s["tables"] for row in rows for c in row]
        for t in texts_here:
            jargon.setdefault(n, []).extend(machine_words(t, tokens))
        for t in texts_here:
            jargon.setdefault(n, []).extend(m.group(0) for m in MACHINE_PHRASE.finditer(t))
    for n, words in sorted(jargon.items()):
        if words:
            shown = ", ".join(sorted(set(words))[:4])
            fails.append(f"slide {n}: the run's own vocabulary on the page ({shown}) — state what was "
                         f"done and found in the reader's words; ids and step tokens stay in the workbook")
    for n, s in enumerate(slides, 1):
        words = [w for nm, t in s["shapes"] if nm in AUTHORED_SHAPES for w in working_paper_words(t, tabs)]
        if words:
            shown = ", ".join(sorted({w.lower() for w in words})[:5])
            fails.append(f"slide {n}: working-paper terms in the slide's text ({shown}) — say what happened to "
                         f"each item in this area's own terms (REPORT.md § 3 Working-paper terms)")
    # GATE 5 — the recipe's schedules, on a plan-driven run whose recipe declares them;
    # GATE 6 — the opening, on every deck, with the key-metrics page held to the recipe.
    schedules = metrics = narrative = None
    if run_dir is not None and (run_dir / "run.json").is_file():
        try:
            run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            rpath = (run.get("plan") or {}).get("recipe")
            if rpath:
                rtext = pathlib.Path(rpath).read_text(encoding="utf-8")
                schedules, metrics = report_schedules(rtext), report_metrics(rtext)
                narrative = report_narrative(rtext)
        except (OSError, ValueError):
            schedules = metrics = narrative = None
    if schedules:
        fails.extend(period_defects)
        fails.extend(schedule_gate(schedules, tabs, workbook_texts(workbook), slides, plan,
                                   workbook_numbers(workbook)))
    fails.extend(twin_rows(slides))
    fails.extend(structure_gate(metrics, schedules, narrative, tabs, slides))
    return {"slides": len(slides), "failures": fails, "numbers": total, "unbacked": unbacked,
            "workbook_values": len(nums), "ledger_values": len(ledger_pool),
            "schedules": len(schedules or [])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("deck", type=pathlib.Path)
    ap.add_argument("--workbook", type=pathlib.Path)
    ap.add_argument("--run-dir", type=pathlib.Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-report", type=int, default=15)
    a = ap.parse_args()
    if not a.deck.is_file():
        print(f"{a.deck}: not a file", file=sys.stderr)
        return 2
    wb = a.workbook or a.deck.with_name("workbook.xlsx")
    if not wb.is_file():
        print(f"{wb}: not a file — use --workbook", file=sys.stderr)
        return 2
    run_dir = a.run_dir
    if run_dir is None:
        run_dir = next((p for p in a.deck.resolve().parents if (p / "workpapers").is_dir()), None)
    try:
        rep = audit(a.deck, wb, run_dir)
    except zipfile.BadZipFile:
        print(f"{a.deck}: not a readable .pptx", file=sys.stderr)
        return 2
    bad = bool(rep["failures"] or rep.get("unbacked"))
    if a.json:
        print(json.dumps(rep, indent=2))
        return 1 if bad else 0
    if rep["failures"]:
        print(f"{a.deck.name}: {len(rep['failures'])} source/layout failure(s) over {rep['slides']} slides.\n")
        for f in rep["failures"][:a.max_report]:
            print(f"    {f}")
        if len(rep["failures"]) > a.max_report:
            print(f"    … and {len(rep['failures']) - a.max_report} more")
        print("\n  Fix: build the deck with scripts/build_report.py from report.yaml — it names every")
        print("  page's sources in the footer, holds the cover and each title to a headline and each")
        print("  sentence to a complete one (REPORT.md § 5).")
    else:
        print(f"{a.deck.name}: {rep['slides']} slides, every figure page naming its source tabs, "
              f"every title a headline, every sentence complete.")
    ub = rep.get("unbacked", [])
    if ub:
        print(f"{a.deck.name}: {len(ub)} of {rep['numbers']} numbers have NO workbook or ledger value behind them:\n")
        for u in ub[:a.max_report]:
            print(f"    slide {u['slide']:<3} {u['where']:<28} {u['token']}")
        if len(ub) > a.max_report:
            print(f"    … and {len(ub) - a.max_report} more")
        print("\n  A number on the deck is copied from the workbook, never typed: reference it as")
        print("  {tab | row label | column header} or {tab!B3} in report.yaml, or put it in a table")
        print("  copied from the tab (REPORT.md § 2).")
    else:
        print(f"{a.deck.name}: {rep['numbers']} numbers on the slides, every one carried by a workbook "
              f"cell ({rep['workbook_values']} values) or a ledger record ({rep['ledger_values']} values).")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
