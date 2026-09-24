#!/usr/bin/env python3
"""How the plugin writes a number or a date, as one table: currencies, scale suffixes, date
forms, and the token grammar the gates read them back with.

Every module that prints money or a date imports this rather than typing a `$`, a `k` or a
`strftime` pattern of its own — `figures.fmt`, `periods` labels, `wbkit` cell formats,
`build_report`, and the gates `check_prose` / `check_report` / `check_workbook`, which parse
with the grammar built from the same table, so the writer and the gate cannot drift:

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from style import money, date_long, date_short, month_label, MONEY_TOKEN, scale_of

    money(9_438_108.22, "usd")            # "$9,438,108"      (prose: whole units)
    money(9_438_108.22, "usd", "deck")    # "$9.4M"           (scaled: K, M, B)
    money(9_438_108.22, "usd", "cell")    # "$9,438,108.22"   (the currency's minor units)
    money(-1_204.4, "eur")                # "(€1,204)"
    money(120_000, "jpy", "cell")         # "¥120,000"        (JPY has no minor unit)
    date_long(d)                          # "September 30, 2025"
    date_short(d)                         # "Sep 30, 2025"
    month_label(2025, 9)                  # "September 2025"
    scale_header("usd", "thousands")      # "$ in thousands"

**US conventions**: month-first dates, `$9.4M` / `$1.2B` / `$81K` everywhere a figure is
scaled — prose, slides and tables — thousands grouped with commas, a period as the decimal
mark, negatives in parentheses.

**A money unit is a currency code** (`usd`, `eur`, `gbp`, `jpy`, ...): the unit names the
currency, so two figures in different currencies never share a unit. `CURRENCIES` is
every active ISO 4217 currency — the common ones with their symbol, the rest written by
code (`RON 5,000`); `minor_units(unit)` is the stored precision (JPY 0, USD 2, KWD 3).

**Reading back.** `MONEY_TOKEN` matches an amount the way any currency in the table writes
it — a symbol (`$`, `€`, `A$`) or an ISO code (`EUR 5,000`, `5,000 EUR`) — with an optional
scale suffix read case-insensitively (`K`, `M`, `MM`, `B`, `BN`, `thousand`, `million`,
`billion`), so a legacy `$9.4m` still parses. `scale_of(suffix)` is its multiplier.
`COL_SCALE` recognizes a stated scale (`$ in thousands`, `€'000`) in any currency.

Run with no arguments to self-check. Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from typing import NamedTuple

__all__ = [
    "Currency", "CURRENCIES", "is_money", "currency", "minor_units", "symbol",
    "money", "compact", "scale_header", "SCALES", "SCALE_WORDS", "scale_of",
    "date_long", "date_short", "month_label", "month_short", "span_label",
    "FMT_DATE_CELL", "MONTHS", "MONTHS_SHORT",
    "MONEY_TOKEN", "NUM", "currency_of", "currency_in", "parse_money", "COL_SCALE", "SUFFIX", "SUFFIX_RE",
]


# --- currencies (ISO 4217) ------------------------------------------------------------
class Currency(NamedTuple):
    code: str          # ISO 4217, upper case
    symbol: str        # the prefix a figure is written with; "" writes the code
    minor: int         # decimal places of the minor unit


def _c(code: str, symbol: str, minor: int = 2) -> Currency:
    return Currency(code, symbol, minor)


# One symbol per currency and no symbol shared: a `$` is the US dollar; the other dollars
# carry their disambiguating prefix. A currency with no distinctive symbol writes its code.
CURRENCIES: dict[str, Currency] = {c.code.lower(): c for c in (
    _c("USD", "$"), _c("EUR", "€"), _c("GBP", "£"), _c("JPY", "¥", 0),
    _c("CNY", "CN¥"), _c("CAD", "CA$"), _c("AUD", "A$"), _c("NZD", "NZ$"),
    _c("HKD", "HK$"), _c("SGD", "S$"), _c("MXN", "MX$"), _c("BRL", "R$"),
    _c("INR", "₹"), _c("KRW", "₩", 0), _c("CHF", ""), _c("SEK", ""), _c("NOK", ""),
    _c("DKK", ""), _c("PLN", ""), _c("CZK", ""), _c("HUF", ""), _c("ZAR", ""),
    _c("ILS", "₪"), _c("TWD", "NT$"), _c("THB", ""), _c("PHP", "₱"), _c("IDR", "", 0),
    _c("MYR", ""), _c("AED", ""), _c("SAR", ""), _c("TRY", ""), _c("VND", "", 0),
    _c("CLP", "", 0), _c("COP", ""), _c("ARS", ""), _c("PEN", ""), _c("EGP", ""),
    _c("NGN", ""), _c("KES", ""), _c("ISK", "", 0),
    _c("KWD", "", 3), _c("BHD", "", 3), _c("OMR", "", 3), _c("JOD", "", 3),
)}

# Every other active ISO 4217 currency, written by its code: a company is never refused
# for the currency it reports in. Minor units per ISO 4217 (2 unless listed).
_ISO_MINOR = {"BIF": 0, "DJF": 0, "GNF": 0, "KMF": 0, "PYG": 0, "RWF": 0, "UGX": 0,
              "VUV": 0, "XAF": 0, "XOF": 0, "XPF": 0, "IQD": 3, "LYD": 3, "TND": 3}
for _code in (
        "AFN ALL AMD ANG AOA AWG AZN BAM BBD BDT BGN BIF BMD BND BOB BSD BTN BWP BYN BZD "
        "CDF CRC CUP CVE DJF DOP DZD ERN ETB FJD FKP GEL GHS GIP GMD GNF GTQ GYD HNL HTG "
        "IQD IRR JMD KGS KHR KMF KPW KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK "
        "MNT MOP MRU MUR MVR MWK MZN NAD NIO NPR PAB PGK PKR PYG QAR RON RSD RUB RWF SBD "
        "SCR SDG SHP SLE SOS SRD SSP STN SVC SYP SZL TJS TMT TND TOP TTD TZS UAH UGX UYU "
        "UZS VED VES VUV WST XAF XCD XCG XOF XPF YER ZMW ZWG").split():
    CURRENCIES.setdefault(_code.lower(), _c(_code, "", _ISO_MINOR.get(_code, 2)))


def is_money(unit: str | None) -> bool:
    return (unit or "").lower() in CURRENCIES


def currency(unit: str) -> Currency:
    c = CURRENCIES.get((unit or "").lower())
    if c is None:
        raise ValueError(f"unit {unit!r} is not a currency this table defines "
                         f"(scripts/style.py CURRENCIES); add it there, never approximate")
    return c


def minor_units(unit: str) -> int:
    return currency(unit).minor


def symbol(unit: str) -> str:
    """The prefix: `$`, `€`, `A$` — or the code and a space where the currency has no
    distinctive symbol (`CHF 1,204`)."""
    c = currency(unit)
    return c.symbol or f"{c.code} "


# --- scale ----------------------------------------------------------------------------
# Writing: upper-case K, M, B (US). Reading: any of these, case-insensitively.
SUFFIX = (("B", 1e9), ("M", 1e6), ("K", 1e3))
# The scales a table or a stated figure is shown at.
SCALES = {"units": 1.0, "thousands": 1e3, "millions": 1e6, "billions": 1e9}
SCALE_WORDS = {"k": 1e3, "thousand": 1e3, "thousands": 1e3,
               "m": 1e6, "mm": 1e6, "mn": 1e6, "million": 1e6, "millions": 1e6,
               "b": 1e9, "bn": 1e9, "billion": 1e9, "billions": 1e9}


def scale_of(suffix: str | None) -> float:
    """The multiplier a suffix or word states; 1 for none. An unknown one is refused."""
    if not suffix:
        return 1.0
    k = suffix.strip().lower()
    if k not in SCALE_WORDS:
        raise ValueError(f"scale {suffix!r}: one of {', '.join(sorted(SCALE_WORDS))}")
    return SCALE_WORDS[k]


def compact(a: float) -> str:
    """A non-negative magnitude, scaled as a slide or a sentence states it: `9.4M`,
    `1.2B`, `81K`, `640`. Rounds up across a boundary (999,600 reads `1.0M`, not `1,000K`)."""
    if a >= 999_500_000:
        return f"{a / 1e9:,.1f}B"
    if a >= 999_500:
        return f"{a / 1e6:,.1f}M"
    if a >= 999.5:
        return f"{a / 1e3:,.0f}K"
    return f"{a:,.0f}"


def money(value: float, unit: str = "usd", style: str = "prose") -> str:
    """One amount as written. `prose`: whole units (`$9,438,108`); `deck`: scaled
    (`$9.4M`); `cell`: the currency's minor units (`$9,438,108.22`, `¥120,000`). Negatives
    in parentheses; an amount that rounds to zero at the shown precision is never
    parenthesized."""
    if style not in ("prose", "deck", "cell"):
        raise ValueError(f"style {style!r}: prose, deck or cell")
    sym = symbol(unit)
    v = float(value)
    a = abs(v)
    if style == "deck":
        body = compact(a)
    elif style == "cell":
        body = f"{a:,.{minor_units(unit)}f}"
    else:
        body = f"{a:,.0f}"
    s = sym + body
    neg = v < 0 and body.strip("0.,KMB") != ""
    return f"({s})" if neg else s


def scale_header(unit: str, scale: str) -> str:
    """The header of a column stated at a scale: `$ in thousands`, `€ in millions`,
    `CHF in thousands`."""
    if scale not in SCALES:
        raise ValueError(f"scale {scale!r}: {', '.join(SCALES)}")
    head = symbol(unit).strip()
    return head if scale == "units" else f"{head} in {scale}"


# --- dates ----------------------------------------------------------------------------
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")
MONTHS_SHORT = tuple(m[:3] for m in MONTHS)
# The workbook's date cell: month first, unambiguous across readers ("Sep 30, 2025").
FMT_DATE_CELL = "mmm d, yyyy"


def _date(d) -> dt.date:
    if isinstance(d, dt.datetime):
        return d.date()
    if isinstance(d, dt.date):
        return d
    if isinstance(d, str):
        return dt.date.fromisoformat(d[:10])
    raise TypeError(f"a date, not {type(d).__name__} {d!r}")


def date_long(d) -> str:
    """`September 30, 2025`."""
    d = _date(d)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def date_short(d) -> str:
    """`Sep 30, 2025`."""
    d = _date(d)
    return f"{MONTHS_SHORT[d.month - 1]} {d.day}, {d.year}"


def month_label(year: int, month: int) -> str:
    """`September 2025`."""
    return f"{MONTHS[month - 1]} {year}"


def month_short(year: int, month: int) -> str:
    """`Sep 2025`."""
    return f"{MONTHS_SHORT[month - 1]} {year}"


def span_label(first: tuple[int, int], last: tuple[int, int]) -> str:
    """`October 2024–September 2025`; within one year `October–December 2025`; one month
    reads as itself."""
    if tuple(first) == tuple(last):
        return month_label(*first)
    if first[0] == last[0]:
        return f"{MONTHS[first[1] - 1]}–{month_label(*last)}"
    return f"{month_label(*first)}–{month_label(*last)}"


# --- reading back: the token grammar the gates use ------------------------------------
NUM = r"\d[\d,]*(?:\.\d+)?"
# Read, never written: another way a currency's symbol is spelled.
_ALIASES = {"US$": "usd"}
_SYMBOLS = sorted({c.symbol for c in CURRENCIES.values() if c.symbol} | set(_ALIASES),
                  key=len, reverse=True)
_CODES = sorted(c.code for c in CURRENCIES.values())
# A symbol never starts inside a word, so `S$` is not read inside `US$`.
_SYM = "|".join(rf"(?<![A-Za-z]){re.escape(s)}" for s in _SYMBOLS)
_PREFIX = "|".join([_SYM, *(rf"\b{c}\s?" for c in _CODES)])
SUFFIX_RE = r"(?i:bn|mm|mn|[kmb]|thousands?|millions?|billions?)\b"
# A money token: a currency prefix, a number, an optional scale — or a number, an optional
# scale and a trailing ISO code (`5,000 EUR`, `1.2M USD`). Named groups: `cur` / `cur2`
# (the prefix or code as written), `money`, `suffix`.
MONEY_TOKEN = (
    rf"(?P<cur>{_PREFIX})\s?(?P<money>{NUM})\s*(?P<suffix>{SUFFIX_RE})?"
    rf"|(?<![\w.,])(?P<money2>{NUM})\s*(?P<suffix2>{SUFFIX_RE})?\s(?P<cur2>{'|'.join(_CODES)})\b"
)
_MONEY_RE = re.compile(MONEY_TOKEN)
# Codes match in upper case only, so `Industry in millions` is not `TRY in millions`.
_HEAD = rf"{_SYM}|\b(?-i:{'|'.join(_CODES)})"
# A column header that states a scale, in any currency: `$ in thousands`, `€'000`,
# `(EUR m)`, `CHF in millions`, `$000s`.
COL_SCALE = (
    (re.compile(rf"(?:{_HEAD})\s?(?:'000|000s?|in thousands|k\b)|\((?:{_HEAD})\s?(?:k|'000)\)",
                re.I), 1e-3),
    (re.compile(rf"(?:{_HEAD})\s?(?:in millions|mm?\b)|\((?:{_HEAD})\s?mm?\)", re.I), 1e-6),
    (re.compile(rf"(?:{_HEAD})\s?(?:in billions|bn?\b)|\((?:{_HEAD})\s?bn?\)", re.I), 1e-9),
)


def currency_of(written: str) -> str:
    """The unit (`usd`, `eur`) a written prefix or code names: `$` → usd, `A$` → aud,
    `EUR` → eur."""
    w = written.strip()
    if w in _ALIASES:
        return _ALIASES[w]
    for c in CURRENCIES.values():
        if w == c.symbol or w.upper() == c.code:
            return c.code.lower()
    raise ValueError(f"{written!r} names no currency in scripts/style.py")


_CODE_RE = re.compile(rf"\b(?:{'|'.join(_CODES)})\b")
_SYM_RE = re.compile(_SYM)


def currency_in(text: str) -> str | None:
    """The unit of the currency `text` names — its first ISO code (`USD whole dollars`),
    else its first symbol (`FY2025 (€)`) — or None."""
    m = _CODE_RE.search(text) or _SYM_RE.search(text)
    return currency_of(m.group(0)) if m else None


def parse_money(text: str) -> list[tuple[str, float]]:
    """Every money token in `text`, as (unit, value in units): `$9.4M` → ("usd",
    9_400_000.0). Parentheses around a token make it negative."""
    out = []
    for m in _MONEY_RE.finditer(text):
        cur = m.group("cur") or m.group("cur2")
        num = m.group("money") or m.group("money2")
        suf = m.group("suffix") or m.group("suffix2")
        v = float(num.replace(",", "")) * scale_of(suf)
        before = text[:m.start()].rstrip()
        after = text[m.end():].lstrip()
        if before.endswith("(") and after.startswith(")"):
            v = -v
        out.append((currency_of(cur), v))
    return out


# --- self-check -----------------------------------------------------------------------
def _selfcheck() -> int:
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
    for fn, arg in ((currency, "xyz"), (scale_of, "lakh")):
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
    sys.exit(_selfcheck())
