#!/usr/bin/env python3
"""The run's period set (DOCTRINE.md § Periods, EVIDENCE.md § 0) as one importable module.

Every step that computes by period imports this rather than typing its own windows,
labels and fiscal-year rule:

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from periods import Periods, fy_of, month_key, month_label, month_seq, cutoff_spec

    P = Periods.load(RUN, "a5_bridge_retention")   # params.columns + params.fiscal_year_end
    for p in P:                       # in the column order the plan declared
        p.key                         # "fy2025" | "2026q1" | "fy2025h1" | "fy2025p03" |
                                      # "2025-12" | "ltm_2025-12" | "ytd_2025-12" |
                                      # "w2025-08-16_2025-09-30"
        p.kind                        # "fy" | "quarter" | "half" | "fperiod" | "month" |
                                      # "ltm" | "ytd" | "window"
        p.start, p.end                # first and last day, datetime.date
        p.months                      # its calendar months ("2024-10", ...); refused unless
                                      # it runs first-of-month to month-end (`p.aligned`)
        p.label()                     # "FY2025" | "December 2025" | "LTM December 2025" | "Q1 FY2026"
        p.label("snapshot")           # a balance at the end: "As of December 2025" (FY keeps "FY2025")
        p.span_label                  # "October 2024–September 2025"
        p.end_long                    # "September 30, 2025"
        rows.filter(p.mask(pl.col("invoice_date")))
        w = p.window(5, 5, "business", ["2025-10-13"], ["sat", "sun"])   # a cutoff window
    P["fy2025"], P.keys, P.labels("flow"), P.fy_of(pl.col("invoice_date"))   # local date

The slug is the id segment (`F.a5.nrr.fy2025`); the label is display only and comes from
here (its words and date forms from scripts/style.py), never typed. A column key outside
the EVIDENCE.md § 0 grammar (ASCII digits, a month 01-12, nothing after the key) is refused.

**Where the numbers come from.** `params.columns` on the step (the plan's period set, in
order), `params.fiscal_year_end`, and optionally `params.timezone` (an IANA zone, the
entity's local time) and `params.column_labels` (`{key: label}`, a client's own heading
for a column), read from the step's own params. A step that declares no year end takes the
run's: every check's one calendar, or their `by_entity` maps merged entity by entity (two
readings of one entity's calendar, or the two forms mixed, are refused). A step that
declares no zone takes it from the checks that share an entity with it, when the checks
declaring a zone cover all of its entities (on a run of one entity, from any check);
otherwise it has none, and a timezone-aware column is refused. Pass any of them
explicitly to override.

**The fiscal calendar** (`params.fiscal_year_end`) is one of:

- `"MM-DD"` (`"09-30"`), a month name or number: every fiscal year is twelve calendar
  months ending on that month's last day, named by the year it ends in (FY2025 runs
  October 1, 2024 to September 30, 2025; `2026q1` is October–December 2025).
- `{"years": [{"name", "start", "end", "label"?, "quarters"?, "halves"?, "periods"?}, ...]}`:
  any other calendar, as the dates the company's own documents state — never computed
  from a rule. A subdivision a column needs and the year does not declare is refused.
- `{"by_entity": {"us_parent": "12-31", "jp_sub": {"years": [...]}}}`: one calendar per
  entity. `Periods.load(..., entity="jp_sub")` selects one (or the step's single
  `params.entities` member); a fiscal column with no entity chosen is refused.

**Calendar-month keys.** `ltm_2025-12` is the twelve calendar months to December 2025 on
any calendar. `ytd_2025-12` runs from the fiscal year's start to that month's end, so it
is read on a `"MM-DD"` calendar only; on declared `years` it is refused (declare the
window `w<start>_<end>`). `fy_of("2025-09")` places a month in the one fiscal year that
holds all of it: a month a declared year boundary splits is refused (give a date).

**Timezones.** `mask()`, `fy_of()`, `month_key()` and `Period.contains()` reduce a datetime
(a column or a single value) to the entity's local date first. A timezone-aware one needs
`params.timezone`; a naive one is taken as local wall time unless `source_timezone=` says
what it is. Refused: a timezone-aware value with no declared zone (a UTC export would move a
23:30 posting on September 30 into October); a `source_timezone` on a value that carries
another zone; a naive wall time that never occurs in `source_timezone` (the
daylight-saving gap), or occurs twice there on two different local dates; a zone that is
not IANA. A column is a polars `Date` or `Datetime` (an all-null column reads as null
dates): a string, integer (`20250930`) or categorical column is refused - parse it first.

**Cutoff windows.** `cutoff_spec(params)` reads a cutoff step's `period_ends` (ISO dates),
`before` / `after` (days each side), `basis` (`calendar` | `business`), and for a
business basis `weekend` (the entity's non-working weekdays, required) and `holidays`
(ISO dates), accepting the legacy `period_end` + `window_days` as `period_ends=[period_end]`,
`before = after = window_days` (`basis` as declared, `calendar` by default). `window(end,
before, after, ...)` is one window, from `before` days before the end to `after` days after
it, the end included; `Period.window(...)` the window around a period's end.

Stdlib only, except `mask()`, `local_date()` and a
`pl.Expr` passed to `fy_of()` / `month_key()`, which use polars.
"""
from __future__ import annotations

import bisect
import calendar
import datetime as dt
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import style  # noqa: E402  sibling, stdlib: the date forms every label is written in

__all__ = ["Period", "Periods", "FiscalCalendar", "fy_of", "fy_label", "month_key",
           "local_date", "month_label", "month_seq", "parse_fiscal_year_end", "calendar_for",
           "calendars",
           "cutoff_spec", "window", "add_business_days", "needs_fiscal_year", "check_key"]

MONTHS = list(style.MONTHS)
DASH = "–"   # en dash for a range

# ASCII digits, and `\Z` so a trailing newline is not read as the end of the key.
KEY_FY = re.compile(r"^fy(\d{4})\Z", re.A)
KEY_MONTH = re.compile(r"^(\d{4})-(\d{2})\Z", re.A)
KEY_LTM = re.compile(r"^ltm_(\d{4})-(\d{2})\Z", re.A)
KEY_YTD = re.compile(r"^ytd_(\d{4})-(\d{2})\Z", re.A)
KEY_QUARTER = re.compile(r"^(\d{4})q([1-4])\Z", re.A)
KEY_HALF = re.compile(r"^fy(\d{4})h([12])\Z", re.A)
KEY_FPERIOD = re.compile(r"^fy(\d{4})p(0[1-9]|1[0-3])\Z", re.A)
KEY_WINDOW = re.compile(r"^w(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\Z", re.A)
FISCAL_KEYS = (KEY_FY, KEY_QUARTER, KEY_HALF, KEY_FPERIOD, KEY_YTD)
GRAMMAR = ("a fiscal year `fy2025`, a fiscal quarter `2026q1`, a fiscal half `fy2025h1`, a "
           "fiscal period `fy2025p03`, a calendar month `2025-12`, an LTM column by its end "
           "month `ltm_2025-12`, fiscal year-to-date by its end month `ytd_2025-12`, or an "
           "explicit window `w2025-08-16_2025-09-30` (EVIDENCE.md § 0)")
