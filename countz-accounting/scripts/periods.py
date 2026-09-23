#!/usr/bin/env python3
"""The run's period set (DOCTRINE.md § Periods, EVIDENCE.md § 0) as one importable module.

Every step that computes by period imports this rather than typing its own windows,
labels and fiscal-year rule:

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from periods import Periods, fy_of, month_key, month_label, month_seq

    P = Periods.load(RUN, "a5_bridge_retention")   # params.columns + params.fiscal_year_end
    for p in P:                       # in the column order the plan declared
        p.key                         # "fy2025" | "2025-12" | "ltm_2025-12" | "2026q1": the id slug
        p.kind                        # "fy" | "month" | "ltm" | "quarter"
        p.start, p.end                # first and last day, datetime.date
        p.months                      # ("2024-10", ..., "2025-09")
        p.label()                     # "FY2025" | "December 2025" | "LTM December 2025" | "Q1 FY2026"
        p.label("snapshot")           # a balance at the end: "As of December 2025" (FY keeps "FY2025")
        p.span_label                  # "October 2024–September 2025"
        p.end_long                    # "30 September 2025"
        rows.filter(p.mask(pl.col("invoice_date")))
    P["fy2025"], P.keys, P.labels("flow"), P.fy_of(pl.col("invoice_date"))

The slug is the id segment (`F.a5.nrr.fy2025`); the label is display only and comes from
here, never typed. A column key outside the EVIDENCE.md § 0 grammar is refused.

Where the numbers come from: `params.columns` on the step (the plan's period set, in
order) and `params.fiscal_year_end` (`"MM-DD"`, the last day of the fiscal year's final
month, e.g. `"09-30"`), read from the step's own params, else from any check in
`run.json` that declares it. Pass either explicitly to override. A fiscal year is named by
the calendar year it ends in: with a 30 September year end, FY2025 runs 1 October 2024 to
30 September 2025, and `2026q1` is October–December 2025. A 52/53-week year is not a
month-end year; pass explicit windows for it rather than this module.

Run with no arguments to self-check. Stdlib only, except `mask()` and a `pl.Expr`
passed to `fy_of()` / `month_key()`, which use polars.
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import pathlib
import re

__all__ = ["Period", "Periods", "fy_of", "fy_label", "month_key", "month_label",
           "month_seq", "parse_fiscal_year_end"]

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
DASH = "–"   # en dash for a range of months

KEY_FY = re.compile(r"^fy(\d{4})$")
KEY_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
KEY_LTM = re.compile(r"^ltm_(\d{4})-(\d{2})$")
KEY_QUARTER = re.compile(r"^(\d{4})q([1-4])$")
GRAMMAR = ("a fiscal year `fy2025`, a month `2025-12`, an LTM column by its end month "
           "`ltm_2025-12`, a fiscal quarter `2026q1` (EVIDENCE.md § 0)")


# --- months ------------------------------------------------------------------------------
def _ym(x) -> tuple[int, int]:
    if isinstance(x, (dt.date, dt.datetime)):
        return x.year, x.month
    if isinstance(x, str):
        m = re.match(r"^(\d{4})-(\d{2})(?:-\d{2})?(?:[T ].*)?$", x.strip())
        if m and 1 <= int(m.group(2)) <= 12:
            return int(m.group(1)), int(m.group(2))
    if isinstance(x, tuple) and len(x) == 2:
        return int(x[0]), int(x[1])
    raise ValueError(f"not a month: {x!r} (a date, `YYYY-MM` or `YYYY-MM-DD`)")


def _add(y: int, m: int, n: int) -> tuple[int, int]:
    i = y * 12 + (m - 1) + n
    return i // 12, i % 12 + 1


def _last_day(y: int, m: int) -> dt.date:
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def month_key(x):
    """`"YYYY-MM"` for a date, a datetime, `"YYYY-MM"` or `"YYYY-MM-DD"`; for a polars
    date or datetime expression, the expression of that string."""
    if _is_expr(x):
        return x.dt.strftime("%Y-%m")
    y, m = _ym(x)
    return f"{y:04d}-{m:02d}"


def month_label(x) -> str:
    """`"December 2025"` — DOCTRINE.md § Number conventions, never a system date key."""
    y, m = _ym(x)
    return f"{MONTHS[m - 1]} {y}"


def month_seq(first, last) -> list[str]:
    """Every `"YYYY-MM"` from `first` to `last`, both included."""
    y, m = _ym(first)
    ly, lm = _ym(last)
    if (y, m) > (ly, lm):
        raise ValueError(f"month_seq: {month_key(first)} is after {month_key(last)}")
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        y, m = _add(y, m, 1)
    return out


def _span_label(months: tuple[str, ...]) -> str:
    fy, fm = _ym(months[0])
    ly, lm = _ym(months[-1])
    if (fy, fm) == (ly, lm):
        return month_label(months[0])
    if fy == ly:
        return f"{MONTHS[fm - 1]}{DASH}{MONTHS[lm - 1]} {ly}"
    return f"{MONTHS[fm - 1]} {fy}{DASH}{MONTHS[lm - 1]} {ly}"


# --- fiscal years --------------------------------------------------------------------------
def parse_fiscal_year_end(v) -> int:
    """The fiscal year's final month (1-12) from `"MM-DD"` (`"09-30"`), `"--09-30"`, a
    month name (`"September"`) or a month number. The day, when given, must end that
    month: a year ending mid-month is a 52/53-week year this module does not model."""
    if isinstance(v, bool):
        raise ValueError(f"fiscal_year_end {v!r}")
    if isinstance(v, int):
        if 1 <= v <= 12:
            return v
        raise ValueError(f"fiscal_year_end month {v} is not 1-12")
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"fiscal_year_end {v!r}: write it `\"MM-DD\"`, e.g. `\"09-30\"`")
    s = v.strip().lstrip("-")
    for i, name in enumerate(MONTHS, 1):
        if s.lower() in (name.lower(), name[:3].lower()):
            return i
    m = re.fullmatch(r"(\d{1,2})(?:-(\d{1,2}))?", s)
    if not m or not 1 <= int(m.group(1)) <= 12:
        raise ValueError(f"fiscal_year_end {v!r}: write it `\"MM-DD\"`, e.g. `\"09-30\"`")
    month = int(m.group(1))
    if m.group(2):
        day = int(m.group(2))
        last = 29 if month == 2 else calendar.monthrange(2001, month)[1]
        if day != last and not (month == 2 and day == 28):
            raise ValueError(f"fiscal_year_end {v!r} does not end its month: a 52/53-week "
                             f"year is not modelled here - pass explicit windows")
    return month


def _is_expr(x) -> bool:
    return type(x).__name__ == "Expr" and type(x).__module__.startswith("polars")


def fy_of(x, fiscal_year_end):
    """The fiscal-year slug (`"fy2025"`) a date or month falls in. `x` is a date, a
    datetime, `"YYYY-MM"`, `"YYYY-MM-DD"`, or a polars date/datetime expression (which
    returns the expression of the slug)."""
    end = parse_fiscal_year_end(fiscal_year_end)
    if _is_expr(x):
        import polars as pl
        year = x.dt.year()
        fy = pl.when(x.dt.month() > end).then(year + 1).otherwise(year)
        return pl.lit("fy") + fy.cast(pl.Utf8)
    y, m = _ym(x)
    return f"fy{y + 1 if m > end else y}"


def fy_label(slug: str) -> str:
    """`"fy2025"` -> `"FY2025"`."""
    m = KEY_FY.match(slug)
    if not m:
        raise ValueError(f"not a fiscal-year slug: {slug!r}")
    return f"FY{m.group(1)}"


# --- one period ----------------------------------------------------------------------------
class Period:
    """One column of the period set. Built by `Period.parse(key, fiscal_year_end)`."""

    __slots__ = ("key", "kind", "months", "fy_end_month", "fiscal_year", "quarter")

    def __init__(self, key, kind, months, fy_end_month, fiscal_year=None, quarter=None):
        self.key, self.kind, self.months = key, kind, tuple(months)
        self.fy_end_month, self.fiscal_year, self.quarter = fy_end_month, fiscal_year, quarter

    @classmethod
    def parse(cls, key: str, fiscal_year_end=None) -> "Period":
        end_m = parse_fiscal_year_end(fiscal_year_end) if fiscal_year_end is not None else None
        if not isinstance(key, str):
            raise ValueError(f"period key {key!r}: {GRAMMAR}")
        if m := KEY_FY.match(key):
            fy = int(m.group(1))
            if end_m is None:
                raise ValueError(f"period `{key}` needs the fiscal year end "
                                 f"(params.fiscal_year_end, e.g. \"09-30\")")
            last = (fy, end_m)
            return cls(key, "fy", month_seq(_add(*last, -11), last), end_m, fy)
        if m := KEY_QUARTER.match(key):
            fy, q = int(m.group(1)), int(m.group(2))
            if end_m is None:
                raise ValueError(f"period `{key}` is a fiscal quarter and needs the fiscal "
                                 f"year end (params.fiscal_year_end, e.g. \"09-30\")")
            first = _add(fy, end_m, -11 + 3 * (q - 1))
            return cls(key, "quarter", month_seq(first, _add(*first, 2)), end_m, fy, q)
        if m := KEY_LTM.match(key):
            last = (int(m.group(1)), int(m.group(2)))
            _check_month(key, last)
            return cls(key, "ltm", month_seq(_add(*last, -11), last), end_m)
        if m := KEY_MONTH.match(key):
            ym = (int(m.group(1)), int(m.group(2)))
            _check_month(key, ym)
            return cls(key, "month", [month_key(ym)], end_m)
        raise ValueError(f"period key {key!r} is outside the grammar: {GRAMMAR}; the "
                         f"display label is carried by `label`, never by the key")

    @property
    def start(self) -> dt.date:
        y, m = _ym(self.months[0])
        return dt.date(y, m, 1)

    @property
    def end(self) -> dt.date:
        return _last_day(*_ym(self.months[-1]))

    @property
    def end_month(self) -> str:
        return self.months[-1]

    @property
    def end_long(self) -> str:
        """`"30 September 2025"`."""
        e = self.end
        return f"{e.day} {MONTHS[e.month - 1]} {e.year}"

    @property
    def span_label(self) -> str:
        """The months covered: `"October 2024–September 2025"`, `"October–December 2025"`."""
        return _span_label(self.months)

    def label(self, basis: str = "flow") -> str:
        """The column heading. `flow` for activity over the period (revenue, billings,
        movements); `snapshot` for a balance at its end (ARR, a receivable), which
        DOCTRINE.md § Periods labels `As of <end month>` — except a fiscal-year column,
        which keeps `FY2025` for both."""
        if basis not in ("flow", "snapshot"):
            raise ValueError(f"basis {basis!r}: `flow` or `snapshot`")
        if self.kind == "fy":
            return f"FY{self.fiscal_year}"
        if basis == "snapshot":
            return f"As of {month_label(self.end_month)}"
        if self.kind == "month":
            return month_label(self.end_month)
        if self.kind == "ltm":
            return f"LTM {month_label(self.end_month)}"
        return f"Q{self.quarter} FY{self.fiscal_year}"

    def contains(self, x) -> bool:
        return month_key(x) in self.months

    def mask(self, expr):
        """A polars boolean expression: the date or datetime `expr` falls in the period."""
        import polars as pl
        d = expr.cast(pl.Date)
        return (d >= pl.lit(self.start)) & (d <= pl.lit(self.end))

    def __repr__(self) -> str:
        return f"Period({self.key!r}, {self.start}..{self.end})"


def _check_month(key: str, ym: tuple[int, int]) -> None:
    if not 1 <= ym[1] <= 12:
        raise ValueError(f"period key {key!r}: month {ym[1]:02d} is not 01-12")


# --- the period set ----------------------------------------------------------------------
class Periods:
    """The ordered period set a step reports on."""

    def __init__(self, keys, fiscal_year_end=None):
        keys = list(keys)
        if not keys:
            raise ValueError("an empty period set")
        dup = sorted({k for k in keys if keys.count(k) > 1})
        if dup:
            raise ValueError(f"period set repeats {dup}")
        self.fiscal_year_end = fiscal_year_end
        self._p = [Period.parse(k, fiscal_year_end) for k in keys]
        self._by = {p.key: p for p in self._p}

    @classmethod
    def load(cls, run_dir, check: str | None = None, *, columns=None,
             fiscal_year_end=None) -> "Periods":
        """The period set from `run.json`: `columns` and `fiscal_year_end` from the
        check's params, `fiscal_year_end` else from any check that declares it."""
        run_dir = pathlib.Path(run_dir)
        checks = []
        rj = run_dir / "run.json"
        if rj.is_file():
            checks = json.loads(rj.read_text()).get("checks") or []
        own = next((c for c in checks if c.get("id") == check), None) if check else None
        if check and own is None and (columns is None or fiscal_year_end is None):
            raise ValueError(f"check {check!r} is not registered in {rj}")
        params = (own or {}).get("params") or {}
        if columns is None:
            columns = params.get("columns")
            if not columns:
                raise ValueError(f"check {check!r} declares no params.columns - the plan's "
                                 f"period set; pass columns=[...]")
        if fiscal_year_end is None:
            fiscal_year_end = params.get("fiscal_year_end")
        if fiscal_year_end is None:
            declared = {c["params"]["fiscal_year_end"] for c in checks
                        if (c.get("params") or {}).get("fiscal_year_end")}
            if len(declared) > 1:
                raise ValueError(f"checks disagree on params.fiscal_year_end: "
                                 f"{sorted(declared)}")
            fiscal_year_end = declared.pop() if declared else None
        return cls(columns, fiscal_year_end)

    def __iter__(self):
        return iter(self._p)

    def __len__(self) -> int:
        return len(self._p)

    def __getitem__(self, k) -> Period:
        if isinstance(k, int):
            return self._p[k]
        if k not in self._by:
            raise KeyError(f"period {k!r} is not in the set {self.keys}")
        return self._by[k]

    def __contains__(self, k) -> bool:
        return k in self._by

    @property
    def keys(self) -> list[str]:
        return [p.key for p in self._p]

    def of_kind(self, *kinds: str) -> list[Period]:
        return [p for p in self._p if p.kind in kinds]

    def labels(self, basis: str = "flow") -> dict[str, str]:
        return {p.key: p.label(basis) for p in self._p}

    def fy_of(self, x):
        if self.fiscal_year_end is None:
            raise ValueError("no fiscal year end declared (params.fiscal_year_end)")
        return fy_of(x, self.fiscal_year_end)

    @property
    def months(self) -> list[str]:
        """Every month any column covers, in calendar order."""
        return sorted({m for p in self._p for m in p.months})

    def __repr__(self) -> str:
        return f"Periods({self.keys}, fiscal_year_end={self.fiscal_year_end!r})"


