#!/usr/bin/env python3
"""Match two streams of transactions by ordered rules, the way reconciliation software does
(NetSuite's bank-data matching, BlackLine's transaction matching), and list what is left.

Two records of the same money are matched: a cash book's deposits and the bank's credits,
its payments and the bank's debits, an invoice register and a cash-application file. Each
rule compares the items the rules before it left open; a pair matches only where each is
the other's one candidate under the rule. What no rule matches is an exception, for a
person to clear. Every match names its rule.

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from resolve import Rule, chain, resolve, rules

    res = resolve(book, bank, rules(window=(0, 3), same_entity=True), transit=3)
    res.items       # one row per item of both streams (check_assignment() accepts it)
    res.matches     # one row per match: its rule, type, both sides' ids and totals, difference
    res.exceptions  # every unmatched item: its reason, its age at the statement's end, and
                    # whether it is in transit
    res.summary     # the reconciliation, left total to right total, net and gross; it foots
    res.by_rule     # what each rule matched
    chain(r1, r2, r3)   # each left item of r1 traced through r2 and r3 (r1's right items are
                        # r2's left items, by id): what it reaches, and by which rules

    res = from_assignment(book, bank, assignment, [Pass("cheque", "same cheque number and "
                          "amount"), ...], transit=3)   # a match built with polars joins, as
                                                        # the same Resolution

**Using it.**

1. Map each population whole, one flow per call: what came in (receipts, with the
   refunds, reversals and returned items that undo them), or what went out (payments, with
   theirs), never both. Each stream is a polars DataFrame of `id` (unique text or integer,
   no `;`), `date` (a Date, a Datetime without a time zone, or ISO text `YYYY-MM-DD`, with
   an optional time and no zone; null where the record has none) and `value` (a number:
   same currency and sign convention on both sides, no finer than `decimals`), with any
   other columns a rule compares: `entity` (a customer, a payee, an account), `ref` (a
   cheque, deposit or invoice number the other side carries too), `text` (a bank
   description), `batch` (the lines of one deposit), `slip`. Where the source's own key
   repeats (a deposit id on each of its lines, a payment id on each invoice it pays), build
   the id from the file and the row, or from the key and a second column; the key itself is
   `batch` when it groups one deposit's lines, and `ref` only when the other side's `ref`
   numbers the same thing.

   **What is refused:** an id, `ref`, `entity`, `text`, `batch` or other compared column
   held as a float or a decimal (cast it to text or an integer; e.g. Excel's cheque 1001,
   read as `1001.0`, keys as `10010`), or as a datetime; a time-zoned datetime (take the
   entity's local date first, `periods.local_date`); date text that is not ISO (`2024-3-1`, `03/01/2024`); a column a
   rule compares that one stream has and the other lacks, or that neither has (other than
   `ref`, which may be absent from both); two rules of one name; a rule whose ranges run
   backwards, or whose `percent` is not a fraction (`0.03` is 3%).
2. Choose the rules. `rules()` gives the defaults below; add a `Rule` for what a record
   names that the other side does not (a processor's fee, a bank's conversion). Measure
   the window before choosing it: match once by reference at any date (`[Rule("ref",
   ("ref",), None), Rule("quoted", ("quote",), None)]`, or on amounts that occur once on
   each side), and read the days from the left date to the right date on those pairs: `window` the few days most pairs fall in, `wide` the longest a pair
   takes. Pass `transit=` the days an item takes to reach the bank where that is longer
   than `window` (a cheque paid out is presented weeks after it is written).
3. Read each item's `status`: `matched` names its rule (`pass`), its group and what it
   matched to; `unmatched` states why (no candidate, or the count of candidates a rule
   found). The exceptions are yours to clear with the records the engine cannot read.
4. `res.summary` is the reconciliation: the left total, less the left items in transit and
   those not matched, plus each named difference, plus the right items not matched, is the
   right total. Each line shows its net and its gross, positive and negative apart.
   `res.decimals` is the precision it was matched at, and `res.end` the date transit and
   age are measured at: `end=` (the statement's end), else the right side's last date.
5. Records that settle in steps (invoice, cash application, receipt, bank line) are
   matched one pair at a time, one call each, and `chain()` traces them end to end.
6. Show the result with `scripts/match_tabs.py`.

**A match built elsewhere** (polars joins, one per pass, where the rules above cannot say
what pairs two records) becomes the same Resolution through `from_assignment()`: the two
streams as above, the assignment `matching.py`'s `check_assignment()` accepts (it is checked
by it here), and every pass the assignment names as a `Pass`, in the order the passes ran,
its criteria in words and the difference it tolerates, named, where its groups differ. An
excluded item is unmatched, its reason the pass that set it aside and why, and never in
transit. `transit` is measured as for `resolve()`, and stated.

**A rule** compares the open items of both sides:
- `on`: columns that must be equal, compared as keys (case, spaces, punctuation and
  leading zeros dropped: `12-345` and `123-45` are one key). `ref` is a number both sides
  carry for the same thing (a cheque number on the book and on the bank); a number only
  one side has goes in `text`, or stays out. `quote` is special: the right item's `text` quotes the left item's `id` or `ref`.
  A rule that does not compare `ref` never pairs two items whose references both exist
  and differ: an amount never overrides a reference. An item whose column is empty is not
  a candidate under a rule that compares that column, so a column set only on the records
  a rule applies to scopes the rule to them (the currency of a foreign receipt, and the
  currency the statement says it converted, for a rule that tolerates a conversion).
- `days`: (lo, hi), the right date less the left date, inclusive; None, dates not
  compared. An undated item is matched only by a rule that does not compare dates.
- `group_left`, `group_right`: first sum the open items sharing these columns, compared as
  keys, into one (a customer's items of one day; the lines of one deposit), dated over
  their span. A group carries its items' references and never pairs with an item whose
  reference differs from any of them.
- amounts equal, or `tolerance` (currency) and `percent` (a fraction of the left amount)
  apart, each a (lo, hi) range, negative where the right side carries less, the two
  bounds added; the difference is reported under `difference`. A zero amount is matched
  only by a rule that wants amounts equal.
A pair matches when it meets the rule and neither side has another candidate under it.
An item with two candidates or more is left for the next rule. An unmatched left item is
in transit when its date, plus `transit` days, reaches past the right side's last date: its
right item would be on a later statement. `transit` is how long the flow's items take to
reach the bank (a receipt a few days, a cheque paid out weeks); by default the end of the
narrowest window a rule compares dates over. Pass `end=`, the statement's end. The
default, the right side's last date, can fall days early on a quiet account and show a
cleared item as in transit.

**The default rules**, `rules(window, wide, same_entity)`, in order, after NetSuite's:
reference (same `ref` and amount); reference, totals (the items sharing a `ref` on each
side, totals equal); quoted (the right text quotes the left `id` or `ref`, same amount),
these three from the start of `window` to the end of `wide`, since a reference two records
share can be reused (a cheque returned and banked again quotes its invoice as the first
banking did); amount and date (same amount within `window`); deposit lines (one left item,
the lines of one right `batch`); day's items (a left `entity`'s items of one day, one right
item); day's items, deposit lines (both at once); amount, wide (same amount within
`wide`); then reference and quoted again at any date, for what no dated rule could pair (an
undated item, a receipt booked weeks after the bank credited it). `same_entity` adds
`entity` to every rule, where both sides name the same party or account.
"""
from __future__ import annotations

