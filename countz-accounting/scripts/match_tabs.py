#!/usr/bin/env python3
"""The match tabs of an item-level reconciliation, as reconciliation software reports it.

A reconciliation (check-recon § 3) shows the reviewer every left item once, beside what it
matched and by which rule, whether it matched with `resolve.py`'s `resolve()` or with
polars joins read back through its `from_assignment()`. `match_tabs()` writes four tabs from that Resolution into the check's
tab workbook and records their figures in the check's ledger:

- **`<token> Match summary`**: the left items by status (Matched, In transit, Unmatched,
  No cash), each line the schedule filtered on its status; then what each rule matched,
  and the right items matched and not.
- **`<token> Match schedule`**: one row per left item: its label, date, amount, status,
  the rule and match group, what it matched to, the difference a rule tolerated (on the
  group's first row only, so the column sums to the differences), and why an unmatched
  item is unmatched. Sorted by
  status in the summary's order; the AutoFilter sits on its header.
- **`<token> Reconciling items`**: the reconciliation, left total to right total, footing,
  each line net and gross (its positive and negative items apart); then every item not
  matched, of both sides and the ones kept out with cash, with its age at the statement's
  end.
- **`<token> Match rules`**: the rules in the order they ran, each rule's criteria and
  what it matched.

`match_tabs()` inserts the four at the front of `wb`, in that order, ahead of every sheet
already there: a second set (another `res` of the same check) goes ahead of the first. At
the seal they follow the Exec Summary (WORKBOOK.md § 2).

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from match_tabs import match_tabs

    names = match_tabs(wb, res, left, right, check="recon_inv_bank", token="recon inv bank",
                       ledger=L, subtitle="Sonos · October 2023 to December 2024 · USD",
                       currency="usd", inputs=[("book", "E.recon_inv_bank.book.fy2024")],
                       population="P.recon_inv_bank.book",
                       right_inputs=[("bank", "E.recon_inv_bank.bank.fy2024")],
                       right_population="P.recon_inv_bank.bank", others=unpaid,
                       left_label=customer, right_label=bank_line)

`left` and `right` are the streams as passed to `resolve()` or `from_assignment()`, and
`res` what it returned; the frames must be the ones it was built from (the same ids, and
the amounts and dates it matched). `inputs` and `population` are what the left items'
figures stand on and are measured over; `right_inputs` (default `inputs`) and
`right_population` the same for the right items. `currency` is the streams' ISO 4217 code
(default `usd`); its minor units are the Resolution's `decimals`, and every amount is shown
to them. `decimals` is optional: the Resolution states it, and one passed must agree.
`others` holds the left items kept out of the streams, as `id`, `value`, `reason` and
optionally `date` and `entity`: a value of 0 (open, void, credited) reads No cash, any
other Unmatched, each with its reason. `left_label` and `right_label` are DataFrames of
`id`, `label`, the words a reviewer finds an item by. The nouns default to invoices and
bank lines; `after_word` names a left item `resolve()` found in transit, dated close enough
to the statement's end that its bank line falls after it (In transit for receipts,
Outstanding for payments). The figures are `F.<check>.match.<token>.<line>`, the token
written as an id segment, so each set of a check keys its own.

Input the tabs could not show faithfully is refused with a ValueError before any tab or
figure is written: frames other than the Resolution's, a token that cannot name a tab or
whose tabs `wb` already holds, a currency whose minor units are not the Resolution's
decimals, text a cell cannot hold, a status word registered with another style, `others`
with a repeated, blank or streamed id, or with no reason.
"""
from __future__ import annotations

import copy
import datetime as dt
import pathlib
import re
import sys
import unicodedata

import polars as pl
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import style as _style  # noqa: E402  sibling: currencies and date forms
from check_playbook import CHECK_ID  # noqa: E402  the check-id grammar
from wbkit import (FMT_AMOUNT, FMT_DATE, FMT_PCT, S, STATUS, STATUS_KINDS, Alignment,  # noqa: E402
                   amount, band, count, finish, grid, header, ident, next_block, register_status,
                   section, stated, status, text, total)

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
MAX_CELL = 32_767                 # characters a cell holds; openpyxl cuts past it, silently
NOT_IN_TAB_NAME = re.compile(r"[\[\]:*?/\\]")
TABS = (("summary", "Match summary", "Summary"), ("schedule", "Match schedule", "Schedule"),
        ("reconciling", "Reconciling items", "Recon items"), ("rules", "Match rules", "Rules"))

