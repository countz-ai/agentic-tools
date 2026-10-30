#!/usr/bin/env python3
"""Check a match you built: every item of both populations accounted for exactly once.

Match with polars (or SQL) in your own step code — a join per pass, in the order the data
room calls for — then hand the assignment to `check_assignment()` before writing the
match table. The module has no matching rule of its own; it checks the bookkeeping.

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from matching import check_assignment

    # assignment: one row per item — side ("left"|"right"), id, status
    # (matched|excluded|unmatched), group (matched rows), pass (matched and excluded
    # rows), reason (excluded rows)
    items = check_assignment(book, bank, assignment, left_id="entry_id",
                             right_id="line_id", amount="amount", currency="ccy")

`check_assignment` raises `MatchError` unless:
- every id of both populations appears exactly once, and no id outside them appears;
- a matched row names its group and pass; an excluded row its pass and reason; an
  unmatched row neither a group nor a pass;
- a group holds items of both sides (a match with nothing on the other side is none);
- a group spans items of one currency (translate first; match the translated amount);
- the ids are text or integers (an id read as a float writes `1001.0`, never `1001`);
- `amount` and `currency` name a column on both sides or on neither, and every matched
  item has its amount;
- the assignment carries no `amount` or `currency` column; both come from the
  populations. A `matched_to` or `diff` it carries (as a `resolve()` Resolution's
  `items` does) is recomputed here.

It returns the assignment with `amount`, `currency`, `matched_to` (the other side's ids
in the group, `;`-joined) and `diff` (the group's left sum less right sum — a netted fee,
a partial payment) added. A group whose `abs(diff)` exceeds `tol` is refused, unless
`tol` is None (differences are recorded, not judged). `amount` is optional: a roster
(check-completeness) has none.

Pitfalls a join makes silently, and this check catches:
- a key repeated on a side makes a join many-to-many: one bank line clears two book
  lines. Use `join(..., validate="1:1")` for a 1:1 pass, or drop the repeated keys first
  and leave them open for a later pass;
- an inner join drops what did not match — those items are the reconciling items;
- null keys, and keys cast to text (`123.0` and `123` differ): cast both sides to one type.

Needs polars.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import polars as pl

__all__ = ["check_assignment", "MatchError"]

STATUSES = ("matched", "excluded", "unmatched")


class MatchError(ValueError):
    """An assignment whose bookkeeping does not close."""


def _pair(v, what: str) -> tuple:
    if v is None or isinstance(v, str):
        return (v, v)
    v = tuple(v)
    if len(v) != 2 or (v[0] is None) != (v[1] is None):
        raise MatchError(f"`{what}` is a column name, or a (left, right) pair of them - on "
                         f"both sides or neither, got {v!r}")
    return v


def check_assignment(left: pl.DataFrame, right: pl.DataFrame, assignment: pl.DataFrame, *,
                     left_id: str, right_id: str, amount=None, currency=None,
                     tol: float | None = 0.0) -> pl.DataFrame:
    """Validate `assignment` against both populations (module docstring); return it
    enriched. `amount` and `currency` are a column name or a (left, right) pair."""
    amt, cur = _pair(amount, "amount"), _pair(currency, "currency")
    if tol is not None and (isinstance(tol, bool) or not isinstance(tol, (int, float))
                            or not tol >= 0 or tol == float("inf")):
        raise MatchError(f"tol is a non-negative number or None, got {tol!r}")
    need = {"side", "id", "status", "group", "pass", "reason"}
    if missing := need - set(assignment.columns):
        raise MatchError(f"assignment lacks column(s) {sorted(missing)}")
    if clash := sorted({"amount", "currency"} & set(assignment.columns)):
        raise MatchError(f"assignment carries {clash}, which this takes from the populations - "
                         f"drop them (an amount riding along is never the one checked)")
    assignment = assignment.drop("matched_to", "diff", strict=False)     # recomputed below
    A = assignment.with_columns(pl.col("id").cast(pl.Utf8), pl.col("side").cast(pl.Utf8))
    if bad := sorted(set(A["side"].drop_nulls()) - {"left", "right"} | (
            {"<null>"} if A["side"].null_count() else set())):
        raise MatchError(f"side is left or right, got {bad}")
    if bad := sorted(set(A["status"].drop_nulls()) - set(STATUSES) | (
            {"<null>"} if A["status"].null_count() else set())):
        raise MatchError(f"status is one of {STATUSES}, got {bad}")

    pops = []
    for side, df, idc, i in (("left", left, left_id, 0), ("right", right, right_id, 1)):
        for c in (idc, amt[i], cur[i]):
            if c is not None and c not in df.columns:
                raise MatchError(f"{side}: no column {c!r}")
        if df[idc].dtype.is_float() or df[idc].dtype.is_decimal():
            raise MatchError(f"{side}: ids in {idc!r} are {df[idc].dtype} - an id read as a "
                             f"number writes `1001.0`; cast it to text or an integer")
        if amt[i] and not (df[amt[i]].dtype.is_numeric() or df[amt[i]].dtype == pl.Null):
            raise MatchError(f"{side}: amount {amt[i]!r} is {df[amt[i]].dtype}, not a number")
        cols = {"id": pl.col(idc).cast(pl.Utf8), "side": pl.lit(side),
                "amount": pl.col(amt[i]).cast(pl.Float64) if amt[i] else pl.lit(None, pl.Float64),
                "currency": (pl.col(cur[i]).cast(pl.Utf8).str.to_uppercase() if cur[i]
                             else pl.lit(None, pl.Utf8))}
        pop = df.select(**cols)
        if pop["id"].null_count() or pop["id"].n_unique() != pop.height:
            raise MatchError(f"{side}: ids in {idc!r} must be present and unique")
        got = A.filter(pl.col("side") == side)
        counts = got.group_by("id").len()
        if (dup := counts.filter(pl.col("len") > 1)["id"]).len():
            raise MatchError(f"{side}: assigned more than once: {sorted(dup)[:5]}")
        if (lost := sorted(set(pop["id"]) - set(got["id"]))):
            raise MatchError(f"{side}: {len(lost)} item(s) not accounted for: {lost[:5]}")
        if (extra := sorted(set(got["id"]) - set(pop["id"]))):
            raise MatchError(f"{side}: id(s) outside the population: {extra[:5]}")
        pops.append(pop)

    def rows(cond):
        return A.filter(cond)["id"].head(5).to_list()
    st = pl.col("status")
    for cond, what in (
            ((st == "matched") & (pl.col("group").is_null() | pl.col("pass").is_null()),
             "matched without a group or pass"),
            ((st == "excluded") & (pl.col("pass").is_null()
                                   | (pl.col("reason").cast(pl.Utf8).str.strip_chars()
                                      .fill_null("") == "")),
             "excluded without a pass or reason"),
            ((st == "unmatched") & (pl.col("group").is_not_null() | pl.col("pass").is_not_null()),
             "unmatched but carrying a group or pass"),
            ((st != "matched") & pl.col("group").is_not_null(), "in a group but not matched")):
        if ids := rows(cond):
            raise MatchError(f"{what}: {ids}")

    out = A.join(pl.concat(pops), on=["side", "id"], how="left")
    g = out.filter(st == "matched")
    if amt[0] and (ids := g.filter(pl.col("amount").is_null() | pl.col("amount").is_nan())["id"]
                   .head(5).to_list()):
        raise MatchError(f"matched without an amount: {ids}")
    one = g.group_by("group").agg(pl.col("side").n_unique().alias("n")).filter(pl.col("n") < 2)
    if one.height:
        raise MatchError(f"group(s) {sorted(one['group'].to_list())[:5]} hold items of one side "
                         f"only - a match pairs both sides")
    per = g.group_by("group").agg(
        curs=pl.col("currency").drop_nulls().unique(),
        passes=pl.col("pass").unique(),
        diff=(pl.when(pl.col("side") == "left").then(pl.col("amount"))
              .otherwise(-pl.col("amount"))).sum(),
        L=pl.col("id").filter(pl.col("side") == "left").sort().str.join(";"),
        R=pl.col("id").filter(pl.col("side") == "right").sort().str.join(";"))
    # the difference summed exactly, each amount as written (its shortest decimal form): a
    # float sum of large amounts leaves residue a cent tolerance would refuse
    exact = defaultdict(Decimal)
    if amt[0]:
        for grp, side, a in g.select("group", "side", "amount").iter_rows():
            if a is not None:
                exact[grp] += Decimal(repr(a)) if side == "left" else -Decimal(repr(a))
    for r in per.iter_rows(named=True):
        if len(r["curs"]) > 1:
            raise MatchError(f"group {r['group']} spans currencies {sorted(r['curs'])} - "
                             f"translate first and match the translated amount")
        if len(r["passes"]) > 1:
            raise MatchError(f"group {r['group']} is claimed by passes {sorted(r['passes'])}")
        if tol is not None and amt[0] and abs(exact[r["group"]]) > Decimal(repr(float(tol))):
            raise MatchError(f"group {r['group']} leaves {exact[r['group']]:.2f} beyond tol {tol}")
    per = per.with_columns(diff=pl.col("group").replace_strict(
        {k: float(v) for k, v in exact.items()}, default=0.0, return_dtype=pl.Float64)) \
        if amt[0] and per.height else per
    per = per.select("group", "L", "R", diff=pl.col("diff") if amt[0]
                     else pl.lit(None, pl.Float64))
    return (out.join(per, on="group", how="left")
            .with_columns(matched_to=pl.when(pl.col("side") == "left").then("R")
                          .otherwise("L").replace("", None))
            .drop("L", "R"))