import datetime as dt
import math
import pathlib
import sys
from dataclasses import dataclass, field

import polars as pl

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from matching import check_assignment  # noqa: E402

__all__ = ["Pass", "Rule", "Resolution", "chain", "from_assignment", "resolve", "rules"]

# The engine's own working columns: a rule never compares or groups by one of these.
RESERVED = frozenset({"value", "day", "c", "g", "ids", "lo", "hi", "refkey", "nref", "quote"})
# Columns every stream may carry, absent meaning empty.
OPTIONAL = ("entity", "ref", "text", "batch")
ISO_TEXT = r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?$"


@dataclass(frozen=True)
class Rule:
    name: str
    on: tuple[str, ...] = ()
    days: tuple[int, int] | None = (0, 0)
    group_left: tuple[str, ...] = ()
    group_right: tuple[str, ...] = ()
    tolerance: tuple[float, float] = (0.0, 0.0)
    percent: tuple[float, float] = (0.0, 0.0)
    difference: str | None = None

    @property
    def exact(self) -> bool:
        return tuple(self.tolerance) == (0.0, 0.0) and tuple(self.percent) == (0.0, 0.0)

    @property
    def criteria(self) -> str:
        """The rule in words, as the rules tab states it."""
        bits = [("the right text quotes the left id or reference" if c == "quote" else f"same {c}")
                for c in self.on]
        if self.exact:
            bits.append("same amount")
        else:
            band = [f"{self.percent[0]:+.2%} to {self.percent[1]:+.2%} of the left amount"] \
                if tuple(self.percent) != (0.0, 0.0) else []
            band += [f"{self.tolerance[0]:+,.2f} to {self.tolerance[1]:+,.2f}"] \
                if tuple(self.tolerance) != (0.0, 0.0) else []
            bits.append(f"the right amount differs by {' and '.join(band)} ({self.difference})")
        bits.append("any date" if self.days is None else
                    f"the right date {self.days[0]} to {self.days[1]} days after the left")
        bits += [f"left items summed by {', '.join(self.group_left)}"] if self.group_left else []
        bits += [f"right items summed by {', '.join(self.group_right)}"] if self.group_right else []
        return "; ".join(bits)


def _check_rule(r) -> None:
    """A rule as the engine reads it, or refused naming what is wrong."""
    if not isinstance(r, Rule):
        raise ValueError(f"rule {r!r} is not a Rule")
    if not isinstance(r.name, str) or not r.name.strip():
        raise ValueError(f"rule {r!r}: a rule has a name")
    for what, cols in (("on", r.on), ("group_left", r.group_left), ("group_right", r.group_right)):
        if isinstance(cols, str) or not isinstance(cols, (tuple, list)) \
                or not all(isinstance(c, str) and c for c in cols):
            raise ValueError(f"rule {r.name!r}: `{what}` is a tuple of column names, not {cols!r}")
        for c in cols:
            if c.startswith("k_") or (c in RESERVED and not (what == "on" and c == "quote")) \
                    or (c == "date" and what == "on"):
                raise ValueError(f"rule {r.name!r}: `{what}` names {c!r}, a column the engine "
                                 f"keeps for itself")
    if r.days is not None:
        if not (isinstance(r.days, (tuple, list)) and len(r.days) == 2
                and all(isinstance(x, int) and not isinstance(x, bool) for x in r.days)
                and r.days[0] <= r.days[1]):
            raise ValueError(f"rule {r.name!r}: `days` is None or (lo, hi), whole days, lo <= hi; "
                             f"got {r.days!r}")
    for what, band, cap in (("tolerance", r.tolerance, math.inf), ("percent", r.percent, 1.0)):
        if not (isinstance(band, (tuple, list)) and len(band) == 2
                and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                        and math.isfinite(x) and abs(x) <= cap for x in band)
                and band[0] <= band[1]):
            raise ValueError(f"rule {r.name!r}: `{what}` is (lo, hi), lo <= hi"
                             + (", each a fraction of the left amount (0.03 is 3%)"
                                if what == "percent" else "") + f"; got {band!r}")
    if not r.exact and not (isinstance(r.difference, str) and r.difference.strip()):
        raise ValueError(f"rule {r.name!r}: a tolerance names the difference it allows")