# (figure key, status, its style, what it means) ({n}/{ns}: the left noun, {o}/{os}: the right one)
LEFT = [("matched", "Matched", "tied", "Matched by the rule the schedule names, to the {os} listed."),
        ("in_transit", "{after}", "review", "Dated close enough to the last {o} that its {o} falls "
                                            "on a later statement."),
        ("unmatched", "Unmatched", "break", "No rule matched it; the Reason column says why (no "
                                            "candidate, or more than one). Clear it with the records "
                                            "behind it."),
        ("no_cash", "No cash", "note", "No cash is recorded against it{reasons}, so there is nothing "
                                       "to find.")]
RIGHT = [("matched", "Matched", "tied", "Matched to the {ns} the schedule lists against it."),
         ("not_in_the_book", "Not in the book", "break", "No rule matched it to a {n}: a bank charge, "
                                                         "interest, cash not recorded, or a match no "
                                                         "rule could make.")]


def _cell(v, what: str) -> str | None:
    """`v` as the text a cell holds whole: no control character, within a cell's length."""
    if v is None:
        return None
    s = v if isinstance(v, str) else str(v)
    if ILLEGAL_CHARACTERS_RE.search(s):
        raise ValueError(f"{what}: {s[:40]!r} holds a control character a worksheet cannot store")
    if len(s) > MAX_CELL:
        raise ValueError(f"{what}: {len(s):,} characters, past the {MAX_CELL:,} a cell holds")
    return s


def _fit(parts: list[str], sep: str, tail, room: int = MAX_CELL) -> str:
    """`parts` joined whole where they fit in `room` characters; else as many as fit, then
    `tail(k)`, the words for the parts from k on."""
    whole = sep.join(parts)
    if len(whole) <= room:
        return whole
    k, size = 0, len(tail(0)) + len(sep) + 40
    while size + len(parts[k]) + len(sep) <= room:
        size += len(parts[k]) + len(sep)
        k += 1
    return sep.join(parts[:k] + [tail(k)])


def _slug(words: str) -> str:
    """Words as a figure-id segment: accents folded, each other run of characters `_`."""
    a = unicodedata.normalize("NFKD", words).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", a).strip("_")


def _names(wb, token) -> dict:
    """The four tab names, refused where Excel would refuse them or `wb` holds one."""
    if not isinstance(token, str) or not token.strip() or token != token.strip():
        raise ValueError(f"token {token!r}: the words the tab names open with, never blank or padded")
    _cell(token, "token")
    if m := NOT_IN_TAB_NAME.search(token):
        raise ValueError(f"token {token!r}: a tab name never holds {m.group(0)!r} "
                         f"(Excel refuses [ ] : * ? / \\)")
    if token.startswith("'"):
        raise ValueError(f"token {token!r}: a tab name never opens with an apostrophe")
    if not _slug(token):
        raise ValueError(f"token {token!r}: it keys the figures (F.<check>.match.<token>), so it "
                         f"holds a letter A-Z or a digit")
    names = {}
    for k, long_, short in TABS:
        # Excel counts a tab name in UTF-16 units
        fits = [f"{token} {t}" for t in (long_, short) if len(f"{token} {t}".encode("utf-16-le")) <= 2 * MAX_TITLE]
        if not fits:
            raise ValueError(f"token {token!r}: `<token> {short}` passes the {MAX_TITLE}-character "
                             f"tab name limit (WORKBOOK.md § 2)")
        names[k] = fits[0]
    have = {t.casefold(): t for t in wb.sheetnames}
    for n in names.values():
        if n.casefold() in have:
            raise ValueError(f"the workbook already holds {have[n.casefold()]!r}: each set of match "
                             f"tabs is written once, under a token no other set uses")
    return names


def _decimals(res, currency, decimals) -> int:
    dec = res.decimals
    if decimals is not None and decimals != dec:
        raise ValueError(f"decimals={decimals!r}: the Resolution was matched at {dec}; pass the "
                         f"same, or leave it out")
    if currency not in _style.CURRENCIES:
        raise ValueError(f"currency {currency!r}: an ISO 4217 code, lower case (scripts/style.py)")
    if (mu := _style.minor_units(currency)) != dec:
        raise ValueError(f"currency {currency!r} is stated to {mu} decimals and the Resolution was "
                         f"matched at {dec}: pass the currency the streams are in, and match at its "
                         f"decimals")
    return dec


