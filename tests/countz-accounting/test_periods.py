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
from periods import DASH, FiscalCalendar, Period, Periods, add_business_days, check_key, cutoff_spec, fy_of, local_date, month_key, month_seq, parse_fiscal_year_end, window  # noqa: E402


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
    NY = "America/New_York"
    # 03:30Z on October 1 is 23:30 on September 30 in New York.
    aware = dt.datetime(2025, 10, 1, 3, 30, tzinfo=dt.timezone.utc)
    naive = dt.datetime(2025, 10, 1, 3, 30)
    y999 = {"years": [{"name": 999, "start": "0999-01-01", "end": "0999-12-31"}]}
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
        # a single timestamp is placed on the local date, as a column is
        (fy_of(aware, "09-30", timezone=NY), "fy2025"),
        (fy_of(naive, "09-30"), "fy2026"),                          # naive: wall time
        (fy_of(naive, "09-30", timezone=NY, source_timezone="UTC"), "fy2025"),
        (Periods(["fy2025"], "09-30", timezone=NY).fy_of(aware), "fy2025"),
        (Periods(["fy2025"], "09-30", timezone=NY)["fy2025"].contains(aware), True),
        (Period.parse("fy2025", "09-30").contains(naive), False),
        (month_key(aware, NY), "2025-09"), (month_key("2025-09-30"), "2025-09"),
        # a DST-overlap wall time whose two instants share one local date is placed
        (fy_of(dt.datetime(2025, 11, 2, 1, 30), "09-30", timezone=NY,
               source_timezone="America/Los_Angeles"), "fy2026"),
        (fy_of(dt.datetime(2025, 11, 2, 1, 30), "09-30", timezone=NY, source_timezone=NY),
         "fy2026"),
        # a month-end calendar places any date; a declared name keeps its four digits
        (fy_of(D(1900, 5, 1), "09-30"), "fy1900"), (fy_of(D(2200, 1, 1), "09-30"), "fy2200"),
        (Period.parse("fy1949", "12-31").start, D(1949, 1, 1)),
        (fy_of(D(999, 6, 1), y999), "fy0999"), (Period.parse("fy0999", y999).end, D(999, 12, 31)),
        # a month wholly inside one declared year is placed
        (fy_of("2025-08", w53), "fy2025"), (fy_of((2025, 8), w53), "fy2025"),
        # a calendar-month column needs no calendar for its entity
        (Periods(["2025-12"], group, entity="uk").keys, ["2025-12"]),
        (window("2025-09-30", 1, 0), (D(2025, 9, 29), D(2025, 9, 30))),
        (add_business_days("2025-09-30", 2, weekend=SS), D(2025, 10, 2)),
        (check_key("ytd_2025-12"), None),
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
        # a timezone-aware timestamp with no zone, or with a contradicting source zone
        lambda: fy_of(aware, "09-30"), lambda: month_key(aware),
        lambda: Period.parse("fy2025", "09-30").contains(aware),
        lambda: fy_of(aware, "09-30", timezone=NY, source_timezone="Asia/Tokyo"),
        lambda: month_seq(aware, "2025-12"),
        # a wall time in the DST gap; an overlap wall time on two local dates
        lambda: fy_of(dt.datetime(2025, 3, 9, 2, 30), "09-30", timezone=NY, source_timezone=NY),
        lambda: fy_of(dt.datetime(2025, 10, 26, 1, 30), "09-30", timezone="Atlantic/Cape_Verde",
                      source_timezone="Europe/London"),
        lambda: Periods(["fy2025"], "09-30", timezone="America/NewYork"),
        # keys outside the grammar: a trailing newline, non-ASCII digits, month 13
        lambda: check_key("fy2025\n"), lambda: check_key("fy\uff12\uff10\uff12\uff15"),
        lambda: check_key("\u0662\u0660\u0662\u0665-\u0661\u0662"),
        lambda: check_key("ytd_2025-13"), lambda: Periods(["fy2025", "fy2025\n"], "09-30"),
        # a month a declared year boundary splits
        lambda: fy_of("2025-09", w53), lambda: fy_of((2025, 9), w53),
        lambda: Periods(["fy2024"], group, entity="uk"),            # fiscal, no calendar
        lambda: Periods(["2025-12"], "09-15"),                      # a bad calendar still
        lambda: FiscalCalendar.parse({"years": [{"name": 10000, "start": "2025-01-01",
                                                  "end": "2025-12-31"}]}),
        lambda: FiscalCalendar.parse("09-30").quarter(2025, 0),
        lambda: FiscalCalendar.parse("09-30").half(2025, 3),
        lambda: window("2025-09-30", 10 ** 7, 0),
        lambda: cutoff_spec({"period_ends": ["2025-09-30"], "before": 10 ** 7, "after": 0}),
        lambda: add_business_days("2025-09-30", 2.7, weekend=SS),
        lambda: add_business_days("2025-09-30", True, weekend=SS),
        lambda: month_key("2025-02-30"), lambda: month_key("2025-09-30T10:00"),
        lambda: month_seq("2025-02-31", "2025-03"),
        lambda: Periods(["2025-12"], labels={"2025-12": 2025}),
        lambda: Periods(["2025-12"], labels={"2025-12": " "}),
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

    def load(checks, check):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "run.json").write_text(json.dumps({"checks": checks}))
            return Periods.load(tmp, check)
    us = {"by_entity": {"us_parent": "12-31"}}
    jps = {"by_entity": {"jp_sub": jp}}
    runs = [
        # one entity: the zone any check declares
        ([{"id": "a", "params": {"columns": ["fy2025"], "fiscal_year_end": "09-30"}},
          {"id": "b", "params": {"timezone": NY}}], "a", lambda P: P.timezone, NY),
        # many entities: never another entity's zone; the zone of a check naming this one
        ([{"id": "us", "params": {"columns": ["fy2024"], "entities": ["us_parent"],
                                  "fiscal_year_end": group}},
          {"id": "jp", "params": {"columns": ["fy2024"], "entities": ["jp_sub"],
                                  "fiscal_year_end": group, "timezone": "Asia/Tokyo"}}],
         "us", lambda P: P.timezone, None),
        ([{"id": "us", "params": {"entities": ["us_parent"], "timezone": NY}},
          {"id": "jp", "params": {"entities": ["jp_sub"], "timezone": "Asia/Tokyo"}},
          {"id": "c", "params": {"columns": ["2024-12"], "entities": ["us_parent"]}}],
         "c", lambda P: P.timezone, NY),
        ([{"id": "us", "params": {"entities": ["us_parent"], "timezone": NY}},
          {"id": "jp", "params": {"entities": ["jp_sub"], "timezone": "Asia/Tokyo"}},
          {"id": "c", "params": {"columns": ["2024-12"]}}], "c", lambda P: P.timezone, None),
        # by_entity maps on different checks merge entity by entity
        ([{"id": "a", "params": {"fiscal_year_end": us}}, {"id": "b", "params":
          {"fiscal_year_end": jps}}, {"id": "c", "params": {"columns": ["fy2024"],
                                                             "entities": ["us_parent"]}},
          {"id": "d", "params": {"columns": ["fy2024"], "entities": ["jp_sub"]}}],
         "c", lambda P: P["fy2024"].end, D(2024, 12, 31)),
        ([{"id": "a", "params": {"fiscal_year_end": us}}, {"id": "b", "params":
          {"fiscal_year_end": jps}}, {"id": "d", "params": {"columns": ["fy2024"],
                                                             "entities": ["jp_sub"]}}],
         "d", lambda P: P["fy2024"].end, D(2025, 3, 31)),
    ]
    for i, (checks, check, got, want) in enumerate(runs):
        try:
            if got(load(checks, check)) != want:
                bad.append(f"load case {i}: got {got(load(checks, check))!r}, want {want!r}")
        except ValueError as exc:
            bad.append(f"load case {i} refused: {exc}")
    for i, checks in enumerate([
            # one check covering two entities whose checks declare two zones
            [{"id": "us", "params": {"entities": ["us_parent"], "timezone": NY}},
             {"id": "jp", "params": {"entities": ["jp_sub"], "timezone": "Asia/Tokyo"}},
             {"id": "c", "params": {"columns": ["2024-12"], "entities": ["us_parent",
                                                                          "jp_sub"]}}],
            # one entity's calendar read two ways; the two forms mixed
            [{"id": "a", "params": {"fiscal_year_end": us}},
             {"id": "b", "params": {"fiscal_year_end": {"by_entity": {"us_parent": "06-30"}}}},
             {"id": "c", "params": {"columns": ["fy2024"], "entities": ["us_parent"]}}],
            [{"id": "a", "params": {"fiscal_year_end": "12-31"}},
             {"id": "b", "params": {"fiscal_year_end": jps}},
             {"id": "c", "params": {"columns": ["fy2024"], "entities": ["jp_sub"]}}]]):
        try:
            load(checks, "c")
            bad.append(f"load refusal case {i} was accepted")
        except ValueError:
            pass
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

        def refused(what, frame, e, words):         # polars keeps the ValueError's text
            try:
                frame.select(e)
                bad.append(f"{what}: accepted")
            except Exception as exc:                # noqa: BLE001
                if words not in str(exc):
                    bad.append(f"{what}: unexpected error {exc}")
        # a column that is not a date or datetime is refused, never cast by guess
        ints = pl.DataFrame({"d": [20250930]})
        refused("mask on yyyymmdd ints", ints, fy25.mask(pl.col("d")), "not a date")
        refused("fy_of on Int32", ints, fy_of(pl.col("d").cast(pl.Int32), "09-30"), "not a date")
        refused("mask on ISO strings", pl.DataFrame({"d": ["2025-09-30"]}),
                fy25.mask(pl.col("d")), "not a date")
        if pl.DataFrame({"d": [None]}).select(fy25.mask(pl.col("d")))["d"].to_list() != [None]:
            bad.append("mask: an all-null column did not read as null dates")
        # the slug keeps the input column's name on either calendar form
        if df.with_columns(fy_of(pl.col("d"), "09-30")).columns != ["d"] or \
                df.tail(2).select(fy_of(pl.col("d"), "09-30"), fy_of(pl.col("d"), sep).alias("x")
                          ).columns != ["d", "x"]:
            bad.append("fy_of: the slug column is not named for its input")
        old = pl.DataFrame({"d": [D(1900, 5, 1), D(2200, 1, 1)]})
        if old.select(fy_of(pl.col("d"), "09-30"))["d"].to_list() != ["fy1900", "fy2200"]:
            bad.append("fy_of expr: a month-end calendar did not place any date")
        # DST: the gap refused, an overlap on two local dates refused, one on one date placed
        gap = pl.DataFrame({"t": [dt.datetime(2025, 3, 9, 2, 30)]})
        refused("DST gap", gap, fy_of(pl.col("t"), "09-30", timezone=NY, source_timezone=NY),
                "never occur")
        ldn = pl.DataFrame({"t": [dt.datetime(2025, 10, 26, 1, 30)]})
        refused("DST overlap on two dates", ldn, fy25.mask(pl.col("t"), "Atlantic/Cape_Verde",
                                                            "Europe/London"), "occur twice")
        fall = pl.DataFrame({"t": [dt.datetime(2025, 11, 2, 1, 30)]})
        got = fall.select(fy_of(pl.col("t"), "09-30", timezone=NY,
                                source_timezone="America/Los_Angeles"))["t"].to_list()
        if got != ["fy2026"]:
            bad.append(f"DST overlap on one local date: {got}")
        # a source zone on an aware column must be the column's own
        refused("source_timezone on an aware column", utc,
                ny.mask(pl.col("t"), source_timezone="Asia/Tokyo"), "already carries")
        if utc.select(ny.mask(pl.col("t"), source_timezone="UTC"))["t"].to_list() != [True]:
            bad.append("mask: a source_timezone equal to the column's zone was refused")
        try:
            local_date(pl.col("t"), "America/NewYork")
            bad.append("local_date: accepted a zone that is not IANA")
        except ValueError:
            pass
        # a timezone-aware column is never read in another entity's zone: refused
        P = load([{"id": "us", "params": {"columns": ["fy2024"], "entities": ["us_parent"],
                                          "fiscal_year_end": group}},
                  {"id": "jp", "params": {"columns": ["fy2024"], "entities": ["jp_sub"],
                                          "fiscal_year_end": group, "timezone": "Asia/Tokyo"}}],
                 "us")
        dec31 = pl.DataFrame({"t": [dt.datetime(2025, 1, 1, 1, 0)]}).with_columns(
            pl.col("t").dt.replace_time_zone("UTC"))    # 20:00 on December 31 in New York
        refused("another entity's zone", dec31, P["fy2024"].mask(pl.col("t")), "timezone")
    except ImportError:
        pass
    for b in bad:
        print(f"periods: {b}")
    print("periods: ok" if not bad else "periods: self-check FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