def rules(window=(0, 2), wide=(0, 89), same_entity=False) -> list[Rule]:
    """The default rule set (module docstring)."""
    e = ("entity",) if same_entity else ()
    ref = (window[0], wide[1])
    return [Rule("reference", e + ("ref",), ref),
            Rule("reference, totals", e + ("ref",), ref, ("ref",), ("ref",)),
            Rule("quoted", e + ("quote",), ref),
            Rule("amount and date", e, tuple(window)),
            Rule("deposit lines", e, tuple(window), group_right=("batch",)),
            Rule("day's items", e, tuple(window), group_left=("entity", "date")),
            Rule("day's items, deposit lines", e, tuple(window), group_left=("entity", "date"),
                 group_right=("batch",)),
            Rule("amount, wide", e, tuple(wide)),
            Rule("reference, any date", e + ("ref",), None),
            Rule("quoted, any date", e + ("quote",), None)]


@dataclass(frozen=True)
class Pass:
    """A pass of a match built outside `resolve()`, for `from_assignment()`: its name as
    the assignment's `pass` column spells it, its criteria in words, and the difference it
    tolerates, named, where its groups' two sides differ."""
    name: str
    criteria: str
    difference: str | None = None


@dataclass
class Resolution:
    items: pl.DataFrame
    matches: pl.DataFrame
    exceptions: pl.DataFrame
    summary: pl.DataFrame
    by_rule: pl.DataFrame
    rules: list[Rule | Pass] = field(default_factory=list)
    engine: str = "resolve"           # "resolve", or "assignment" from from_assignment()
    decimals: int = 2                 # the minor-unit places the values were matched at
    end: dt.date | None = None        # the date transit and age are measured at


def _key(e: pl.Expr) -> pl.Expr:
    """A value as a key: upper case, letters and digits only, no leading zeros."""
    return (e.cast(pl.Utf8).str.to_uppercase().str.replace_all(r"[^A-Z0-9]", "")
            .str.replace(r"^0+(\d)", "$1").replace("", None))


def _keyable(name: str, c: str, dtype) -> None:
    """A column compared as a key holds text, a category, an integer, a date or nothing."""
    if dtype.is_float() or dtype.is_decimal():
        raise ValueError(f"{name}: column {c!r} is {dtype} - a key compares as text, and a "
                         f"number held as {dtype} writes `1001.0` (keyed `10010`, never "
                         f"`1001`); cast it to text or an integer first")
    if not (dtype == pl.Utf8 or dtype == pl.Categorical or isinstance(dtype, pl.Enum)
            or dtype.is_integer() or dtype == pl.Date or dtype == pl.Null or dtype == pl.Boolean):
        raise ValueError(f"{name}: column {c!r} is {dtype} - a key column is text, a category, "
                         f"an integer or a date")


def _stream(df: pl.DataFrame, name: str, scale: int, used: set[str]) -> pl.DataFrame:
    """A stream checked and keyed: `day` (days since 1970), `c` (minor units), the columns
    the rules compare as text, and `quote`, the keys an item may be quoted by (left) or
    quotes (right). Any other column is ignored."""
    if not isinstance(df, pl.DataFrame):
        raise ValueError(f"{name} stream is a {type(df).__name__}, not a polars DataFrame")
    for c in ("id", "date", "value"):
        if c not in df.columns:
            raise ValueError(f"{name} stream lacks column {c!r}")
    if df["id"].dtype != pl.Null:
        _keyable(name, "id", df["id"].dtype)
    ids = df["id"].cast(pl.Utf8)
    if ids.null_count() or ids.n_unique() != df.height:
        raise ValueError(f"{name}: id must be present and unique")
    if ids.str.contains(";", literal=True).any():
        raise ValueError(f"{name}: an id may not contain ';', which separates the ids a match names")
    if not (df["value"].dtype.is_numeric() or df["value"].dtype == pl.Null) \
            or df["value"].dtype == pl.Boolean:
        raise ValueError(f"{name}: value is {df['value'].dtype}, not a number")
    v = df["value"].cast(pl.Float64)
    if v.null_count() or v.is_nan().any() or v.is_infinite().any():
        raise ValueError(f"{name}: value must be a finite number on every item")
    x = v * scale
    off = (x - x.round()).abs() > (v.abs() * scale * 2.0 ** -49).clip(lower_bound=1e-6)
    if off.any():
        k = off.arg_true()[0]
        raise ValueError(f"{name}: value {v[k]!r} on {ids[k]!r} is finer than the stated decimals")
    d = df["date"]
    if d.dtype == pl.Utf8:
        bad = d.is_not_null() & ~d.str.contains(ISO_TEXT).fill_null(False)
        iso = d.str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False)
        bad = bad | (d.is_not_null() & iso.is_null())
        if bad.any():
            raise ValueError(f"{name}: date text is ISO YYYY-MM-DD (a time may follow, no zone), "
                             f"got {d.filter(bad)[0]!r}")
        d = iso
    elif isinstance(d.dtype, pl.Datetime):
        if d.dtype.time_zone is not None:
            raise ValueError(f"{name}: date is a datetime in {d.dtype.time_zone} - its date "
                             f"depends on the zone; take the entity's local date first "
                             f"(periods.local_date) and give a Date")
        d = d.dt.date()
    elif not (d.dtype == pl.Date or d.dtype == pl.Null):
        raise ValueError(f"{name}: date must be a Date, a Datetime or ISO text, not {d.dtype}")
    keep = [c for c in df.columns if c in used | set(OPTIONAL) and c not in ("id", "date", "value")]
    for c in keep:
        _keyable(name, c, df[c].dtype)
    out = df.select(pl.col(c).cast(pl.Utf8) for c in keep)
    out = out.with_columns(id=ids, day=d.cast(pl.Date).cast(pl.Int32), c=x.round().cast(pl.Int64))
    for c in OPTIONAL:
        if c not in out.columns:
            out = out.with_columns(pl.lit(None, pl.Utf8).alias(c))
    quote = (pl.concat_list(_key(pl.col("id")), _key(pl.col("ref"))) if name == "left" else
             pl.col("text").str.extract_all(r"[A-Za-z0-9-]*\d[A-Za-z0-9-]*").list.eval(_key(pl.element())))
    return out.with_columns(quote=quote.list.eval(pl.element().filter(pl.element().str.len_chars() >= 4))
                            .list.unique()).sort("id")


