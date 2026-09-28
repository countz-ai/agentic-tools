#!/usr/bin/env python3
"""Match two streams of transactions by ordered rules, the way reconciliation software does
(NetSuite's bank-data matching, BlackLine's transaction matching), and list what is left.

Two records of the same money are matched: a cash book's deposits and the bank's credits,
its payments and the bank's debits, an invoice register and a cash-application file. Each
rule compares the items the rules before it left open; a pair matches only where each is
the other's one candidate under the rule. What no rule matches is an exception, for a
person to clear. Every match names its rule.

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from resolve import Rule, resolve, rules

    res = resolve(book, bank, rules(window=(0, 3), same_entity=True))
    res.items       # one row per item of both streams (check_assignment() accepts it)
    res.matches     # one row per match: its rule, type, both sides' ids and totals, difference
    res.exceptions  # every unmatched item, with its reason and its age at the statement's end
    res.summary     # the reconciliation, left total to right total; it foots
    res.by_rule     # what each rule matched

**Using it.**

1. Map each population whole, one direction per call: receipts, or payments, never both.
   Each stream is a polars DataFrame of `id` (unique text, no `;`), `date` (a Date,
   Datetime or ISO text; null where the record has none) and `value` (same currency and
   sign on both sides, no finer than `decimals`), with any other columns a rule compares:
   `entity` (a customer, a payee, an account), `ref` (a transaction, cheque or invoice
   number), `text` (a bank description), `batch` (the lines of one deposit), `slip`.
2. Choose the rules. `rules()` gives the defaults below; add a `Rule` for what the records
   name that they do not (a processor's fee, a bank's conversion). Measure `window` on the
   data: the days from the left date to the right date that the matches show.
3. Read each item's `status`: `matched` names its rule (`pass`), its group and what it
   matched to; `unmatched` states why (no candidate, or the count of candidates a rule
   found). The exceptions are yours to clear with the records the engine cannot read.
4. `res.summary` is the reconciliation: the left total, less the left items not matched,
   plus the right items not matched, plus each named difference, is the right total.
5. Show the result with `scripts/match_tabs.py`.

**A rule** compares the open items of both sides:
- `on`: columns that must be equal, compared as keys (case, spaces, punctuation and
  leading zeros dropped). `quote` is special: the right item's `text` quotes the left
  item's `id` or `ref`.
- `days`: (lo, hi), the right date less the left date, inclusive; None, dates not
  compared. An undated item is matched only by a rule that does not compare dates.
- `group_left`, `group_right`: first sum the open items sharing these columns into one (a
  customer's items of one day; the lines of one deposit), dated over their span.
- amounts equal, or `tolerance` (currency) and `percent` (of the left amount) apart, each
  a (lo, hi) range, negative where the right side carries less; the difference is
  reported under `difference`.
A pair matches when it meets the rule and neither side has another candidate under it.
An item with two candidates or more is left for the next rule.

**The default rules**, `rules(window, wide, same_entity)`, in order, after NetSuite's:
reference (same `ref` and amount, any date); reference, totals (the items sharing a `ref`
on each side, totals equal); quoted (the right text quotes the left `id` or `ref`, same
amount, any date); amount and date (same amount within `window`); deposit lines (one left
item, the lines of one right `batch`); day's items (a left `entity`'s items of one day, one
right item); day's items, deposit lines (both at once); amount, wide (same amount within
`wide`). `same_entity` adds `entity` to
every rule, where both sides name the same party or account.

Run with no arguments to self-check.
"""
from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass, field

import polars as pl

__all__ = ["Rule", "Resolution", "resolve", "rules"]


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


