#!/usr/bin/env python3
"""A bounded first look at a client file: what it is, in a few rows, never the whole.

    peek.py <path>... [--rows N] [--lines N] [--json]

Each path is a file, or a folder whose non-hidden files are peeked in sorted order. For
every file it prints the index facts - path, name, folder, extension, size, mtime - and a
peek that is bounded by construction:

    xlsx/xlsm     every sheet's name, state and extent (the sheet's own `dimension`
                  record), then the first ROWS non-empty rows of each of the first
                  SHEETS sheets with formulas shown as formulas; the sheet XML is
                  streamed and abandoned after those rows. A cell is shown as its
                  number format writes it where that changes what it is: a date
                  (serial 45322 is `2024-01-31`), a percentage (0.05 is `5%`)
    csv/tsv/txt/  the first LINES lines, each clipped to CHARS, plus the line count
    md/json/...   (counted in a stream, never printed) and a delimiter guess for csv
    pdf           the page count and up to TEXT_CHARS of text pulled from the first
                  content streams in file order - enough to name the document, not to
                  read it; a depth read of a PDF is page-ranged, in the harness
    docx/pptx     the first TEXT_CHARS of body text
    xls/xlsb      the sheet names and the first ROWS rows of each, through fastexcel
                  when it is importable (run under `uv run --project
                  ${CLAUDE_PLUGIN_ROOT}`); without it, size only and that instruction
    zip           the entry count and the first entry names
    anything else the first bytes, as hex

**Past a preamble.** A title block above a table would hide the header behind the first
ROWS rows, so the peek reads on past ROWS until three rows in a row share one width of
two or more cells (lines: fields) — the table's header and first data rows — up to
ROWS_MAX / LINES_MAX, and says so.

`--rows` and `--lines` widen the peek up to ROWS_MAX / LINES_MAX and no further. A wider
look is a bounded read in code (`nrows=`, a row range, `head`), never this tool with its
ceiling removed. The tool reads no more than it prints, with three in-process exceptions
that never reach the caller's context: an xlsx shared-string table is loaded to resolve
the peeked cells, a docx/pptx/pdf body is scanned for its first text, and a text file's
newlines are counted.

Exit 0; a file that cannot be read is reported with `unreadable` and the rest still
print. Exit 2 on a `--rows` / `--lines` above the ceiling. Stdlib only, except the
optional fastexcel read of xls / xlsb.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import html
import json
import os
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_workbook  # sibling: sheet order + shared strings, one xlsx reader per plugin

ROWS = 5                # non-empty rows shown per sheet
ROWS_MAX = 50           # the ceiling --rows can reach
LINES = 20              # lines shown per text file
LINES_MAX = 200         # the ceiling --lines can reach
CHARS = 200             # characters kept per text line
CELL_CHARS = 60         # characters kept per cell
COLS = 30               # cells shown per row; the cut is stated
SHEETS = 30             # sheets peeked per workbook; the rest are named only
TEXT_CHARS = 1200       # characters of body text from a pdf / docx / pptx
PDF_STREAMS = 40        # content streams scanned for text before giving up
PPTX_SLIDES = 3         # slides read for text
ZIP_ENTRIES = 10        # entry names shown
FILES = 400             # files peeked per folder; the cut is stated
RULER_WIDTH = 160       # characters of each line shown under the character ruler


def col_letter(i: int) -> str:
    """1-based column index -> spreadsheet letter (1 -> A, 27 -> AA)."""
    s = ""
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def ruler(lines: list[str], width: int = RULER_WIDTH) -> list[str]:
    """The lines under a character ruler - tens on the first line, units on the second -
    so a fixed-width column's first and last character can be read off it."""
    w = min(max((len(l) for l in lines), default=0), width)
    tens = "".join(str((i // 10) % 10) if i % 10 == 0 else " " for i in range(1, w + 1))
    ones = "".join(str(i % 10) for i in range(1, w + 1))
    return [tens, ones, *(l[:w] for l in lines)]
COUNT_BYTES = 256 << 20 # bytes streamed to count a text file's lines before reporting "at least"

TEXT_EXT = {"csv", "tsv", "txt", "md", "json", "jsonl", "ndjson", "yaml", "yml", "xml",
            "html", "htm", "log", "prn", "dat"}
XLSX_EXT = {"xlsx", "xlsm", "xltx", "xltm"}
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _clip(s: str, n: int) -> str:
    s = s.replace("\r", "").replace("\n", "\\n")
    return s if len(s) <= n else s[: n - 1] + "…"


def _human(n: int) -> str:
    x = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if x < 1024 or unit == "GB":
            return f"{x:,.0f} {unit}" if unit == "B" else f"{x:,.1f} {unit}"
        x /= 1024
    return f"{n} B"


def index_entry(path: pathlib.Path, root: pathlib.Path | None) -> dict:
    st = path.stat()
    folder = ""
    if root is not None and root.is_dir():
        rel = path.parent.relative_to(root)
        folder = "" if str(rel) == "." else str(rel)
    return {"path": str(path), "name": path.name, "folder": folder,
            "ext": path.suffix.lower().lstrip("."), "size_bytes": st.st_size,
            "mtime": _iso(st.st_mtime)}


# ---------------------------------------------------------------- xlsx

def _col_of(ref: str) -> str:
    m = re.match(r"([A-Z]+)", ref or "")
    return m.group(1) if m else ""


def _col_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def _extent(dim: str | None) -> tuple[int | None, int | None]:
    m = re.match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", dim or "")
    if not m:
        return None, None
    return int(m.group(4)) - int(m.group(2)) + 1, \
        _col_index(m.group(3)) - _col_index(m.group(1)) + 1


# Built-in number formats that write a date or a time (ECMA-376 § 18.8.30), and the ones
# that write a percentage.
DATE_FMT_IDS = set(range(14, 23)) | set(range(27, 37)) | set(range(45, 48)) | set(range(50, 59))
PCT_FMT_IDS = {9, 10}


def _fmt_kind(code: str) -> str | None:
    """`date`, `time`, `pct` or None for a custom number-format code."""
    bare = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", code or "")
    if "%" in bare:
        return "pct"
    if re.search(r"[dy]", bare, re.I) or re.search(r"(?<![hs:])m{3,}", bare, re.I):
        return "date"
    if re.search(r"[hs]", bare, re.I):
        return "time"
    return None


def cell_formats(z: zipfile.ZipFile) -> tuple[list[str | None], bool]:
    """(kind per cell style index, date1904): which styles write a date, a time or a
    percentage."""
    kinds: list[str | None] = []
    try:
        styles = z.read("xl/styles.xml")
    except KeyError:
        return kinds, False
    root = ET.fromstring(styles)
    custom = {int(n.get("numFmtId")): n.get("formatCode", "")
              for n in root.iter(NS + "numFmt")}
    xfs = root.find(NS + "cellXfs")
    for xf in (xfs if xfs is not None else []):
        i = int(xf.get("numFmtId") or 0)
        if i in custom:
            kinds.append(_fmt_kind(custom[i]))
        elif i in DATE_FMT_IDS:
            kinds.append("date")
        elif i in PCT_FMT_IDS:
            kinds.append("pct")
        else:
            kinds.append(None)
    try:
        wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
    except KeyError:
        wb = ""
    return kinds, bool(re.search(r'date1904="(1|true)"', wb))


def _formatted(raw: str, kind: str | None, date1904: bool) -> str:
    try:
        x = float(raw)
    except ValueError:
        return raw
    if kind in ("date", "time"):
        base = datetime.datetime(1904, 1, 1) if date1904 else datetime.datetime(1899, 12, 30)
        d = base + datetime.timedelta(days=x)
        if kind == "time":
            return d.strftime("%H:%M:%S")
        return d.strftime("%Y-%m-%d") if x == int(x) else d.strftime("%Y-%m-%d %H:%M:%S")
    if kind == "pct":
        return f"{x * 100:g}%"
    return raw


def _cell_text(c, shared: list[str], kinds: list | None = None,
               date1904: bool = False) -> tuple[str | None, bool]:
    """(display, is_formula) for one <c> element; None when the cell is empty. A number
    whose style writes a date, a time or a percentage is shown as written."""
    t = c.get("t", "n")
    f = c.find(NS + "f")
    v = c.find(NS + "v")
    val: str | None = None
    if t == "inlineStr":
        val = "".join(x.text or "" for x in c.iter(NS + "t"))
    elif v is not None and v.text is not None:
        raw = v.text
        if t == "s":
            try:
                val = shared[int(raw)]
            except (ValueError, IndexError):
                val = f"<s{raw}>"
        elif t == "b":
            val = "TRUE" if raw == "1" else "FALSE"
        elif t == "n" and kinds:
            si = int(c.get("s") or 0)
            val = _formatted(raw, kinds[si] if si < len(kinds) else None, date1904)
        else:
            val = raw
    if f is not None:
        formula = f.text or ""
        shown = f"={formula}" if formula else "=<shared formula>"
        if val is not None:
            shown += f" → {val}"
        return shown, True
    return val, False


def _sheet_states(z: zipfile.ZipFile) -> dict[str, str]:
    try:
        wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
    except KeyError:
        return {}
    out = {}
    for el in check_workbook.SHEET_EL.findall(wb):
        name = check_workbook.ATTR("name").search(el)
        state = check_workbook.ATTR("state").search(el)
        if name:
            out[html.unescape(name.group(1))] = state.group(1) if state else "visible"
    return out


def settled(widths: list[int]) -> bool:
    """Three rows in a row of one width of two or more: a table's header and data."""
    return len(widths) >= 3 and widths[-1] >= 2 and widths[-1] == widths[-2] == widths[-3]


def peek_sheet(z: zipfile.ZipFile, part: str, shared: list[str], rows: int,
               kinds: list | None = None, date1904: bool = False) -> dict:
    """Stream one sheet's XML; stop after `rows` non-empty rows once the rows have
    settled into a table (`settled`), or at ROWS_MAX."""
    out: dict = {"dimension": None, "rows": [], "formula_columns": []}
    widths: list[int] = []
    formula_cols: set[str] = set()
    with z.open(part) as fh:
        for _ev, el in ET.iterparse(fh, events=("end",)):
            tag = el.tag
            if tag == NS + "dimension":
                out["dimension"] = el.get("ref")
            elif tag == NS + "row":
                rnum = int(el.get("r") or 0)
                cells = {}
                for c in el.findall(NS + "c"):
                    text, is_f = _cell_text(c, shared, kinds, date1904)
                    col = _col_of(c.get("r", ""))
                    if is_f:
                        formula_cols.add(col)
                    if text is not None and text != "":
                        cells[col] = _clip(text, CELL_CHARS)
                el.clear()
                if not cells:
                    continue
                cut = len(cells) - COLS
                if cut > 0:
                    cells = dict(list(cells.items())[:COLS])
                    cells["…"] = f"{cut} more cells"
                widths.append(len(cells))
                out["rows"].append({"r": rnum, "cells": cells})
                if len(out["rows"]) >= rows and (settled(widths) or len(out["rows"]) >= ROWS_MAX):
                    break
            elif tag == NS + "sheetData":
                break
            elif tag not in (NS + "c", NS + "v", NS + "f", NS + "is", NS + "t"):
                el.clear()
    if len(out["rows"]) > rows:
        out["read_past"] = f"read past {rows} rows to reach the table under a preamble"
    out["formula_columns"] = sorted(formula_cols, key=_col_index)
    out["rows_extent"], out["cols_extent"] = _extent(out["dimension"])
    return out


def peek_xlsx(path: pathlib.Path, rows: int) -> dict:
    with zipfile.ZipFile(path) as z:
        order = check_workbook.sheet_order(z)
        shared = check_workbook.shared_strings(z)
        states = _sheet_states(z)
        kinds, date1904 = cell_formats(z)
        sheets = []
        for i, (part, name) in enumerate(order):
            entry: dict = {"name": name, "state": states.get(name, "visible")}
            if i < SHEETS:
                try:
                    entry.update(peek_sheet(z, part, shared, rows, kinds, date1904))
                except Exception as exc:                      # one bad sheet, not the book
                    entry["unreadable"] = f"{type(exc).__name__}: {exc}"
            else:
                entry["not_peeked"] = f"beyond the first {SHEETS} sheets"
            sheets.append(entry)
    return {"kind": "workbook", "sheets": sheets, "sheet_names": [n for _p, n in order]}


def peek_binary_book(path: pathlib.Path, rows: int) -> dict:
    """xls / xlsb through fastexcel (calamine), bounded to `rows` rows per sheet. Row
    numbers are the used range's, which starts at its first non-empty row."""
    try:
        import fastexcel
    except ImportError:
        return {"kind": "xls", "note": f"binary .{path.suffix.lower().lstrip('.')} - no "
                "stdlib reader; peek it again under `uv run --project "
                "${CLAUDE_PLUGIN_ROOT} python3 scripts/peek.py`, which has fastexcel"}
    book = fastexcel.read_excel(str(path))
    sheets = []
    for i, name in enumerate(book.sheet_names):
        entry: dict = {"name": name, "state": "visible"}
        if i >= SHEETS:
            entry["not_peeked"] = f"beyond the first {SHEETS} sheets"
            sheets.append(entry)
            continue
        try:
            sh = book.load_sheet(name, header_row=None, n_rows=rows)
            recs = sh.to_polars().rows()
        except Exception as exc:
            entry["unreadable"] = f"{type(exc).__name__}: {exc}"
            sheets.append(entry)
            continue
        out_rows = []
        for k, rec in enumerate(recs):
            cells = {col_letter(j + 1): _clip(str(v), CELL_CHARS)
                     for j, v in enumerate(rec) if v not in (None, "")}
            if cells:
                out_rows.append({"r": k + 1, "cells": dict(list(cells.items())[:COLS])})
        entry.update({"rows": out_rows, "formula_columns": [], "dimension": None,
                      "rows_extent": sh.total_height, "cols_extent": sh.width,
                      "read_past": "row numbers count from the used range's first row"})
        sheets.append(entry)
    return {"kind": "workbook", "sheets": sheets, "sheet_names": list(book.sheet_names)}


# ---------------------------------------------------------------- text

def _read_line(fh, limit: int) -> tuple[bytes, bool, bool]:
    """(clipped line, was clipped, at eof). A line longer than `limit` is skipped past in
    chunks, so a one-line multi-megabyte file costs its bytes, never its memory."""
    buf = fh.readline(limit)
    if not buf:
        return b"", False, True
    if buf.endswith(b"\n"):
        return buf.rstrip(b"\r\n"), False, False
    clipped = False
    while True:
        chunk = fh.readline(1 << 20)
        if not chunk:
            return buf, clipped, True
        clipped = True
        if chunk.endswith(b"\n"):
            return buf, True, False


def _fields(line: str) -> int:
    """The widest field count any common delimiter gives a line: 0 for a blank line."""
    if not line.strip():
        return 0
    return max(next(csv.reader([line], delimiter=d), []).__len__() for d in ",;\t|")


def peek_text(path: pathlib.Path, lines: int, ext: str) -> dict:
    shown, counted, at_least = [], 0, False
    widths: list[int] = []
    tabular = ext in ("csv", "tsv", "prn", "dat", "txt")
    with open(path, "rb") as fh:
        eof = False
        while not eof and (len(shown) < lines or (
                tabular and not settled(widths) and len(shown) < LINES_MAX)):
            raw, _clipped, eof = _read_line(fh, CHARS * 4)
            if eof and not raw:
                break
            counted += 1
            text = raw.decode("utf-8", "replace").lstrip("﻿")
            shown.append(_clip(text, CHARS))
            if tabular:
                widths.append(_fields(text))
        # the rest of the file is counted, never kept
        streamed = 0
        while not eof:
            chunk = fh.read(1 << 20)
            if not chunk:
                break
            streamed += len(chunk)
            counted += chunk.count(b"\n")
            if streamed >= COUNT_BYTES:
                at_least = True
                break
    out: dict = {"kind": "text", "lines": shown,
                 "lines_total" if not at_least else "lines_at_least": counted}
    if len(shown) > lines:
        out["read_past"] = f"read past {lines} lines to reach the table under a preamble"
    if any("\x00" in l or "\ufffd" in l for l in shown):
        out["encoding_note"] = ("bytes that are not UTF-8 shown as \ufffd: the file is in "
                                "another encoding (cp1252, UTF-16) - declare the "
                                "encoding in the extract step's script")
    if ext in ("csv", "tsv", "prn", "dat") and shown:
        try:
            out["delimiter"] = csv.Sniffer().sniff("\n".join(shown[:5])).delimiter
        except csv.Error:
            out["delimiter"] = None
    if tabular and looks_fixed(shown):
        out["ruler"] = ruler(shown, CHARS)
        out["fixed_note"] = ("no delimiter; columns aligned by position - the extract "
                             "step's script slices them by the characters read off "
                             "this ruler")
    return out


def looks_fixed(lines: list[str]) -> bool:
    """Columns aligned by position: most non-blank lines split into one field under every
    delimiter, and carry runs of spaces between their values."""
    body = [l for l in lines if l.strip()]
    if len(body) < 3:
        return False
    aligned = [l for l in body if _fields(l) <= 1 and re.search(r"\S {2,}\S", l)]
    return len(aligned) * 2 > len(body)


# ---------------------------------------------------------------- pdf / ooxml prose

_PDF_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.S)
_PDF_TJ = re.compile(rb"\((.*?)(?<!\\)\)\s*Tj", re.S)
_PDF_TJ_ARR = re.compile(rb"\[(.*?)\]\s*TJ", re.S)
_PDF_STR = re.compile(rb"\((.*?)(?<!\\)\)", re.S)
_PDF_PAGE = re.compile(rb"/Type\s*/Page\b(?!s)")


def _pdf_unescape(b: bytes) -> str:
    s = b.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
    return re.sub(r"[^\x20-\x7e -￿]", " ", s.decode("latin-1"))


_PDF_TJ_TOKEN = re.compile(rb"\((.*?)(?<!\\)\)|(-?\d+(?:\.\d+)?)", re.S)


def _pdf_tj_array(arr: bytes) -> str:
    """Text of one TJ array: strings joined, a kerning offset at or below -180 read as
    a word gap (the convention most writers follow; the result is approximate)."""
    out: list[str] = []
    for m in _PDF_TJ_TOKEN.finditer(arr):
        if m.group(1) is not None:
            out.append(_pdf_unescape(m.group(1)))
        elif float(m.group(2)) <= -180:
            out.append(" ")
    return "".join(out)


def peek_pdf(path: pathlib.Path) -> dict:
    """The page count and the first page's text layer as the page lays it out (pypdf,
    when the plugin's environment has it), under a character ruler so a statement's
    columns can be declared; else the first content streams, stdlib."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return _peek_pdf_streams(path)
    try:
        r = PdfReader(str(path))
        if r.is_encrypted and not r.decrypt(""):
            return {"kind": "pdf", "pages": len(r.pages), "text": "",
                    "text_note": "password-protected - ask for an unprotected copy"}
        n = len(r.pages)
        text = r.pages[0].extract_text(extraction_mode="layout") if n else ""
    except Exception:
        return _peek_pdf_streams(path)
    lines, total = [], 0
    for ln in (text or "").splitlines():
        if len(lines) >= LINES or total >= TEXT_CHARS:
            break
        lines.append(_clip(ln.rstrip(), CHARS))
        total += len(lines[-1])
    if not any(l.strip() for l in lines):
        return {"kind": "pdf", "pages": n, "text": "",
                "text_note": "page 1 has no text layer (a scan) - read it page-ranged in "
                             "the harness"}
    return {"kind": "pdf", "pages": n, "lines": ruler(lines, CHARS),
            "text_note": "page 1's text layer as laid out, under a character ruler: "
                         "the extract step's script reads a statement's rows by page "
                         "and line, its columns by the characters read off it"}


def _peek_pdf_streams(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    pages = len(_PDF_PAGE.findall(data))
    parts: list[str] = []
    total = 0
    scanned = 0
    for m in _PDF_STREAM.finditer(data):
        if scanned >= PDF_STREAMS or total >= TEXT_CHARS:
            break
        scanned += 1
        body = m.group(1)
        try:
            body = zlib.decompress(body)
        except zlib.error:
            pass
        frags = [_pdf_unescape(t) for t in _PDF_TJ.findall(body)]
        for arr in _PDF_TJ_ARR.findall(body):
            frags.append(_pdf_tj_array(arr))
        text = " ".join(f.strip() for f in frags if f.strip())
        if text:
            parts.append(text)
            total += len(text)
    text = _clip(" ".join(parts), TEXT_CHARS)
    return {"kind": "pdf", "pages": pages, "text": text,
            "text_note": ("first content streams, file order, approximate" if text else
                          "no extractable text in the first streams - scanned pages or "
                          "font-encoded text; read page-ranged in the harness")}


def _xml_text(xml: bytes, tag: str) -> str:
    pat = re.compile(rb"<%s\b[^>]*>(.*?)</%s>" % (tag.encode(), tag.encode()), re.S)
    return html.unescape(" ".join(
        re.sub(rb"<[^>]+>", b"", t).decode("utf-8", "replace") for t in pat.findall(xml)))


def peek_docx(path: pathlib.Path) -> dict:
    with zipfile.ZipFile(path) as z:
        try:
            body = z.read("word/document.xml")
        except KeyError:
            return {"kind": "docx", "text": "", "text_note": "no word/document.xml part"}
    return {"kind": "docx", "text": _clip(_xml_text(body, "w:t"), TEXT_CHARS)}


def peek_pptx(path: pathlib.Path) -> dict:
    with zipfile.ZipFile(path) as z:
        slides = sorted((int(m.group(1)), n) for n in z.namelist()
                        for m in [re.match(r"ppt/slides/slide(\d+)\.xml$", n)] if m)
        texts = [_xml_text(z.read(n), "a:t") for _i, n in slides[:PPTX_SLIDES]]
    return {"kind": "pptx", "slides": len(slides),
            "text": _clip(" | ".join(t for t in texts if t), TEXT_CHARS)}


def peek_zip(path: pathlib.Path) -> dict:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    return {"kind": "zip", "entries": len(names), "first_entries": names[:ZIP_ENTRIES]}


def peek_other(path: pathlib.Path) -> dict:
    with open(path, "rb") as fh:
        head = fh.read(16)
    return {"kind": "binary", "head_hex": head.hex(" ")}


# ---------------------------------------------------------------- dispatch

def peek_file(path: pathlib.Path, root: pathlib.Path | None, rows: int, lines: int) -> dict:
    entry = index_entry(path, root)
    ext = entry["ext"]
    try:
        if ext in XLSX_EXT:
            entry["peek"] = peek_xlsx(path, rows)
            entry["sheets"] = entry["peek"]["sheet_names"]
        elif ext in TEXT_EXT:
            entry["peek"] = peek_text(path, lines, ext)
        elif ext == "pdf":
            entry["peek"] = peek_pdf(path)
        elif ext == "docx":
            entry["peek"] = peek_docx(path)
        elif ext == "pptx":
            entry["peek"] = peek_pptx(path)
        elif ext in ("xls", "xlsb"):
            entry["peek"] = peek_binary_book(path, rows)
            if entry["peek"].get("sheet_names"):
                entry["sheets"] = entry["peek"]["sheet_names"]
        elif ext == "zip":
            entry["peek"] = peek_zip(path)
        else:
            entry["peek"] = peek_other(path)
    except Exception as exc:
        entry["unreadable"] = f"{type(exc).__name__}: {exc}"
    return entry


def walk(target: pathlib.Path) -> tuple[list[pathlib.Path], int]:
    """(files to peek, files beyond the FILES cut). Hidden entries are skipped."""
    files: list[pathlib.Path] = []
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for f in sorted(filenames):
            if not f.startswith("."):
                files.append(pathlib.Path(dirpath) / f)
    return files[:FILES], max(0, len(files) - FILES)


def render(entry: dict) -> str:
    out = [f"== {entry['path']}",
           f"   {entry['ext'] or '(no ext)'} · {_human(entry['size_bytes'])} · "
           f"mtime {entry['mtime']}" + (f" · folder {entry['folder']}" if entry["folder"]
                                        else "")]
    if entry.get("unreadable"):
        out.append(f"   unreadable: {entry['unreadable']}")
        return "\n".join(out)
    p = entry.get("peek") or {}
    kind = p.get("kind")
    if kind == "workbook":
        out.append(f"   sheets ({len(p['sheets'])}): " + ", ".join(
            f"{s['name']}" + (f" [{s['state']}]" if s.get("state") != "visible" else "")
            + (f" {s['dimension']}" if s.get("dimension") else "")
            for s in p["sheets"]))
        for s in p["sheets"]:
            if s.get("unreadable"):
                out.append(f"   [{s['name']}] unreadable: {s['unreadable']}")
                continue
            if s.get("not_peeked"):
                continue
            ext_ = (f"{s['rows_extent']:,} rows × {s['cols_extent']} cols"
                    if s.get("rows_extent") else "extent unknown")
            fc = f"; formulas in {', '.join(s['formula_columns'])}" if s.get(
                "formula_columns") else ""
            past = f" ({s['read_past']})" if s.get("read_past") else ""
            out.append(f"   [{s['name']}] {ext_}{fc} - first {len(s['rows'])} non-empty "
                       f"rows{past}:")
            for r in s["rows"]:
                out.append(f"     r{r['r']:<6}" + " | ".join(
                    f"{k}={v}" for k, v in r["cells"].items()))
    elif kind == "text":
        n = p.get("lines_total")
        count = f"{n:,} lines" if n is not None else f"≥{p['lines_at_least']:,} lines"
        delim = f"; delimiter {p['delimiter']!r}" if p.get("delimiter") else ""
        past = f" ({p['read_past']})" if p.get("read_past") else ""
        out.append(f"   {count}{delim} - first {len(p['lines'])}{past}:")
        if p.get("encoding_note"):
            out.append(f"   note: {p['encoding_note']}")
        if p.get("ruler"):
            out.append(f"   note: {p['fixed_note']}")
            out += [f"     {ln}" for ln in p["ruler"]]
        else:
            out += [f"     {ln}" for ln in p["lines"]]
    elif kind == "pdf":
        out.append(f"   {p['pages']} page(s); {p.get('text_note', '')}")
        if p.get("lines"):
            out += [f"     {ln}" for ln in p["lines"]]
        elif p.get("text"):
            out.append(f"     {p['text']}")
    elif kind in ("docx", "pptx"):
        if kind == "pptx":
            out.append(f"   {p['slides']} slide(s)")
        out.append(f"     {p.get('text') or p.get('text_note') or '(no text)'}")
    elif kind == "xls":
        out.append(f"   {p['note']}")
    elif kind == "zip":
        out.append(f"   {p['entries']} entries: " + ", ".join(p["first_entries"]))
    elif kind == "binary":
        out.append(f"   first bytes: {p['head_hex']}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=pathlib.Path)
    ap.add_argument("--rows", type=int, default=ROWS,
                    help=f"non-empty rows per sheet (default {ROWS}, ceiling {ROWS_MAX})")
    ap.add_argument("--lines", type=int, default=LINES,
                    help=f"lines per text file (default {LINES}, ceiling {LINES_MAX})")
    ap.add_argument("--json", action="store_true",
                    help="one JSON object per file, the index fields plus `peek`")
    a = ap.parse_args()
    if not (1 <= a.rows <= ROWS_MAX) or not (1 <= a.lines <= LINES_MAX):
        print(f"peek: --rows stays within 1..{ROWS_MAX} and --lines within 1..{LINES_MAX}; "
              f"a wider look is a bounded read in code, never this tool unbounded",
              file=sys.stderr)
        return 2

    entries: list[dict] = []
    notes: list[str] = []
    for target in a.paths:
        target = target.expanduser().resolve()
        if target.is_dir():
            files, beyond = walk(target)
            entries += [peek_file(f, target, a.rows, a.lines) for f in files]
            if beyond:
                notes.append(f"{target}: {beyond} more file(s) beyond the first {FILES} "
                             f"- peek them by subfolder")
        elif target.is_file():
            entries.append(peek_file(target, None, a.rows, a.lines))
        else:
            entries.append({"path": str(target), "name": target.name, "folder": "",
                            "ext": target.suffix.lower().lstrip("."), "size_bytes": 0,
                            "mtime": None, "unreadable": "no such file or folder"})

    if a.json:
        for e in entries:
            print(json.dumps(e, ensure_ascii=False))
    else:
        print("\n\n".join(render(e) for e in entries))
    for n in notes:
        print(f"note: {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