def _group(S: pl.DataFrame, by: tuple[str, ...], on: tuple[str, ...]) -> pl.DataFrame:
    """The candidates on one side: each open item, or the open items sharing every `by`
    column (compared as keys) summed into one: its ids, total, date span, the rule's keys,
    and its references (`nref` distinct, `refkey` the one when there is one)."""
    keyed = [k for k in on if k != "quote"]
    keys = {f"k_{k}": _key(pl.col(k)) for k in keyed}
    one = S.select(g="id", ids=pl.concat_list("id"), c="c", lo="day", hi="day", quote="quote",
                   refkey=_key(pl.col("ref")), **keys).with_columns(
        nref=pl.col("refkey").is_not_null().cast(pl.UInt32))
    if not by:
        return one
    gk = {f"gk_{c}": (pl.col("day") if c == "date" else _key(pl.col(c))) for c in by}
    T = S.with_columns(refkey=_key(pl.col("ref")), **gk)
    whole = pl.all_horizontal(pl.col(c).is_not_null() for c in gk)
    many = T.filter(whole).group_by(list(gk)).agg(
        g=pl.col("id").min(), ids=pl.col("id").sort(), c=pl.col("c").sum(), lo=pl.col("day").min(),
        hi=pl.when(pl.col("day").null_count() == 0).then(pl.col("day").max()),
        quote=pl.col("quote").list.explode(keep_nulls=False, empty_as_null=False).unique(),
        nref=pl.col("refkey").drop_nulls().n_unique().cast(pl.UInt32),
        refkey=pl.col("refkey").drop_nulls().first(),
        **{k: pl.when(e.n_unique() == 1).then(e.first()) for k, e in keys.items()})
    return pl.concat([one.filter(pl.Series(~T.select(whole).to_series())), many.select(one.columns)])


# The most pairs a rule the counting path cannot take (a tolerance, a quote) may compare
# at once; past it the rule is refused.
MAX_PAIRS = 30_000_000


def _pairs(Lg: pl.DataFrame, Rg: pl.DataFrame, rule: Rule, scale: int) -> pl.DataFrame:
    """Every pair of left and right candidates the rule accepts: g, g_r, c, c_r, d."""
    keys = [f"k_{k}" for k in rule.on if k != "quote"] + (["c"] if rule.exact else [])
    cols = ["g", "c", "lo", "hi", "refkey", "nref"] + [k for k in keys if k != "c"]
    Ls, Rs = Lg.select(cols + (["quote"] if "quote" in rule.on else [])), \
        Rg.select(cols + (["quote"] if "quote" in rule.on else []))
    if not rule.exact:                     # a zero has no direction to tolerate a difference in
        Ls, Rs = Ls.filter(pl.col("c") != 0), Rs.filter(pl.col("c") != 0)
    if "quote" in rule.on:
        Ls, Rs = Ls.explode("quote", empty_as_null=False), Rs.explode("quote", empty_as_null=False)
        keys.append("quote")
    Rs = Rs.rename(lambda c: c if c in keys else c + "_r")
    if keys:
        n = (Ls.drop_nulls(keys).group_by(keys).len()
             .join(Rs.drop_nulls(keys).group_by(keys).len(), on=keys)
             .select((pl.col("len").cast(pl.Int64) * pl.col("len_right")).sum()).item() or 0)
    else:
        n = Ls.height * Rs.height
    if n > MAX_PAIRS:
        raise ValueError(f"rule {rule.name!r} would compare {n:,} pairs of candidates - give it "
                         f"a key (`on`) or a date window that narrows them")
    if keys:
        p = Ls.drop_nulls(keys).join(Rs.drop_nulls(keys), on=keys)
    elif rule.days is not None:                       # no key: the dates bound the pairs
        p = Ls.drop_nulls("hi").join_where(Rs.drop_nulls("hi_r"), pl.col("hi_r") >= pl.col("lo") + rule.days[0],
                                           pl.col("lo_r") <= pl.col("hi") + rule.days[1])
    else:
        p = Ls.join(Rs, how="cross")
    if "c_r" not in p.columns:
        p = p.with_columns(c_r=pl.col("c"))
    if rule.days is not None:
        p = p.filter(pl.col("hi_r") >= pl.col("lo") + rule.days[0], pl.col("lo_r") <= pl.col("hi") + rule.days[1])
    if "ref" not in rule.on:                         # an amount never overrides a reference
        p = p.filter((pl.col("nref") == 0) | (pl.col("nref_r") == 0)
                     | ((pl.col("nref") == 1) & (pl.col("nref_r") == 1)
                        & (pl.col("refkey") == pl.col("refkey_r"))))
    d = pl.col("c_r") - pl.col("c")
    way, size = d * pl.col("c").sign(), pl.col("c").abs()      # in the stream's direction
    p = p.filter((way >= size * rule.percent[0] + round(rule.tolerance[0] * scale))
                 & (way <= size * rule.percent[1] + round(rule.tolerance[1] * scale)))
    return p.select("g", "g_r", "c", "c_r", d=d).unique(["g", "g_r"])


