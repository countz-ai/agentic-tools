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
the work — never the company, never the period — the subtitle the entity detail and the
period, the kicker and the prepared line the company and the date.

GATE 4 — the message. Every page title is a headline — at most 80 characters and no
full stop (`(continued)` on a flowed page is not counted) — and every sentence the
builder set as prose (the `message` under a headline, a `text` block) is complete: it
ends with a full stop, a question mark or an exclamation. And the deck has at least one
page beyond its cover.

GATE 5 — the recipe's schedules. On a plan-driven run whose recipe declares `## Report`
schedules (RECIPE_FORMAT.md § Report), each is on the deck as a table from its family's
tab carrying every declared column and period, at the full population its `where` and
`through` leave: every row's identity is on the deck, none is trimmed. A run with no
recipe, or a recipe with no `## Report`, is not held to it.

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
from check_workbook import sheet_cells, sheet_order, shared_strings  # noqa: E402
from recipe_format import report_schedules  # noqa: E402

TITLE_MAX = 80                          # build_report.TITLE_MAX — a headline, not a sentence
# The cover's budgets and patterns, restated from build_report.py (the SoT): this gate
# reads the stored deck with the standard library only and imports nothing from it.
COVER_TITLE_MAX, COVER_SUB_MAX = 60, 72
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")
PERIOD_TOKEN = re.compile(
    rf"\b(?:FY|CY)\s?(?:19|20)?\d\d\b|\b(?:19|20)\d\d\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b"
    rf"|\b(?:{'|'.join(m[:3] for m in MONTHS)})[a-z]*\.?\s+\d{{1,4}}\b", re.I)
LEGAL_FORM = re.compile(r"[\s,]*\b(?:inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|plc|"
                        r"gmbh|s\.a|sa|sas|bv|nv|ag|pty|llp|lp|holdings?|group)\b\.?", re.I)
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

# A schedule of dollars is shown at a scale, its column headed with it (REPORT.md § 4);
# the figure behind such a cell is the workbook's, times that scale.
COL_SCALE = ((re.compile(r"\$'000|\$000|\$ ?in thousands", re.I), 1e-3),
             (re.compile(r"\(\$m\)|\$ ?in millions", re.I), 1e-6),
             (re.compile(r"\(\$bn\)|\$ ?in billions", re.I), 1e-9))
NUM = r"\d[\d,]*(?:\.\d+)?"
TOKEN = re.compile(
    rf"\(\$?\s?(?P<neg>{NUM})\s*(?P<nsuf>bn\b|[KMBkmb]\b)?%?\)"        # (1,234)  ($1.2m)  (3.1%)
    rf"|\$\s?(?P<money>{NUM})\s*(?P<suffix>bn\b|[KMBkmb]\b|thousand\b|million\b|billion\b)?"
    rf"|(?<![\d.,\-–+$])(?P<days>{NUM})[\s-]days?\b"
    rf"|(?<![\d.,])(?P<pct>{NUM})\s?%"
    rf"|(?<![\d.,])(?P<mult>{NUM})x\b"
    rf"|(?<![\w.,$])(?P<plain>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+\.\d+|\d{{3,}})(?![\w.,%]|\s?days?\b)")
# The deck writes `$50.5m`, `$81k`, `$1.2bn` (REPORT.md § 4); a workbook text cell may
# carry the spelled form.
SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6,
         "b": 1e9, "bn": 1e9, "billion": 1e9}
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