def rules(window=(0, 2), wide=(0, 89), same_entity=False) -> list[Rule]:
    """The default rule set (module docstring)."""
    e = ("entity",) if same_entity else ()
    return [Rule("reference", e + ("ref",), None),
            Rule("reference, totals", e + ("ref",), None, ("ref",), ("ref",)),
            Rule("quoted", e + ("quote",), None),
            Rule("amount and date", e, tuple(window)),
            Rule("deposit lines", e, tuple(window), group_right=("batch",)),
            Rule("day's items", e, tuple(window), group_left=("entity", "date")),
            Rule("day's items, deposit lines", e, tuple(window), group_left=("entity", "date"),
                 group_right=("batch",)),
            Rule("amount, wide", e, tuple(wide))]


@dataclass
class Resolution:
    items: pl.DataFrame
    matches: pl.DataFrame
    exceptions: pl.DataFrame
    summary: pl.DataFrame
    by_rule: pl.DataFrame
    rules: list[Rule] = field(default_factory=list)


def _key(e: pl.Expr) -> pl.Expr:
    """A value as a key: upper case, letters and digits only, no leading zeros."""
    return (e.cast(pl.Utf8).str.to_uppercase().str.replace_all(r"[^A-Z0-9]", "")
            .str.replace(r"^0+(\d)", "$1").replace("", None))


def _stream(df: pl.DataFrame, name: str, scale: int, used: set[str]) -> pl.DataFrame:
    """A stream checked and keyed: `day` (days since 1970), `c` (minor units), the columns
    the rules compare as text, and `quote`, the keys an item may be quoted by (left) or
    quotes (right). Any other column is ignored."""
    for c in ("id", "date", "value"):
        if c not in df.columns:
            raise ValueError(f"{name} stream lacks column {c!r}")
    ids = df["id"].cast(pl.Utf8)
    if ids.null_count() or ids.n_unique() != df.height:
        raise ValueError(f"{name}: id must be present and unique")
    if ids.str.contains(";", literal=True).any():
        raise ValueError(f"{name}: an id may not contain ';', which separates the ids a match names")
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
        iso = d.str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False)
        if (bad := d.is_not_null() & iso.is_null()).any():
            raise ValueError(f"{name}: date text must be ISO YYYY-MM-DD, got {d.filter(bad)[0]!r}")
        d = iso
    elif not (d.dtype == pl.Date or isinstance(d.dtype, pl.Datetime) or d.dtype == pl.Null):
        raise ValueError(f"{name}: date must be a Date, a Datetime or ISO text, not {d.dtype}")
    out = df.select(pl.col(c).cast(pl.Utf8) for c in df.columns
                    if c in used | {"entity", "ref", "text", "batch"} and c not in ("id", "date", "value"))
    out = out.with_columns(id=ids, day=d.cast(pl.Date).cast(pl.Int32), c=x.round().cast(pl.Int64))
    for c in ("entity", "ref", "text", "batch"):
        if c not in out.columns:
            out = out.with_columns(pl.lit(None, pl.Utf8).alias(c))
    quote = (pl.concat_list(_key(pl.col("id")), _key(pl.col("ref"))) if name == "left" else
             pl.concat_list(pl.col("text").str.extract_all(r"[A-Za-z0-9-]*\d[A-Za-z0-9-]*")
                            .list.eval(_key(pl.element())), _key(pl.col("ref"))))
    return out.with_columns(quote=quote.list.eval(pl.element().filter(pl.element().str.len_chars() >= 4))
                            .list.unique()).sort("id")


def _group(S: pl.DataFrame, by: tuple[str, ...], on: tuple[str, ...]) -> pl.DataFrame:
    """The candidates on one side: each open item, or the open items sharing every `by`
    column summed into one: its ids, total, date span and the rule's keys."""
    by = tuple("day" if c == "date" else c for c in by)
    keyed = [k for k in on if k != "quote"]
    keys = {f"k_{k}": _key(pl.col(k)) for k in keyed}
    one = S.select(g="id", ids=pl.concat_list("id"), c="c", lo="day", hi="day", quote="quote", **keys)
    if not by:
        return one
    whole = pl.all_horizontal(pl.col(c).is_not_null() for c in by)
    many = S.filter(whole).group_by(by).agg(
        g=pl.col("id").min(), ids=pl.col("id").sort(), c=pl.col("c").sum(), lo=pl.col("day").min(),
        hi=pl.when(pl.col("day").null_count() == 0).then(pl.col("day").max()),
        quote=pl.col("quote").list.explode(keep_nulls=False, empty_as_null=False).unique(),
        **{k: pl.when(e.n_unique() == 1).then(e.first()) for k, e in keys.items()})
    return pl.concat([one.filter(pl.Series(~S.select(whole).to_series())), many.select(one.columns)])