def _dates(s: pl.Series, what: str) -> list:
    """A date column as dates: a Date, a Datetime or ISO text (YYYY-MM-DD, a time after it
    allowed); None where the record has none."""
    if s.dtype == pl.Date:
        d = s
    elif isinstance(s.dtype, pl.Datetime):
        d = s.dt.date()
    elif s.dtype == pl.Null:
        d = s.cast(pl.Date)
    elif s.dtype == pl.Utf8:
        d = s.str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False)
        bad = s.is_not_null() & (d.is_null() | ~s.str.contains(r"^\d{4}-\d{2}-\d{2}").fill_null(False))
        if bad.any():
            raise ValueError(f"{what}: date {s.filter(bad)[0]!r} is not ISO YYYY-MM-DD")
    else:
        raise ValueError(f"{what}: date is a Date, a Datetime or ISO text, not {s.dtype}")
    return d.to_list()


def _frame(df, what: str, cols) -> None:
    if not isinstance(df, pl.DataFrame):
        raise ValueError(f"{what}: a polars DataFrame")
    if miss := [c for c in cols if c not in df.columns]:
        raise ValueError(f"{what} lacks column(s) {miss}")


def _values(df, what: str, s: int) -> list[float]:
    """Each item's value: a finite number, no finer than the Resolution's decimals."""
    v = df["value"].cast(pl.Float64)
    if (bad := v.is_null() | ~v.is_finite().fill_null(False)).any():
        raise ValueError(f"{what}: value is a finite number on every item, not on "
                         f"{df['id'][bad.arg_true()[0]]!r}")
    x = v * s
    if (off := (x - x.round()).abs() > (v.abs() * s * 2.0 ** -49).clip(lower_bound=1e-6)).any():
        k = off.arg_true()[0]
        raise ValueError(f"{what}: value {v[k]!r} on {df['id'][k]!r} is finer than the Resolution's decimals")
    return v.to_list()


def _ids(df, what: str) -> list[str]:
    ids = df["id"].cast(pl.Utf8)
    if ids.null_count() or ids.n_unique() != df.height:
        raise ValueError(f"{what}: id must be present and unique")
    return [_cell(i, f"{what} id") for i in ids.to_list()]


def _stream(df, what: str, s: int) -> dict:
    """{id: {date, value, entity}} of a stream."""
    _frame(df, what, ("id", "date", "value"))
    ent = df["entity"].cast(pl.Utf8).to_list() if "entity" in df.columns else [None] * df.height
    return {i: dict(date=d, value=v, entity=_cell(e, f"{what} {i!r}: entity"))
            for i, d, v, e in zip(_ids(df, what), _dates(df["date"], what), _values(df, what, s), ent)}


def _agree(res, streams: dict, s: int) -> None:
    """The frames are the ones the Resolution was built from: the same ids, each match
    group's totals and each unmatched item's amount and date."""
    for side, rows in streams.items():
        want = set(res.items.filter(pl.col("side") == side)["id"].to_list())
        if want != set(rows):
            miss, extra = sorted(want - set(rows)), sorted(set(rows) - want)
            raise ValueError(f"{side}: not the stream the Resolution was built from - {len(miss)} of "
                             f"its ids absent {miss[:3]}, {len(extra)} it never saw {extra[:3]}")
    c = {(side, i): round(r["value"] * s) for side, rows in streams.items() for i, r in rows.items()}
    for g, a, b, la, ra in res.matches.select("group", "left_ids", "right_ids", "left_amount",
                                              "right_amount").iter_rows():
        for side, ids_, amt in (("left", a, la), ("right", b, ra)):
            if sum(c[side, i] for i in ids_.split(";")) != round(amt * s):
                raise ValueError(f"{side}: not the stream the Resolution was built from - match group "
                                 f"{g} totals {amt} in it, otherwise in the frame")
    for side, i, d, amt in res.exceptions.select("side", "id", "date", "amount").iter_rows():
        r = streams[side][i]
        if c[side, i] != round(amt * s) or r["date"] != d:
            raise ValueError(f"{side}: not the stream the Resolution was built from - {i!r} reads "
                             f"{r['value']} on {r['date']} in the frame, {amt} on {d} in it")


