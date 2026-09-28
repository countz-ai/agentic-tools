#!/usr/bin/env python3
"""Self-test for scripts/periods.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_periods.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from periods import DASH, FiscalCalendar, Period, Periods, cutoff_spec, fy_of, month_key, month_seq, parse_fiscal_year_end, window  # noqa: E402


def main() -> int:
    D = dt.date
    P = Periods(["fy2023", "fy2024", "fy2025", "2025-12", "ltm_2025-12", "2026q1"], "09-30")
    fy25, dec, ltm, q1 = P["fy2025"], P["2025-12"], P["ltm_2025-12"], P["2026q1"]
    cal = Periods(["fy2025", "2025q4"], "12-31")
    # Japan/India: March year end named by its start year, `FY2024-25` headings - declared.
    jp = {"years": [
        {"name": 2024, "start": "2024-04-01", "end": "2025-03-31", "label": "FY2024-25",
         "quarters": [["2024-04-01", "2024-06-30"], ["2024-07-01", "2024-09-30"],
                      ["2024-10-01", "2024-12-31"], ["2025-01-01", "2025-03-31"]],
         "halves": [["2024-04-01", "2024-09-30"], ["2024-10-01", "2025-03-31"]]}]}
    jpP = Periods(["fy2024", "2024q1", "fy2024h2"], jp)
    # A 52/53-week year and a 13-period year: the dates the company states, not a rule.
    w53 = {"years": [
        {"name": 2024, "start": "2023-10-01", "end": "2024-09-28"},
        {"name": 2025, "start": "2024-09-29", "end": "2025-09-27",
         "quarters": [["2024-09-29", "2024-12-28"], ["2024-12-29", "2025-03-29"],
                      ["2025-03-30", "2025-06-28"], ["2025-06-29", "2025-09-27"]]}]}
    c53 = FiscalCalendar.parse(w53)
    p13 = [[str(D(2025, 1, 1) + dt.timedelta(days=28 * i)),
            str(D(2025, 1, 1) + dt.timedelta(days=28 * i + 27))] for i in range(13)]
    p13[-1][1] = "2025-12-30"
    c13 = {"years": [{"name": 2025, "start": "2025-01-01", "end": "2025-12-30",
                      "periods": p13}]}
    # A change of year end: the short transition year is one more declared year.
    hist = {"years": [{"name": 2023, "start": "2022-07-01", "end": "2023-06-30"},
                      {"name": 2024, "start": "2023-07-01", "end": "2023-12-31",
                       "label": "Transition period 2023"},
                      {"name": 2025, "start": "2024-01-01", "end": "2024-12-31"}]}
    hc = FiscalCalendar.parse(hist)
    # Parent and subsidiary on different year ends.
    group = {"by_entity": {"us_parent": "12-31", "jp_sub": jp}}
    SS = ["sat", "sun"]
    checks = [
        (fy25.start, D(2024, 10, 1)), (fy25.end, D(2025, 9, 30)),
        (len(fy25.months), 12), (fy25.label(), "FY2025"), (fy25.label("snapshot"), "FY2025"),
        (fy25.span_label, f"October 2024{DASH}September 2025"),
        (fy25.end_long, "September 30, 2025"),
        (dec.label(), "December 2025"), (dec.label("snapshot"), "As of December 2025"),
        (ltm.label(), "LTM December 2025"), (ltm.months[0], "2025-01"),
        (q1.months, ("2025-10", "2025-11", "2025-12")), (q1.label(), "Q1 FY2026"),
        (q1.span_label, f"October{DASH}December 2025"),
        (fy_of("2025-09-30", "09-30"), "fy2025"), (fy_of(D(2025, 10, 1), 9), "fy2026"),
        (fy_of("2025-12", "12-31"), "fy2025"), (cal["fy2025"].start, D(2025, 1, 1)),
        (cal["2025q4"].months, ("2025-10", "2025-11", "2025-12")),
        (parse_fiscal_year_end("February"), 2), (parse_fiscal_year_end("02-29"), 2),
        (month_seq("2025-11", "2026-02"), ["2025-11", "2025-12", "2026-01", "2026-02"]),
        (P.months[0], "2022-10"), (P.months[-1], "2025-12"),
        (P.labels("snapshot")["2025-12"], "As of December 2025"),
        # Japan / India, declared
        ((jpP["fy2024"].start, jpP["fy2024"].end), (D(2024, 4, 1), D(2025, 3, 31))),
        (jpP["fy2024"].label(), "FY2024-25"), (jpP["2024q1"].label(), "Q1 FY2024-25"),
        (jpP["2024q1"].months, ("2024-04", "2024-05", "2024-06")),
        ((jpP["fy2024h2"].start, jpP["fy2024h2"].end), (D(2024, 10, 1), D(2025, 3, 31))),
        (fy_of(D(2025, 3, 31), jp), "fy2024"),
        # 52/53-week, declared
        ((c53.year(2025).start, c53.year(2025).end), (D(2024, 9, 29), D(2025, 9, 27))),
        (Period.parse("fy2025", w53).end_long, "September 27, 2025"),
        (Period.parse("2025q1", w53).end, D(2024, 12, 28)),
        (fy_of(D(2024, 9, 28), w53), "fy2024"),
        # 13 periods of four weeks, the last one stretched to the year end
        ((Period.parse("fy2025p13", c13).start, Period.parse("fy2025p13", c13).end),
         (D(2025, 12, 3), D(2025, 12, 30))),
        (Period.parse("fy2025p02", c13).label(), "P2 FY2025"),
        # transition year
        ((hc.year_of("2023-09-15").start, hc.year_of("2023-09-15").end),
         (D(2023, 7, 1), D(2023, 12, 31))),
        (Period.parse("fy2024", hist).label(), "Transition period 2023"),
        # parent / subsidiary
        (Periods(["fy2024"], group, entity="us_parent")["fy2024"].end, D(2024, 12, 31)),
        (Periods(["fy2024"], group, entity="jp_sub")["fy2024"].end, D(2025, 3, 31)),
        # windows, YTD
        (Period.parse("w2025-08-16_2025-09-30").label(), f"Aug 16, 2025{DASH}Sep 30, 2025"),
        (Periods(["w2025-08-16_2025-09-30"], labels={"w2025-08-16_2025-09-30": "Stub"})
         ["w2025-08-16_2025-09-30"].label(), "Stub"),
        (Period.parse("w2025-08-16_2025-09-30").label("snapshot"), "As of September 2025"),
        ((Period.parse("ytd_2025-12", "09-30").start), D(2025, 10, 1)),
        (Period.parse("ytd_2025-12", "09-30").label(), "YTD December 2025"),
        (Period.parse("fy2025h1", "09-30").months,
         ("2024-10", "2024-11", "2024-12", "2025-01", "2025-02", "2025-03")),
        # cutoff: Friday Oct 10 + Monday Oct 13 holiday; 3 business days either side of Tue Sep 30
        (window("2025-09-30", 3, 3, "business", weekend=SS), (D(2025, 9, 25), D(2025, 10, 3))),
        (window("2025-10-10", 1, 1, "business", ["2025-10-13"], SS),
         (D(2025, 10, 9), D(2025, 10, 14))),
        # a Friday-Saturday weekend: 2 business days after Thursday Sep 25 is Monday Sep 29
        (window("2025-09-25", 0, 2, "business", weekend=["fri", "sat"]),
         (D(2025, 9, 25), D(2025, 9, 29))),
        (window("2025-09-30", 5, 5), (D(2025, 9, 25), D(2025, 10, 5))),
        (fy25.window(2, 2, "business", weekend=SS).key, "w2025-09-26_2025-10-02"),
        (cutoff_spec({"period_end": "2025-09-30", "window_days": 5})["windows"],
         [(D(2025, 9, 25), D(2025, 10, 5))]),
        (cutoff_spec({"period_ends": ["2025-06-30", "2025-09-30"], "before": 0, "after": 3,
                      "basis": "business", "holidays": ["2025-07-04"],
                      "weekend": SS})["windows"],
         [(D(2025, 6, 30), D(2025, 7, 3)), (D(2025, 9, 30), D(2025, 10, 3))]),
        # an unaligned period keeps its dates; LTM is calendar months on any calendar
        (Period.parse("w2025-08-16_2025-09-30").contains("2025-08-16"), True),
        (Period.parse("w2025-08-16_2025-09-30").contains("2025-08-15"), False),
        (Period.parse("fy2025", w53).label(), "FY2025"),
        (Period.parse("ltm_2025-06", w53).months[0], "2024-07"),
        (Period.parse("ltm_2025-06", w53).label(), "LTM June 2025"),
    ]
    bad = [f"got {got!r}, want {want!r}" for got, want in checks if got != want]
    refusals = [
        lambda: Period.parse("FY2025", "09-30"), lambda: Period.parse("m9_2025-09", "09-30"),
        lambda: Period.parse("fy2025", None), lambda: Period.parse("2025-13", None),
        lambda: Period.parse("fy2025", "09-15"),
        lambda: Periods(["fy2024"], group),                         # no entity chosen
        lambda: Period.parse("fy2025p03", w53),                     # no periods declared
        lambda: Period.parse("2024q1", w53),                        # no quarters for 2024
        lambda: Period.parse("fy2026", w53),                        # no such year
        lambda: FiscalCalendar.parse(w53).year_of("2026-01-15"),    # after the last year
        lambda: Period.parse("w2025-09-30_2025-09-01"),
        lambda: FiscalCalendar.parse({"calendar": "52_53", "month": 9}),
        lambda: FiscalCalendar.parse({"years": [{"name": 2025, "start": "2024-10-01",
                                                  "end": "2025-09-30"},
                                                 {"name": 2026, "start": "2025-09-01",
                                                  "end": "2026-09-30"}]}),   # overlap
        lambda: FiscalCalendar.parse({"years": [{"name": 2025, "start": "2025-01-01",
                                                  "end": "2025-12-31", "quarters": [
                                                      ["2025-01-01", "2025-06-30"],
                                                      ["2025-07-02", "2025-12-31"]]}]}),
        lambda: window("2025-09-30", 2, 2, "business"),              # no weekend declared
        lambda: cutoff_spec({"period_ends": ["2025-09-30"], "before": 2, "after": 2,
                             "basis": "business"}),
        lambda: cutoff_spec({"period_end": "Sept 30", "window_days": 5}),
        lambda: cutoff_spec({"period_ends": ["2025-09-30"], "before": 5}),
        lambda: cutoff_spec({"period_end": "2025-09-30", "window_days": 5, "before": 2,
                             "after": 2}),
        lambda: cutoff_spec({"period_ends": ["2025-09-30"], "before": 2, "after": 2,
                             "holidays": ["2025-10-01"]}),
        lambda: cutoff_spec({"period_ends": ["2025-09-30"], "before": 2.5, "after": 2}),
        lambda: Period.parse("stub_2025-08-16_2025-09-30"),
        lambda: Period.parse("w2025-08-16_2025-09-30").months,     # no exact set of months
        lambda: Period.parse("w2025-08-16_2025-09-30").contains("2025-09"),
        lambda: Period.parse("fy2025", w53).months,                 # a 52/53-week year
        lambda: Periods(["2025-09", "w2025-08-16_2025-09-30"]).months,
        lambda: Period.parse("ytd_2024-12", hist),                  # ytd on declared years
        lambda: Period.parse("ytd_2025-06", w53),
    ]
    for i, f in enumerate(refusals):
        try:
            f()
            bad.append(f"refusal case {i} was accepted")
        except ValueError:
            pass
    import tempfile                                 # one calendar, two spellings
    with tempfile.TemporaryDirectory() as tmp:
        (pathlib.Path(tmp) / "run.json").write_text(json.dumps({"checks": [
            {"id": "a", "params": {"columns": ["fy2025"]}},
            {"id": "b", "params": {"fiscal_year_end": "09-30"}},
            {"id": "c", "params": {"fiscal_year_end": "September"}}]}))
        if Periods.load(tmp, "a")["fy2025"].end != D(2025, 9, 30):
            bad.append("load: `09-30` and `September` did not agree")
    try:
        import polars as pl
        df = pl.DataFrame({"d": [D(2024, 9, 30), D(2024, 10, 1), D(2025, 12, 31)]})
        got = df.select(fy_of(pl.col("d"), "09-30").alias("fy"),
                        fy25.mask(pl.col("d")).alias("in"),
                        month_key(pl.col("d")).alias("m"))
        if got["fy"].to_list() != ["fy2024", "fy2025", "fy2026"]:
            bad.append(f"fy_of expr: {got['fy'].to_list()}")
        if got["in"].to_list() != [False, True, False]:
            bad.append(f"mask: {got['in'].to_list()}")
        if got["m"].to_list() != ["2024-09", "2024-10", "2025-12"]:
            bad.append(f"month_key expr: {got['m'].to_list()}")
        utc_m = pl.DataFrame({"t": [dt.datetime(2025, 10, 1, 3, 30)]}).with_columns(
            pl.col("t").dt.replace_time_zone("UTC"))
        if utc_m.select(month_key(pl.col("t"), "America/New_York"))["t"].to_list() != ["2025-09"]:
            bad.append("month_key: a 23:30 local posting on September 30 keyed to October")
        w = df.head(2).select(fy_of(pl.col("d"), hist).alias("w"))["w"].to_list()
        if w != ["fy2025", "fy2025"]:
            bad.append(f"fy_of declared-years expr: {w}")
        try:
            df.select(fy_of(pl.col("d"), hist))
            bad.append("fy_of: a date in no declared year was placed")
        except Exception as exc:                    # polars wraps the ValueError
            if "no declared fiscal year" not in str(exc):
                bad.append(f"fy_of: unexpected error {exc}")
        # A UTC export: 03:30Z on October 1 is 23:30 on September 30 in New York.
        utc = pl.DataFrame({"t": [dt.datetime(2025, 10, 1, 3, 30)]}).with_columns(
            pl.col("t").dt.replace_time_zone("UTC"))
        ny = Periods(["fy2025"], "09-30", timezone="America/New_York")["fy2025"]
        if utc.select(ny.mask(pl.col("t")))["t"].to_list() != [True]:
            bad.append("mask: a 23:30 local posting on September 30 fell outside FY2025")
        sep = {"years": [{"name": 2025, "start": "2024-10-01", "end": "2025-09-30"},
                         {"name": 2026, "start": "2025-10-01", "end": "2026-09-30"}]}
        NY = "America/New_York"
        for what, e in (("fy_of", fy_of(pl.col("t"), "09-30", timezone=NY)),
                        ("Periods.fy_of", Periods(["fy2025"], "09-30", timezone=NY)
                         .fy_of(pl.col("t"))),
                        ("fy_of declared", fy_of(pl.col("t"), sep, timezone=NY))):
            got = utc.select(e).to_series().to_list()
            if got != ["fy2025"]:
                bad.append(f"{what}: a 23:30 posting on September 30 was placed in {got}")
        try:
            utc.select(fy_of(pl.col("t"), "09-30"))
            bad.append("fy_of: accepted a timezone-aware column with no declared zone")
        except Exception as exc:                    # polars wraps the ValueError
            if "timezone" not in str(exc):
                bad.append(f"fy_of: unexpected error {exc}")
        naive = pl.DataFrame({"t": [dt.datetime(2025, 10, 1, 3, 30)]})
        if naive.select(ny.mask(pl.col("t"), source_timezone="UTC"))["t"].to_list() != [True]:
            bad.append("mask: a naive UTC timestamp was not converted")
        if naive.select(fy25.mask(pl.col("t")))["t"].to_list() != [False]:
            bad.append("mask: a naive timestamp is local wall time")
        try:
            utc.select(fy25.mask(pl.col("t")))
            bad.append("mask: accepted a timezone-aware column with no declared zone")
        except Exception as exc:                    # polars wraps the ValueError
            if "timezone" not in str(exc):
                bad.append(f"mask: unexpected error {exc}")
    except ImportError:
        pass
    for b in bad:
        print(f"periods: {b}")
    print("periods: ok" if not bad else "periods: self-check FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