def _pairs(L: pl.DataFrame, R: pl.DataFrame, rule: Rule, scale: int) -> pl.DataFrame:
    """Every pair of left and right candidates the rule accepts, with the difference d."""
    Lg, Rg = _group(L, rule.group_left, rule.on), _group(R, rule.group_right, rule.on)
    keys = [f"k_{k}" for k in rule.on if k != "quote"] + (["c"] if rule.exact else [])
    if "quote" in rule.on:
        Lg, Rg = Lg.explode("quote", empty_as_null=False), Rg.explode("quote", empty_as_null=False)
        keys.append("quote")
    Rg = Rg.rename(lambda c: c if c in keys else c + "_r")
    if keys:
        p = Lg.drop_nulls(keys).join(Rg.drop_nulls(keys), on=keys)
    elif rule.days is not None:                       # no key: the dates bound the pairs
        p = Lg.drop_nulls("hi").join_where(Rg.drop_nulls("hi_r"), pl.col("hi_r") >= pl.col("lo") + rule.days[0],
                                           pl.col("lo_r") <= pl.col("hi") + rule.days[1])
    else:
        p = Lg.join(Rg, how="cross")
    if "c_r" not in p.columns:
        p = p.with_columns(c_r=pl.col("c"))
    if rule.days is not None:
        p = p.filter(pl.col("hi_r") >= pl.col("lo") + rule.days[0], pl.col("lo_r") <= pl.col("hi") + rule.days[1])
    d = pl.col("c_r") - pl.col("c")
    way, size = d * pl.col("c").sign(), pl.col("c").abs()      # in the stream's direction
    p = p.filter((way >= size * rule.percent[0] + round(rule.tolerance[0] * scale))
                 & (way <= size * rule.percent[1] + round(rule.tolerance[1] * scale)))
    return p.select("g", "g_r", "ids", "ids_r", "c", "c_r", d=d).unique(["g", "g_r"])


def resolve(left: pl.DataFrame, right: pl.DataFrame, rule_set: list[Rule] | None = None, *,
            decimals: int = 2) -> Resolution:
    """Match `left` to `right` by `rule_set` (default `rules()`), in order (module docstring)."""
    if int(decimals) != decimals or not 0 <= decimals <= 6:
        raise ValueError("decimals is a whole number of minor-unit places, 0 to 6")
    scale = 10 ** int(decimals)
    rule_set = rules() if rule_set is None else list(rule_set)
    for r in rule_set:
        if not r.exact and not r.difference:
            raise ValueError(f"rule {r.name!r}: a tolerance names the difference it allows")
    used = {c for r in rule_set for c in r.on + r.group_left + r.group_right}
    L, R = _stream(left, "left", scale, used), _stream(right, "right", scale, used)
    open_L, open_R = set(L["id"]), set(R["id"])
    matches, why = [], {}
    for rule in rule_set:
        p = _pairs(L.filter(pl.col("id").is_in(list(open_L))), R.filter(pl.col("id").is_in(list(open_R))),
                   rule, scale)
        p = p.with_columns(n_l=pl.len().over("g"), n_r=pl.len().over("g_r"))
        for side, ids, n in (("L", "ids", "n_l"), ("R", "ids_r", "n_r")):
            for count_, members in p.filter((pl.col("n_l") > 1) | (pl.col("n_r") > 1)).select(n, ids).iter_rows():
                for x in members:
                    why.setdefault((side, x), f"{count_} candidates under {rule.name}" if count_ > 1 else
                                   f"its candidate has another under {rule.name}")
        for ids_l, ids_r, c_l, c_r, d in (p.filter(pl.col("n_l") == 1, pl.col("n_r") == 1).sort("g")
                                          .select("ids", "ids_r", "c", "c_r", "d").iter_rows()):
            matches.append((rule.name, ids_l, ids_r, c_l, c_r, d, rule.difference if d else None))
            open_L -= set(ids_l)
            open_R -= set(ids_r)
    return _report(L, R, rule_set, matches, why, open_L, open_R, scale)