def _labels(df, what: str) -> dict:
    if df is None:
        return {}
    _frame(df, what, ("id", "label"))
    t = df.select(pl.col("id").cast(pl.Utf8), pl.col("label").cast(pl.Utf8)).drop_nulls().unique()
    if (dup := t.filter(pl.col("id").is_duplicated())["id"]).len():
        raise ValueError(f"{what}: id {dup[0]!r} carries two labels")
    return {i: _cell(lab, f"{what} {i!r}") for i, lab in t.iter_rows()}


def _others(df, s: int, streamed: dict) -> list[dict]:
    """The left items kept out of the streams, checked."""
    if df is None:
        return []
    _frame(df, "others", ("id", "value", "reason"))
    ids = _ids(df, "others")
    if dup := sorted(set(ids) & set(streamed)):
        raise ValueError(f"others: {dup[:3]} are also in the left stream")
    why = df["reason"].cast(pl.Utf8)
    if (blank := why.is_null() | (why.str.strip_chars() == "")).any():
        raise ValueError(f"others: {ids[blank.arg_true()[0]]!r} states no reason it is kept out")
    dates = _dates(df["date"], "others") if "date" in df.columns else [None] * df.height
    ent = df["entity"].cast(pl.Utf8).to_list() if "entity" in df.columns else [None] * df.height
    return [dict(id=i, value=v, date=d, entity=_cell(e, f"others {i!r}: entity"),
                 reason=_cell(r, f"others {i!r}: reason"))
            for i, v, d, e, r in zip(ids, _values(df, "others", s), dates, ent, why.to_list())]


