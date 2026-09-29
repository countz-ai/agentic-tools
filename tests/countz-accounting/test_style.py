#!/usr/bin/env python3
"""Self-test for scripts/style.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_style.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from style import COL_SCALE, currency, currency_in, date_long, date_short, is_money, minor_units, money, month_label, parse_money, scale_header, scale_of, span_label  # noqa: E402


def main() -> int:
    d = dt.date(2025, 9, 30)
    cases = [
        (money(9_438_108.22, "usd"), "$9,438,108"),
        (money(9_438_108.22, "usd", "deck"), "$9.4M"),
        (money(1_204_000_000, "usd", "deck"), "$1.2B"),
        (money(81_000, "usd", "deck"), "$81K"),
        (money(999_600, "usd", "deck"), "$1.0M"),
        (money(640, "usd", "deck"), "$640"),
        (money(9_438_108.226, "usd", "cell"), "$9,438,108.23"),
        (money(-1_204.4, "eur"), "(€1,204)"),
        (money(-0.4, "usd"), "$0"),
        (money(120_000, "jpy", "cell"), "¥120,000"),
        (money(1_234.567, "kwd", "cell"), "KWD 1,234.567"),
        (money(5_000_000, "aud", "deck"), "A$5.0M"),
        (money(1_204, "chf"), "CHF 1,204"),
        (scale_header("usd", "thousands"), "$ in thousands"),
        (scale_header("eur", "millions"), "€ in millions"),
        (scale_header("chf", "thousands"), "CHF in thousands"),
        (date_long(d), "September 30, 2025"),
        (date_short(d), "Sep 30, 2025"),
        (month_label(2025, 9), "September 2025"),
        (span_label((2024, 10), (2025, 9)), "October 2024–September 2025"),
        (span_label((2025, 10), (2025, 12)), "October\u2013December 2025"),
        (minor_units("jpy"), 0), (minor_units("kwd"), 3), (is_money("usd"), True),
        (is_money("pct"), False),
    ]
    reads = [
        ("revenue was $9.4M in FY2025", [("usd", 9_400_000.0)]),
        ("a legacy $9.4m and $1.2bn", [("usd", 9_400_000.0), ("usd", 1_200_000_000.0)]),
        ("€5,000,000 and £81k", [("eur", 5_000_000.0), ("gbp", 81_000.0)]),
        ("A$1.2M and CHF 1,204", [("aud", 1_200_000.0), ("chf", 1_204.0)]),
        ("EUR 5,000 then 7,500 USD", [("eur", 5_000.0), ("usd", 7_500.0)]),
        ("a loss of ($1,204)", [("usd", -1_204.0)]),
        ("$50.5 million", [("usd", 50_500_000.0)]),
        ("US$1.2M and S$81K", [("usd", 1_200_000.0), ("sgd", 81_000.0)]),
    ]
    cases += [(currency_in("USD whole dollars"), "usd"), (currency_in("US$ whole dollars"), "usd"),
              (currency_in("FY2025 (€)"), "eur"), (currency_in("Balance (EUR)"), "eur"),
              (currency_in("Industry total"), None)]
    heads = [("$ in thousands", 1e-3), ("€'000", 1e-3), ("(EUR m)", 1e-6),
             ("$ in millions", 1e-6), ("CHF in billions", 1e-9), ("$'000", 1e-3),
             ("US$ in thousands", 1e-3), ("Industry in millions", None),
             ("Overall in thousands", None), ("Plan km", None)]
    bad = [f"{got!r} != {want!r}" for got, want in cases if got != want]
    for text, want in reads:
        got = parse_money(text)
        if [(u, round(v, 2)) for u, v in got] != want:
            bad.append(f"parse {text!r}: {got} != {want}")
    for h, want in heads:
        got = next((f for rx, f in COL_SCALE if rx.search(h)), None)
        if got != want:
            bad.append(f"header {h!r}: {got} != {want}")
    for fn, arg in ((currency, "xyz"), (scale_of, "lakh"), (money, float("nan")),
                    (money, float("inf")), (money, float("-inf"))):
        try:
            fn(arg)
            bad.append(f"{fn.__name__}({arg!r}) did not refuse")
        except ValueError:
            pass
    for b in bad:
        print("FAIL", b)
    print("style.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