def _report(L, R, rule_set, matches, why, open_L, open_R, s) -> Resolution:
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
    last = R["day"].max()
    ex = pl.concat([
        S.filter(pl.col("id").is_in(list(open_))).select(
            side=pl.lit(side), id="id", date=pl.col("day").cast(pl.Date), amount=pl.col("c") / s, c="c",
            entity="entity", after_end=(pl.col("day") > pl.lit(last, pl.Int32)).fill_null(False),
            age=pl.lit(last, pl.Int32) - pl.col("day"))
        for side, S, open_ in (("left", L, open_L), ("right", R, open_R))])
    ex = ex.join(items.select("side", "id", "reason"), on=["side", "id"]).sort("side", "date", "id", nulls_last=True)
    un_l, un_r = ex.filter(pl.col("side") == "left"), ex.filter(pl.col("side") == "right")
    after, before = un_l.filter("after_end"), un_l.filter(~pl.col("after_end"))
    lines = [("left_total", L.height, L["c"].sum()), ("left_after_end", after.height, -after["c"].sum()),
             ("left_unmatched", before.height, -before["c"].sum())]
    lines += [(f"difference:{n}", g.height, round(g["difference"].sum() * s)) for (n,), g in
              mt.filter(pl.col("difference") != 0).group_by("difference_name", maintain_order=True)]
    lines += [("right_unmatched", un_r.height, un_r["c"].sum()), ("right_total", R.height, R["c"].sum())]
    off = sum(v for _, _, v in lines[:-1]) - lines[-1][2]
    assert off == 0, f"the reconciliation does not foot by {off}"
    summary = pl.DataFrame([(k, n, v / s) for k, n, v in lines], orient="row",
                           schema={"line": pl.Utf8, "items": pl.Int64, "amount": pl.Float64})
    ex = ex.drop("c")
    by_rule = (pl.DataFrame({"rule": [r.name for r in rule_set], "criteria": [r.criteria for r in rule_set]})
               .join(mt.group_by("rule").agg(matches=pl.len(),
                                             left_items=pl.col("left_ids").str.split(";").list.len().sum(),
                                             left_amount=pl.col("left_amount").sum(),
                                             right_items=pl.col("right_ids").str.split(";").list.len().sum(),
                                             right_amount=pl.col("right_amount").sum(),
                                             difference=pl.col("difference").sum()),
                     on="rule", how="left", maintain_order="left").fill_null(0))
    return Resolution(items.sort("side", "id"), mt, ex, summary, by_rule, list(rule_set))


