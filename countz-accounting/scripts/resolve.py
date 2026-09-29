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
   theirs), never both. Each stream is a polars DataFrame of `id` (unique text, no `;`),
   `date` (a Date, Datetime or ISO text; null where the record has none) and `value` (same
   currency and sign convention on both sides, no finer than `decimals`), with any other
   columns a rule compares: `entity` (a customer, a payee, an account), `ref` (a cheque,
   deposit or invoice number the other side carries too), `text` (a bank description),
   `batch` (the lines of one deposit), `slip`. Where the source's own key repeats (a deposit id on
   each of its lines, a payment id on each invoice it pays), build the id from the file and
   the row, or from the key and a second column; the key itself is `batch` when it groups
   one deposit's lines, and `ref` only when the other side's `ref` numbers the same thing.
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
  leading zeros dropped). `ref` is a number both sides carry for the same thing (a cheque
  number on the book and on the bank); a number only one side has goes in `text`, or stays
  out. `quote` is special: the right item's `text` quotes the left item's `id` or `ref`.
  A rule that does not compare `ref` never pairs two items whose references both exist
  and differ: an amount never overrides a reference. An item whose column is empty is not
  a candidate under a rule that compares that column, so a column set only on the records
  a rule applies to scopes the rule to them (the currency of a foreign receipt, and the
  currency the statement says it converted, for a rule that tolerates a conversion).
- `days`: (lo, hi), the right date less the left date, inclusive; None, dates not
  compared. An undated item is matched only by a rule that does not compare dates.
- `group_left`, `group_right`: first sum the open items sharing these columns into one (a
  customer's items of one day; the lines of one deposit), dated over their span.
- amounts equal, or `tolerance` (currency) and `percent` (of the left amount) apart, each
  a (lo, hi) range, negative where the right side carries less; the difference is
  reported under `difference`.
A pair matches when it meets the rule and neither side has another candidate under it.
An item with two candidates or more is left for the next rule. An unmatched left item is
in transit when its date, plus `transit` days, reaches past the right side's last date: its
right item would be on a later statement. `transit` is how long the flow's items take to
reach the bank (a receipt a few days, a cheque paid out weeks); by default the end of the
narrowest window a rule compares dates over.

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

import pathlib
import sys
from dataclasses import dataclass, field

import polars as pl

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from matching import check_assignment  # noqa: E402

__all__ = ["Pass", "Rule", "Resolution", "chain", "from_assignment", "resolve", "rules"]


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
             pl.col("text").str.extract_all(r"[A-Za-z0-9-]*\d[A-Za-z0-9-]*").list.eval(_key(pl.element())))
    return out.with_columns(quote=quote.list.eval(pl.element().filter(pl.element().str.len_chars() >= 4))
                            .list.unique()).sort("id")


def _group(S: pl.DataFrame, by: tuple[str, ...], on: tuple[str, ...]) -> pl.DataFrame:
    """The candidates on one side: each open item, or the open items sharing every `by`
    column summed into one: its ids, total, date span and the rule's keys."""
    by = tuple("day" if c == "date" else c for c in by)
    keyed = [k for k in on if k != "quote"]
    keys = {f"k_{k}": _key(pl.col(k)) for k in keyed} | {"refkey": _key(pl.col("ref"))}
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
    if "ref" not in rule.on:                         # an amount never overrides a reference
        p = p.filter(pl.col("refkey").is_null() | pl.col("refkey_r").is_null()
                     | (pl.col("refkey") == pl.col("refkey_r")))
    d = pl.col("c_r") - pl.col("c")
    way, size = d * pl.col("c").sign(), pl.col("c").abs()      # in the stream's direction
    p = p.filter((way >= size * rule.percent[0] + round(rule.tolerance[0] * scale))
                 & (way <= size * rule.percent[1] + round(rule.tolerance[1] * scale)))
    return p.select("g", "g_r", "ids", "ids_r", "c", "c_r", d=d).unique(["g", "g_r"])


def resolve(left: pl.DataFrame, right: pl.DataFrame, rule_set: list[Rule] | None = None, *,
            decimals: int = 2, transit: int | None = None) -> Resolution:
    """Match `left` to `right` by `rule_set` (default `rules()`), in order (module docstring)."""
    if int(decimals) != decimals or not 0 <= decimals <= 6:
        raise ValueError("decimals is a whole number of minor-unit places, 0 to 6")
    if transit is not None and (int(transit) != transit or transit < 0):
        raise ValueError("transit is a whole number of days, 0 or more")
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
    if transit is None:
        transit = max(0, min((r.days[1] for r in rule_set if r.days is not None), default=0))
    return _report(L, R, rule_set, matches, why, open_L, open_R, scale, transit)


def from_assignment(left: pl.DataFrame, right: pl.DataFrame, assignment: pl.DataFrame,
                    passes: list[Pass], *, transit: int, decimals: int = 2) -> Resolution:
    """A match built outside `resolve()` as its Resolution (module docstring): `left` and
    `right` the streams, `assignment` one row per item of both (side, id, status, group,
    pass, reason), `passes` every pass it names, in the order they ran."""
    if int(decimals) != decimals or not 0 <= decimals <= 6:
        raise ValueError("decimals is a whole number of minor-unit places, 0 to 6")
    if int(transit) != transit or transit < 0:
        raise ValueError("transit is a whole number of days, 0 or more")
    scale = 10 ** int(decimals)
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
    return _report(L, R, list(passes), matches, why, open_L, open_R, scale, int(transit), held, "assignment")


def _report(L, R, rule_set, matches, why, open_L, open_R, s, transit, held=frozenset(),
            engine="resolve") -> Resolution:
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
    assert off == 0, f"the reconciliation does not foot by {off}"
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
    return Resolution(items.sort("side", "id"), mt, ex, summary, by_rule, list(rule_set), engine)


def chain(*results: Resolution) -> pl.DataFrame:
    """Each left item of the first call traced through the calls after it, call k's right
    ids being call k+1's left ids. One row per item: `status` traced (every step matched),
    partly traced (the step it `stopped` at matched some of what reached it) or open, the
    `reason` of the first item left at that step, the `rules` of each step, and the last
    call's right ids it `reaches`."""
    if not results:
        raise ValueError("chain() takes one resolution or more")
    front = results[0].items.filter(pl.col("side") == "left").select(start="id", id="id")
    out = front.select(id="start")
    for k, r in enumerate(results, start=1):
        step = front.join(r.items.filter(pl.col("side") == "left"), on="id", how="left").with_columns(
            ok=(pl.col("status") == "matched").fill_null(False),
            reason=pl.col("reason").fill_null(pl.lit(f"not among call {k}'s left items")))
        out = out.join(step.group_by("start").agg(
            **{f"all{k}": pl.col("ok").all(), f"any{k}": pl.col("ok").any(),
               f"why{k}": pl.col("reason").filter(~pl.col("ok")).sort().first(),
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
