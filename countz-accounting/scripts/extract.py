#!/usr/bin/env python3
"""Parse the data-room files the plan's steps read into one typed cache, once.

    extract.py <run_dir> --step <step id>          the files the definition step declares
    extract.py <run_dir> --files '<json>' | @file  the same list, given directly
    extract.py <run_dir> --show                    print the manifest
    extract.py <run_dir> --reperform <id>          re-read the source block; compare
    extract.py <run_dir> --step <id> --override '{"<file id>": {<spec keys>}}'

The `extract` step kind runs this (skills/check-extract/SKILL.md). Its input is the
step's `params.files`, one entry per file the planner scheduled for extraction:

    {"id": "invoice_lines_fy2025",                # a slug; what every consumer reads by
     "path": "3 Revenue/3.5 Invoices/3.5.16 Invoice Lines FY2025.csv",
     "source": "dataroom",                        # the run's source id; `path` is
                                                  # relative to that source's registered
                                                  # path, or absolute
     "file_role": "system_export",               # EVIDENCE.md § 1; carried into spans
     "header_row": 5,                             # 1-based; omitted = detected
     "rows": "6:1204",                            # 1-based data records, inclusive; several
                                                  # ranges as "6:40,42:1204" cut a row that is
                                                  # not data; omitted = the block under the
                                                  # header (below)
     "sheet": "Detail",                           # xlsx only
     "types": {"invoice_amount": "Float64", "invoice_date": "Date"},   # overrides
     "control": "invoice_amount"}                 # the control-total column; omitted =
                                                  # the first amount-like numeric column

Output, under `<run_dir>/cache/`: `<id>.parquet` per file and `manifest.json` — per
file its source path, bytes and sha256, the header row and the preamble above it, every
column with its letter and dtype, the row count and the control total, each re-read
from the parquet after writing. Consumers load through `read()` / `scan()` and cite
through `scripts/evidence.py span`, which builds the citation from this manifest so the
`file`, `header_at`, `rows`, `columns` and `control_total` of every span are measured on
the file. The parquet is a derived copy: no citation names it.

**A block, not a file.** A text file is read as one block: the header line and the data
lines under it, ending at the first blank line or the first line whose field count is
not the header's. What follows that end is never read into the block. Non-blank lines
below it — a second table, a totals section, a footer — are counted into the manifest
as `trailing` and printed as `TRAILING: <id> — lines N..M below the block`; the step
puts them to the plan (skills/check-extract/SKILL.md § 2). A file that stacks several
tables is several entries, one id per block, each with its `header_row` and `rows`
from the planner's anchors; a total row inside a block is cut the same way. A sheet
reads `rows` as well; without it the sheet is read whole under its header.

**Every block is checked.** Four checks run on every block and land in
the manifest:

- `header_check` — a `header_row` the spec gives is read as given, never detected, so
  it is checked against the file itself: whether it starts its run of equal-width records
  (a text file's layout; a data row sits inside a run that starts higher up), and
  header names that are values (a number, a date), which a data row read as the header
  carries. Printed as `HEADER: <id> — read at line N as the spec gives it; <why>`; it
  exits 1. The profile's anchor is where the spec's `header_row` came from, so agreeing
  with it is not a check.
- `suspects` — rows inside the block that look like they are not data: a repeated
  header line (a paged export), a row of text in a column that is otherwise numeric (a
  second table's header, a note), and a total or subtotal row (a row whose amounts equal
  the sum of the rows above it, or whose label says total). Printed as `SUSPECT: <id>
  row N (line L) — <reason>`. The row stays in the block; the step rules on each
  (skills/check-extract/SKILL.md § 2) and cuts it with `rows` where it is not data.
- `profile_check` — where the planner's profile ledger
  (`workpapers/evidence-profile-<source>.yaml`) holds a whole-block span of the same
  file, the block's sum of that span's control column is compared to the span's
  `control_total`: two independent reads of one file. Printed as `AGREES:` or
  `DISAGREES: <id> — <ours> vs <profile id> <theirs>`; a disagreement exits 1.
- `sha256` of the source, so a later read can tell the file has not changed.

A step that finds the cache wrong downstream re-performs the read against the source
(`scripts/evidence.py span <id> --reperform`, or `reperform()` here) and records a
cache defect (agents/worker.md § Your procedure); the fix is an override, and a cached
file is not edited: `--override '{"<id>": {"rows": "6:120", ...}}'` writes
`cache/overrides.json`, applied over the step's `params.files` on every run and
recorded on the manifest entry as `overrides`.

A file that will not parse is printed as `FAILED: <id> — <reason>`, left out of the
manifest, and the exit is 1; the step records it as a blocker and every step that reads
the id falls back to the source file. Exit 0 when every file landed, every header check
passed and every profile check agrees.

Requires polars (and fastexcel for xlsx) — run as
`uv run --project ${CLAUDE_PLUGIN_ROOT} python3 scripts/extract.py`.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import pathlib
import re
import sys

SCHEMA = "countz-accounting/cache@1"
CACHE_DIR = "cache"
MANIFEST = "manifest.json"
OVERRIDES = "overrides.json"
TOTAL_WORDS = re.compile(r"\b(grand\s+)?(sub)?totals?\b|\bsum\b", re.I)
SUSPECTS_MAX = 50
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
TEXT_EXT = {"csv", "tsv", "txt", "prn", "dat"}
SHEET_EXT = {"xlsx", "xlsm", "xlsb", "xls"}
AMOUNT_WORDS = ("amount", "value", "total", "balance", "debit", "credit", "net", "gross",
                "revenue", "arr", "mrr", "usd")
DTYPES = {"Float64", "Float32", "Int64", "Int32", "Utf8", "String", "Date", "Datetime",
          "Boolean"}


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def col_letter(i: int) -> str:
    """1-based column index -> spreadsheet letter (1 -> A, 27 -> AA)."""
    s = ""
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- header detection

def sniff_delimiter(lines: list[str]) -> str:
    try:
        return csv.Sniffer().sniff("\n".join(lines), delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def records(path: pathlib.Path, delim: str):
    """(start line, fields) per CSV record. Records, not lines: a quoted field may hold a
    newline, and a spreadsheet numbers the file by record; `start line` is the physical
    line the record begins on, which is the row number a reader sees."""
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter=delim)
        start = 1
        for rec in reader:
            yield start, rec
            start = reader.line_num + 1


def detect_header(path: pathlib.Path, probe: int = 60) -> tuple[int, str, list[str]]:
    """(header_row 1-based, delimiter, preamble lines) for a delimited text file: the
    first record with two or more fields whose field count the next three records
    share. A preamble (a title, an export stamp, a blank line) has a different count, so
    it is skipped and kept for the manifest."""
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        head = [next(fh, None) for _ in range(probe)]
    lines = [l.rstrip("\r\n") for l in head if l is not None]
    if not lines:
        raise ValueError("empty file")
    delim = sniff_delimiter([l for l in lines if l.strip()][:10])
    recs = []
    for start, rec in records(path, delim):
        recs.append((start, 0 if not any(f.strip() for f in rec) else len(rec)))
        if len(recs) >= probe:
            break
    for i, (start, n) in enumerate(recs):
        if n < 2:
            continue
        following = [c for _, c in recs[i + 1:i + 4] if c]
        if following and all(c == n for c in following):
            return start, delim, lines[:start - 1]
    for start, n in recs:                          # a short file: the first two-field record
        if n >= 2:
            return start, delim, lines[:start - 1]
    raise ValueError("no delimited header row found in the first "
                     f"{len(recs)} records (delimiter {delim!r})")


# ---------------------------------------------------------------- the frame

def _pl():
    try:
        import polars as pl
    except ImportError as exc:                      # pragma: no cover
        sys.exit(f"extract.py needs polars ({exc}); run it as "
                 "`uv run --project ${CLAUDE_PLUGIN_ROOT} python3 scripts/extract.py`")
    return pl


def _overrides(types: dict | None):
    pl = _pl()
    out = {}
    for col, name in (types or {}).items():
        if name not in DTYPES:
            raise ValueError(f"types[{col!r}] = {name!r}; one of {', '.join(sorted(DTYPES))}")
        out[col] = getattr(pl, "String" if name == "Utf8" else name)
    return out


ROWS = re.compile(r"^\d+:\d+(?:\s*,\s*\d+:\d+)*$")


def parse_rows(spec: dict) -> list[tuple[int, int]] | None:
    """`rows: "N:M[,N2:M2...]"` as [(first, last), ...] 1-based inclusive data records in
    ascending, non-overlapping order, or None."""
    r = spec.get("rows")
    if r is None:
        return None
    text = str(r).strip()
    if not ROWS.match(text):
        raise ValueError(f"rows {r!r}: want \"first:last\" ranges, comma-separated, of "
                         f"1-based inclusive data records")
    out = []
    for part in text.split(","):
        a, b = (int(x) for x in part.split(":"))
        if a < 1 or a > b or (out and a <= out[-1][1]):
            raise ValueError(f"rows {r!r}: ranges ascend and do not overlap")
        out.append((a, b))
    return out


def block_extent(path: pathlib.Path, header_row: int, delim: str) -> tuple[int, dict]:
    """(data records in the block, trailing) for a text file: the block runs from the
    record under the header to the record before the first blank record or the first
    record whose field count is not the header's. Records, not lines: a quoted field
    may hold a newline, and a spreadsheet numbers the file by record. `trailing` counts
    the non-blank records below the block's end — `{"from_line": N, "to_line": M,
    "lines": k}`, numbered as records — or is None."""
    n_fields = None
    data, first_bad, trailing_nonblank, last_nonblank = 0, None, 0, None
    seen_header = False
    for start, rec in records(path, delim):
        if start < header_row:
            continue
        blank = not any(f.strip() for f in rec)
        count = 0 if blank else len(rec)
        if not seen_header:
            if start != header_row:
                raise ValueError(f"no record starts at header_row {header_row}")
            n_fields, seen_header = count, True
            continue
        if first_bad is None:
            if count == n_fields:
                data += 1
                continue
            first_bad = start
        if not blank:
            trailing_nonblank += 1
            last_nonblank = start
    if not seen_header:
        raise ValueError(f"the file ends before header_row {header_row}")
    trailing = None
    if trailing_nonblank:
        trailing = {"from_line": first_bad, "to_line": last_nonblank, "lines": trailing_nonblank}
    return data, trailing


def _retype(df):
    """A text column that parses as a number on every non-empty row becomes Float64:
    polars typed it as text on a row the caller has since cut with `rows`."""
    pl = _pl()
    for c, (parsed, share) in _numeric_view(df).items():
        if df.schema[c] == pl.String and share >= 1.0:
            df = df.with_columns(parsed.alias(c))
    return df


def _keep_ranges(df, rows, header_row: int):
    """Keep the records `rows` names (1-based file records; the frame's row 0 is record
    header_row + 1), dropping the gaps between ranges."""
    if not rows or len(rows) == 1:
        return df
    pl = _pl()
    rec = pl.int_range(0, df.height, eager=True) + (header_row + 1)
    keep = None
    for a, b in rows:
        m = (rec >= a) & (rec <= b)
        keep = m if keep is None else (keep | m)
    return df.filter(keep)


def load_frame(path: pathlib.Path, spec: dict) -> tuple["object", dict]:
    """The file as a typed polars frame, and the facts about how it was read."""
    pl = _pl()
    ext = path.suffix.lower().lstrip(".")
    facts: dict = {}
    overrides = _overrides(spec.get("types"))
    rows = parse_rows(spec)
    if ext in SHEET_EXT:
        header_row = int(spec.get("header_row") or 1)
        if rows and rows[0][0] != header_row + 1:
            raise ValueError(f"rows {spec['rows']!r} does not start under header_row {header_row}")
        opts = {"header_row": header_row - 1}
        if rows:
            opts["n_rows"] = rows[-1][1] - rows[0][0] + 1
        df = pl.read_excel(path, sheet_name=spec.get("sheet"), read_options=opts,
                           schema_overrides=overrides or None)
        df = _retype(_keep_ranges(df, rows, header_row))
        facts.update(header_row=header_row, sheet=spec.get("sheet"), preamble=[],
                     delimiter=None, trailing=None)
    else:
        if spec.get("header_row"):
            header_row = int(spec["header_row"])
            with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
                preamble = [next(fh, "").rstrip("\r\n") for _ in range(header_row - 1)]
                header_line = next(fh, "")
            delim = spec.get("delimiter") or sniff_delimiter([header_line])
        else:
            header_row, delim, preamble = detect_header(path)
        if rows:
            if rows[0][0] != header_row + 1:
                raise ValueError(f"rows {spec['rows']!r} does not start under header_row "
                                 f"{header_row}")
            n_rows, trailing = rows[-1][1] - rows[0][0] + 1, None
        else:
            n_rows, trailing = block_extent(path, header_row, delim)
        if n_rows == 0:
            raise ValueError(f"no data line under the header at line {header_row}")
        df = pl.read_csv(path, skip_rows=header_row - 1, n_rows=n_rows, separator=delim,
                         infer_schema_length=None, schema_overrides=overrides or None,
                         try_parse_dates=True, encoding="utf8-lossy")
        if df.height != n_rows:
            raise ValueError(f"read {df.height} rows where the block holds {n_rows} records "
                             f"- a ragged record inside the block; name `rows` to cut it")
        df = _retype(_keep_ranges(df, rows, header_row))
        facts.update(header_row=header_row, sheet=None, preamble=preamble, delimiter=delim,
                     trailing=trailing)
        if spec.get("header_row"):
            facts["detected_header_row"] = run_start(path, header_row, delim)
    return df, facts


def run_start(path: pathlib.Path, line: int, delim: str) -> int:
    """The line the run of records holding `line` starts on: a run is consecutive
    non-blank records of one field count, as a table's header and data lines are. A
    header starts its run; a data row read as the header sits inside one that starts
    higher up. Local to the block, so a second table stacked under a first is judged on
    its own lines, never against the first table's header."""
    start, width = None, None
    for s, rec in records(path, delim):
        n = len(rec) if any(f.strip() for f in rec) else 0
        if n < 2 or n != width:
            start = s if n >= 2 else None
        width = n
        if s >= line:
            return start if s == line and start is not None else line
    return line


DATA_LIKE = re.compile(r"^\s*(?:[-+(]?[$€£]?\s*[\d,]*\.?\d+\)?%?|\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4})\s*$")


def header_check(columns: list[str], facts: dict) -> dict | None:
    """Whether the row read as the header is one. A `header_row` the spec gives is read
    as given, so it is checked two independent ways: whether it starts its run of
    equal-width records (text files, `run_start`), and header names that are values — a number or a date — which a data
    row read as the header carries. None when neither fires."""
    given, detected = facts["header_row"], facts.get("detected_header_row", facts["header_row"])
    data_like = [c for c in columns if DATA_LIKE.match(str(c))]
    if detected == given and not data_like:
        return None
    return {"given": given, "detected": detected, "data_like": data_like}


def pick_control(df, wanted: str | None) -> str | None:
    """The control-total column: `wanted`, or the first amount-like column that is
    numeric — typed so, or a text column that parses as a number on most of its rows
    (a repeated header or a note inside the block types the column as text; the rows
    that do not parse are the block's suspects)."""
    view = _numeric_view(df)
    if wanted:
        if wanted not in df.columns:
            raise ValueError(f"control column {wanted!r} is not in the file: {df.columns}")
        if wanted not in view:
            raise ValueError(f"control column {wanted!r} is {df.schema[wanted]} and does not "
                             f"parse as a number; name it in `types` or cut the rows that "
                             f"are not data with `rows`")
        return wanted
    for c in view:
        if any(w in c.lower() for w in AMOUNT_WORDS):
            return c
    return next(iter(view), None)


def _numeric_view(df):
    """Every column as Float64 where it parses: numeric columns as they are, string
    columns cast non-strictly after stripping thousands separators and currency marks.
    Returns {column: (series, parsed_share)} for columns that parse on more than half of
    their non-empty values: a text column (names, codes) parses on none, and a numeric
    column with a repeated header or a note inside the block parses on all but those
    rows, which `find_suspects` names."""
    pl = _pl()
    out = {}
    for c, t in df.schema.items():
        if t.is_numeric():
            out[c] = (df[c].cast(pl.Float64), 1.0)
            continue
        if t != pl.String:
            continue
        raw = df[c].str.strip_chars()
        nonempty = raw.filter(raw.is_not_null() & (raw != ""))
        if nonempty.len() == 0:
            continue
        cleaned = raw.str.replace_all(r"[,$€£\s]", "").str.replace_all(r"^\((.*)\)$", "-$1")
        parsed = cleaned.cast(pl.Float64, strict=False)
        share = parsed.filter(raw.is_not_null() & (raw != "")).is_not_null().sum() / nonempty.len()
        if share > 0.5:
            out[c] = (parsed, float(share))
    return out


def find_suspects(df, header: list[str]) -> list[dict]:
    """Rows inside a block that do not look like data. Each is
    {"row": n (1-based in the block), "reason": ..., "values": [first fields]}."""
    pl = _pl()
    if df.height < 2:
        return []
    reasons: dict[int, list[str]] = {}
    str_cols = [c for c, t in df.schema.items() if t == pl.String]
    first_text = str_cols[0] if str_cols else None
    # 1. a repeated header: every string column carries its own header name
    if str_cols:
        mask = None
        for c in str_cols[:4]:
            m = df[c].str.strip_chars().str.to_lowercase() == c.strip().lower()
            mask = m if mask is None else (mask & m)
        for i in mask.arg_true().to_list():
            reasons.setdefault(i, []).append("a repeated header line (a paged export)")
    # 2. text inside a numeric column
    view = _numeric_view(df)
    for c, (parsed, share) in view.items():
        if share >= 1.0 or df.schema[c].is_numeric():
            continue
        raw = df[c].str.strip_chars()
        bad = (parsed.is_null() & raw.is_not_null() & (raw != "")).arg_true().to_list()
        for i in bad[:SUSPECTS_MAX]:
            reasons.setdefault(i, []).append(f"text in the numeric column `{c}` "
                                             f"({share:.0%} of it parses as a number)")
    # 3. a total or subtotal row: amounts equal the running sum of the rows above it
    #    since the last such row, over at least three rows
    labels = df[first_text].str.strip_chars().fill_null("") if first_text else None
    sums: dict[int, int] = {}
    for c, (parsed, _) in view.items():
        vals = parsed.fill_null(0.0).to_list()
        run, since = 0.0, 0
        for i, v in enumerate(vals):
            if since >= 3 and abs(run) > 0.005 and abs(v - run) <= 0.005 + abs(run) * 1e-9:
                sums[i] = sums.get(i, 0) + 1
                run, since = 0.0, 0
                continue
            run += v
            since += 1
    for i, n in sums.items():
        labelled = bool(labels is not None and TOTAL_WORDS.search(labels[i] or ""))
        if n >= 2 or labelled:
            reasons.setdefault(i, []).append(
                f"a total row: {n} amount column(s) equal the sum of the rows above it"
                + (f"; labelled `{labels[i]}`" if labelled else ""))
    if labels is not None:
        for i in labels.str.contains(TOTAL_WORDS.pattern).arg_true().to_list():
            if i not in reasons:
                reasons.setdefault(i, []).append(f"labelled `{labels[i]}` in `{first_text}`")
    out = []
    for i in sorted(reasons)[:SUSPECTS_MAX]:
        vals = [str(df[c][i]) for c in df.columns[:4]]
        out.append({"row": i + 1, "reason": "; ".join(reasons[i]), "values": vals})
    return out


def profile_spans(run_dir: pathlib.Path, source: str, rel_file: str) -> list[dict]:
    """The planner's whole-block spans of this file, from
    workpapers/evidence-profile-<source>.yaml (check-plan SKILL.md § 2); [] if none."""
    p = run_dir / "workpapers" / f"evidence-profile-{source}.yaml"
    if not p.is_file():
        return []
    try:
        import yaml
        entries = yaml.safe_load(p.read_text()) or []
    except Exception:
        return []
    if not isinstance(entries, list):
        return []
    want = pathlib.PurePath(rel_file).as_posix()
    return [e for e in entries if isinstance(e, dict) and e.get("kind") == "span"
            and pathlib.PurePath(str(e.get("file", ""))).as_posix() == want
            and str(e.get("filter", "")).strip().lower().startswith("none")
            and isinstance(e.get("control_total"), dict)]


def profile_check(df, spans: list[dict]) -> dict | None:
    """Compare the block's sum of the profile span's control column to the span's
    control_total. The first comparable span decides; None when none is comparable."""
    for e in spans:
        col = (e.get("control_total") or {}).get("column")
        theirs = (e.get("control_total") or {}).get("value")
        if col not in df.columns or not isinstance(theirs, (int, float)):
            continue
        view = _numeric_view(df.select(col))
        if col not in view:
            continue
        ours = round(float(view[col][0].fill_null(0.0).sum()), 2)
        return {"citation": e.get("id"), "column": col, "profile": float(theirs),
                "cache": ours, "agrees": abs(ours - float(theirs)) <= 0.01}
    return None


def read_overrides(run_dir: pathlib.Path) -> dict:
    p = run_dir / CACHE_DIR / OVERRIDES
    return json.loads(p.read_text()) if p.is_file() else {}


def write_overrides(run_dir: pathlib.Path, new: dict) -> dict:
    """Merge `new` ({id: {spec keys}}) into cache/overrides.json; returns the whole."""
    cur = read_overrides(run_dir)
    for fid, keys in new.items():
        if not isinstance(keys, dict):
            raise ValueError(f"override for {fid!r} is not an object of spec keys")
        cur.setdefault(fid, {}).update(keys)
    p = run_dir / CACHE_DIR / OVERRIDES
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cur, indent=1) + "\n")
    tmp.replace(p)
    return cur


def apply_overrides(files: list[dict], overrides: dict) -> list[dict]:
    out = []
    for f in files:
        fid = (f or {}).get("id")
        if fid in overrides:
            out.append({**f, **overrides[fid], "_overrides": overrides[fid]})
        else:
            out.append(f)
    return out


def reperform(run_dir, file_id: str) -> dict:
    """Re-read the source block as the manifest anchors it and compare: sha256 of the
    file, the row count and the control total. `agrees` is False on any difference —
    a cache defect the reader records (agents/worker.md § Your procedure)."""
    run_dir = pathlib.Path(run_dir)
    e = entry(run_dir, file_id)
    path = pathlib.Path(e["path"])
    if not path.is_file():
        return {"id": file_id, "agrees": False, "why": f"source missing: {path}"}
    digest = sha256(path)
    spec = {"header_row": e["header_row"], "rows": e.get("rows"), "sheet": e.get("sheet"),
            "delimiter": e.get("delimiter")}
    try:
        df, _ = load_frame(path, spec)
    except Exception as exc:
        return {"id": file_id, "agrees": False, "why": f"source no longer reads: {exc}"}
    col = (e.get("control_total") or {}).get("column")
    ours = control_value(df, col if col in df.columns else None)
    out = {"id": file_id, "sha256_agrees": digest == e.get("sha256"),
           "row_count": {"manifest": e["row_count"], "source": df.height},
           "control_total": {"column": col, "manifest": (e.get("control_total") or {}).get("value"),
                             "source": ours}}
    out["agrees"] = (out["sha256_agrees"] and df.height == e["row_count"]
                     and abs(float(ours) - float(out["control_total"]["manifest"] or 0)) <= 0.01)
    if not out["agrees"]:
        out["why"] = ("the source file changed" if not out["sha256_agrees"] else
                      "the block re-read from the source does not match the cache")
    return out


def control_value(df, col: str | None) -> float | int:
    """The sum of `col` over the frame, parsed as `_numeric_view` parses it; the row
    count when `col` is None."""
    if col is None:
        return df.height
    view = _numeric_view(df.select(col))
    if col not in view:
        return 0.0
    v = view[col][0].fill_null(0.0).sum()
    return round(float(v), 2) if v is not None else 0.0


# ---------------------------------------------------------------- the run

def load_run(run_dir: pathlib.Path) -> dict:
    return json.loads((run_dir / "run.json").read_text())


def sources_by_id(run: dict) -> dict[str, dict]:
    return {s["id"]: s for s in run.get("sources", [])}


def resolve_path(spec: dict, sources: dict[str, dict]) -> tuple[pathlib.Path, str, str]:
    """(absolute path, source id, path relative to that source's registered path)."""
    raw = pathlib.Path(str(spec.get("path") or ""))
    if not str(raw):
        raise ValueError("no `path`")
    sid = spec.get("source")
    if raw.is_absolute():
        p = raw
        if not sid:
            for s in sources.values():
                root = pathlib.Path(s["path"])
                if p == root or root in p.parents:
                    sid = s["id"]
                    break
        if not sid:
            raise ValueError(f"{p} lies under no registered source; name `source`")
        root = pathlib.Path(sources[sid]["path"])
    else:
        if not sid:
            raise ValueError(f"a relative `path` needs `source`: {raw}")
        if sid not in sources:
            raise ValueError(f"source {sid!r} is not registered in run.json")
        root = pathlib.Path(sources[sid]["path"])
        p = root / raw
    if not p.is_file():
        raise ValueError(f"not a file: {p}")
    try:
        rel = str(p.relative_to(root)) if root.is_dir() else p.name
    except ValueError:
        rel = str(p)
    return p, sid, rel


def step_files(run_dir: pathlib.Path, run: dict, step_id: str) -> list[dict]:
    pb = (run.get("playbook") or {}).get("path") or (run.get("plan") or {}).get("playbook")
    if not pb:
        raise ValueError("run.json names no playbook definition (playbook.path / plan.playbook)")
    definition = json.loads(pathlib.Path(pb).read_text())
    for st in definition.get("steps", []):
        if st.get("id") == step_id:
            files = (st.get("params") or {}).get("files")
            if not isinstance(files, list) or not files:
                raise ValueError(f"step {step_id} declares no `params.files`")
            return files
    raise ValueError(f"step {step_id!r} is not in {pb}")


def read_manifest(run_dir: pathlib.Path) -> dict:
    p = run_dir / CACHE_DIR / MANIFEST
    if p.is_file():
        return json.loads(p.read_text())
    return {"schema": SCHEMA, "run_dir": str(run_dir), "written_at": None, "files": []}


def write_manifest(run_dir: pathlib.Path, man: dict) -> pathlib.Path:
    p = run_dir / CACHE_DIR / MANIFEST
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(p)
    return p


def extract_one(run_dir: pathlib.Path, spec: dict, sources: dict[str, dict]) -> dict:
    pl = _pl()
    fid = str(spec.get("id") or "")
    if not SLUG.match(fid):
        raise ValueError(f"id {fid!r} is not a slug")
    path, sid, rel = resolve_path(spec, sources)
    df, facts = load_frame(path, spec)
    if df.width == 0:
        raise ValueError("no columns read")
    control = pick_control(df, spec.get("control"))
    out = run_dir / CACHE_DIR / f"{fid}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".parquet.tmp")
    df.write_parquet(tmp)
    tmp.replace(out)
    back = pl.read_parquet(out)                      # the manifest states what is on disk
    st = path.stat()
    suspects = find_suspects(back, list(back.columns))
    check = profile_check(back, profile_spans(run_dir, sid, rel))
    entry_ = {
        "id": fid, "source": sid, "path": str(path), "file": rel,
        "file_role": spec.get("file_role"),
        "size_bytes": st.st_size, "mtime": _iso(st.st_mtime), "sha256": sha256(path),
        "sheet": facts["sheet"], "header_row": facts["header_row"],
        "rows": spec.get("rows"),
        "delimiter": facts["delimiter"], "preamble": facts["preamble"],
        "trailing": facts.get("trailing"),
        "columns": [{"name": c, "at": col_letter(i + 1), "dtype": str(t)}
                    for i, (c, t) in enumerate(back.schema.items())],
        "row_count": back.height,
        "control_total": {"column": control, "value": control_value(back, control)},
        "parquet": f"{CACHE_DIR}/{fid}.parquet",
        "suspects": suspects,
        "profile_check": check,
        "header_check": header_check(list(back.columns), facts),
        "overrides": spec.get("_overrides"),
        "read_at": _now(),
    }
    return entry_


def extract(run_dir: pathlib.Path, files: list[dict], step: str | None = None) -> tuple[list[dict], list[str]]:
    """Cache every spec; (entries landed, problem lines). A problem line is `FAILED:`
    (not cached), `HEADER:` (cached, but the row read as the header may not be one) or
    `DISAGREES:` (cached, but the profile's read of the file differs)."""
    run = load_run(run_dir)
    sources = sources_by_id(run)
    man = read_manifest(run_dir)
    kept = {e["id"]: e for e in man.get("files", [])}
    done, failed = [], []
    for spec in apply_overrides(files, read_overrides(run_dir)):
        fid = str((spec or {}).get("id") or "?")
        try:
            entry_ = extract_one(run_dir, spec, sources)
        except Exception as exc:                      # one bad file never stops the rest
            failed.append(f"FAILED: {fid} — {exc}")
            continue
        if step:
            entry_["step"] = step
        kept[entry_["id"]] = entry_
        done.append(entry_)
        hc = entry_.get("header_check")
        if hc:
            failed.append(header_line(fid, hc))
        pc = entry_.get("profile_check")
        if pc and not pc["agrees"]:
            failed.append(f"DISAGREES: {fid} — {pc['column']} sums to {pc['cache']:,} in the "
                          f"cache; the plan's {pc['citation']} recorded {pc['profile']:,}")
    man["files"] = [kept[k] for k in sorted(kept)]
    man["written_at"] = _now()
    write_manifest(run_dir, man)
    return done, failed


# ---------------------------------------------------------------- the readers

def manifest(run_dir) -> dict:
    return read_manifest(pathlib.Path(run_dir))


def entry(run_dir, file_id: str) -> dict:
    for e in manifest(run_dir).get("files", []):
        if e["id"] == file_id:
            return e
    raise KeyError(f"{file_id!r} is not in {pathlib.Path(run_dir) / CACHE_DIR / MANIFEST}")


def read(run_dir, file_id: str):
    """The cached file as a polars DataFrame, typed as the manifest states."""
    return _pl().read_parquet(pathlib.Path(run_dir) / entry(run_dir, file_id)["parquet"])


def scan(run_dir, file_id: str):
    """The cached file as a polars LazyFrame — for a large file read in part."""
    return _pl().scan_parquet(pathlib.Path(run_dir) / entry(run_dir, file_id)["parquet"])


def header_line(fid: str, hc: dict) -> str:
    why = []
    if hc["detected"] != hc["given"]:
        why.append(f"it sits inside a run of records of its width that starts at line "
                   f"{hc['detected']}")
    if hc["data_like"]:
        why.append(f"header names read as values: {', '.join(map(str, hc['data_like']))}")
    return f"HEADER: {fid} — read at line {hc['given']} as the spec gives it; " + "; ".join(why)


def describe(e: dict, checks: bool = True) -> str:
    ct = e["control_total"]
    cols = ", ".join(f"{c['name']}:{c['dtype']}" for c in e["columns"])
    line = (f"{e['id']}  rows={e['row_count']:,}  control {ct['column']}={ct['value']:,}  "
            f"header_row={e['header_row']}  [{cols}]")
    t = e.get("trailing")
    if t:
        line += (f"\nTRAILING: {e['id']} — {t['lines']} non-blank line(s) at lines "
                 f"{t['from_line']}..{t['to_line']} below the block were not read: a second "
                 f"table, a totals section or a footer - name it as its own entry with "
                 f"header_row and rows, or record why it is not a table")
    for su in e.get("suspects") or []:
        line += (f"\nSUSPECT: {e['id']} row {su['row']} (line {e['header_row'] + su['row']}) "
                 f"— {su['reason']}: {su['values']}")
    if checks and e.get("header_check"):
        line += "\n" + header_line(e["id"], e["header_check"])
    pc = e.get("profile_check")
    if pc and (checks or pc["agrees"]):
        line += (f"\n{'AGREES' if pc['agrees'] else 'DISAGREES'}: {e['id']} — {pc['column']} "
                 f"{pc['cache']:,} against the plan's {pc['citation']} {pc['profile']:,}")
    if e.get("overrides"):
        line += f"\nOVERRIDDEN: {e['id']} — {json.dumps(e['overrides'])}"
    return line


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=pathlib.Path)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--step", help="the definition step whose params.files to extract")
    g.add_argument("--files", help="a JSON list of file specs, or @<path> to one")
    g.add_argument("--show", action="store_true", help="print the manifest")
    g.add_argument("--reperform", metavar="ID",
                   help="re-read ID's source block and compare it to the manifest")
    ap.add_argument("--override", help="JSON {\"<id>\": {<spec keys>}} merged into "
                                       "cache/overrides.json before extracting")
    a = ap.parse_args()
    run_dir = a.run_dir.resolve()
    if not (run_dir / "run.json").is_file():
        print(f"{run_dir}: no run.json", file=sys.stderr)
        return 2
    if a.show:
        for e in read_manifest(run_dir).get("files", []):
            print(describe(e))
        return 0
    if a.reperform:
        try:
            r = reperform(run_dir, a.reperform)
        except KeyError as exc:
            print(f"extract.py: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(r, indent=1))
        return 0 if r["agrees"] else 1
    if a.override:
        try:
            write_overrides(run_dir, json.loads(a.override))
        except (ValueError, OSError) as exc:
            print(f"extract.py: --override: {exc}", file=sys.stderr)
            return 2
    try:
        if a.step:
            files = step_files(run_dir, load_run(run_dir), a.step)
        else:
            text = pathlib.Path(a.files[1:]).read_text() if a.files.startswith("@") else a.files
            files = json.loads(text)
            if not isinstance(files, list) or not files:
                raise ValueError("--files is a non-empty JSON list")
    except (ValueError, OSError) as exc:
        print(f"extract.py: {exc}", file=sys.stderr)
        return 2
    done, failed = extract(run_dir, files, a.step)
    for e in done:
        print(describe(e, checks=False))
    for line in failed:
        print(line)
    print(f"manifest: {run_dir / CACHE_DIR / MANIFEST}  ({len(done)} file(s) cached, "
          f"{len(failed)} failed)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