# ---------------------------------------------------------------------------- self-check
def _selfcheck() -> int:
    bad: list[str] = []

    def expect(cond, what):
        if not cond:
            bad.append(what)
    D = dt.date(2024, 3, 1)
    cols = ("id", "date", "value", "entity", "ref", "text", "batch")
    frame = lambda rows: pl.DataFrame([tuple(r) + (None,) * (len(cols) - len(r)) for r in rows], orient="row",  # noqa: E731
                                      schema={c: pl.Date if c == "date" else pl.Float64 if c == "value"
                                              else pl.Utf8 for c in cols})
    day = lambda n: D + dt.timedelta(days=n)  # noqa: E731
    book = frame([("b1", day(0), 100.37, "OPER", "1001"),          # its cheque number on the bank
                  ("b2", day(0), 250.13, "OPER"),                  # same amount, a day later
                  ("b3", day(1), 75.25, "OPER"), ("b4", day(1), 75.25, "OPER"),   # twins
                  ("b5", day(2), 40.00, "OPER"), ("b6", day(2), 60.01, "OPER"),   # one slip
                  ("b7", day(3), 500.00, "OPER"),                  # credited on two lines
                  ("b8", day(4), 1000.00, "MERCH"),                # net of a fee
                  ("b9", day(30), 99.99, "OPER"),                  # after the statement
                  ("b10", None, 12.34, "OPER")])                   # undated
    bank = frame([("x1", day(5), 100.37, "OPER", None, "CHECK 1001"),
                  ("x2", day(1), 250.13, "OPER"),
                  ("x3", day(1), 75.25, "OPER"), ("x4", day(2), 75.25, "OPER"),
                  ("x5", day(3), 100.01, "OPER"),
                  ("x6", day(4), 200.00, "OPER", None, None, "D7"), ("x7", day(4), 300.00, "OPER", None, None, "D7"),
                  ("x8", day(5), 971.00, "MERCH"),
                  ("x9", day(9), -35.00, "OPER", None, "SERVICE CHARGE")])
    fee = Rule("card fee", ("entity",), (0, 3), percent=(-0.035, -0.015), difference="card fee")
    rs = rules(window=(0, 2), same_entity=True) + [fee]
    res = resolve(book, bank, rs)
    it = {(r["side"], r["id"]): r for r in res.items.iter_rows(named=True)}
    expect(it[("left", "b1")]["pass"] == "quoted" and it[("left", "b1")]["matched_to"] == "x1",
           f"a number the bank quotes matches whatever the dates: {it[('left', 'b1')]}")
    expect(it[("left", "b2")]["pass"] == "amount and date", "an amount the only one within the window matches")
    expect(it[("left", "b3")]["status"] == it[("left", "b4")]["status"] == "unmatched"
           and "candidates" in (it[("left", "b3")]["reason"] or ""), "twins are left for a person, with the count")
    expect(it[("left", "b5")]["pass"] == "day's items" and it[("left", "b5")]["type"] == "n:1",
           f"a day's items against one line, n:1: {it[('left', 'b5')]}")
    expect(it[("left", "b7")]["pass"] == "deposit lines" and it[("left", "b7")]["type"] == "1:n",
           f"a deposit's lines against one item, 1:n: {it[('left', 'b7')]}")
    expect(it[("left", "b8")]["pass"] == "card fee" and it[("left", "b8")]["difference"] == -29.0,
           f"a tolerated difference is matched and named: {it[('left', 'b8')]}")
    expect(it[("left", "b10")]["status"] == "unmatched" and it[("right", "x9")]["status"] == "unmatched",
           "what no rule reaches stays open")
    walk = dict((k, v) for k, _, v in res.summary.iter_rows())
    expect(walk["left_after_end"] == -99.99 and walk["difference:card fee"] == -29.0
           and abs(walk["right_unmatched"] - (75.25 * 2 - 35.00)) < 1e-9, f"the reconciliation's lines: {walk}")
    expect(res.by_rule.filter(pl.col("rule") == "quoted")["matches"][0] == 1, "each rule's count")
    for a, b in ((book.reverse(), bank.reverse()), (book.sample(fraction=1, shuffle=True, seed=3), bank)):
        expect(resolve(a, b, rs).items.equals(res.items, null_equal=True), "row order does not matter")
    for bad_left, what in ((book.with_columns(date=pl.lit("03/04/2024")), "a date not ISO"),
                           (book.with_columns(value=pl.lit(1.005)), "a value finer than cents"),
                           (book.with_columns(id=pl.lit("x")), "repeated ids")):
        try:
            resolve(bad_left, bank)
            bad.append(f"did not refuse {what}")
        except ValueError:
            pass
    try:
        from matching import check_assignment
        check_assignment(book, bank, res.items, left_id="id", right_id="id", amount="value", tol=None)
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        bad.append(f"check_assignment refused the output: {e}")
    for b in bad:
        print("FAIL", b)
    print("resolve.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    sys.exit(_selfcheck())
