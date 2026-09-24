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
- a group spans items of one currency (translate first; match the translated amount).

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

Run with no arguments to self-check. Needs polars.
"""
from __future__ import annotations

import sys

import polars as pl

__all__ = ["check_assignment", "MatchError"]

STATUSES = ("matched", "excluded", "unmatched")


class MatchError(ValueError):
    """An assignment whose bookkeeping does not close."""


def _pair(v) -> tuple:
    if v is None or isinstance(v, str):
        return (v, v)
    return tuple(v)


def check_assignment(left: pl.DataFrame, right: pl.DataFrame, assignment: pl.DataFrame, *,
                     left_id: str, right_id: str, amount=None, currency=None,
                     tol: float | None = 0.0) -> pl.DataFrame:
    """Validate `assignment` against both populations (module docstring); return it
    enriched. `amount` and `currency` are a column name or a (left, right) pair."""
    amt, cur = _pair(amount), _pair(currency)
    need = {"side", "id", "status", "group", "pass", "reason"}
    if missing := need - set(assignment.columns):
        raise MatchError(f"assignment lacks column(s) {sorted(missing)}")
    A = assignment.with_columns(pl.col("id").cast(pl.Utf8), pl.col("side").cast(pl.Utf8))
    if bad := sorted(set(A["side"].drop_nulls()) - {"left", "right"} | (
            {"<null>"} if A["side"].null_count() else set())):
        raise MatchError(f"side is left or right, got {bad}")
    if bad := sorted(set(A["status"].drop_nulls()) - set(STATUSES) | (
            {"<null>"} if A["status"].null_count() else set())):
        raise MatchError(f"status is one of {STATUSES}, got {bad}")

    pops = []
    for side, df, idc, i in (("left", left, left_id, 0), ("right", right, right_id, 1)):
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
    per = g.group_by("group").agg(
        curs=pl.col("currency").drop_nulls().unique(),
        passes=pl.col("pass").unique(),
        diff=(pl.when(pl.col("side") == "left").then(pl.col("amount"))
              .otherwise(-pl.col("amount"))).sum(),
        L=pl.col("id").filter(pl.col("side") == "left").sort().str.join(";"),
        R=pl.col("id").filter(pl.col("side") == "right").sort().str.join(";"))
    for r in per.iter_rows(named=True):
        if len(r["curs"]) > 1:
            raise MatchError(f"group {r['group']} spans currencies {sorted(r['curs'])} - "
                             f"translate first and match the translated amount")
        if len(r["passes"]) > 1:
            raise MatchError(f"group {r['group']} is claimed by passes {sorted(r['passes'])}")
        if tol is not None and amt[0] and abs(r["diff"]) > tol + 1e-9:
            raise MatchError(f"group {r['group']} leaves {r['diff']:.2f} beyond tol {tol}")
    per = per.select("group", "L", "R", diff=pl.col("diff").round(10) if amt[0]
                     else pl.lit(None, pl.Float64))
    return (out.join(per, on="group", how="left")
            .with_columns(matched_to=pl.when(pl.col("side") == "left").then("R")
                          .otherwise("L").replace("", None))
            .drop("L", "R"))


def _selfcheck() -> int:
    bad: list[str] = []

    def expect(cond, what):
        if not cond:
            bad.append(what)

    def refuses(fn, what):
        try:
            fn()
            bad.append(f"did not refuse: {what}")
        except MatchError:
            pass

    book = pl.DataFrame({"id": ["b1", "b2", "b3", "b4", "b5"],
                         "amt": [100.0, 40.0, 60.0, 75.0, 12.0], "ccy": ["USD"] * 5})
    bank = pl.DataFrame({"id": ["k1", "k2", "k3", "k4"],
                         "amt": [100.0, 100.0, 72.5, 30.0], "ccy": ["USD", "usd", "USD", "EUR"]})
    asg = pl.DataFrame({
        "side": ["left"] * 5 + ["right"] * 4,
        "id": ["b1", "b2", "b3", "b4", "b5", "k1", "k2", "k3", "k4"],
        "status": ["matched", "matched", "matched", "matched", "excluded",
                   "matched", "matched", "matched", "unmatched"],
        "group": [1, 2, 2, 3, None, 1, 2, 3, None],
        "pass": ["ref", "deposit", "deposit", "fee", "void", "ref", "deposit", "fee", None],
        "reason": [None, None, None, None, "voided", None, None, None, None]})
    kw = dict(left_id="id", right_id="id", amount="amt", currency="ccy")
    out = check_assignment(book, bank, asg, tol=None, **kw)
    by = {r["id"]: r for r in out.to_dicts()}
    expect(by["b2"]["matched_to"] == "k2" and by["k2"]["matched_to"] == "b2;b3",
           "matched_to across an n:1 group")
    expect(abs(by["b4"]["diff"] - 2.5) < 1e-9, "the fee group records its 2.5 difference")
    expect(by["k4"]["matched_to"] is None and by["b5"]["diff"] is None, "open items carry no group")
    refuses(lambda: check_assignment(book, bank, asg, tol=1.0, **kw), "a diff beyond tol")
    expect(check_assignment(book, bank, asg, tol=2.5, **kw).height == 9, "a diff within tol")
    refuses(lambda: check_assignment(book, bank, asg.filter(pl.col("id") != "k4"), **kw),
            "an item not accounted for")
    refuses(lambda: check_assignment(book, bank, asg.vstack(asg.head(1)), **kw),
            "an item assigned twice")
    refuses(lambda: check_assignment(book, bank, asg.with_columns(
        reason=pl.lit(None, pl.Utf8)), tol=None, **kw), "an exclusion with no reason")
    refuses(lambda: check_assignment(book, bank, asg.with_columns(
        group=pl.when(pl.col("id") == "k4").then(3).otherwise(pl.col("group")),
        status=pl.when(pl.col("id") == "k4").then(pl.lit("matched")).otherwise("status"),
        **{"pass": pl.when(pl.col("id") == "k4").then(pl.lit("fee")).otherwise("pass")}),
        tol=None, **kw), "a group spanning currencies")
    refuses(lambda: check_assignment(book, bank, asg.with_columns(
        id=pl.when(pl.col("id") == "k4").then(pl.lit("k9")).otherwise("id")), **kw),
        "an id outside the population")

    # a roster: no amounts
    ra = pl.DataFrame({"gl": ["1010", "1020"]})
    rb = pl.DataFrame({"acct": ["x1", "x2"]})
    ros = pl.DataFrame({"side": ["left", "left", "right", "right"],
                        "id": ["1010", "1020", "x1", "x2"],
                        "status": ["matched", "unmatched", "matched", "unmatched"],
                        "group": [1, None, 1, None], "pass": ["gl_account", None, "gl_account", None],
                        "reason": [None] * 4})
    r = check_assignment(ra, rb, ros, left_id="gl", right_id="acct")
    expect(r.filter(pl.col("id") == "1010")["matched_to"][0] == "x1", "roster match")

    for b in bad:
        print("FAIL", b)
    print("matching.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_selfcheck())