def match_tabs(wb, res, left: pl.DataFrame, right: pl.DataFrame, *, check: str, token: str,
               ledger, subtitle: str, inputs, population: str, right_population: str,
               right_inputs=None, others: pl.DataFrame | None = None,
               left_label: pl.DataFrame | None = None, right_label: pl.DataFrame | None = None,
               nouns=("invoice", "invoices"), other_nouns=("bank line", "bank lines"),
               label_header="Customer", after_word="In transit", currency: str = "usd",
               decimals: int | None = None) -> dict:
    """Write the four tabs into `wb` ahead of its other sheets, record their figures in
    `ledger` (a figures.Ledger), and return {"summary", "schedule", "reconciling", "rules":
    tab names, "figures": {(side, status, "count" | "amount"): id}}. Refuses (ValueError)
    input it cannot show faithfully before writing anything (module docstring)."""
    # ---- the arguments, each checked before anything is written
    if not isinstance(check, str) or not CHECK_ID.fullmatch(check):
        raise ValueError(f"check {check!r}: a check id, {CHECK_ID.pattern} (scripts/check_playbook.py)")
    for what, pop in (("population", population), ("right_population", right_population)):
        if not pop:
            raise ValueError(f"{what}: the `P.` id its side's figures are measured over, never omitted")
    names = _names(wb, token)
    tok = _slug(token)
    dec = _decimals(res, currency, decimals)
    s = 10 ** dec
    money = FMT_AMOUNT if dec == 0 else '#,##0.{0};(#,##0.{0});"–"'.format("0" * dec)
    if res.engine not in ("resolve", "assignment"):
        raise ValueError(f"res: a Resolution from resolve() or from_assignment(), not engine {res.engine!r}")
    for what, pair in (("nouns", nouns), ("other_nouns", other_nouns)):
        if not (isinstance(pair, (tuple, list)) and len(pair) == 2 and
                all(isinstance(w, str) and w.strip() for w in pair)):
            raise ValueError(f"{what}: (one, many), as ('invoice', 'invoices')")
        for w in pair:
            _cell(w, what)
    for what, w in (("after_word", after_word), ("label_header", label_header), ("subtitle", subtitle)):
        if not isinstance(w, str) or not w.strip():
            raise ValueError(f"{what}: words, never blank")
        _cell(w, what)
    W = lambda f, **k: f.format(n=nouns[0], ns=nouns[1], o=other_nouns[0], os=other_nouns[1],  # noqa: E731
                                after=after_word, **k)
    cap = lambda w: w[:1].upper() + w[1:]  # noqa: E731
    Ns, Os = cap(nouns[1]), cap(other_nouns[1])
    left_words = [W(w) for _, w, _, _ in LEFT]
    if len({w.casefold() for w in left_words}) < len(left_words):
        raise ValueError(f"after_word {after_word!r}: another status reads so (Matched, Unmatched, No cash)")
    statuses = [(W(w), kind) for _, w, kind, _ in LEFT + RIGHT]
    for w, kind in statuses:
        if (have := STATUS.get(w)) and have != STATUS_KINDS[kind]:
            raise ValueError(f"status {w!r} is registered as {have} in this process, and the match "
                             f"tabs read it as {kind}: one word, one style")
    sched_head = [cap(nouns[0]), label_header, "Date", AMOUNT_HEADER, STATUS_HEADER, "Rule", "Match",
                  "Matched to", "Difference", "Reason"]
    if len({h.casefold() for h in sched_head}) < len(sched_head):
        raise ValueError(f"the schedule's headers repeat {sched_head}: name the {nouns[0]} and "
                         f"label_header apart from its other columns")
    by_rule = res.by_rule
    if by_rule["rule"].n_unique() != by_rule.height:
        raise ValueError("res.by_rule names a rule twice: each rule's line would carry both's matches")
    for b in by_rule.iter_rows(named=True):
        _cell(b["rule"], "rule name")
        _cell(b["criteria"], f"rule {b['rule']!r}: criteria")

    # ---- the frames: the Resolution's own, and what the tabs label them with
    Lr, Rr = _stream(left, "left", s), _stream(right, "right", s)
    _agree(res, {"left": Lr, "right": Rr}, s)
    llab, rlab = _labels(left_label, "left_label"), _labels(right_label, "right_label")
    kept_out = _others(others, s, Lr)
    src = "scripts/resolve.py" if res.engine == "resolve" else \
        f"scripts/resolve.py from_assignment() over the passes of checks/{check}.md"
    it = res.items
    ex = {(r["side"], r["id"]): r for r in res.exceptions.iter_rows(named=True)}

    def line(rid: str) -> str:
        r = Rr[rid]
        return " · ".join(str(b) for b in (rlab.get(rid, rid), r["date"] and _style.date_short(r["date"]),
                                           f"{r['value']:,.{dec}f}") if b)

    def matched_to(ids_: list[str], g) -> str:
        return _fit([line(x) for x in ids_], "; ", lambda k: (
            f"and {len(ids_) - k:,} more {other_nouns[1]} in match group {g}, together "
            f"{sum(Rr[x]['value'] for x in ids_[k:]):,.{dec}f}"))

    # ---- the schedule's rows
    rows = []
    for r in it.filter(pl.col("side") == "left").iter_rows(named=True):
        i, lr, e = r["id"], Lr[r["id"]], ex.get(("left", r["id"]))
        st = "Matched" if r["status"] == "matched" else W("{after}") if e and e["in_transit"] else "Unmatched"
        rows.append(dict(id=i, label=llab.get(i, lr["entity"]), date=lr["date"], amount=lr["value"],
                         status=st, rule=r["pass"], group=r["group"],
                         to=matched_to(r["matched_to"].split(";"), r["group"]) if r["matched_to"] else None,
                         diff=r["difference"] or None, reason=_cell(r["reason"], f"left {i!r}: reason"),
                         kept=False))
    for o in kept_out:
        rows.append(dict(id=o["id"], label=llab.get(o["id"], o["entity"]), date=o["date"], amount=o["value"],
                         status="Unmatched" if o["value"] else "No cash", rule=None, group=None, to=None,
                         diff=None, reason=_cell(f"kept out of the matching: {o['reason']}",
                                                 f"others {o['id']!r}: reason"), kept=True))
    reasons = sorted({o["reason"] for o in kept_out if not o["value"]})
    order = {w: k for k, w in enumerate(left_words)}
    rows.sort(key=lambda x: (order[x["status"]], x["date"] or dt.date.max, x["id"]))
    seen = set()
    for x in rows:                     # a group's difference once, on its first row
        if x["group"] is not None:
            if x["group"] in seen:
                x["diff"] = None
            seen.add(x["group"])

    # ---- the figures, and the lines that show them
    specs, figs = [], {}
    total_n, total_a = len(rows), round(sum(x["amount"] for x in rows), dec)
    over = {"left": (inputs, population, total_n), "right": (right_inputs or inputs, right_population, len(Rr))}

    def fig(key, label, value, unit, expr, side="left"):
        """A figure of one side's items, measured over its population: a 0 over no items
        is not measured."""
        fid = f"F.{check}.match.{tok}.{key}"
        ins, pop, n_items = over[side]
        specs.append(dict(fid=fid, label=label, value=value, unit=unit, expression=expr, inputs=ins,
                          population=pop, zero_basis=None if value else
                          "measured_zero" if n_items else "not_measured"))
        return fid

    what = lambda st: f"the rows of {names['schedule']} whose {STATUS_HEADER} reads {st}"  # noqa: E731
    all_id = fig("left.all.amount", f"All {nouns[1]}, amount", total_a, currency,
                 f"sum of {AMOUNT_HEADER} over every row of {names['schedule']}")
    no_cash = _fit(reasons, ", ", lambda k: f"and {len(reasons) - k:,} more", MAX_CELL - 200)
    left_lines = []
    for key, w, _, meaning in LEFT:
        st = W(w)
        mine = [x for x in rows if x["status"] == st]
        n, a = len(mine), round(sum(x["amount"] for x in mine), dec)
        figs[("left", st, "count")] = fig(f"left.{key}.count", f"{Ns}, {st}, count", n, "count",
                                          f"count of {what(st)}")
        figs[("left", st, "amount")] = fid = fig(f"left.{key}.amount", f"{Ns}, {st}, amount", a, currency,
                                                 f"sum of {AMOUNT_HEADER} over {what(st)}")
        left_lines.append((fid, st, n, a, W(meaning, reasons=f" ({no_cash})" if reasons else "")))
    R_status = dict(it.filter(pl.col("side") == "right").select("id", "status").iter_rows())
    r_total = round(sum(r["value"] for r in Rr.values()), dec)
    right_lines = []
    for (key, w, _, meaning), st in zip(RIGHT, ("matched", "unmatched")):
        mine = [i for i, x in R_status.items() if x == st]
        n, a = len(mine), round(sum(Rr[i]["value"] for i in mine), dec)
        figs[("right", W(w), "count")] = fig(
            f"right.{key}.count", f"{Os}, {W(w)}, count", n, "count",
            f"count of the {other_nouns[1]} {src} reports {st}", "right")
        figs[("right", W(w), "amount")] = fid = fig(
            f"right.{key}.amount", f"{Os}, {W(w)}, amount", a, currency,
            f"sum of the {other_nouns[1]} {src} reports {st}", "right")
        right_lines.append((fid, W(w), n, a, W(meaning)))

    # the reconciliation: kept-out items are in the left total; those with cash are taken
    # out again as not matched
    kept = [x["amount"] for x in rows if x["kept"]]
    cash = [v for v in kept if v]
    kp, km = sum(v for v in kept if v > 0), sum(v for v in kept if v < 0)
    words = {"left_total": (f"{Ns} per books", f"Every {nouns[0]} in the matching, and those kept out of it."),
             "left_in_transit": (f"Less: {W('{after}').lower()}", f"{Ns} not matched, dated close enough to "
                                 f"the last {other_nouns[0]} that theirs fall on a later statement."),
             "left_unmatched": (f"Less: {nouns[1]} not matched", f"{Ns} no rule matched, dated within the "
                                f"statements, and those kept out with cash."),
             "right_unmatched": (f"Add: {other_nouns[1]} not in the book",
                                 f"{Os} no rule matched to a {nouns[0]}.")}
    recon_lines, differences = [], {}
    for key_, n_, v_, p_, m_ in res.summary.iter_rows():
        if key_ == "right_total":
            continue
        if key_.startswith("difference:"):
            name = _cell(key_.split(":", 1)[1], "difference name")
            slug = _slug(name) or str(len(differences) + 1)
            if slug in differences:
                raise ValueError(f"differences {differences[slug]!r} and {name!r} key one figure "
                                 f"(recon.difference.{slug}): name them apart")
            differences[slug] = name
            fkey, (label_, why_) = f"recon.difference.{slug}", (
                f"Difference: {name}", "What the rule of that name tolerated between the two sides.")
        elif key_ in words:
            fkey, (label_, why_) = f"recon.{key_}", words[key_]
        else:
            raise ValueError(f"res.summary: line {key_!r} is not one the reconciling items know")
        if key_ == "left_total":
            n_, v_, p_, m_ = n_ + len(kept), v_ + sum(kept), p_ + kp, m_ + km
        elif key_ == "left_unmatched":
            n_, v_, p_, m_ = n_ + len(cash), v_ - sum(cash), p_ - km, m_ - kp
        fid = fig(fkey, label_, round(v_, dec), currency, f"{label_}, the `summary` of {src}",
                  "right" if key_ == "right_unmatched" else "left")
        recon_lines.append((fid, label_, n_, round(v_, dec), round(p_, dec), round(m_, dec), why_))
    rt = res.summary.filter(pl.col("line") == "right_total").row(0)
    end = res.end
    open_items = [(e["side"], e["id"], (llab if e["side"] == "left" else rlab).get(e["id"], e["entity"]),
                   e["date"], e["amount"], e["age"], _cell(e["reason"], f"{e['side']} {e['id']!r}: reason"))
                  for e in res.exceptions.iter_rows(named=True)]
    open_items += [("left", x["id"], x["label"], x["date"], x["amount"],
                    (end - x["date"]).days if end and x["date"] else None, x["reason"])
                   for x in rows if x["kept"] and x["amount"]]
    open_items.sort(key=lambda t: (t[0] != "left", t[3] is None, t[3] or dt.date.min, t[1]))

    # every figure minted on a copy first: a refusal leaves the ledger and `wb` as they were
    trial = copy.deepcopy(ledger)
    for spec in specs:
        trial.fig(**spec)

    # ---- nothing below refuses: the writing
    for spec in specs:
        ledger.fig(**spec)
    for w, kind in statuses:
        register_status(w, kind)

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
                amount(cell, v, fmt=money)
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
    r_ = 5
    cells(ws, r_, [("id", all_id), ("text", f"All {nouns[1]}"), ("count", total_n), ("amount", total_a),
                   ("percent", 1.0 if total_a else 0.0), ("text", W("Every {n} in the population."))], "Subtotal")
    for fid, st, n, a, meaning in left_lines:
        r_ += 1
        cells(ws, r_, [("id", fid), ("text", st), ("count", n), ("amount", a),
                       ("percent", a / total_a if total_a else 0.0), ("text", meaning)])
        status(ws.cell(r_, 3), st)
    r_ += 1
    cells(ws, r_, [("id", None), ("text", "Total"), ("count", total_n), ("amount", total_a),
                   ("percent", 1.0 if total_a else 0.0), ("text", W("Every {n}, once."))], "Total")
    # the opening "All" line and the Total are each the status lines between them, live
    # (WORKBOOK.md § 7): a status line that drops out of the schedule shows here
    if r_ > 6:
        for c, v in ((4, total_n), (5, total_a), (6, 1.0 if total_a else 0.0)):
            total(ws.cell(5, c), v, rows=range(6, r_), style=None)
            total(ws.cell(r_, c), v, rows=range(6, r_), style=None)
    last_primary = r_
    # what each rule matched
    r_ = section(ws, next_block(r_), "Matched, by rule")
    header(ws, r_, ["id", "Rule", Ns, f"{AMOUNT_HEADER}, {nouns[1]}", Os,
                     f"{AMOUNT_HEADER}, {other_nouns[1]}", "Difference"],
           ["id", "description", "count", "amount", "count", "amount", "amount"], primary=False)
    h_ = r_
    for k, b in enumerate(by_rule.iter_rows(named=True), start=1):
        r_ += 1
        cells(ws, r_, [("id", f"{k}"), ("text", b["rule"]), ("count", b["left_items"]),
                       ("amount", round(b["left_amount"], dec)), ("count", b["right_items"]),
                       ("amount", round(b["right_amount"], dec)), ("amount", round(b["difference"], dec))])
    grid(ws, h_, r_, 2, 8)
    # the right items
    r_ = section(ws, next_block(r_), f"The {other_nouns[1]}")
    header(ws, r_, ["id", STATUS_HEADER, Os, AMOUNT_HEADER, "Share of amount", "What it means"],
           ["id", "description", "count", "amount", "percent", "note"], primary=False)
    h_ = r_
    for fid, st, n, a, meaning in right_lines:
        r_ += 1
        cells(ws, r_, [("id", fid), ("text", st), ("count", n), ("amount", a),
                       ("percent", a / r_total if r_total else 0.0), ("text", meaning)])
        status(ws.cell(r_, 3), st)
    r_ += 1
    cells(ws, r_, [("id", None), ("text", "Total"), ("count", len(Rr)), ("amount", r_total),
                   ("percent", 1.0 if r_total else 0.0)], "Total")
    if r_ > h_ + 1:
        for c, v in ((4, len(Rr)), (5, r_total), (6, 1.0 if r_total else 0.0)):
            total(ws.cell(r_, c), v, rows=range(h_ + 1, r_), style=None)
    grid(ws, h_, r_, 2, 7)
    r_ = next_block(r_)
    section(ws, r_, "To reperform")
    for k, step in enumerate((
            f"Open {names['schedule']} and filter {STATUS_HEADER} on a line's words; count the rows and "
            f"sum {AMOUNT_HEADER}.",
            f"The matches come from scripts/resolve.py run on the two streams with the rules on "
            f"{names['rules']}, in that order (checks/{check}.md)." if res.engine == "resolve" else
            f"The matches come from the passes on {names['rules']}, run in that order on the two "
            f"streams as checks/{check}.md records them, each item accounted for once by "
            f"scripts/matching.py."), start=1):
        r_ += 1
        text(ws.cell(r_, 2), f"{k}. {step}")
    finish(ws, last_primary)

    # ---- the schedule tab
    ws2 = wb.create_sheet(names["schedule"], 1)
    band(ws2, f"{token}{SCHEDULE_MARK}: each {nouns[0]} and what it matched", subtitle,
         f"One row per {nouns[0]}, sorted by status as the summary lists them; filter {STATUS_HEADER} "
         f"to reproduce a summary line. A match group's difference stands on its first row.")
    header(ws2, 4, sched_head,
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
    amount(ws2.cell(r_, 5), total_a, fmt=money, style="Total")
    if last_row >= 5:
        total(ws2.cell(r_, 5), total_a, rows=range(5, last_row + 1), style=None)
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
    r_ = 4
    for fid, label_, n_, v_, p_, m_, why_ in recon_lines:
        r_ += 1
        cells(ws4, r_, [("id", fid), ("text", label_), ("count", n_), ("amount", v_),
                        ("amount", p_), ("amount", m_), ("text", why_)])
    r_ += 1
    cells(ws4, r_, [("id", None), ("text", f"{Os} per bank"), ("count", rt[1]), ("amount", round(rt[2], dec)),
                    ("amount", round(rt[3], dec)), ("amount", round(rt[4], dec))], "Total")
    if recon_lines:                             # the walk: per books through each line to per bank
        total(ws4.cell(r_, 5), rt[2], rows=range(5, r_), style=None)
    for c in (4, 6, 7):                         # the count and the split per bank are stated, not
        stated(ws4.cell(r_, c))                 # sums: each line counts and splits its own items
    last4 = r_
    r_ = section(ws4, next_block(r_), "The items not matched" +
                 (f", aged at {_style.date_short(end)}" if end else ""))
    header(ws4, r_, ["id", "Side", "Label", "Date", AMOUNT_HEADER, "Age (days)", "Reason"],
           ["id", "description", "description", "period", "amount", "count", "note"], primary=False)
    h_ = r_
    for side, i, lab, d, a, age, why in open_items:
        r_ += 1
        cells(ws4, r_, [("id", i), ("text", nouns[0] if side == "left" else other_nouns[0]),
                        ("text", lab), ("date", d), ("amount", a), ("count", age), ("text", why)])
    grid(ws4, h_, r_, 2, 8)
    finish(ws4, last4)

    # ---- the rules tab
    ws3 = wb.create_sheet(names["rules"], 3)
    band(ws3, f"{token}{RULES_MARK}: the rules, in the order they ran", subtitle,
         "Each rule compared what the rules before it left open; a pair matched only where each was "
         "the other's one candidate." if res.engine == "resolve" else
         f"Each pass compared what the passes before it left open, as checks/{check}.md records it.")
    header(ws3, 4, ["id", "Rule", "Criteria", "Matches", Ns, Os, "Difference"],
           ["id", "description", "note", "count", "count", "count", "amount"])
    r_ = 4
    for k, b in enumerate(by_rule.iter_rows(named=True), start=1):
        r_ += 1
        cells(ws3, r_, [("id", f"{k}"), ("text", b["rule"]), ("text", b["criteria"]), ("count", b["matches"]),
                        ("count", b["left_items"]), ("count", b["right_items"]),
                        ("amount", round(b["difference"], dec))])
    finish(ws3, r_)
    return {**names, "figures": figs}