# --- self-check ----------------------------------------------------------------------------
def _selfcheck() -> int:
    P = Periods(["fy2023", "fy2024", "fy2025", "2025-12", "ltm_2025-12", "2026q1"], "09-30")
    fy25, dec, ltm, q1 = P["fy2025"], P["2025-12"], P["ltm_2025-12"], P["2026q1"]
    cal = Periods(["fy2025", "2025q4"], "12-31")
    checks = [
        (fy25.start, dt.date(2024, 10, 1)), (fy25.end, dt.date(2025, 9, 30)),
        (len(fy25.months), 12), (fy25.label(), "FY2025"), (fy25.label("snapshot"), "FY2025"),
        (fy25.span_label, f"October 2024{DASH}September 2025"),
        (fy25.end_long, "30 September 2025"),
        (dec.label(), "December 2025"), (dec.label("snapshot"), "As of December 2025"),
        (ltm.label(), "LTM December 2025"), (ltm.months[0], "2025-01"),
        (q1.months, ("2025-10", "2025-11", "2025-12")), (q1.label(), "Q1 FY2026"),
        (q1.span_label, f"October{DASH}December 2025"),
        (fy_of("2025-09-30", "09-30"), "fy2025"), (fy_of(dt.date(2025, 10, 1), 9), "fy2026"),
        (fy_of("2025-12", "12-31"), "fy2025"), (cal["fy2025"].start, dt.date(2025, 1, 1)),
        (cal["2025q4"].months, ("2025-10", "2025-11", "2025-12")),
        (parse_fiscal_year_end("February"), 2), (parse_fiscal_year_end("02-29"), 2),
        (month_seq("2025-11", "2026-02"), ["2025-11", "2025-12", "2026-01", "2026-02"]),
        (P.months[0], "2022-10"), (P.months[-1], "2025-12"),
        (P.labels("snapshot")["2025-12"], "As of December 2025"),
    ]
    bad = [f"got {got!r}, want {want!r}" for got, want in checks if got != want]
    for key, fye in (("FY2025", "09-30"), ("m9_2025-09", "09-30"), ("fy2025", None),
                     ("2025-13", None), ("fy2025", "09-15")):
        try:
            Period.parse(key, fye)
            bad.append(f"accepted {key!r} with fiscal_year_end {fye!r}")
        except ValueError:
            pass
    try:
        import polars as pl
        df = pl.DataFrame({"d": [dt.date(2024, 9, 30), dt.date(2024, 10, 1),
                                 dt.date(2025, 12, 31)]})
        got = df.select(fy_of(pl.col("d"), "09-30").alias("fy"),
                        fy25.mask(pl.col("d")).alias("in"),
                        month_key(pl.col("d")).alias("m"))
        if got["fy"].to_list() != ["fy2024", "fy2025", "fy2026"]:
            bad.append(f"fy_of expr: {got['fy'].to_list()}")
        if got["in"].to_list() != [False, True, False]:
            bad.append(f"mask: {got['in'].to_list()}")
        if got["m"].to_list() != ["2024-09", "2024-10", "2025-12"]:
            bad.append(f"month_key expr: {got['m'].to_list()}")
    except ImportError:
        pass
    for b in bad:
        print(f"periods: {b}")
    print("periods: ok" if not bad else "periods: self-check FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