def _reach(Q: pl.DataFrame, T: pl.DataFrame, K: list[str], dated: bool, guard: bool) -> pl.DataFrame:
    """How many target candidates each query candidate may pair with, counted without
    listing the pairs: `Q` (g, K, a, b, nref, refkey) and `T` (g, K, lo, hi, nref,
    refkey); a target qualifies when it shares every K, its span reaches [a, b]
    (hi >= a and lo <= b) when `dated`, and, under `guard`, no reference on either
    disagrees. Returns Q's g, `n`, and the one `partner` when n is 1."""
    # A target sits in its key's `*` partition (every reference) and in the partition of
    # its references: `0` none, `=<ref>` one, `m` several. A query looks in `*` when no
    # reference constrains it, else in `0` and, with one reference, in `=<ref>` too.
    rc = pl.when(pl.col("nref") == 0).then(pl.lit("0")).when(pl.col("nref") == 1) \
        .then(pl.lit("=") + pl.col("refkey")).otherwise(pl.lit("m"))
    T = T.select("g", *K, "lo", "hi", rc=rc)
    T = pl.concat([T.with_columns(rc=pl.lit("*")), T]) if guard else T.with_columns(rc=pl.lit("*"))
    look = (pl.concat_list(pl.lit("0"), pl.lit("=") + pl.col("refkey")) if guard else None)
    Q = Q.with_columns(rc=pl.when(pl.lit(not guard) | (pl.col("nref") == 0)).then(pl.concat_list(pl.lit("*")))
                       .when(pl.col("nref") == 1).then(look).otherwise(pl.concat_list(pl.lit("0")))
                       if guard else pl.concat_list(pl.lit("*"))).explode("rc")
    part = [*K, "rc"]
    if not dated:
        got = Q.join(T.group_by(part).agg(cnt=pl.len(), arg=pl.col("g").first()), on=part, how="left")
    else:
        Q, T = Q.drop_nulls(["a", "b"]), T.drop_nulls(["lo", "hi"])
        by_lo = (T.sort([*part, "lo", "hi"])
                 .with_columns(cl=pl.int_range(1, pl.len() + 1).over(part),
                               cm=pl.col("hi").cum_max().over(part))
                 .with_columns(arg=pl.when(pl.col("hi") == pl.col("cm")).then(pl.col("g"))
                               .forward_fill().over(part))
                 .group_by([*part, "lo"]).agg(pl.col("cl", "cm", "arg").last()).sort("lo"))
        by_hi = (T.sort([*part, "hi"]).with_columns(ch=pl.int_range(1, pl.len() + 1).over(part))
                 .group_by([*part, "hi"]).agg(pl.col("ch").last()).sort("hi"))
        got = (Q.with_columns(a1=pl.col("a") - 1).sort("b")
               .join_asof(by_lo, left_on="b", right_on="lo", by=part, strategy="backward",
                          check_sortedness=False)
               .sort("a1")
               .join_asof(by_hi, left_on="a1", right_on="hi", by=part, strategy="backward",
                          check_sortedness=False)
               .with_columns(cnt=pl.col("cl").fill_null(0) - pl.col("ch").fill_null(0)))
    got = got.with_columns(cnt=pl.col("cnt").fill_null(0).cast(pl.Int64))
    return got.group_by("g").agg(n=pl.col("cnt").sum(),
                                 partner=pl.col("arg").filter(pl.col("cnt") == 1).first())