WEEKDAYS = {n: i for i, n in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))}


# --- months ------------------------------------------------------------------------------
def _aware(x) -> bool:
    return isinstance(x, dt.datetime) and x.utcoffset() is not None


def _ym(x) -> tuple[int, int]:
    """(year, month) of a date, a naive datetime, `"YYYY-MM"`, a real `"YYYY-MM-DD"` or a
    `(year, month)` pair; a timezone-aware datetime is refused (its month is the local
    date's: `month_key(x, timezone)`)."""
    if isinstance(x, dt.datetime) and _aware(x):
        raise ValueError(f"{x!r} is timezone-aware: its month is the entity's local date's "
                         f"- reduce it first (`month_key(x, timezone)`)")
    if isinstance(x, dt.date):
        return x.year, x.month
    if isinstance(x, str):
        s = x.strip()
        if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", s, re.A):
            return int(s[:4]), int(s[5:])
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s, re.A):
            try:
                d = dt.date.fromisoformat(s)
                return d.year, d.month
            except ValueError:
                pass
    if isinstance(x, tuple) and len(x) == 2 and all(
            isinstance(v, int) and not isinstance(v, bool) for v in x) and 1 <= x[1] <= 12:
        return x[0], x[1]
    raise ValueError(f"not a month: {x!r} (a date, `YYYY-MM` or a real `YYYY-MM-DD`)")


def _add(y: int, m: int, n: int) -> tuple[int, int]:
    i = y * 12 + (m - 1) + n
    return i // 12, i % 12 + 1


def _last_day(y: int, m: int) -> dt.date:
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def _iso(v, what: str) -> dt.date:
    """A strict ISO date (`YYYY-MM-DD`), a date or a naive datetime (its date); anything
    else, a timezone-aware datetime included, is refused."""
    if isinstance(v, dt.datetime):
        if _aware(v):
            raise ValueError(f"{what} {v!r} is a timezone-aware timestamp, not a date: reduce "
                             f"it to the entity's local date first")
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip(), re.A):
        try:
            return dt.date.fromisoformat(v.strip())
        except ValueError:
            pass
    raise ValueError(f"{what} {v!r} is not an ISO date (`YYYY-MM-DD`, e.g. `2025-09-30`)")


def month_key(x, timezone: str | None = None, source_timezone: str | None = None):
    """`"YYYY-MM"` for a date, a datetime, `"YYYY-MM"` or a real `"YYYY-MM-DD"`; for a
    polars date or datetime expression, the expression of that string. A datetime, scalar
    or column, is taken on the entity's local date (`local_date`): a timezone-aware one
    needs `timezone`."""
    if _is_expr(x):
        return local_date(x, timezone, source_timezone).dt.strftime("%Y-%m")
    y, m = _ym(_local_scalar(x, timezone, source_timezone))
    return f"{y:04d}-{m:02d}"


def month_label(x) -> str:
    """`"December 2025"` — DOCTRINE.md § Number conventions, never a system date key."""
    return style.month_label(*_ym(x))


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


# --- business days -------------------------------------------------------------------------
def _holidays(hs) -> frozenset:
    if hs is None:
        return frozenset()
    if not isinstance(hs, (list, tuple, set, frozenset)):
        raise ValueError(f"holidays must be a list of ISO dates, got {hs!r}")
    return frozenset(_iso(h, "holiday") for h in hs)


def _weekend(wk) -> frozenset:
    """The declared non-working weekdays, as `date.weekday()` numbers. Required: the
    weekend is the entity's (Saturday and Sunday in most places, Friday and Saturday in
    most of the Gulf), never assumed."""
    if not isinstance(wk, (list, tuple, set, frozenset)) or isinstance(wk, str):
        raise ValueError(f"weekend must be a list of weekday names (e.g. [\"sat\", \"sun\"]), "
                         f"got {wk!r} - declared, never assumed")
    out = set()
    for w in wk:
        k = str(w).strip().lower()[:3]
        if k not in WEEKDAYS:
            raise ValueError(f"weekend day {w!r}: one of {', '.join(WEEKDAYS)}")
        out.add(WEEKDAYS[k])
    if len(out) >= 7:
        raise ValueError("weekend names every day of the week")
    return frozenset(out)


