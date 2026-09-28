#!/usr/bin/env python3
"""The match tabs of an item-level reconciliation, as reconciliation software reports it.

A check that matches items with `resolve.py` (check-recon § 3) shows the reviewer every
left item once, beside what it matched and by which rule, so each match can be verified
line by line. `match_tabs()` writes four tabs from the engine's result into the check's tab
workbook and records their figures in the check's ledger:

- **`<token> Match summary`**: the left items by status (Matched, In transit, Unmatched,
  No cash), each line the schedule filtered on its status; then what each rule matched,
  and the right items matched and not.
- **`<token> Match schedule`**: one row per left item: its label, date, amount, status,
  the rule and match group, what it matched to, the difference a rule tolerated, and why
  an unmatched item is unmatched. Sorted by status in the summary's order; the AutoFilter
  sits on its header.
- **`<token> Reconciling items`**: the reconciliation, left total to right total, footing,
  each line net and gross (its positive and negative items apart); then every unmatched
  item of both sides with its age at the statement's end.
- **`<token> Match rules`**: the rules in the order they ran, each rule's criteria and
  what it matched.

The tabs follow the Exec Summary, in that order (WORKBOOK.md § 2).

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from match_tabs import match_tabs

    names = match_tabs(wb, res, left, right, check="recon_inv_bank", token="recon inv bank",
                       ledger=L, subtitle="Sonos · October 2023 to December 2024 · USD",
                       inputs=[("book", "E.recon_inv_bank.book.fy2024")],
                       population="P.recon_inv_bank.book", others=unpaid,
                       left_label=customer, right_label=bank_line)

`left` and `right` are the streams as passed to `resolve()`, and `res` what it returned.
`others` holds the left items kept out of the streams, as `id`, `value`, `reason` and
optionally `date` and `entity`: a value of 0 (open, void, credited) reads No cash, any
other Unmatched, each with its reason. `left_label` and `right_label` are DataFrames of
`id`, `label`, the words a reviewer finds an item by. The nouns default to invoices and
bank lines; `after_word` names a left item `resolve()` found in transit, dated close enough
to the statement's end that its bank line falls after it (In transit for receipts,
Outstanding for payments).
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

import polars as pl

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from wbkit import (FMT_CENTS, FMT_DATE, FMT_PCT, S, Alignment, amount, band,  # noqa: E402
                   count, finish, grid, header, ident, register_status, section, status, text)

__all__ = ["match_tabs", "SUMMARY_MARK", "SCHEDULE_MARK", "RULES_MARK", "RECON_MARK",
           "STATUS_HEADER", "AMOUNT_HEADER"]

# The markers the gate and the linker find the tabs by, in B1 after the token.
SUMMARY_MARK = " · Match summary"
SCHEDULE_MARK = " · Match schedule"
RULES_MARK = " · Match rules"
RECON_MARK = " · Reconciling items"
STATUS_HEADER = "Status"
AMOUNT_HEADER = "Amount"
MAX_TITLE = 31
TOP = {"alignment": Alignment(horizontal="right", vertical="top")}

# status -> its style and what it means ({n}/{ns}: the left noun, {o}/{os}: the right one)
LEFT = [("Matched", "tied", "Matched by the rule the schedule names, to the {os} listed."),
        ("{after}", "review", "Dated close enough to the last {o} that its {o} falls on a later "
                              "statement."),
        ("Unmatched", "break", "No rule matched it; the Reason column says why (no candidate, or "
                               "more than one). Clear it with the records behind it."),
        ("No cash", "note", "No cash is recorded against it{reasons}, so there is nothing to find.")]
RIGHT = [("Matched", "tied", "Matched to the {ns} the schedule lists against it."),
         ("Not in the book", "break", "No rule matched it to a {n}: a bank charge, interest, cash "
                                      "not recorded, or a match no rule could make.")]


def _tab_name(token: str, long_: str, short: str) -> str:
    for t in (long_, short):
        if len(f"{token} {t}") <= MAX_TITLE:
            return f"{token} {t}"
    raise ValueError(f"token {token!r}: `<token> {short}` passes the {MAX_TITLE}-character tab "
                     f"name limit (WORKBOOK.md § 2)")


def _labels(df) -> dict:
    return {} if df is None else dict(df.select(pl.col("id").cast(pl.Utf8), pl.col("label").cast(pl.Utf8))
                                      .drop_nulls().iter_rows())


def _day(d):
    if d is None:
        return None
    if isinstance(d, str):
        return dt.date.fromisoformat(d[:10])
    return d.date() if isinstance(d, dt.datetime) else d


def match_tabs(wb, res, left: pl.DataFrame, right: pl.DataFrame, *, check: str, token: str,
               ledger, subtitle: str, inputs, population: str, right_inputs=None,
               right_population: str | None = None, others: pl.DataFrame | None = None,
               left_label: pl.DataFrame | None = None, right_label: pl.DataFrame | None = None,
               nouns=("invoice", "invoices"), other_nouns=("bank line", "bank lines"),
               label_header="Customer", after_word="In transit", currency: str = "usd",
               decimals: int = 2) -> dict:
    """Write the four tabs into `wb` ahead of its other sheets, record their figures in
    `ledger` (a figures.Ledger), and return {"summary", "schedule", "reconciling", "rules":
    tab names, "figures": {(side, status, "count" | "amount"): id}}."""
    names = {k: _tab_name(token, a, b) for k, a, b in (
        ("summary", "Match summary", "Summary"), ("schedule", "Match schedule", "Schedule"),
        ("reconciling", "Reconciling items", "Recon items"), ("rules", "Match rules", "Rules"))}
    W = lambda f, **k: f.format(n=nouns[0], ns=nouns[1], o=other_nouns[0], os=other_nouns[1],  # noqa: E731
                                after=after_word, **k)
    for table_ in (LEFT, RIGHT):
        for w, kind, _ in table_:
            register_status(W(w), kind)
    Ns, Os = nouns[1][:1].upper() + nouns[1][1:], other_nouns[1][:1].upper() + other_nouns[1][1:]
    llab, rlab = _labels(left_label), _labels(right_label)
    rows_R = {r["id"]: r for r in right.with_columns(pl.col("id").cast(pl.Utf8)).iter_rows(named=True)}
    it = res.items
    ex = {(r["side"], r["id"]): r for r in res.exceptions.iter_rows(named=True)}

    def line(rid: str) -> str:
        r, d = rows_R.get(rid, {}), _day(rows_R.get(rid, {}).get("date"))
        return " · ".join(str(b) for b in (rlab.get(rid, rid), d and f"{d:%b} {d.day}, {d.year}",
                                           r.get("value") is not None and f"{r['value']:,.{decimals}f}") if b)

    # ---- the schedule's rows
    rows = []
    for r, lr in zip(it.filter(pl.col("side") == "left").sort("id").iter_rows(named=True),
                     left.with_columns(pl.col("id").cast(pl.Utf8)).sort("id").iter_rows(named=True)):
        e = ex.get(("left", r["id"]))
        st = "Matched" if r["status"] == "matched" else W("{after}") if e and e["in_transit"] else "Unmatched"
        rows.append(dict(id=r["id"], label=llab.get(r["id"], lr.get("entity")), date=_day(lr["date"]),
                         amount=float(lr["value"]), status=st, rule=r["pass"], group=r["group"],
                         to="; ".join(line(x) for x in (r["matched_to"] or "").split(";") if x) or None,
                         diff=r["difference"] or None, reason=r["reason"]))
    reasons = []
    if others is not None:
        o = others.with_columns(pl.col("id").cast(pl.Utf8))
        if dup := sorted(set(o["id"]) & {x["id"] for x in rows}):
            raise ValueError(f"others: {dup[:3]} are also in the left stream")
        for r in o.iter_rows(named=True):
            v = float(r.get("value") or 0.0)
            rows.append(dict(id=r["id"], label=llab.get(r["id"], r.get("entity")), date=_day(r.get("date")),
                             amount=v, status="Unmatched" if v else "No cash", rule=None, group=None, to=None,
                             diff=None, reason=f"kept out of the matching: {r.get('reason') or 'no reason given'}"))
        reasons = sorted({str(r["reason"]) for r in o.iter_rows(named=True) if r.get("reason") and not r.get("value")})
    order = {W(w): k for k, (w, _, _) in enumerate(LEFT)}
    rows.sort(key=lambda x: (order[x["status"]], x["date"] or dt.date.max, x["id"]))

    figs = {}

    def fig(key, label, value, unit, expr, inputs_, pop):
        fid = f"F.{check}.match.{key}"
        ledger.fig(fid, label, value, unit, expr, inputs_, population=pop,
                   zero_basis="measured_zero" if not value else None)
        return fid

    def cells(ws, r_, vals, style_=None):
        """B.. onward: id, words, count, amount, share, note."""
        for c, (kind, v) in enumerate(vals, start=2):
            cell = ws.cell(r_, c)
            if v is None:
                pass
            elif kind == "id":
                ident(cell, v)
            elif kind == "count":
                count(cell, v)
            elif kind == "amount":
                amount(cell, v, fmt=FMT_CENTS)
            elif kind == "percent":
                amount(cell, v, fmt=FMT_PCT)
            elif kind == "date":
                amount(cell, v, fmt=FMT_DATE)
            else:
                text(cell, v)
            cell.alignment = Alignment(horizontal="right", vertical="top") if kind in (
                "count", "amount", "percent", "date") else Alignment(wrap_text=True, vertical="top")
            if style_:
                keep = cell.number_format
                cell.style = S[style_]
                cell.number_format = keep

    # ---- the summary tab
    ws = wb.create_sheet(names["summary"], 0)
    band(ws, f"{token}{SUMMARY_MARK}: {nouns[1]} to {other_nouns[1]}", subtitle,
         f"Every {nouns[0]} is on one row of the schedule. Each line below is the schedule filtered "
         f"on its status; its words open those rows.")
    header(ws, 4, ["id", STATUS_HEADER, Ns, AMOUNT_HEADER, "Share of amount", "What it means"],
           ["id", "description", "count", "amount", "percent", "note"])
    total_n, total_a = len(rows), round(sum(x["amount"] for x in rows), decimals)
    what = lambda st: f"the rows of {names['schedule']} whose {STATUS_HEADER} reads {st}"  # noqa: E731
    r_ = 5
    fid = fig("left.all.amount", f"All {nouns[1]}, amount", total_a, currency,
              f"sum of {AMOUNT_HEADER} over every row of {names['schedule']}", inputs, population)
    cells(ws, r_, [("id", fid), ("text", f"All {nouns[1]}"), ("count", total_n), ("amount", total_a),
                   ("percent", 1.0 if total_a else 0.0), ("text", W("Every {n} in the population."))], "Subtotal")
    for w, _, meaning in LEFT:
        st = W(w)
        mine = [x for x in rows if x["status"] == st]
        n, a = len(mine), round(sum(x["amount"] for x in mine), decimals)
        slug = st.lower().replace(" ", "_")
        fig(f"left.{slug}.count", f"{Ns}, {st}, count", n, "count", f"count of {what(st)}", inputs, population)
        fid = fig(f"left.{slug}.amount", f"{Ns}, {st}, amount", a, currency,
                  f"sum of {AMOUNT_HEADER} over {what(st)}", inputs, population)
        figs[("left", st, "amount")] = fid
        r_ += 1
        cells(ws, r_, [("id", fid), ("text", st), ("count", n), ("amount", a),
                       ("percent", a / total_a if total_a else 0.0),
                       ("text", W(meaning, reasons=f" ({', '.join(reasons)})" if reasons else ""))])
        status(ws.cell(r_, 3), st)
    r_ += 1
    cells(ws, r_, [("id", None), ("text", "Total"), ("count", total_n), ("amount", total_a),
                   ("percent", 1.0 if total_a else 0.0), ("text", W("Every {n}, once."))], "Total")
    last_primary = r_
    # what each rule matched
    r_ += 2
    section(ws, r_, "Matched, by rule")
    r_ += 1
    header(ws, r_, ["id", "Rule", Ns, AMOUNT_HEADER, Os, AMOUNT_HEADER + " ", "Difference"],
           ["id", "description", "count", "amount", "count", "amount", "amount"], primary=False)
    h_ = r_
    for k, b in enumerate(res.by_rule.iter_rows(named=True), start=1):
        r_ += 1
        cells(ws, r_, [("id", f"{k}"), ("text", b["rule"]), ("count", b["left_items"]),
                       ("amount", round(b["left_amount"], decimals)), ("count", b["right_items"]),
                       ("amount", round(b["right_amount"], decimals)), ("amount", round(b["difference"], decimals))])
    grid(ws, h_, r_, 2, 8)
    # the right items
    r_ += 2
    section(ws, r_, f"The {other_nouns[1]}")
    r_ += 1
    header(ws, r_, ["id", STATUS_HEADER, Os, AMOUNT_HEADER, "Share of amount", "What it means"],
           ["id", "description", "count", "amount", "percent", "note"], primary=False)
    h_ = r_
    R_it = it.filter(pl.col("side") == "right")
    rv = {i: float(r["value"]) for i, r in rows_R.items()}
    r_total = round(sum(rv.values()), decimals)
    for (w, _, meaning), st in zip(RIGHT, ("matched", "unmatched")):
        mine = R_it.filter(pl.col("status") == st)["id"].to_list()
        n, a = len(mine), round(sum(rv[i] for i in mine), decimals)
        slug = W(w).lower().replace(" ", "_")
        fig(f"right.{slug}.count", f"{Os}, {W(w)}, count", n, "count",
            f"count of the {other_nouns[1]} scripts/resolve.py reports {st}", right_inputs or inputs, right_population)
        fid = fig(f"right.{slug}.amount", f"{Os}, {W(w)}, amount", a, currency,
                  f"sum of the {other_nouns[1]} scripts/resolve.py reports {st}", right_inputs or inputs, right_population)
        figs[("right", W(w), "amount")] = fid
        r_ += 1
        cells(ws, r_, [("id", fid), ("text", W(w)), ("count", n), ("amount", a),
                       ("percent", a / r_total if r_total else 0.0), ("text", W(meaning))])
        status(ws.cell(r_, 3), W(w))
    r_ += 1
    cells(ws, r_, [("id", None), ("text", "Total"), ("count", R_it.height), ("amount", r_total),
                   ("percent", 1.0 if r_total else 0.0)], "Total")
    grid(ws, h_, r_, 2, 7)
    r_ += 2
    section(ws, r_, "To reperform")
    for k, step in enumerate((
            f"Open {names['schedule']} and filter {STATUS_HEADER} on a line's words; count the rows and "
            f"sum {AMOUNT_HEADER}.",
            f"The matches come from scripts/resolve.py run on the two streams with the rules on "
            f"{names['rules']}, in that order (checks/{check}.md)."), start=1):
        r_ += 1
        text(ws.cell(r_, 2), f"{k}. {step}")
    finish(ws, last_primary)

    # ---- the schedule tab
    ws2 = wb.create_sheet(names["schedule"], 1)
    band(ws2, f"{token}{SCHEDULE_MARK}: each {nouns[0]} and what it matched", subtitle,
         f"One row per {nouns[0]}, sorted by status as the summary lists them; filter {STATUS_HEADER} "
         f"to reproduce a summary line.")
    header(ws2, 4, [nouns[0][:1].upper() + nouns[0][1:], label_header, "Date", AMOUNT_HEADER, STATUS_HEADER,
                    "Rule", "Match", "Matched to", "Difference", "Reason"],
           ["id", "description", "period", "amount", "status", "description", "count", "note", "amount", "note"])
    r_ = 4
    for x in rows:
        r_ += 1
        cells(ws2, r_, [("id", x["id"]), ("text", x["label"]), ("date", x["date"]), ("amount", x["amount"]),
                        ("text", None), ("text", x["rule"]), ("count", x["group"]), ("text", x["to"]),
                        ("amount", x["diff"]), ("text", x["reason"])])
        status(ws2.cell(r_, 6), x["status"])
    last_row = r_
    r_ += 1
    text(ws2.cell(r_, 3), "Total", "Total")
    amount(ws2.cell(r_, 5), total_a, fmt=FMT_CENTS, style="Total")
    for c in (2, 4, 6, 7, 8, 9, 10, 11):
        ws2.cell(r_, c).style = S["Total"]
    grid(ws2, r_, r_, 2, 11)
    finish(ws2, last_row)

    # ---- the reconciling items tab
    ws4 = wb.create_sheet(names["reconciling"], 2)
    band(ws4, f"{token}{RECON_MARK}: {nouns[1]} per books to {other_nouns[1]} per bank", subtitle,
         f"The {nouns[1]} walked to the {other_nouns[1]}: every item not matched, and each difference "
         f"a rule tolerated, net and gross. The lines foot.")
    header(ws4, 4, ["id", "Line", "Items", AMOUNT_HEADER, "Positive", "Negative", "What it holds"],
           ["id", "description", "count", "amount", "amount", "amount", "note"])
    kept = [x["amount"] for x in rows if x["rule"] is None and x["reason"] and x["reason"].startswith("kept out")]
    kept_n, kept_a = len(kept), round(sum(kept), decimals)
    kept_p, kept_m = round(sum(v for v in kept if v > 0), decimals), round(sum(v for v in kept if v < 0), decimals)
    words = {"left_total": (f"{Ns} per books", f"Every {nouns[0]} in the matching, and those kept out of it."),
             "left_in_transit": (f"Less: {W('{after}').lower()}", f"{Ns} not matched, dated close enough to "
                                 f"the last {other_nouns[0]} that theirs fall on a later statement."),
             "left_unmatched": (f"Less: {nouns[1]} not matched", f"{Ns} no rule matched, dated within the "
                                f"statements, and those kept out with cash."),
             "right_unmatched": (f"Add: {other_nouns[1]} not in the book",
                                 f"{Os} no rule matched to a {nouns[0]}.")}
    r_ = 4
    for key_, n_, v_, p_, m_ in res.summary.iter_rows():
        if key_ == "right_total":
            continue
        label_, why_ = words.get(key_, (f"Difference: {key_.split(':', 1)[-1]}",
                                        "What the rule of that name tolerated between the two sides."))
        if key_ == "left_total":                  # the items kept out with cash: in the total,
            n_, v_, p_, m_ = n_ + kept_n, v_ + kept_a, p_ + kept_p, m_ + kept_m      # and out again
        elif key_ == "left_unmatched":            # as not matched
            n_, v_, p_, m_ = n_ + kept_n, v_ - kept_a, p_ - kept_m, m_ - kept_p
        fid = fig(f"recon.{key_.replace(':', '.').replace(' ', '_')}", label_, round(v_, decimals), currency,
                  f"{label_}, from scripts/resolve.py `summary`", inputs, population)
        r_ += 1
        cells(ws4, r_, [("id", fid), ("text", label_), ("count", n_), ("amount", round(v_, decimals)),
                        ("amount", round(p_, decimals)), ("amount", round(m_, decimals)), ("text", why_)])
    rt = res.summary.filter(pl.col("line") == "right_total").row(0)
    r_ += 1
    cells(ws4, r_, [("id", None), ("text", f"{Os} per bank"), ("count", rt[1]), ("amount", round(rt[2], decimals)),
                    ("amount", round(rt[3], decimals)), ("amount", round(rt[4], decimals))], "Total")
    last4 = r_
    r_ += 2
    section(ws4, r_, "The items not matched")
    r_ += 1
    header(ws4, r_, ["id", "Side", "Label", "Date", AMOUNT_HEADER, "Age (days)", "Reason"],
           ["id", "description", "description", "period", "amount", "count", "note"], primary=False)
    h_ = r_
    for e in res.exceptions.iter_rows(named=True):
        r_ += 1
        lab = (llab if e["side"] == "left" else rlab).get(e["id"], e["entity"])
        cells(ws4, r_, [("id", e["id"]), ("text", nouns[0] if e["side"] == "left" else other_nouns[0]),
                        ("text", lab), ("date", e["date"]), ("amount", e["amount"]), ("count", e["age"]),
                        ("text", e["reason"])])
    grid(ws4, h_, r_, 2, 8)
    finish(ws4, last4)

    # ---- the rules tab
    ws3 = wb.create_sheet(names["rules"], 3)
    band(ws3, f"{token}{RULES_MARK}: the rules, in the order they ran", subtitle,
         f"Each rule compared what the rules before it left open; a pair matched only where each was "
         f"the other's one candidate.")
    header(ws3, 4, ["id", "Rule", "Criteria", "Matches", Ns, Os, "Difference"],
           ["id", "description", "note", "count", "count", "count", "amount"])
    r_ = 4
    for k, b in enumerate(res.by_rule.iter_rows(named=True), start=1):
        r_ += 1
        cells(ws3, r_, [("id", f"{k}"), ("text", b["rule"]), ("text", b["criteria"]), ("count", b["matches"]),
                        ("count", b["left_items"]), ("count", b["right_items"]),
                        ("amount", round(b["difference"], decimals))])
    finish(ws3, r_)
    return {**names, "figures": figs}