def _candidates(L: pl.DataFrame, R: pl.DataFrame, rule: Rule, scale: int):
    """Each side's candidates under the rule: g, ids, c, `n` (how many on the other side
    it may pair with) and `partner` (the one, when n is 1). A rule wanting amounts equal
    and quoting nothing is counted by ranges (`_reach`), in the time a sort takes, however
    many items share an amount; any other lists its pairs (`_pairs`)."""
    Lg, Rg = _group(L, rule.group_left, rule.on), _group(R, rule.group_right, rule.on)
    if rule.exact and "quote" not in rule.on:
        K = [f"k_{k}" for k in rule.on] + ["c"]
        Lq, Rq = Lg.drop_nulls(K), Rg.drop_nulls(K)
        d0, d1 = rule.days if rule.days is not None else (0, 0)
        guard = "ref" not in rule.on
        cols = ["g", *K, "nref", "refkey"]
        nl = _reach(Lq.select(*cols, a=pl.col("lo") + d0, b=pl.col("hi") + d1),
                    Rq.select(*cols, "lo", "hi"), K, rule.days is not None, guard)
        nr = _reach(Rq.select(*cols, a=pl.col("lo") - d1, b=pl.col("hi") - d0),
                    Lq.select(*cols, "lo", "hi"), K, rule.days is not None, guard)
    else:
        p = _pairs(Lg, Rg, rule, scale)
        nl = p.group_by("g").agg(n=pl.len(), partner=pl.col("g_r").first())
        nr = p.group_by("g_r").agg(n=pl.len(), partner=pl.col("g").first()).rename({"g_r": "g"})
    side = lambda G, N: G.select("g", "ids", "c").join(N, on="g", how="left").with_columns(  # noqa: E731
        n=pl.col("n").fill_null(0).cast(pl.Int64),
        partner=pl.when(pl.col("n") == 1).then(pl.col("partner")))
    return side(Lg, nl), side(Rg, nr)


def _end(end, R: pl.DataFrame) -> dt.date | None:
    """The date transit and age are measured at: `end`, else the right side's last date."""
    if end is None:
        last = R["day"].max()
        return None if last is None else dt.date(1970, 1, 1) + dt.timedelta(days=int(last))
    if isinstance(end, dt.datetime):
        raise ValueError(f"end is the statement's end date, not a datetime {end!r}")
    if isinstance(end, str):
        try:
            return dt.date.fromisoformat(end)
        except ValueError:
            raise ValueError(f"end {end!r}: an ISO date YYYY-MM-DD") from None
    if isinstance(end, dt.date):
        return end
    raise ValueError(f"end {end!r}: a date")


def _precision(decimals, transit, transit_required: bool):
    if isinstance(decimals, bool) or not isinstance(decimals, int) or not 0 <= decimals <= 6:
        raise ValueError("decimals is a whole number of minor-unit places, 0 to 6")
    if transit is None and transit_required or transit is not None and (
            isinstance(transit, bool) or not isinstance(transit, int) or transit < 0):
        raise ValueError("transit is a whole number of days, 0 or more")
    return 10 ** decimals


def resolve(left: pl.DataFrame, right: pl.DataFrame, rule_set: list[Rule] | None = None, *,
            decimals: int = 2, transit: int | None = None, end=None) -> Resolution:
    """Match `left` to `right` by `rule_set` (default `rules()`), in order (module
    docstring). `end`: the statement's end (a date or ISO text), where transit and age are
    measured; default the right side's last date."""
    for name, df in (("left", left), ("right", right)):
        if not isinstance(df, pl.DataFrame):
            raise ValueError(f"{name} stream is a {type(df).__name__}, not a polars DataFrame")
    scale = _precision(decimals, transit, False)
    rule_set = rules() if rule_set is None else list(rule_set)
    names: set[str] = set()
    for r in rule_set:
        _check_rule(r)
        if r.name in names:
            raise ValueError(f"rule name {r.name!r} is used twice - each rule is named once, "
                             f"as the matches and the rules tab name it")
        names.add(r.name)
    for c in sorted({c for r in rule_set for c in r.on if c != "quote"}):
        inL, inR = c in left.columns, c in right.columns
        if inL != inR:
            raise ValueError(f"a rule compares {c!r}, which only the {'left' if inL else 'right'} "
                             f"stream has - a column a rule compares is on both sides (a number "
                             f"only one side has goes in `text`, or stays out)")
        if not inL and c != "ref":
            raise ValueError(f"a rule compares {c!r}, which neither stream has")
    for side, df, cols in (("left", left, {c for r in rule_set for c in r.group_left}),
                           ("right", right, {c for r in rule_set for c in r.group_right})):
        if missing := sorted(cols - set(df.columns) - {"date", *OPTIONAL}):
            raise ValueError(f"a rule sums the {side} items by {missing}, which the {side} "
                             f"stream lacks")
    used = {c for r in rule_set for c in r.on + r.group_left + r.group_right}
    L, R = _stream(left, "left", scale, used), _stream(right, "right", scale, used)
    open_L, open_R = set(L["id"]), set(R["id"])
    matches, why = [], {}
    for rule in rule_set:
        cl, cr = _candidates(L.filter(pl.col("id").is_in(list(open_L))),
                             R.filter(pl.col("id").is_in(list(open_R))), rule, scale)
        for side, mine, theirs in (("L", cl, cr), ("R", cr, cl)):
            amb = mine.join(theirs.select(partner="g", n_p="n"), on="partner", how="left").filter(
                (pl.col("n") > 1) | ((pl.col("n") == 1) & (pl.col("n_p") > 1)))
            for count_, members in amb.select("n", "ids").iter_rows():
                for x in members:
                    why.setdefault((side, x), f"{count_} candidates under {rule.name}" if count_ > 1
                                   else f"its candidate has another under {rule.name}")
        one = (cl.filter(pl.col("n") == 1)
               .join(cr.filter(pl.col("n") == 1).select(partner="g", back="partner", ids_r="ids", c_r="c"),
                     on="partner").filter(pl.col("back") == pl.col("g")).sort("g"))
        for ids_l, ids_r, c_l, c_r in one.select("ids", "ids_r", "c", "c_r").iter_rows():
            d = c_r - c_l
            matches.append((rule.name, ids_l, ids_r, c_l, c_r, d, rule.difference if d else None))
            open_L -= set(ids_l)
            open_R -= set(ids_r)
    if transit is None:
        transit = max(0, min((r.days[1] for r in rule_set if r.days is not None), default=0))
    return _report(L, R, rule_set, matches, why, open_L, open_R, scale, transit, _end(end, R),
                   decimals=decimals)