def add_business_days(d, n: int, holidays=(), *, weekend) -> dt.date:
    """The date `n` business days after `d` (before it for a negative `n`), skipping the
    declared `weekend` days and `holidays`; `d` itself is not counted. `n` is a whole
    number (a float or a bool is refused); a count that runs past the calendar is refused."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise ValueError(f"business days must be a whole number, got {n!r}")
    d, hol, wk = _iso(d, "date"), _holidays(holidays), _weekend(weekend)
    step, left, start = (1 if n >= 0 else -1), abs(n), d
    try:
        while left:
            d += dt.timedelta(days=step)
            if d.weekday() not in wk and d not in hol:
                left -= 1
    except OverflowError:
        raise ValueError(f"{n} business days from {start} runs past the calendar") from None
    return d


def window(end, before: int, after: int, basis: str = "calendar",
           holidays=(), weekend=None) -> tuple[dt.date, dt.date]:
    """The window around a period end: from `before` days before it to `after` days after
    it, both ends and the period end itself included (`before=5` spans the end and the
    five days before it). `basis="business"` counts business days: every day but the
    declared `weekend` days and `holidays`. A window that runs past the calendar is
    refused."""
    end = _iso(end, "period end")
    for name, v in (("before", before), ("after", after)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"window `{name}` must be a whole number of days >= 0, got {v!r}")
    if basis == "calendar":
        if holidays or weekend:
            raise ValueError("holidays and weekend apply to basis `business` only")
        try:
            return end - dt.timedelta(days=before), end + dt.timedelta(days=after)
        except OverflowError:
            raise ValueError(f"a window of {before} days before and {after} after {end} "
                             f"runs past the calendar") from None
    if basis == "business":
        if weekend is None:
            raise ValueError("a business-day window needs `weekend` (e.g. [\"sat\", \"sun\"])")
        return (add_business_days(end, -before, holidays, weekend=weekend),
                add_business_days(end, after, holidays, weekend=weekend))
    raise ValueError(f"window basis {basis!r}: `calendar` or `business`")


def cutoff_spec(params: dict) -> dict:
    """A cutoff step's windows from its params, refusing any shape the step could not
    run on (a window past the calendar included). Returns `{period_ends, before, after,
    basis, holidays, weekend, windows}`, where `windows` is `[(start, end), ...]`, one per
    period end in the order declared; two windows may overlap, each its own population."""
    if not isinstance(params, dict):
        raise ValueError(f"cutoff params must be an object, got {params!r}")
    pes, pe = params.get("period_ends"), params.get("period_end")
    if pes is not None and pe is not None:
        raise ValueError("declare `params.period_ends` or the legacy `params.period_end`, "
                         "not both")
    if pes is None and pe is None:
        raise ValueError("a cutoff needs `params.period_ends` (a list of ISO dates, e.g. "
                         "[\"2025-09-30\"])")
    raw = pes if pes is not None else [pe]
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"`params.period_ends` must be a non-empty list of ISO dates, "
                         f"got {pes!r}")
    ends = [_iso(v, "`params.period_ends` entry" if pes is not None else
                 "`params.period_end`") for v in raw]
    if len(set(ends)) != len(ends):
        raise ValueError(f"`params.period_ends` repeats a date: {raw}")
    wd, before, after = params.get("window_days"), params.get("before"), params.get("after")
    if wd is not None:
        if before is not None or after is not None:
            raise ValueError("declare `params.before` + `params.after` or the legacy "
                             "`params.window_days`, not both")
        if isinstance(wd, bool) or not isinstance(wd, (int, float)) or wd <= 0 \
                or not float(wd).is_integer():
            raise ValueError(f"`params.window_days` must be a positive whole number of days "
                             f"each side, got {wd!r}")
        before = after = int(wd)
    elif before is None or after is None:
        raise ValueError("a cutoff needs `params.before` and `params.after` (days each side "
                         "of the period end)")
    for name, v in (("before", before), ("after", after)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"`params.{name}` must be a whole number of days >= 0, got {v!r}")
    if before == 0 and after == 0:
        raise ValueError("`params.before` and `params.after` are both 0: the window is the "
                         "period end alone")
    basis = params.get("basis", "calendar")
    if basis not in ("calendar", "business"):
        raise ValueError(f"`params.basis` must be `calendar` or `business`, got {basis!r}")
    hol, wk = params.get("holidays") or [], params.get("weekend")
    if (hol or wk) and basis != "business":
        raise ValueError("`params.holidays` and `params.weekend` apply to `basis: business` "
                         "only")
    if basis == "business" and wk is None:
        raise ValueError("`basis: business` needs `params.weekend`, the entity's non-working "
                         "days (e.g. [\"sat\", \"sun\"], or [\"fri\", \"sat\"])")
    hol = sorted(_holidays(hol))
    if wk is not None:
        _weekend(wk)
    return {"period_ends": ends, "before": before, "after": after, "basis": basis,
            "holidays": hol, "weekend": wk,
            "windows": [window(e, before, after, basis, hol, wk) for e in ends]}


# --- fiscal calendars ----------------------------------------------------------------------
def _month_of(v, what: str = "fiscal_year_end") -> int:
    """A month number from `"MM-DD"`, `"--MM-DD"`, `"MM"`, a month name or a number."""
    if isinstance(v, bool):
        raise ValueError(f"{what} {v!r}")
    if isinstance(v, int):
        if 1 <= v <= 12:
            return v
        raise ValueError(f"{what} month {v} is not 1-12")
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{what} {v!r}: write it `\"MM-DD\"`, e.g. `\"09-30\"`")
    s = v.strip().lstrip("-")
    for i, name in enumerate(MONTHS, 1):
        if s.lower() in (name.lower(), name[:3].lower()):
            return i
    m = re.fullmatch(r"(\d{1,2})(?:-(\d{1,2}))?", s, re.A)
    if not m or not 1 <= int(m.group(1)) <= 12:
        raise ValueError(f"{what} {v!r}: write it `\"MM-DD\"`, e.g. `\"09-30\"`")
    return int(m.group(1))


def parse_fiscal_year_end(v) -> int:
    """The final month (1-12) of a month-end fiscal year: `"MM-DD"` (`"09-30"`),
    `"--09-30"`, a month name (`"September"`) or a month number. A day that does not end
    its month is refused: declare that calendar's `years` (FiscalCalendar). `"02-28"` and
    `"02-29"` both read as February's last day, the 29th in a leap year; a year that ends
    on February 28 every year is a declared `years` calendar."""
    month = _month_of(v)
    if isinstance(v, str):
        m = re.fullmatch(r"(\d{1,2})-(\d{1,2})", v.strip().lstrip("-"), re.A)
        if m:
            day = int(m.group(2))
            last = 29 if month == 2 else calendar.monthrange(2001, month)[1]
            if day != last and not (month == 2 and day == 28):
                raise ValueError(f"fiscal_year_end {v!r} does not end its month: declare "
                                 f"the company's fiscal years as {YEARS_FORM}")
    return month


YEARS_FORM = ('{"years": [{"name": 2025, "start": "2024-09-29", "end": "2025-09-27"}, ...]} '
              'with each year\'s optional `label`, `quarters`, `halves` and `periods` as '
              '[[start, end], ...], taken from the company\'s own documents')


class _Year:
    __slots__ = ("name", "start", "end", "label", "subs")

    def __init__(self, name, start, end, label, subs):
        self.name, self.start, self.end, self.label, self.subs = name, start, end, label, subs


def _spans(v, yr_start, yr_end, what: str) -> list[tuple[dt.date, dt.date]]:
    """Declared subdivisions of one year: in order, contiguous, covering the year."""
    if not isinstance(v, list) or not v:
        raise ValueError(f"{what}: a non-empty list of [start, end] pairs")
    out = []
    for i, pair in enumerate(v):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(f"{what}[{i}]: a [start, end] pair of ISO dates, got {pair!r}")
        s, e = _iso(pair[0], f"{what}[{i}] start"), _iso(pair[1], f"{what}[{i}] end")
        if s > e:
            raise ValueError(f"{what}[{i}]: starts after it ends")
        out.append((s, e))
    if out[0][0] != yr_start or out[-1][1] != yr_end:
        raise ValueError(f"{what}: must run from the year's start {yr_start} to its end {yr_end}")
    for (_, a), (b, _) in zip(out, out[1:]):
        if b != a + dt.timedelta(days=1):
            raise ValueError(f"{what}: {a} is not followed by the next day ({b}) - "
                             f"subdivisions are contiguous")
    return out


class FiscalCalendar:
    """A company's fiscal years, from one of two `params.fiscal_year_end` forms:

    - `"MM-DD"` (a month name or number too): every year is twelve calendar months ending
      on that month's last day, named by the calendar year it ends in; quarters, halves
      and periods (months) follow from the months.
    - `{"years": [...]}`: every other calendar, declared rather than computed — each year's
      `name` (the company's), `start`, `end`, optional `label` (default `FY<name>`) and any
      `quarters`, `halves` and `periods` the company reports, as `[[start, end], ...]`.
      A 52/53-week year, a 13-period year, a start-year name, a change of year end: each
      is the dates the company's own documents state. Years are in order and never overlap;
      a `name` is 0-9999, so its slug `fy%04d` is a key.

    A month-end calendar places any date; a declared one only a date inside a declared year.
    """

    def __init__(self, month_end: int | None = None, years: list[_Year] | None = None):
        self.month_end = month_end
        years = [] if month_end is not None else years
        self._years = years
        self._ends = [yr.end for yr in years]
        self._by_name = {yr.name: yr for yr in years}
        self._key = json.dumps(month_end if month_end is not None else
                               [[y.name, y.start.isoformat(), y.end.isoformat(), y.label,
                                 {k: [[a.isoformat(), b.isoformat()] for a, b in v]
                                  for k, v in (y.subs or {}).items()}] for y in years])

    @classmethod
    def parse(cls, spec) -> "FiscalCalendar":
        if isinstance(spec, FiscalCalendar):
            return spec
        if isinstance(spec, dict) and "by_entity" in spec:
            raise ValueError("fiscal_year_end is declared per entity (`by_entity`): name the "
                             "entity (Periods.load(..., entity=...) or a single "
                             "`params.entities` member)")
        if not isinstance(spec, dict):
            return cls(month_end=parse_fiscal_year_end(spec))
        extra = sorted(set(spec) - {"years"})
        if extra or not isinstance(spec.get("years"), list) or not spec["years"]:
            raise ValueError(f"fiscal_year_end {spec!r}: \"MM-DD\" for a month-end year, "
                             f"else {YEARS_FORM}")
        years, names = [], set()
        for i, y in enumerate(spec["years"]):
            what = f"fiscal_year_end.years[{i}]"
            if not isinstance(y, dict) or not {"name", "start", "end"} <= set(y):
                raise ValueError(f"{what}: needs `name`, `start` and `end`")
            stray = sorted(set(y) - {"name", "start", "end", "label", "quarters", "halves",
                                     "periods"})
            if stray:
                raise ValueError(f"{what}: unknown key(s) {stray}")
            name = y["name"]
            if isinstance(name, bool) or not isinstance(name, int) or not 0 <= name <= 9999:
                raise ValueError(f"{what}: `name` is the year's number as the company names "
                                 f"it (2025 for FY2025, 0-9999), got {name!r}")
            if name in names:
                raise ValueError(f"{what}: fiscal year {name} is declared twice")
            names.add(name)
            s, e = _iso(y["start"], f"{what}.start"), _iso(y["end"], f"{what}.end")
            if s > e:
                raise ValueError(f"{what}: starts after it ends")
            if years and s <= years[-1].end:
                raise ValueError(f"{what}: starts on or before the previous year's end - "
                                 f"years are in order and never overlap")
            subs = {k: _spans(y[k], s, e, f"{what}.{k}")
                    for k in ("quarters", "halves", "periods") if k in y}
            for k, n in (("quarters", 4), ("halves", 2)):
                if k in subs and len(subs[k]) != n:
                    raise ValueError(f"{what}.{k}: {n} spans, got {len(subs[k])}")
            label = y.get("label") or f"FY{name}"
            years.append(_Year(name, s, e, str(label), subs))
        return cls(years=years)

    def __eq__(self, other) -> bool:
        return isinstance(other, FiscalCalendar) and self._key == other._key

    def __hash__(self) -> int:
        return hash(self._key)

    # -- years
    def year(self, name: int) -> _Year:
        if self.month_end is not None:
            n = int(name)
            try:
                return _Year(n, dt.date(*_add(n, self.month_end, -11), 1),
                             _last_day(n, self.month_end), f"FY{n}", None)
            except ValueError:
                raise ValueError(f"no fiscal year named {name} in this calendar") from None
        yr = self._by_name.get(int(name))
        if yr is None:
            raise ValueError(f"no fiscal year named {name} in this calendar")
        return yr

    def year_of(self, d) -> _Year:
        """The fiscal year a date falls in. A month (`"YYYY-MM"` or `(year, month)`) must
        fall wholly inside one year: a month a declared year boundary splits, or that runs
        outside the declared years, is refused - give a date."""
        if isinstance(d, tuple) or (isinstance(d, str) and len(d.strip()) == 7):
            y, m = _ym(d)
            try:
                first, last = self.year_of(dt.date(y, m, 1)), self.year_of(_last_day(y, m))
            except ValueError:
                raise ValueError(f"month {y:04d}-{m:02d} runs outside the declared fiscal "
                                 f"years: give a date") from None
            if first.name != last.name:
                raise ValueError(f"month {y:04d}-{m:02d} is split between fiscal years "
                                 f"{first.name} and {last.name}: give a date")
            return last
        d = _iso(d, "date")
        if self.month_end is not None:
            return self.year(d.year + (d.month > self.month_end))
        i = bisect.bisect_left(self._ends, d)
        if i >= len(self._years) or self._years[i].start > d:
            raise ValueError(f"{d} falls in no declared fiscal year")
        return self._years[i]

    def name_of(self, d) -> int:
        return self.year_of(d).name

    def label(self, name: int) -> str:
        return self.year(name).label

    # -- subdivisions
    def _declared(self, name: int, kind: str) -> list[tuple[dt.date, dt.date]]:
        yr = self.year(name)
        got = (yr.subs or {}).get(kind)
        if got is None:
            raise ValueError(f"fiscal year {name} declares no {kind}: add `{kind}` to its "
                             f"entry in fiscal_year_end.years, from the company's calendar")
        return got

    def _months(self, name: int, first: int, n: int) -> tuple[dt.date, dt.date]:
        yr = self.year(name)
        s = _add(yr.start.year, yr.start.month, first)
        e = _add(*s, n - 1)
        return dt.date(*s, 1), _last_day(*e)

    def periods(self, name: int) -> list[tuple[dt.date, dt.date]]:
        """The fiscal periods of a year: its months on a month-end calendar, else the
        periods declared."""
        if self.month_end is not None:
            return [self._months(name, i, 1) for i in range(12)]
        return self._declared(name, "periods")

    def quarter(self, name: int, q: int) -> tuple[dt.date, dt.date]:
        if isinstance(q, bool) or q not in (1, 2, 3, 4):
            raise ValueError(f"quarter {q!r}: 1-4")
        if self.month_end is not None:
            return self._months(name, 3 * (q - 1), 3)
        return self._declared(name, "quarters")[q - 1]

    def half(self, name: int, h: int) -> tuple[dt.date, dt.date]:
        if isinstance(h, bool) or h not in (1, 2):
            raise ValueError(f"half {h!r}: 1 or 2")
        if self.month_end is not None:
            return self._months(name, 6 * (h - 1), 6)
        return self._declared(name, "halves")[h - 1]


def calendar_for(spec, entity: str | None = None) -> FiscalCalendar:
    """The fiscal calendar a `params.fiscal_year_end` declares — for `entity` when it is a
    `by_entity` map of entity ids to either form."""
    if isinstance(spec, dict) and "by_entity" in spec:
        m = spec["by_entity"]
        if not isinstance(m, dict) or not m:
            raise ValueError("fiscal_year_end `by_entity` must map entity ids to calendars")
        if entity is None:
            raise ValueError(f"fiscal_year_end is declared per entity ({', '.join(m)}): "
                             f"name the entity")
        if entity not in m:
            raise ValueError(f"entity {entity!r} has no fiscal_year_end in by_entity "
                             f"({', '.join(m)})")
        return FiscalCalendar.parse(m[entity])
    return FiscalCalendar.parse(spec)


def calendars(spec) -> dict:
    """`{entity or None: FiscalCalendar}` for a `params.fiscal_year_end` in any form, each
    parsed by `calendar_for` (which refuses what it cannot read)."""
    if isinstance(spec, dict) and "by_entity" in spec:
        m = spec["by_entity"]
        return {e: calendar_for(spec, e) for e in (list(m) if isinstance(m, dict) else [])
                or [None]}
    return {None: calendar_for(spec)}


def _is_expr(x) -> bool:
    return type(x).__name__ == "Expr" and type(x).__module__.startswith("polars")


def _zone(name, what: str = "timezone"):
    """The `zoneinfo` zone an IANA name names; any other value is refused."""
    import zoneinfo
    if isinstance(name, str) and name.strip():
        try:
            return zoneinfo.ZoneInfo(name)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            pass
    raise ValueError(f"{what} {name!r} is not an IANA time zone (e.g. \"America/New_York\"); "
                     f"if it is one, this Python has no time-zone database - add `tzdata`")


def _check_zone(name, what: str = "timezone") -> str:
    """`name`, refused unless it is an IANA zone (read by polars where it is installed,
    the zone database that converts a column, else by `zoneinfo`)."""
    try:
        import polars as pl
    except ImportError:
        _zone(name, what)
        return name
    if isinstance(name, str) and name.strip():
        try:
            pl.Series([dt.datetime(2000, 1, 1)]).dt.replace_time_zone(name)
            return name
        except Exception:  # noqa: BLE001  polars names a bad zone in its own error types
            pass
    raise ValueError(f"{what} {name!r} is not an IANA time zone (e.g. \"America/New_York\")")


def _local_scalar(x, timezone: str | None = None, source_timezone: str | None = None):
    """A scalar `x` on the entity's local calendar, as `local_date` reduces a column: a
    timezone-aware datetime converted to `timezone` (refused without one); a naive one in
    `source_timezone` converted too (refused when that wall time never occurs there, or
    occurs twice on two different local dates); any other naive datetime its own date.
    Anything else is returned as it is."""
    if not isinstance(x, dt.datetime):
        return x
    if _aware(x):
        own = getattr(x.tzinfo, "key", None) or x.tzname()
        if source_timezone and source_timezone != own:
            raise ValueError(f"{x!r} already carries its zone ({own}): `source_timezone` "
                             f"{source_timezone!r} describes a naive timestamp only")
        if not timezone:
            raise ValueError(f"{x!r} is timezone-aware and no `params.timezone` is declared: "
                             f"its local date depends on it - declare the entity's IANA zone")
        return x.astimezone(_zone(timezone)).date()
    if source_timezone:
        if not timezone:
            raise ValueError(f"{x!r} is declared in {source_timezone} but no "
                             f"`params.timezone` names the local zone")
        src, tz = _zone(source_timezone, "source_timezone"), _zone(timezone)
        a, b = (x.replace(tzinfo=src, fold=f) for f in (0, 1))
        if a.astimezone(dt.timezone.utc).astimezone(src).replace(tzinfo=None) != x:
            raise ValueError(f"{x} never occurs in {source_timezone} (the daylight-saving "
                             f"gap): the timestamp is not a {source_timezone} wall time")
        da, db = a.astimezone(tz).date(), b.astimezone(tz).date()
        if da != db:
            raise ValueError(f"{x} occurs twice in {source_timezone} (the daylight-saving "
                             f"overlap) and the two instants fall on {da} and {db} in "
                             f"{timezone}: the local date is ambiguous")
        return da
    return x.date()


def local_date(expr, timezone: str | None = None, source_timezone: str | None = None):
    """A polars expression: `expr` reduced to the entity's local calendar date.

    A timezone-aware datetime is converted to `timezone` (the entity's IANA zone) before
    the date is taken; with no zone declared it is refused, and a `source_timezone` other
    than its own zone is refused. A naive datetime is local wall time unless
    `source_timezone` names what it is (e.g. `"UTC"`), in which case it is converted too:
    a wall time that never occurs in that zone (the daylight-saving gap) is refused, and
    one that occurs twice (the overlap) is refused when its two instants fall on different
    local dates. A date passes through, and an all-null column reads as null dates. Any
    other dtype - a string, an integer (`20250930`), a categorical - is refused: parse it
    to a date first (`str.to_date(<the file's format>)`), never by guess. A `timezone` or
    `source_timezone` that is not an IANA zone is refused when the expression is built."""
    import polars as pl
    tz = _check_zone(timezone) if timezone is not None else None
    if source_timezone is not None:
        _check_zone(source_timezone, "source_timezone")

    def to_date(s):
        dtype = s.dtype
        if isinstance(dtype, pl.Datetime):
            if dtype.time_zone is not None:
                if source_timezone and source_timezone != dtype.time_zone:
                    raise ValueError(f"`{s.name}` already carries its zone "
                                     f"({dtype.time_zone}): `source_timezone` "
                                     f"{source_timezone!r} describes a naive column only")
                if not tz:
                    raise ValueError(
                        f"`{s.name}` is timezone-aware ({dtype.time_zone}) and no "
                        f"`params.timezone` is declared: the local date of a timestamp "
                        f"near midnight depends on it - declare the entity's IANA zone")
                return s.dt.convert_time_zone(tz).dt.date()
            if source_timezone:
                if not tz:
                    raise ValueError(f"`{s.name}` is declared in {source_timezone} but "
                                     f"no `params.timezone` names the local zone")
                early, late = (s.dt.replace_time_zone(source_timezone, ambiguous=a,
                                                      non_existent="null")
                               .dt.convert_time_zone(tz).dt.date()
                               for a in ("earliest", "latest"))
                gap = s.is_not_null() & early.is_null()
                if gap.any():
                    raise ValueError(
                        f"`{s.name}` holds {gap.sum()} wall time(s) that never occur in "
                        f"{source_timezone} (the daylight-saving gap), first "
                        f"{s.filter(gap)[0]}: they are not {source_timezone} wall times")
                two = (early != late).fill_null(False)
                if two.any():
                    raise ValueError(
                        f"`{s.name}` holds {two.sum()} wall time(s) that occur twice in "
                        f"{source_timezone} (the daylight-saving overlap) on two different "
                        f"local dates in {tz}, first {s.filter(two)[0]}: the local date is "
                        f"ambiguous")
                return early
            return s.dt.date()
        if dtype == pl.Date:
            return s
        if dtype == pl.Null:
            return s.cast(pl.Date)
        raise ValueError(f"`{s.name}` is {dtype}, not a date or datetime: parse it to a date "
                         f"first (`str.to_date(<the file's format>)`) - a column is never read "
                         f"as a date by guess")
    return expr.map_batches(to_date, return_dtype=pl.Date)


def _slug(name: int) -> str:
    return f"fy{name:04d}"


def fy_of(x, fiscal_year_end, *, timezone: str | None = None,
          source_timezone: str | None = None):
    """The fiscal-year slug (`"fy2025"`) a date or month falls in, under any calendar
    `params.fiscal_year_end` declares (not a `by_entity` map: give the entity's own). `x`
    is a date, a datetime, `"YYYY-MM"` or `(year, month)` (refused when a declared year
    boundary splits the month: give a date), `"YYYY-MM-DD"`, or a polars date/datetime
    expression, which returns the expression of the slug under the input column's own name
    (alias it). A datetime, scalar or column, is reduced to the entity's local date first
    (`local_date`, with `timezone` and `source_timezone`): a timezone-aware one with no
    `timezone` is refused. A date in no declared year is refused."""
    cal = FiscalCalendar.parse(fiscal_year_end)
    if _is_expr(x):
        import polars as pl
        x = local_date(x, timezone, source_timezone)
        if cal.month_end is not None:
            year = x.dt.year()
            fy = pl.when(x.dt.month() > cal.month_end).then(year + 1).otherwise(year)
            return fy.cast(pl.Utf8).str.zfill(4).str.replace("^", "fy")

        def per_value(d):
            uniq = d.unique().drop_nulls().to_list()
            names = {u: _slug(cal.name_of(u)) for u in uniq}
            return d.replace_strict(names, default=None, return_dtype=pl.Utf8)
        return x.map_batches(per_value, return_dtype=pl.Utf8)
    if isinstance(x, str):
        x = x.strip()
    return _slug(cal.name_of(_local_scalar(x, timezone, source_timezone)))


def fy_label(slug: str) -> str:
    """`"fy2025"` -> `"FY2025"` (the default template; a calendar's own template is
    `FiscalCalendar.label`)."""
    m = KEY_FY.match(slug)
    if not m:
        raise ValueError(f"not a fiscal-year slug: {slug!r}")
    return f"FY{m.group(1)}"


def needs_fiscal_year(key: str) -> bool:
    """A column key that cannot be placed without the fiscal calendar."""
    return isinstance(key, str) and any(r.match(key) for r in FISCAL_KEYS)


def check_key(key) -> None:
    """Refuse a key outside the grammar, without a calendar: ASCII digits only, nothing
    after the key (a trailing newline included), a month 01-12, a window that ends on or
    after its start."""
    if not isinstance(key, str):
        raise ValueError(f"period key {key!r}: {GRAMMAR}")
    if any(r.match(key) for r in FISCAL_KEYS if r is not KEY_YTD):
        return
    if m := (KEY_MONTH.match(key) or KEY_LTM.match(key) or KEY_YTD.match(key)):
        _check_month(key, (int(m.group(1)), int(m.group(2))))
        return
    if m := KEY_WINDOW.match(key):
        a, b = _iso(m.group(1), "window start"), _iso(m.group(2), "window end")
        if a > b:
            raise ValueError(f"period key {key!r}: the window starts after it ends")
        return
    raise ValueError(f"period key {key!r} is outside the grammar: {GRAMMAR}; the "
                     f"display label is carried by `label`, never by the key")


# --- one period ----------------------------------------------------------------------------
class Period:
    """One column of the period set. Built by `Period.parse(key, fiscal_year_end)`."""

    __slots__ = ("key", "kind", "start", "end", "fiscal_year", "quarter", "_fy_label",
                 "_label", "timezone", "fy_end_month")

    def __init__(self, key, kind, start, end, *, fiscal_year=None, quarter=None,
                 fy_label=None, label=None, timezone=None, fy_end_month=None):
        if start > end:
            raise ValueError(f"period {key!r} starts after it ends")
        self.key, self.kind, self.start, self.end = key, kind, start, end
        self.fiscal_year, self.quarter, self._fy_label = fiscal_year, quarter, fy_label
        self._label, self.timezone, self.fy_end_month = label, timezone, fy_end_month

    @classmethod
    def parse(cls, key: str, fiscal_year_end=None, *, label: str | None = None,
              timezone: str | None = None, entity: str | None = None) -> "Period":
        check_key(key)
        cal = None
        if fiscal_year_end is not None:
            cals = calendars(fiscal_year_end)      # every calendar it declares, each read
            per = isinstance(fiscal_year_end, dict) and "by_entity" in fiscal_year_end
            cal = (calendar_for(fiscal_year_end, entity) if needs_fiscal_year(key)
                   else cals.get(entity if per else None))
        elif needs_fiscal_year(key):
            raise ValueError(f"period `{key}` needs the fiscal year end "
                             f"(params.fiscal_year_end, e.g. \"09-30\")")
        fem = cal.month_end if cal is not None else None
        kw = dict(label=label, timezone=timezone, fy_end_month=fem)
        if m := KEY_FY.match(key):
            n = int(m.group(1))
            yr = cal.year(n)
            return cls(key, "fy", yr.start, yr.end, fiscal_year=n, fy_label=cal.label(n), **kw)
        if m := KEY_QUARTER.match(key):
            n, q = int(m.group(1)), int(m.group(2))
            s, e = cal.quarter(n, q)
            return cls(key, "quarter", s, e, fiscal_year=n, quarter=q,
                       fy_label=cal.label(n), **kw)
        if m := KEY_HALF.match(key):
            n, h = int(m.group(1)), int(m.group(2))
            s, e = cal.half(n, h)
            return cls(key, "half", s, e, fiscal_year=n, quarter=h, fy_label=cal.label(n),
                       **kw)
        if m := KEY_FPERIOD.match(key):
            n, p = int(m.group(1)), int(m.group(2))
            ps = cal.periods(n)
            if p > len(ps):
                raise ValueError(f"period `{key}`: fiscal year {n} has {len(ps)} periods")
            s, e = ps[p - 1]
            return cls(key, "fperiod", s, e, fiscal_year=n, quarter=p, fy_label=cal.label(n),
                       **kw)
        if m := KEY_YTD.match(key):
            if cal.month_end is None:
                raise ValueError(f"period `{key}`: year-to-date by calendar month is read on "
                                 f"a \"MM-DD\" calendar only - a declared year need not "
                                 f"start on a month's first day; declare the window "
                                 f"`w<start>_<end>` from the company's dates")
            end = _last_day(int(m.group(1)), int(m.group(2)))
            yr = cal.year_of(end)
            return cls(key, "ytd", yr.start, end, fiscal_year=yr.name,
                       fy_label=cal.label(yr.name), **kw)
        if m := KEY_LTM.match(key):
            last = (int(m.group(1)), int(m.group(2)))
            first = _add(*last, -11)
            return cls(key, "ltm", dt.date(*first, 1), _last_day(*last), **kw)
        if m := KEY_MONTH.match(key):
            ym = (int(m.group(1)), int(m.group(2)))
            return cls(key, "month", dt.date(*ym, 1), _last_day(*ym), **kw)
        m = KEY_WINDOW.match(key)
        return cls(key, "window", _iso(m.group(1), "start"), _iso(m.group(2), "end"), **kw)

    @property
    def months(self) -> tuple[str, ...]:
        """The period's calendar months, in order. A period that does not run from a
        month's first day to a month's last day (`aligned`) has no exact set: refused."""
        if not self.aligned:
            raise ValueError(f"period `{self.key}` ({self.start}..{self.end}) does not run "
                             f"from a month's first day to a month's last day: it has no "
                             f"exact set of months - filter by its dates with `mask()`")
        return tuple(month_seq(self.start, self.end))

    @property
    def aligned(self) -> bool:
        """The period starts on a month's first day and ends on a month's last day."""
        return self.start.day == 1 and self.end == _last_day(self.end.year, self.end.month)

    @property
    def end_month(self) -> str:
        return month_key(self.end)

    @property
    def end_long(self) -> str:
        """`"September 30, 2025"`."""
        return style.date_long(self.end)

    @property
    def span_label(self) -> str:
        """What the period covers: `"October 2024–September 2025"` for whole months,
        `"Aug 16, 2025–Sep 30, 2025"` otherwise."""
        if self.aligned:
            return style.span_label(_ym(self.start), _ym(self.end))
        return f"{style.date_short(self.start)}{DASH}{style.date_short(self.end)}"

    def label(self, basis: str = "flow") -> str:
        """The column heading. `flow` for activity over the period (revenue, billings,
        movements); `snapshot` for a balance at its end (ARR, a receivable), which
        DOCTRINE.md § Periods labels `As of <end month>`. A fiscal-year column keeps
        `FY2025` for both. A `column_labels` heading replaces the flow label (and a
        fiscal-year column's one label). Two columns can share a label (e.g. `2025-12` and
        `ltm_2025-12` both read `As of December 2025`)."""
        if basis not in ("flow", "snapshot"):
            raise ValueError(f"basis {basis!r}: `flow` or `snapshot`")
        if self.kind == "fy":
            return self._label or self._fy_label
        if basis == "snapshot":
            if self.end == _last_day(self.end.year, self.end.month):
                return f"As of {month_label(self.end)}"
            return f"As of {style.date_short(self.end)}"
        if self._label:
            return self._label
        if self.kind == "month":
            return month_label(self.end)
        if self.kind == "ltm":
            return f"LTM {month_label(self.end)}"
        if self.kind == "ytd":
            return f"YTD {month_label(self.end)}"
        if self.kind == "quarter":
            return f"Q{self.quarter} {self._fy_label}"
        if self.kind == "half":
            return f"H{self.quarter} {self._fy_label}"
        if self.kind == "fperiod":
            return f"P{self.quarter} {self._fy_label}"
        return self.span_label

    def contains(self, x, timezone: str | None = None,
                 source_timezone: str | None = None) -> bool:
        """A month key (`"2025-09"`) is in the period when it is one of its `months`
        (refused for a period that is not `aligned`); a date when it falls between the
        period's first and last day; a datetime on the entity's local date, as `mask`
        reads a column (a timezone-aware one needs the set's `params.timezone`)."""
        if isinstance(x, str) and len(x.strip()) == 7:
            return month_key(x) in self.months
        d = _local_scalar(x, timezone or self.timezone, source_timezone)
        return self.start <= _iso(d, "date") <= self.end

    def local_date(self, expr, timezone: str | None = None, source_timezone: str | None = None):
        """`local_date(expr, ...)` with the period set's `params.timezone` by default."""
        return local_date(expr, timezone or self.timezone, source_timezone)

    def mask(self, expr, timezone: str | None = None, source_timezone: str | None = None):
        """A polars boolean expression: the date or datetime `expr` falls in the period,
        on the entity's local calendar (`local_date`)."""
        import polars as pl
        d = self.local_date(expr, timezone, source_timezone)
        return (d >= pl.lit(self.start)) & (d <= pl.lit(self.end))

    def window(self, before: int, after: int, basis: str = "calendar",
               holidays=(), weekend=None) -> "Period":
        """The cutoff window around the period's end, as a `window` period."""
        s, e = window(self.end, before, after, basis, holidays, weekend)
        return Period(f"w{s}_{e}", "window", s, e, timezone=self.timezone)

    def __repr__(self) -> str:
        return f"Period({self.key!r}, {self.start}..{self.end})"


def _check_month(key: str, ym: tuple[int, int]) -> None:
    if not 1 <= ym[1] <= 12:
        raise ValueError(f"period key {key!r}: month {ym[1]:02d} is not 01-12")


# --- the period set ----------------------------------------------------------------------
def _entities(c) -> list[str]:
    e = (c.get("params") or {}).get("entities")
    return [x for x in e if isinstance(x, str)] if isinstance(e, list) else []


def _year_end_of(checks):
    """The `params.fiscal_year_end` the checks declare, for a check that declares none:
    one calendar for the run (every check reads the same; `"09-30"` and `"September"` are
    one), or the checks' `by_entity` maps merged entity by entity. Two checks that read one
    entity's calendar differently disagree, and a run that mixes the two forms is refused."""
    plain, per = [], {}
    for c in checks:
        v = (c.get("params") or {}).get("fiscal_year_end")
        if v is None:
            continue
        if isinstance(v, dict) and "by_entity" in v:
            for e, cal in calendars(v).items():
                if e in per and per[e][1] != cal:
                    raise ValueError(f"checks disagree on params.fiscal_year_end for entity "
                                     f"{e!r}: {per[e][0]!r} and {c.get('id')!r}")
                per.setdefault(e, (c.get("id"), cal, v["by_entity"][e]))
        elif all(calendars(v) != calendars(g) for g in plain):
            plain.append(v)
    if len(plain) > 1:
        raise ValueError(f"checks disagree on params.fiscal_year_end: {plain}")
    if plain and per:
        raise ValueError("some checks declare one params.fiscal_year_end for the run and "
                         "others a `by_entity` map - declare the map on every check")
    if per:
        return {"by_entity": {e: spec for e, (_, _, spec) in per.items()}}
    return plain[0] if plain else None


def _timezone_of(checks, ents: list[str]):
    """The `params.timezone` the checks declare, for a check that declares none. On a run
    whose checks name more than one entity: None unless the zone-declaring checks together
    cover this check's entities, and then only the zones of checks sharing one of them.
    Two zones for the same check disagree."""
    got = [(z, _entities(c)) for c in checks
           if (z := (c.get("params") or {}).get("timezone")) is not None]
    if len({e for c in checks for e in _entities(c)}) > 1:
        covered = {e for _, es in got for e in es}
        if not ents or not set(ents) <= covered:
            return None
        got = [(z, es) for z, es in got if set(es) & set(ents)]
    zones = sorted({z for z, _ in got}, key=str)
    if len(zones) > 1:
        who = f" for {', '.join(ents)}" if ents else ""
        raise ValueError(f"checks disagree on params.timezone{who}: {zones}")
    return zones[0] if zones else None


class Periods:
    """The ordered period set a step reports on."""

    def __init__(self, keys, fiscal_year_end=None, *, timezone: str | None = None,
                 labels: dict | None = None, entity: str | None = None):
        keys = list(keys)
        if not keys:
            raise ValueError("an empty period set")
        dup = sorted({k for k in keys if keys.count(k) > 1})
        if dup:
            raise ValueError(f"period set repeats {dup}")
        labels = labels or {}
        if not isinstance(labels, dict):
            raise ValueError(f"column_labels must map period keys to headings, got {labels!r}")
        stray = sorted(set(labels) - set(keys))
        if stray:
            raise ValueError(f"column_labels names keys outside the period set: {stray}")
        blank = sorted(k for k, v in labels.items() if not isinstance(v, str) or not v.strip())
        if blank:
            raise ValueError(f"column_labels headings must be non-empty text: {blank}")
        if timezone is not None:
            _check_zone(timezone)
        self.fiscal_year_end, self.timezone, self.entity = fiscal_year_end, timezone, entity
        self._p = [Period.parse(k, fiscal_year_end, label=labels.get(k), timezone=timezone,
                                entity=entity) for k in keys]
        self._by = {p.key: p for p in self._p}

    @classmethod
    def load(cls, run_dir, check: str | None = None, *, columns=None,
             fiscal_year_end=None, timezone=None, labels=None, entity=None) -> "Periods":
        """The period set from `run.json`: `columns`, `fiscal_year_end`, `timezone` and
        `column_labels` from the check's params; the year end else from the other checks
        (one calendar for the run, or their `by_entity` maps merged per entity), the
        timezone else from the checks that name this check's entities (on a run of one
        entity, any check). `entity` selects a `by_entity` calendar (default: the check's
        single `params.entities` member)."""
        run_dir = pathlib.Path(run_dir)
        checks = []
        rj = run_dir / "run.json"
        if rj.is_file():
            checks = json.loads(rj.read_text(encoding="utf-8")).get("checks") or []
        own = next((c for c in checks if c.get("id") == check), None) if check else None
        if check and own is None and (columns is None or fiscal_year_end is None):
            raise ValueError(f"check {check!r} is not registered in {rj}")
        params = (own or {}).get("params") or {}
        if columns is None:
            columns = params.get("columns")
            if not columns:
                raise ValueError(f"check {check!r} declares no params.columns - the plan's "
                                 f"period set; give columns=[...]")
        if fiscal_year_end is None:
            fiscal_year_end = params.get("fiscal_year_end")
        if fiscal_year_end is None:
            fiscal_year_end = _year_end_of(checks)
        if labels is None:
            labels = params.get("column_labels")
        ents = _entities(own or {})
        if entity is None and len(ents) == 1:
            entity = ents[0]
        if timezone is None:
            timezone = params.get("timezone")
        if timezone is None:
            timezone = _timezone_of(checks, [entity] if entity is not None else ents)
        return cls(columns, fiscal_year_end, timezone=timezone, labels=labels, entity=entity)

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

    @property
    def calendar(self) -> FiscalCalendar:
        if self.fiscal_year_end is None:
            raise ValueError("no fiscal year end declared (params.fiscal_year_end)")
        return calendar_for(self.fiscal_year_end, self.entity)

    def fy_of(self, x, source_timezone: str | None = None):
        """`fy_of` on this set's calendar, a datetime (scalar or column) reduced to its
        `timezone`'s date."""
        return fy_of(x, self.calendar, timezone=self.timezone, source_timezone=source_timezone)

    @property
    def months(self) -> list[str]:
        """Every month of every column, in calendar order (refused for a column that is
        not `aligned`)."""
        return sorted({m for p in self._p for m in p.months})

    def __repr__(self) -> str:
        return f"Periods({self.keys}, fiscal_year_end={self.fiscal_year_end!r})"