def read_slide(z: zipfile.ZipFile, part: str) -> dict:
    xml = z.read(part).decode("utf-8", "replace")
    name = ""
    m = re.search(r"<p:cSld\b[^>]*\bname=\"([^\"]*)\"", xml)
    if m:
        name = html.unescape(m.group(1))
    shapes: list[tuple[str, str]] = []
    for sp in re.findall(r"<p:sp\b.*?</p:sp>", xml, re.S):
        nm = re.search(r"<p:cNvPr\b[^>]*\bname=\"([^\"]*)\"", sp)
        shapes.append((html.unescape(nm.group(1)) if nm else "", para_text(sp)))
    tables: list[tuple[str, list[list[str]]]] = []
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
            "kicker": next((t for n, t in shapes if n == "kicker"), ""),
            "title": next((t for n, t in shapes if n == "title"), ""),
            "footer_source": next((t for n, t in shapes if n == "footer-source"), "")}


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
    if title is None:
        hr = 4
    else:
        hr = next((r for r in sorted(grid) if r >= 4 and len(grid[r]) == 1
                   and (next(iter(grid[r].values())).strip() == title.strip()
                        or fold(next(iter(grid[r].values()))).startswith(fold(title)))), None)
        if hr is None:
            return [], []
        hr = next((r for r in sorted(grid) if r > hr and len(grid[r]) >= 2), None)
        if hr is None:
            return [], []
    if hr not in grid or len(grid[hr]) < 2:
        return [], []
    cols = sorted(grid[hr])
    headers = [grid[hr][c] for c in cols]
    rows = []
    r = hr + 1
    while r in grid:
        rows.append([grid[r].get(c, "") for c in cols])
        r += 1
    return headers, rows


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


def schedule_gate(schedules: list[dict], tabs: list[str], texts: dict[str, dict[int, dict[int, str]]],
                  slides: list[dict]) -> list[str]:
    """GATE 5 — the recipe's schedules (RECIPE_FORMAT.md § Report): each is on the deck as
    a table from its family's tab, carrying every declared column and period, at the
    full population the schedule's `where` / `through` leave — every row's identity
    (the first declared column) present, none trimmed."""
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
        headers, rows = tab_block(texts.get(tab, {}), sc.get("block"))
        if not headers:
            fails.append(f"schedule `{title}`: `{tab}` has no "
                         + (f"block titled `{sc['block']}`" if sc.get("block") else "primary table"))
            continue
        periods = [h for h in headers if PERIOD_TOKEN.search(h)]
        want = list(words)
        if sc.get("periods") == "all":
            want += periods
        elif sc.get("periods") == "latest" and periods:
            want.append(periods[-1])
        candidates = [(k, body) for k, body in groups.items() if k[0] == tab]
        if not candidates:
            fails.append(f"schedule `{title}`: no page carries a table from `{tab}` — the recipe's "
                         f"schedules open the deck (REPORT.md § 1)")
            continue
        match = None
        for k, body in candidates:
            missing = [w for w in want if header_at(list(k[1]), w) is None]
            if not missing:
                match = (k, body)
                break
        if match is None:
            k = candidates[0][0]
            missing = [w for w in want if header_at(list(k[1]), w) is None]
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
        wanted_rows = [rows[j][ident].strip() for j in keep if rows[j][ident].strip()]
        absent = [x for x in wanted_rows if x not in shown]
        if absent:
            named = "; ".join(a[:44] for a in absent[:3])
            fails.append(f"schedule `{title}`: {len(absent)} of {len(wanted_rows)} rows on `{tab}` are not "
                         f"on the deck ({'…; ' if len(absent) > 3 else ''}{named}) — a recipe schedule "
                         f"is shown at full population, continued over pages, never trimmed")
        elif match[0] in trimmed:
            fails.append(f"schedule `{title}`: a table from `{tab}` states rows left on the tab — "
                         f"a recipe schedule is never trimmed")
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
    """Yield (token, value, tolerance, variants) for every figure-looking number."""
    for m in TOKEN.finditer(text):
        g = m.groupdict()
        raw = g["neg"] or g["money"] or g["days"] or g["pct"] or g["mult"] or g["plain"]
        if raw is None:
            continue
        if g["plain"] and YEAR.match(raw):
            continue
        if g["neg"] and re.fullmatch(r"\d{1,2}", raw) and not (g["nsuf"] or m.group(0).rstrip(")").endswith("%")):
            continue                       # "(3)" is a count in a heading, not a negative
        suffix = (g["suffix"] or g["nsuf"] or "").strip()
        scale = SCALE.get(suffix.lower(), 1.0)
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        value = float(raw.replace(",", "")) * scale
        tol = 0.5 * scale * 10 ** -decimals
        is_pct = bool(g["pct"]) or (g["neg"] is not None and m.group(0).rstrip(")").endswith("%"))
        variants = (1.0, 100.0) if is_pct else (1.0,)
        yield m.group(0).strip(), value, tol, variants