def from_assignment(left: pl.DataFrame, right: pl.DataFrame, assignment: pl.DataFrame,
                    passes: list[Pass], *, transit: int, decimals: int = 2, end=None) -> Resolution:
    """A match built outside `resolve()` as its Resolution (module docstring): `left` and
    `right` the streams, `assignment` one row per item of both (side, id, status, group,
    pass, reason), `passes` every pass it names, in the order they ran; `end` as for
    `resolve()`."""
    scale = _precision(decimals, transit, True)
    if not all(isinstance(p, Pass) and isinstance(p.name, str) and p.name for p in passes):
        raise ValueError("passes: each is a Pass with a name")
    order = {p.name: k for k, p in enumerate(passes)}
    if len(order) != len(passes):
        raise ValueError("passes: each pass is named once")
    L, R = _stream(left, "left", scale, set()), _stream(right, "right", scale, set())
    A = check_assignment(left, right, assignment, left_id="id", right_id="id", amount="value", tol=None)
    if extra := sorted(set(A["pass"].drop_nulls()) - set(order)):
        raise ValueError(f"the assignment names pass(es) {extra} that `passes` does not")
    c = {(side, i): v for side, S in (("left", L), ("right", R)) for i, v in S.select("id", "c").iter_rows()}
    matches = []
    for (g,), grp in A.filter(pl.col("status") == "matched").group_by("group"):
        ids_l = sorted(grp.filter(pl.col("side") == "left")["id"])
        ids_r = sorted(grp.filter(pl.col("side") == "right")["id"])
        if not ids_l or not ids_r:
            raise ValueError(f"group {g}: a match holds items of both sides")
        p = passes[order[grp["pass"][0]]]
        c_l, c_r = sum(c["left", i] for i in ids_l), sum(c["right", i] for i in ids_r)
        if c_r != c_l and not p.difference:
            raise ValueError(f"group {g}: its sides differ by {(c_r - c_l) / scale:.{decimals}f} and pass "
                             f"{p.name!r} names no difference")
        matches.append((p.name, ids_l, ids_r, c_l, c_r, c_r - c_l, p.difference if c_r != c_l else None))
    matches.sort(key=lambda m: (order[m[0]], m[1][0]))
    why, held = {}, set()
    for side, i, st, p, reason in A.filter(pl.col("status") != "matched").select(
            "side", "id", "status", "pass", "reason").iter_rows():
        if st == "excluded":
            why["L" if side == "left" else "R", i] = f"excluded by {p}: {reason}"
            if side == "left":
                held.add(i)
        else:
            why["L" if side == "left" else "R", i] = reason or "no candidate under any pass"
    open_L = set(L["id"]) - {i for m in matches for i in m[1]}
    open_R = set(R["id"]) - {i for m in matches for i in m[2]}
    return _report(L, R, list(passes), matches, why, open_L, open_R, scale, int(transit), _end(end, R),
                   held, "assignment", decimals)


def _report(L, R, rule_set, matches, why, open_L, open_R, s, transit, end, held=frozenset(),
            engine="resolve", decimals=2) -> Resolution:
    kind = lambda a, b: f"{'1' if len(a) == 1 else 'n'}:{'1' if len(b) == 1 else 'n'}"  # noqa: E731
    mt = pl.DataFrame([(k, rn, kind(a, b), ";".join(a), ";".join(b), cl / s, cr / s, d / s, dn)
                       for k, (rn, a, b, cl, cr, d, dn) in enumerate(matches, start=1)], orient="row",
                      schema={"group": pl.Int64, "rule": pl.Utf8, "type": pl.Utf8, "left_ids": pl.Utf8,
                              "right_ids": pl.Utf8, "left_amount": pl.Float64, "right_amount": pl.Float64,
                              "difference": pl.Float64, "difference_name": pl.Utf8})
    per_item = pl.concat([
        mt.select("group", "rule", "type", "difference", side=pl.lit(side), id=pl.col(mine).str.split(";"),
                  matched_to=theirs).explode("id", empty_as_null=False)
        for side, mine, theirs in (("left", "left_ids", "right_ids"), ("right", "right_ids", "left_ids"))])
    ids = pl.concat([L.select("id", side=pl.lit("left")), R.select("id", side=pl.lit("right"))])
    reasons = pl.DataFrame([(("left" if s_ == "L" else "right"), x, r) for (s_, x), r in why.items()],
                           orient="row", schema={"side": pl.Utf8, "id": pl.Utf8, "why": pl.Utf8})
    items = (ids.join(per_item, on=["side", "id"], how="left").join(reasons, on=["side", "id"], how="left")
             .select("side", "id", status=pl.when(pl.col("group").is_null()).then(pl.lit("unmatched"))
                     .otherwise(pl.lit("matched")), group="group", **{"pass": "rule"},
                     reason=pl.when(pl.col("group").is_null())
                     .then(pl.col("why").fill_null("no candidate under any rule")),
                     type="type", matched_to="matched_to", difference="difference"))
    last = None if end is None else (end - dt.date(1970, 1, 1)).days
    ex = pl.concat([
        S.filter(pl.col("id").is_in(list(open_))).select(
            side=pl.lit(side), id="id", date=pl.col("day").cast(pl.Date), amount=pl.col("c") / s, c="c",
            entity="entity", in_transit=(pl.col("day") + transit > pl.lit(last, pl.Int32)).fill_null(False)
            & pl.lit(side == "left") & ~pl.col("id").is_in(list(held)),
            age=pl.lit(last, pl.Int32) - pl.col("day"))
        for side, S, open_ in (("left", L, open_L), ("right", R, open_R))])
    ex = ex.join(items.select("side", "id", "reason"), on=["side", "id"]).sort("side", "date", "id", nulls_last=True)
    un_l, un_r = ex.filter(pl.col("side") == "left"), ex.filter(pl.col("side") == "right")
    transit_, other = un_l.filter("in_transit"), un_l.filter(~pl.col("in_transit"))
    lines = [("left_total", L["c"]), ("left_in_transit", -transit_["c"]), ("left_unmatched", -other["c"])]
    lines += [(f"difference:{n}", (g["difference"] * s).round().cast(pl.Int64)) for (n,), g in
              mt.filter(pl.col("difference") != 0).group_by("difference_name", maintain_order=True)]
    lines += [("right_unmatched", un_r["c"]), ("right_total", R["c"])]
    off = sum(v.sum() for _, v in lines[:-1]) - lines[-1][1].sum()
    if off != 0:
        raise RuntimeError(f"the reconciliation does not foot by {off} minor units")
    summary = pl.DataFrame([(k, v.len(), v.sum() / s, v.filter(v > 0).sum() / s, v.filter(v < 0).sum() / s)
                            for k, v in lines], orient="row",
                           schema={"line": pl.Utf8, "items": pl.Int64, "amount": pl.Float64,
                                   "plus": pl.Float64, "minus": pl.Float64})
    ex = ex.drop("c")
    by_rule = (pl.DataFrame({"rule": [r.name for r in rule_set], "criteria": [r.criteria for r in rule_set]})
               .join(mt.group_by("rule").agg(matches=pl.len(),
                                             left_items=pl.col("left_ids").str.split(";").list.len().sum(),
                                             left_amount=pl.col("left_amount").sum(),
                                             right_items=pl.col("right_ids").str.split(";").list.len().sum(),
                                             right_amount=pl.col("right_amount").sum(),
                                             difference=pl.col("difference").sum()),
                     on="rule", how="left", maintain_order="left").fill_null(0))
    return Resolution(items.sort("side", "id"), mt, ex, summary, by_rule, list(rule_set), engine,
                      decimals, end)


def chain(*results: Resolution) -> pl.DataFrame:
    """Each left item of the first call traced through the calls after it, call k's right
    ids being call k+1's left ids. One row per item: `status` traced (every step matched),
    partly traced (the step it `stopped` at matched some of what reached it) or open, the
    `reason` of the first item (by id) left at that step, the `rules` of each step, and the
    last call's right ids it `reaches`."""
    if not results:
        raise ValueError("chain() takes one resolution or more")
    if not all(isinstance(r, Resolution) for r in results):
        raise ValueError("chain() takes Resolutions, from resolve() or from_assignment()")
    front = results[0].items.filter(pl.col("side") == "left").select(start="id", id="id")
    out = front.select(id="start")
    for k, r in enumerate(results, start=1):
        step = front.join(r.items.filter(pl.col("side") == "left"), on="id", how="left").with_columns(
            ok=(pl.col("status") == "matched").fill_null(False),
            reason=pl.col("reason").fill_null(pl.lit(f"not among call {k}'s left items"))).sort("start", "id")
        out = out.join(step.group_by("start", maintain_order=True).agg(
            **{f"all{k}": pl.col("ok").all(), f"any{k}": pl.col("ok").any(),
               f"why{k}": pl.col("reason").filter(~pl.col("ok")).first(),
               f"rules{k}": pl.col("pass").drop_nulls().unique().sort().str.join(", ")}).rename({"start": "id"}),
                       on="id", how="left")
        front = (step.filter("ok").select("start", id=pl.col("matched_to").str.split(";"))
                 .explode("id", empty_as_null=False).unique())
    n = range(1, len(results) + 1)
    stop = lambda c: pl.coalesce(pl.when(~pl.col(f"all{k}").fill_null(False)).then(c(k)) for k in n)  # noqa: E731
    reached = front.group_by("start").agg(reaches=pl.col("id").sort().str.join(";")).rename({"start": "id"})
    return (out.join(reached, on="id", how="left").select(
        "id", status=pl.when(stop(lambda k: pl.lit(k)).is_null()).then(pl.lit("traced"))
        .when(stop(lambda k: pl.col(f"any{k}"))).then(pl.lit("partly traced")).otherwise(pl.lit("open")),
        stopped=stop(lambda k: pl.lit(k)), reason=stop(lambda k: pl.col(f"why{k}")),
        rules=pl.concat_str([pl.when(pl.col(f"rules{k}") != "").then(pl.col(f"rules{k}")) for k in n],
                            separator=" > ", ignore_nulls=True),
        reaches="reaches").sort("id"))