def backed(value: float, tol: float, variants, pool: list[float]) -> bool:
    for av in pool:
        a = abs(av)
        for f in variants:
            if abs(a * f - value) <= tol:
                return True
    return False


def company_phrase(company: str) -> str:
    """The company without its legal form — `Demo DGII Corp` reads `demo dgii` — for
    matching a mention of it in another cover string (build_report.company_phrase)."""
    return " ".join(LEGAL_FORM.sub(" ", company or "").split()).strip(" ,.-").lower()


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
    fails: list[str] = []
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
        company = shp.get("cover-company", "")
        name = company_phrase(company)
        if len(ctitle) > COVER_TITLE_MAX:
            fails.append(f"the cover title is {len(ctitle)} characters; it names the work, "
                         f"at most {COVER_TITLE_MAX}")
        if name and name in company_phrase(ctitle):
            fails.append(f"the cover title names the company (`{company}`) — the kicker and the "
                         f"prepared line carry it")
        m = PERIOD_TOKEN.search(ctitle)
        if m:
            fails.append(f"the cover title carries the period (`{m.group(0)}`) — the period is the "
                         f"subtitle's, the date the prepared line's")
        if len(csub) > COVER_SUB_MAX:
            fails.append(f"the cover subtitle is {len(csub)} characters; the entity and the period, "
                         f"at most {COVER_SUB_MAX}")
        if name and name in company_phrase(csub):
            fails.append(f"the cover subtitle names the company (`{company}`) — the kicker and the "
                         f"prepared line carry it")

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
        for tname, rows in s["tables"]:
            head = rows[0] if rows else []
            scales = [next((f for pat, f in COL_SCALE if pat.search(h)), None) for h in head]
            for r, row in enumerate(rows):
                if r == 0:
                    continue                       # the header row: period labels, counts of columns
                for ci, cell in enumerate(row):
                    at_scale = scales[ci] if ci < len(scales) else None
                    for token, value, tol, variants in tokenize(cell):
                        total += 1
                        if at_scale is not None:
                            variants = tuple(v * at_scale for v in variants)
                        if not backed(value, tol, variants, pool):
                            unbacked.append({"slide": n, "where": tname, "token": token})
        for cname, vals in s["charts"]:
            for v in vals:
                total += 1
                if not backed(abs(v), 0.5, (1.0,), pool):
                    unbacked.append({"slide": n, "where": cname, "token": f"{v:g}"})
        has_figures = bool(s["tables"] or s["charts"] or figures_here
                           or any(n_ in ("stat-value", "kv-value") for n_, _ in s["shapes"]))
        if has_figures:
            src = s["footer_source"]
            named = [t.strip() for t in src.split("·")[1:]] if src.startswith("Source:") else []
            if not named:
                fails.append(f"slide {n} (`{s['title'][:50]}`) states a figure and names no source tab "
                             f"in its footer — declare `source:` on the page")
            else:
                for t in named:
                    if t not in tabs:
                        fails.append(f"slide {n}: footer names `{t}`, no tab of the workbook")
                for tname, _ in s["tables"] + s["charts"]:
                    tab = tname.split(":", 1)[1] if ":" in tname else ""
                    if tab and tab not in named:
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
    # GATE 5 — the recipe's schedules, on a plan-driven run whose recipe declares them.
    schedules = None
    if run_dir is not None and (run_dir / "run.json").is_file():
        try:
            run = json.loads((run_dir / "run.json").read_text())
            rpath = (run.get("plan") or {}).get("recipe")
            if rpath:
                schedules = report_schedules(pathlib.Path(rpath).read_text())
        except (OSError, ValueError):
            schedules = None
    if schedules:
        fails.extend(schedule_gate(schedules, tabs, workbook_texts(workbook), slides))
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
        print(f"{wb}: not a file — pass --workbook", file=sys.stderr)
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
