#!/usr/bin/env python3
"""Resolve two streams of items into groups that tie to the cent.

The matching engine behind a reconciliation at item grain: invoices to bank deposits,
book entries to statement lines, bills to payments. The caller maps each side to one
generic stream and reads back which items settle which; the engine knows nothing of
invoices or banks.

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from resolve import resolve

    res = resolve(left, right, window=(0, 0), split_days=90)
    res.items         # one row per item of both streams: side, id, status, group, pass,
                      # allocation, reason, link, link_basis, review, note —
                      # check_assignment() accepts it as is
    res.allocations   # group, left_id, right_id, value: which left item each right carries
    res.routes        # left_entity, right_entity, groups, proved, by_name: what was learned
    res.calibration   # rule, tried, agreed, precision, trusted: each inference rule's record
                      # on the items the allocation proved

**The streams.** Each is a polars DataFrame with these columns (rename yours to them):

- `id` — unique within its stream, text.
- `date` — the date on which the two sides are expected to agree (a paid date on an
  invoice, the batch date a deposit carries). An item without one can match only by
  `ref`; otherwise it stays unmatched, which is where the caller wants it seen.
- `value` — the amount, same currency and sign convention on both sides.
- `entity` — optional. Who the item belongs to: the customer on an invoice, the account
  on a deposit. The two streams may name different things (customer vs bank account);
  the engine learns which left entity lands in which right entity from the groups it
  proves (`entities="learn"`: a route restricts matching once two groups show it),
  requires the two names to agree (`"equal"`), or ignores it (`"none"`). Names are
  compared as keys — case, punctuation and legal-form words dropped, a name cut short by
  the bank accepted at five characters — and under `learn` a name agreeing counts as one
  group toward a route, never as a route by itself. A group counts toward a route only
  where its amount singles it out: an amount the entity bills again and again (a
  subscription at 19.99) shows nothing.
- `known_routes` (a parameter, not a column) — optional: a table of `left_entity`,
  `right_entity` confirmed in an earlier period. A carried route is a prior: one group this
  period proves it, it never restricts matching, a route this period proves otherwise
  replaces it (`routes.contradicted`), and where this period shows an entity nothing it
  links flagged unless carried routes held for the entities the period does show.
- `ref` — optional. A reference both sides carry (a cheque number, an invoice number on a
  remittance line). Items sharing a ref are tried together first.
- `text` — optional, either side. Free text: a bank line's description or memo, a payer
  name. The engine reads the other side's ids and refs out of it (word by word, so
  `INV 1001` reads as `INV-1001`) and the left side's entity names; a right item whose
  text names its payer admits that payer's items whatever the route says.

**Parameters.** `window=(lo, hi)`: a right item dated `lo..hi` days after a left item can
settle it whole. `split_days`: a left item may instead be settled in parts, each part up
to `split_days` beyond the window on either side (0 turns parts off). `max_subset`: the
largest candidate set searched exhaustively for a sum. `max_group`: the most items a
closed group may hold before it is left open as too large to call. `min_evidence`: the
groups a route needs before a link through it goes unflagged. `min_precision`: how often
an inference rule must agree with the proved items before it is trusted.

**The method** — the order a senior accountant clears a cash application, every step
accepting only an answer that is the only one possible, repeated until a round finds
nothing. Proved routes are used first; an entity with no proved route is searched only
once they stall.

1. `reference` — items sharing a ref whose sums agree; then `text_ref` — items the free
   text ties together, where their sums agree (where they do not, every item it names is
   flagged with the difference).
2. `one_to_one` — the one left item of that amount eligible for a right item, and the one
   right item of that amount eligible for it.
3. `subset` — the one set of eligible left items summing to a right item (tried first by
   entity-and-date units, the way one remittance pays a customer's day), and the one set
   of eligible right items summing to a left item (a deposit split over two lines).
4. `closed_group` — the items still open, linked by eligibility, fall into small closed
   groups; a group whose two sides agree to the cent is proved as a whole. An entity with
   no proved route joins the one right entity whose day it fills exactly.
5. `running_balance` — per right entity in date order, the consecutive days over which
   the running difference returns to where it stood (part payments crossing days).
6. `instalment` — a left item paid in parts: a group short by T joins the one set of
   nearby groups over by T (or the reverse), and the merged group ties.
7. the solver — a group that ties but whose allocation stays ambiguous gets the
   allocation with the fewest links and, among those, the links nearest each left item's
   own date (HiGHS, a mixed-integer program), accepted only where no other allocation is
   as good on both; its items carry `allocation: solver`. The solver is
   first run on groups the peel proved outright, and is flagged unless it agreed there.
8. differences — every group still open reports, in `note`, what its right side is over
   or short by and which open items equal that amount: the arithmetic an agent reads the
   rest with.

A sum search is refused where its candidates are so many that a match to the cent is
likely by coincidence: an exact sum among thousands of subsets is not evidence.

Every group ties to the cent: nothing is inferred, no remainder is carried. Within a
group the engine then allocates — which right item carries how much of which left item —
settling an item only by a step with no alternative: the one right item its dates allow,
the one set that sums to it, the last item standing. `allocation` is `exact` on an item
so settled, and `ambiguous` on the rest of a group that ties: the cash is proved, which
right item paid which left item is not.

What stays `unmatched` is the reconciling population: timing, one-sided items, errors, and
cash the files cannot place at item grain (a part payment whose other part cannot be told
from another item's).

**Links** answer a second question: which right item carries a left item, whether or not
the amounts tie. `link` names them and `link_basis` says how it is known:

- `allocation` — proved by the group's allocation, to the cent.
- `anchor` — the right items of the left item's routed entity on its date, where amounts
  do not tie (a part payment: the link names the deposit its last part landed in). The
  rule is first tried on the items the allocation proved (`calibration`); it links
  without a flag only where it agreed with at least `min_precision` of them. An entity no
  group proved is routed by where its days' cash could sit — the right entity whose items
  on each of its dates can hold that date's total — under the same test on the proved
  entities.

- `solver` — the solver's allocation (step 7).
- `remainder` — a left item whose date finds nothing (none, or no right item of its
  entity on it): the one right item nearby — or one entity's right items of one day,
  a deposit credited on two lines — whose unexplained remainder (value less everything
  linked to it alone) equals it, or the one set of such items that fills a remainder.

`review` carries the reason a link, or its absence, needs someone to look: a route shown
by too few groups, a route inferred rather than proved, several right items on the date
(the link names them all), an entity with no route at all (the link names every right
item on its date), no right item on the date, free text that ties items whose amounts
differ or that names another item than the one linked, a solver allocation the solver
could not first prove itself on. Those are the items the caller settles with what the
engine does not see — names, memo text, remittances — or leaves open.

Run with no arguments to self-check. Needs polars; the solver step needs highspy and is
skipped without it.
"""
from __future__ import annotations

import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass

import polars as pl

__all__ = ["resolve", "Resolution", "PASSES"]

PASSES = ("reference", "text_ref", "one_to_one", "subset", "closed_group",
          "running_balance", "instalment")
_LEARN_FROM = {"reference", "text_ref", "one_to_one", "subset", "closed_group"}


@dataclass
class Resolution:
    items: pl.DataFrame
    allocations: pl.DataFrame
    routes: pl.DataFrame
    calibration: pl.DataFrame


class _Side:
    def __init__(self, df: pl.DataFrame, name: str):
        for c in ("id", "date", "value"):
            if c not in df.columns:
                raise ValueError(f"{name} stream lacks column {c!r}")
        ids = df["id"].cast(pl.Utf8)
        if ids.null_count() or ids.n_unique() != df.height:
            raise ValueError(f"{name}: id must be present and unique")
        d = df["date"]
        if d.dtype == pl.Utf8:
            d = d.str.to_date(strict=False)
        d = d.cast(pl.Date)
        v = df["value"].cast(pl.Float64)
        if v.null_count():
            raise ValueError(f"{name}: value must be present on every item")
        self.id = ids.to_list()
        self.day = [x.toordinal() if x is not None else None for x in d.to_list()]
        self.c = [int(round(x * 100)) for x in v.to_list()]
        self.ent = (df["entity"].cast(pl.Utf8).to_list() if "entity" in df.columns
                    else [None] * df.height)
        self.ref = (df["ref"].cast(pl.Utf8).to_list() if "ref" in df.columns
                    else [None] * df.height)
        self.text = (df["text"].cast(pl.Utf8).to_list() if "text" in df.columns
                     else [None] * df.height)
        self.n = df.height


_LEGAL = {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co",
          "company", "plc", "gmbh", "ag", "sa", "sas", "bv", "nv", "pty", "lp", "llp", "the"}


def _norm_name(s):
    """A name as a comparison key: case, punctuation and legal-form words dropped."""
    if s is None:
        return None
    t = "".join(ch if ch.isalnum() else " " for ch in s.casefold().replace("&", " and "))
    return " ".join(w for w in t.split() if w not in _LEGAL) or None


def _norm_id(s):
    """An identifier as a comparison key: letters and digits only, upper case."""
    return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if s is not None else ""


def _grams(text, n=4):
    """Every run of 1..n consecutive words of `text`, each as an identifier key — so
    'INV 2023-10-0001' and 'INV-2023-10-0001' read alike, and no id matches half a word."""
    toks = re.findall(r"[A-Za-z0-9]+", (text or "").upper())
    return {"".join(toks[a:b]) for a in range(len(toks)) for b in range(a + 1, min(a + n, len(toks)) + 1)}


def _names_agree(a, b):
    """Two names for one party: the same key, or one the other cut short (a bank truncates
    a payer's name), at five characters or more."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 5 and long_.startswith(short)


def _subsets(items, target, maxsol=2, maxn=24):
    """Up to `maxsol` non-empty subsets of `items` [(key, cents)] summing to `target`;
    None when the set is too large to search exhaustively (meet in the middle)."""
    n = len(items)
    if n == 0:
        return []
    if n > maxn:
        return None
    h = n // 2
    A, B = items[:h], items[h:]

    def enum(L):
        out = defaultdict(list)
        sums = [(0, ())]
        for idx, (_, c) in enumerate(L):
            sums += [(s + c, comb + (idx,)) for s, comb in sums]
        for s, comb in sums:
            out[s].append(comb)
        return out
    ea, eb = enum(A), enum(B)
    sols = []
    for s, ca_list in ea.items():
        cb_list = eb.get(target - s)
        if not cb_list:
            continue
        for ca in ca_list:
            for cb in cb_list:
                if not ca and not cb:
                    continue
                sols.append(tuple(A[i][0] for i in ca) + tuple(B[i][0] for i in cb))
                if len(sols) >= maxsol:
                    return sols
    return sols


def _unique(items, target, maxn):
    """The one subset of `items` summing to `target`, with why not otherwise. A search whose
    2^n subsets crowd the sums they reach finds a sum by coincidence, so it is refused as
    `too_large` whatever its answer. Subset sums bunch in the middle of their range — they
    spread as sqrt(sum of squares)/2, not as the sum — and a batch total sits there, so the
    chance of a false hit is read at that peak. A run makes thousands of these searches, so
    the bar is set for all of them together: refused above 1 in 10,000 each."""
    spread = 0.5 * math.sqrt(sum(c * c for _, c in items))
    if len(items) > maxn or (2 ** len(items)) > 1e-4 * math.sqrt(2 * math.pi) * max(spread, 1):
        return None, "too_large"
    s = _subsets(items, target, maxn=maxn)
    if s is None:
        return None, "too_large"
    if len(s) == 1:
        return s[0], "unique"
    return None, ("none" if not s else "ambiguous")


def resolve(left: pl.DataFrame, right: pl.DataFrame, *, window=(0, 0), split_days=0,
            entities="learn", max_subset=24, max_group=200, min_evidence=3,
            min_precision=0.98, known_routes=None) -> Resolution:
    """Group the items of two streams into sets that tie to the cent (module docstring)."""
    if entities not in ("learn", "equal", "none"):
        raise ValueError("entities is learn, equal or none")
    L, R = _Side(left, "left"), _Side(right, "right")
    lo, hi = window
    elo, ehi = lo - split_days, hi + split_days
    openL, openR = set(range(L.n)), set(range(R.n))
    evidence: dict[str, Counter] = defaultdict(Counter)   # left entity -> right entity -> groups
    routes: dict[str, set] = {}                            # routes proved by two groups or more
    groups: list[dict] = []

    R_by_day = defaultdict(list)
    for j in range(R.n):
        if R.day[j] is not None:
            R_by_day[R.day[j]].append(j)
    L_by_day = defaultdict(list)
    for i in range(L.n):
        if L.day[i] is not None:
            L_by_day[L.day[i]].append(i)

    ents = entities if (any(e is not None for e in L.ent)
                        and any(e is not None for e in R.ent)) else "none"
    Lval = Counter(zip(L.ent, L.c))
    named: dict[str, set] = defaultdict(set)   # left entity -> right entities by name alone
    carried: dict[str, set] = defaultdict(set)  # routes confirmed in an earlier period: a
    if known_routes is not None and ents == "learn":  # prior, never a restriction by itself
        for le, a in known_routes.select("left_entity", "right_entity").iter_rows():
            if le is not None and a is not None:
                carried[le].add(a)
    if ents == "learn":
        rnorm = defaultdict(set)
        for e in set(R.ent) - {None}:
            rnorm[_norm_name(e)].add(e)
        for le in set(L.ent) - {None}:
            k = _norm_name(le)
            for rk, res_ in rnorm.items():
                if _names_agree(k, rk):
                    named[le] |= res_
        for le, res_ in named.items():
            for a in res_:
                evidence[le][a] += 1          # a name agreeing counts once, never proves

    # what the free text says: ids of the other side it quotes, and names it prints
    def id_index(S):
        ix = defaultdict(set)
        for k in range(S.n):
            for key in (_norm_id(S.id[k]), _norm_id(S.ref[k])):
                if len(key) >= 4 and any(ch.isdigit() for ch in key):
                    ix[key].add(k)
        return ix
    mR, mL = defaultdict(set), defaultdict(set)   # right j -> lefts it quotes; left i -> rights
    if any(R.text):
        lix = id_index(L)
        for j in range(R.n):
            if R.text[j]:
                for g in _grams(R.text[j]):
                    mR[j] |= lix.get(g, set())
    if any(L.text):
        rix = id_index(R)
        for i in range(L.n):
            if L.text[i]:
                for g in _grams(L.text[i]):
                    mL[i] |= rix.get(g, set())
    for j, ls in list(mR.items()):
        for i in ls:
            mL[i].add(j)
    for i, js in list(mL.items()):
        for j in js:
            mR[j].add(i)
    named_by_text = defaultdict(set)              # right j -> left entities its text names
    if ents != "none" and any(R.text):
        keys = {}
        for le in set(L.ent) - {None}:
            k = _norm_name(le)
            if k and len(k) >= 5:
                keys[le] = f" {k} "
        for j in range(R.n):
            if R.text[j]:
                t = f" {_norm_name(R.text[j]) or ''} "
                named_by_text[j] = {le for le, k in keys.items() if k in t}
        if ents == "learn":
            for le, a in {(le, R.ent[j]) for j, ns in named_by_text.items() for le in ns
                          if R.ent[j] is not None}:
                if a not in named[le]:
                    named[le].add(a)
                    evidence[le][a] += 1      # a payer named in the text: once, never proves
    hints = defaultdict(list)                     # (side, index) -> why an agent must look
    notes = defaultdict(list)                     # (side, index) -> arithmetic for context

    def ent_ok(i, j, firm=False):
        """May left i land in right j's entity? `firm`: only on a route already proved.
        A right item whose text names its payer admits that payer's items, and — on a
        firm test — no one else's."""
        if ents == "none":
            return True
        nj = named_by_text.get(j)
        if nj:
            if L.ent[i] in nj:
                return True
            if firm:
                return False
        le, re_ = L.ent[i], R.ent[j]
        if le is None or re_ is None:
            return True
        if ents == "equal":
            return _names_agree(_norm_name(le), _norm_name(re_))
        rs = routes.get(le)
        if rs:
            return re_ in rs
        return not firm

    def rights_for(i, a, b, firm=False):
        d = L.day[i]
        if d is None:
            return []
        return [j for k in range(d + a, d + b + 1) for j in R_by_day.get(k, ())
                if j in openR and ent_ok(i, j, firm)]

    def lefts_for(j, a, b, firm=False):
        d = R.day[j]
        if d is None:
            return []
        return [i for k in range(d - b, d - a + 1) for i in L_by_day.get(k, ())
                if i in openL and ent_ok(i, j, firm)]

    def elig(i, j, a, b, firm=False):
        if L.day[i] is None or R.day[j] is None:
            return False
        return a <= R.day[j] - L.day[i] <= b and ent_ok(i, j, firm)

    def allocate(Ls, Rs):
        """Peel what a group that ties proves: {(i, j): cents} over the items it settles.
        An item is settled only by a step with no alternative — the one right item its
        dates allow, the one set that sums to it, the last item standing on a side."""
        remL = {i: L.c[i] for i in Ls}
        remR = {j: R.c[j] for j in Rs}
        out = defaultdict(int)
        signed = all(v > 0 for v in remL.values()) and all(v > 0 for v in remR.values())

        def give(i, j, c):
            out[(i, j)] += c
            remL[i] -= c
            remR[j] -= c
            if remL[i] == 0:
                del remL[i]
            if remR[j] == 0:
                del remR[j]

        for _ in range(4 * (len(Ls) + len(Rs)) + 4):
            if not remL or not remR:
                break
            if len(remL) == 1 or len(remR) == 1:
                one_left = len(remL) == 1
                x = next(iter(remL if one_left else remR))
                others = sorted(remR if one_left else remL)
                if all(elig(x, y, elo, ehi) if one_left else elig(y, x, elo, ehi)
                       for y in others):
                    for y in others:
                        if one_left:
                            give(x, y, remR[y])
                        else:
                            give(y, x, remL[y])
                break
            moved = False
            if signed:
                for i in sorted(remL):
                    E = [j for j in remR if elig(i, j, elo, ehi)]
                    if len(E) == 1 and remR[E[0]] >= remL[i]:
                        give(i, E[0], remL[i]); moved = True; break
                if moved:
                    continue
                for j in sorted(remR):
                    E = [i for i in remL if elig(i, j, elo, ehi)]
                    if len(E) == 1 and remL[E[0]] >= remR[j]:
                        give(E[0], j, remR[j]); moved = True; break
                if moved:
                    continue
            for j in sorted(remR):
                cand = [(i, remL[i]) for i in sorted(remL) if elig(i, j, elo, ehi)]
                take, how = _unique(cand, remR[j], max_subset)
                if take:
                    for i in take:
                        give(i, j, remL[i])
                    moved = True
                    break
            if moved:
                continue
            for i in sorted(remL):
                cand = [(j, remR[j]) for j in sorted(remR) if elig(i, j, elo, ehi)]
                take, how = _unique(cand, remL[i], max_subset)
                if take:
                    for j in take:
                        give(i, j, remR[j])
                    moved = True
                    break
            if not moved:
                break
        settledL = {i for i in Ls if i not in remL}
        settledR = {j for j in Rs if j not in remR}
        return {k: v for k, v in out.items() if k[0] in settledL or k[1] in settledR}, \
            settledL, settledR

    def commit(pas, Ls, Rs, alloc=None):
        Ls, Rs = sorted(Ls), sorted(Rs)
        assert sum(L.c[i] for i in Ls) == sum(R.c[j] for j in Rs), pas
        if alloc is None:
            alloc, sL, sR = allocate(Ls, Rs)
        else:
            sL, sR = set(Ls), set(Rs)
        groups.append(dict(pas=pas, L=Ls, R=Rs, alloc=alloc, sL=sL, sR=sR))
        openL.difference_update(Ls)
        openR.difference_update(Rs)
        if ents == "learn" and pas in _LEARN_FROM:
            rents = {R.ent[j] for j in Rs if R.ent[j] is not None}
            if len(rents) == 1:
                a = next(iter(rents))
                for le in {L.ent[i] for i in Ls if L.ent[i] is not None}:
                    mine = [i for i in Ls if L.ent[i] == le]
                    # an amount the entity bills again and again singles nothing out
                    if all(Lval[(le, L.c[i])] > 1 for i in mine):
                        continue
                    evidence[le][a] += 1
                    if evidence[le][a] >= 2 or (a in carried.get(le, ()) and
                                                evidence[le][a] - (a in named.get(le, ())) >= 1):
                        routes.setdefault(le, set()).add(a)

    # 1. reference
    byref = defaultdict(lambda: ([], []))
    for i in range(L.n):
        if L.ref[i]:
            byref[L.ref[i]][0].append(i)
    for j in range(R.n):
        if R.ref[j]:
            byref[R.ref[j]][1].append(j)
    for ref in sorted(byref):
        Ls, Rs = byref[ref]
        Ls = [i for i in Ls if i in openL]
        Rs = [j for j in Rs if j in openR]
        if Ls and Rs and sum(L.c[i] for i in Ls) == sum(R.c[j] for j in Rs):
            commit("reference", Ls, Rs)

    # 1b. text: the items the free text ties together, where their sums agree
    if mR:
        parent = {}

        def tfind(x):
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for j, ls in mR.items():
            for i in ls:
                a_, b_ = tfind(("L", i)), tfind(("R", j))
                if a_ != b_:
                    parent[a_] = b_
        comp = defaultdict(lambda: ([], []))
        for x in list(parent):
            (comp[tfind(x)][0] if x[0] == "L" else comp[tfind(x)][1]).append(x[1])
        for Ls, Rs in sorted((sorted(a_), sorted(b_)) for a_, b_ in comp.values()):
            Ls = [i for i in Ls if i in openL]
            Rs = [j for j in Rs if j in openR]
            if not Ls or not Rs:
                continue
            d = sum(R.c[j] for j in Rs) - sum(L.c[i] for i in Ls)
            if d == 0:
                commit("text_ref", Ls, Rs)
            else:
                note = (f"text ties {', '.join(L.id[i] for i in Ls)} to "
                        f"{', '.join(R.id[j] for j in Rs)}; right side "
                        f"{'over' if d > 0 else 'short'} by {abs(d) / 100:,.2f}")
                for i in Ls:
                    hints[("L", i)].append(note)
                for j in Rs:
                    hints[("R", j)].append(note)

    def one_to_one():
        n = 0
        for j in sorted(openR, key=lambda x: (R.day[x] or 0, x)):
            if j not in openR:
                continue
            c = [i for i in lefts_for(j, lo, hi) if L.c[i] == R.c[j]]
            if len(c) != 1:
                continue
            back = [k for k in rights_for(c[0], lo, hi) if R.c[k] == L.c[c[0]]]
            if back == [j]:
                commit("one_to_one", c, [j], {(c[0], j): R.c[j]}); n += 1
        return n

    def subset(firm):
        n = 0
        for j in sorted(openR, key=lambda x: (R.day[x] or 0, -R.c[x], x)):
            if j not in openR:
                continue
            cand = lefts_for(j, lo, hi, firm)
            if not cand:
                continue
            units = defaultdict(list)
            for i in cand:
                units[(L.ent[i], L.day[i])].append(i)
            uitems = [(tuple(v), sum(L.c[i] for i in v)) for _, v in
                      sorted(units.items(), key=lambda x: (str(x[0][0]), x[0][1]))]
            take, how = _unique(uitems, R.c[j], max_subset)
            if take:
                take = [i for u in take for i in u]
            elif how in ("none", "too_large") and len(cand) <= max_subset:
                take, how = _unique([(i, L.c[i]) for i in sorted(cand)], R.c[j], max_subset)
            if take:
                commit("subset", take, [j], {(i, j): L.c[i] for i in take}); n += 1
        for i in sorted(openL, key=lambda x: (L.day[x] or 0, -L.c[x], x)):
            if i not in openL:
                continue
            cand = rights_for(i, lo, hi, firm)
            if len(cand) < 2:
                continue
            take, how = _unique([(j, R.c[j]) for j in sorted(cand)], L.c[i], max_subset)
            if take and len(take) > 1:
                commit("subset", [i], take, {(i, j): R.c[j] for j in take}); n += 1
        return n

    def components(a, b, firm):
        """Connected components of the open items, linked in window (a, b)."""
        parent = {}

        def find(x):
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for i in openL:
            find(("L", i))
            for j in rights_for(i, a, b, firm):
                ra, rb = find(("L", i)), find(("R", j))
                if ra != rb:
                    parent[ra] = rb
        for j in openR:
            find(("R", j))
        comp = defaultdict(lambda: ([], []))
        for x in list(parent):
            r = find(x)
            (comp[r][0] if x[0] == "L" else comp[r][1]).append(x[1])
        return sorted((sorted(Ls), sorted(Rs)) for Ls, Rs in comp.values())

    def closed_groups(firm):
        n = 0
        for Ls, Rs in components(lo, hi, firm):
            if Ls and Rs and len(Ls) + len(Rs) <= max_group and \
                    sum(L.c[i] for i in Ls) == sum(R.c[j] for j in Rs):
                commit("closed_group", Ls, Rs); n += 1
        return n

    def gap_fill():
        """An entity with no proved route: on a day, the one right entity whose open items
        exceed what its routed left items explain, by exactly the sum of one set of the
        unrouted remittances of that day, takes them — and the day closes as a group."""
        if ents != "learn":
            return 0
        n = 0
        byday = defaultdict(lambda: defaultdict(list))
        for j in openR:
            if R.day[j] is not None and R.ent[j] is not None:
                byday[R.day[j]][R.ent[j]].append(j)
        for d in sorted(byday):
            buckets = byday[d]
            unr = defaultdict(list)                 # unrouted remittances due on day d
            for k in range(d - hi, d - lo + 1):
                for i in L_by_day.get(k, ()):
                    if i in openL and L.ent[i] is not None and not routes.get(L.ent[i]):
                        unr[(L.ent[i], L.day[i])].append(i)
            if not unr:
                continue
            units = [(tuple(v), sum(L.c[i] for i in v)) for _, v in
                     sorted(unr.items(), key=lambda x: (str(x[0][0]), x[0][1]))]
            fits = {}
            for a, Rs in sorted(buckets.items()):
                if any(j not in openR for j in Rs):
                    continue
                own = [i for k in range(d - hi, d - lo + 1) for i in L_by_day.get(k, ())
                       if i in openL and routes.get(L.ent[i]) == {a}]
                gap = sum(R.c[j] for j in Rs) - sum(L.c[i] for i in own)
                if gap <= 0:
                    continue
                take, how = _unique(units, gap, max_subset)
                if take:
                    fits[a] = (own, Rs, take)
            used = [u for f in fits.values() for u in f[2]]
            for a, (own, Rs, take) in sorted(fits.items()):
                if any(used.count(u) > 1 for u in take):
                    continue                        # the same remittance fits two entities
                commit("closed_group", own + [i for u in take for i in u], Rs); n += 1
        return n

    def instalments(firm):
        if not split_days:
            return 0
        comps = [c for c in components(lo, hi, firm) if c[0] or c[1]]
        gap = [sum(R.c[j] for j in Rs) - sum(L.c[i] for i in Ls) for Ls, Rs in comps]
        n, used = 0, set()

        def links(k, m):
            """A left item of one component may take a part from a right item of the other."""
            (La, Ra), (Lb, Rb) = comps[k], comps[m]
            return any(elig(i, j, elo, ehi, firm) for i in La for j in Rb) or \
                any(elig(i, j, elo, ehi, firm) for i in Lb for j in Ra)
        for k in sorted(range(len(comps)), key=lambda x: (-abs(gap[x]), x)):
            if k in used or gap[k] == 0:
                continue
            cand = [(m, abs(gap[m])) for m in range(len(comps))      # the other sign
                    if m != k and m not in used and gap[m] * gap[k] < 0 and links(k, m)]
            one = [m for m, g in cand if g == abs(gap[k])]
            if len(one) == 1:
                take = one                  # one partner carries the whole difference
            elif one:
                continue                    # several would: no call
            elif len(cand) <= 12:           # a wider search finds sums by coincidence
                take, how = _unique(cand, abs(gap[k]), 12)
            else:
                continue
            if not take:
                continue
            members = [k, *take]
            Ls = [i for m in members for i in comps[m][0]]
            Rs = [j for m in members for j in comps[m][1]]
            if len(Ls) + len(Rs) > 60 or sum(L.c[i] for i in Ls) != sum(R.c[j] for j in Rs):
                continue
            used.update(members)
            commit("instalment", Ls, Rs); n += 1
        return n

    def running_balance():
        """Per right entity, in date order: the open items of consecutive days whose
        running difference returns to where it stood close as one group."""
        if not split_days:
            return 0
        byent = defaultdict(lambda: defaultdict(lambda: ([], [])))
        for j in openR:
            if R.day[j] is not None:
                byent[R.ent[j] if ents != "none" else None][R.day[j]][1].append(j)
        for i in openL:
            if L.day[i] is None:
                continue
            if ents == "none":
                a = None
            else:
                rs = routes.get(L.ent[i]) if ents == "learn" else {L.ent[i]}
                if L.ent[i] is None or not rs or len(rs) != 1:
                    continue
                a = next(iter(rs))
            byent[a][L.day[i] + lo][0].append(i)
        n = 0
        for a in sorted(byent, key=str):
            days = sorted(byent[a])
            seen, run, start = {0: 0}, 0, 0
            for k, d in enumerate(days, start=1):
                Ls, Rs = byent[a][d]
                run += sum(R.c[j] for j in Rs) - sum(L.c[i] for i in Ls)
                if run in seen:
                    span = days[seen[run]:k]
                    GL = [i for dd in span for i in byent[a][dd][0]]
                    GR = [j for dd in span for j in byent[a][dd][1]]
                    if GL and GR and span[-1] - span[0] <= split_days and \
                            len(GL) + len(GR) <= max_group:
                        commit("running_balance", GL, GR); n += 1
                    seen = {run: k}
                else:
                    seen[run] = k
        return n

    # proved routes first; an unproved entity is searched only once those stall
    for _ in range(100):
        if one_to_one() + subset(True):
            continue
        if closed_groups(True) or subset(False) or gap_fill() or closed_groups(False):
            continue
        if running_balance() or instalments(True) or instalments(False):
            continue
        break

    # 7. the solver: a group that ties but whose allocation the peel could not settle gets
    # the allocation with the fewest links, accepted only where no other allocation with as
    # few links exists (its links then form a forest, so each amount is fixed too).
    def solve(Ls, Rs, alloc, sL, sR):
        try:
            import highspy
        except ImportError:
            return None
        remL = {i: L.c[i] - sum(v for (a_, _), v in alloc.items() if a_ == i)
                for i in Ls if i not in sL}
        remR = {j: R.c[j] - sum(v for (_, b_), v in alloc.items() if b_ == j)
                for j in Rs if j not in sR}
        remL = {k: v for k, v in remL.items() if v}
        remR = {k: v for k, v in remR.items() if v}
        if not remL or not remR or any(v < 0 for v in (*remL.values(), *remR.values())):
            return None
        pairs = [(i, j) for i in sorted(remL) for j in sorted(remR) if elig(i, j, elo, ehi)]
        if not pairs or len(pairs) > 400:
            return None

        def run(cut=None, cap=None):
            h = highspy.Highs()
            h.silent()
            h.setOptionValue("time_limit", 1.0)
            x = {p_: h.addVariable(lb=0, ub=min(remL[p_[0]], remR[p_[1]])) for p_ in pairs}
            y = {p_: h.addBinary() for p_ in pairs}
            for p_ in pairs:
                h.addConstr(x[p_] <= min(remL[p_[0]], remR[p_[1]]) * y[p_])
            for i in remL:
                h.addConstr(sum(x[p_] for p_ in pairs if p_[0] == i) == remL[i])
            for j in remR:
                h.addConstr(sum(x[p_] for p_ in pairs if p_[1] == j) == remR[j])
            # fewest links first; among those, the links nearest each left item's own date
            far = {p_: abs(R.day[p_[1]] - L.day[p_[0]]) for p_ in pairs}
            big = sum(far.values()) + 1
            cost = sum((big + far[p_]) * y[p_] for p_ in pairs)
            if cut is not None:           # any allocation differing in at least one link
                h.addConstr(sum(1 - y[p_] for p_ in cut) + sum(y[p_] for p_ in pairs if p_ not in cut) >= 1)
                h.addConstr(cost <= cap)
            h.minimize(cost)
            if h.getModelStatus() != highspy.HighsModelStatus.kOptimal:
                return None
            used = {p_ for p_ in pairs if h.val(y[p_]) > 0.5}
            return used, {p_: int(round(h.val(x[p_]))) for p_ in used}, \
                sum((big + far[p_]) for p_ in used)
        first = run()
        if first is None:
            return None
        used, flow, best = first
        if run(cut=used, cap=best) is not None:
            return None                   # another allocation as good on links and dates
        if len(used) > len(remL) + len(remR) - 1:
            return None                   # a cycle: the amounts are not fixed
        return flow

    sv_tried = sv_agree = 0
    for grp in groups:                    # tried first where the peel already proved it
        if sv_tried >= 40:
            break
        # a group with one item on a side has one allocation: it tests nothing
        if len(grp["L"]) >= 2 and len(grp["R"]) >= 2 and grp["sL"] == set(grp["L"]) \
                and grp["sR"] == set(grp["R"]):
            flow = solve(grp["L"], grp["R"], {}, set(), set())
            if flow is not None:
                sv_tried += 1
                sv_agree += flow == {k: v for k, v in grp["alloc"].items() if v}
    solver_ok = sv_tried >= 20 and sv_agree / sv_tried >= min_precision

    solved_by = {}
    for grp in groups:
        if len(grp["sL"]) < len(grp["L"]) or len(grp["sR"]) < len(grp["R"]):
            flow = solve(grp["L"], grp["R"], grp["alloc"], grp["sL"], grp["sR"])
            if flow:
                for (i, j), c in flow.items():
                    grp["alloc"][(i, j)] = grp["alloc"].get((i, j), 0) + c
                    solved_by[("L", i)] = solved_by[("R", j)] = True
                grp["sL"] = set(grp["L"])
                grp["sR"] = set(grp["R"])
                grp["solver"] = True

    # 8. differences: what each group still open is over or short by, and which open
    # amounts equal it — the arithmetic an agent needs to read the rest
    if openL and openR:
        comps = [c for c in components(lo, hi, False) if c[0] and c[1]]
        amounts = defaultdict(list)       # cents -> open items of that amount
        for i in openL:
            amounts[L.c[i]].append(("L", i))
        for j in openR:
            amounts[R.c[j]].append(("R", j))
        for Ls, Rs in comps:
            d = sum(R.c[j] for j in Rs) - sum(L.c[i] for i in Ls)
            if d == 0:
                continue
            own = {("L", i) for i in Ls} | {("R", j) for j in Rs}
            eq = [x for x in amounts.get(abs(d), []) if x not in own]
            if eq:
                names = ", ".join((L.id if sd == "L" else R.id)[k] for sd, k in eq[:5])
                what = f"{'several' if len(eq) > 1 else 'one'} open item(s) equal it: {names}"
            else:
                what = "no open item equals it"
            note = (f"right side {'over' if d > 0 else 'short'} by {abs(d) / 100:,.2f} on "
                    f"{', '.join(R.id[j] for j in Rs[:3])}{'…' if len(Rs) > 3 else ''}; {what}")
            for x in own:
                notes[x].append(note)

    # links: which right items carry each left item
    link = defaultdict(set)          # ("L"|"R", index) -> set of indices on the other side
    basis, review = {}, {}
    for grp in groups:
        for (i, j), c in grp["alloc"].items():
            if c:
                link[("L", i)].add(j)
                link[("R", j)].add(i)
        for i in grp["sL"]:
            basis[("L", i)] = "solver" if solved_by.get(("L", i)) else "allocation"
        for j in grp["sR"]:
            basis[("R", j)] = "solver" if solved_by.get(("R", j)) else "allocation"

    # a carried route this period contradicts — another route proved, the carried one shown
    # by nothing — gives way to what this period proved, and says so
    contradicted, cr_tried, cr_agree = {}, 0, 0
    for le, was in carried.items():
        now = routes.get(le)
        if now:
            cr_tried += 1
            cr_agree += bool(now & was)
            if not (now & was):
                contradicted[le] = (sorted(was), sorted(now))
    carried_ok = cr_tried >= 20 and cr_agree / cr_tried >= min_precision
    carried_only = set()
    for le, was in carried.items():       # an entity this period shows nothing for
        if not routes.get(le):
            routes[le] = set(was)
            carried_only.add(le)

    # inferred routes: an entity no group proved is placed where its days' cash could sit —
    # the right entity whose items on each of its dates can hold that date's total. The
    # rule is tried first on the entities whose routes are proved, and trusted only as far
    # as it agrees with them.
    # the cash on each right entity's day that no proved allocation already accounts for
    r_day_total = defaultdict(int)
    for j in range(R.n):
        if R.day[j] is not None and R.ent[j] is not None:
            r_day_total[(R.ent[j], R.day[j])] += R.c[j]
    for grp in groups:
        for (i, j), c in grp["alloc"].items():
            if R.day[j] is not None and R.ent[j] is not None:
                r_day_total[(R.ent[j], R.day[j])] -= c
    r_ents = sorted(set(R.ent) - {None})
    taken = defaultdict(int)              # day totals of entities already placed by inference

    def open_days(e):
        days = defaultdict(int)
        for i in range(L.n):
            if L.ent[i] == e and L.day[i] is not None and \
                    basis.get(("L", i)) not in ("allocation", "solver"):
                days[L.day[i] + lo] += L.c[i]
        return days

    def infer_route(e):
        """(entity, why, margin): the one right entity whose unaccounted cash holds this
        entity's open total on nearly all its dates, well clear of the next."""
        days = open_days(e)
        if len(days) < 3:
            return None, None, 0.0
        score = {a: sum(r_day_total[(a, d)] - taken[(a, d)] >= v for d, v in days.items())
                 / len(days) for a in r_ents}
        ranked = sorted(score.items(), key=lambda x: (-x[1], x[0]))
        best, runner = ranked[0], (ranked[1] if len(ranked) > 1 else (None, 0.0))
        if best[1] >= 0.9 and best[1] - runner[1] >= 0.2:
            return best[0], f"{best[1]:.0%} of its dates, next {runner[1]:.0%}", best[1] - runner[1]
        return None, None, 0.0

    inferred, inf_tried, inf_agree = {}, 0, 0
    if ents == "learn":
        for e, rs in routes.items():
            if len(rs) == 1 and e not in carried_only:
                a, _, _ = infer_route(e)
                if a is not None:
                    inf_tried += 1
                    inf_agree += a in rs
        inf_ok = inf_tried >= 20 and inf_agree / inf_tried >= min_precision
        todo = set(L.ent) - {None} - {e for e in routes if e not in carried_only}
        while inf_ok and todo:            # the clearest first; its cash then leaves its days
            calls = [(m, e, a, why) for e in sorted(todo)
                     for a, why, m in [infer_route(e)] if a is not None]
            if not calls:
                break
            m, e, a, why = max(calls)
            inferred[e] = (a, why)
            todo.discard(e)
            for d, v in open_days(e).items():
                taken[(a, d)] += v

    def anchor(i):
        """The right items of i's entity inside the window, any status: ([j], why-not)."""
        if ents == "none" or L.day[i] is None or L.ent[i] is None:
            return [], "no entity or date"
        rs = routes.get(L.ent[i]) if ents == "learn" else None
        if ents == "learn" and not rs:
            if L.ent[i] not in inferred:
                return [], "entity unrouted"
            rs = {inferred[L.ent[i]][0]}
        near = [j for k in range(L.day[i] + lo, L.day[i] + hi + 1) for j in R_by_day.get(k, ())
                if (R.ent[j] in rs if ents == "learn" else ent_ok(i, j))]
        return near, (None if near else "no right item on its date")

    def spare(near):
        """Right items that other items do not already fill to the cent."""
        return [j for j in near if basis.get(("R", j)) != "allocation"] or near

    # calibration: the anchor rule tried on the items the allocation already proved
    tried = agree = 0
    for i in range(L.n):
        if basis.get(("L", i)) == "allocation" and len(link[("L", i)]) == 1:
            near, why = anchor(i)
            if len(near) == 1:
                tried += 1
                agree += near[0] in link[("L", i)]
    precision = agree / tried if tried else 0.0
    rule_ok = tried >= 30 and precision >= min_precision
    for i in range(L.n):
        if basis.get(("L", i)) in ("allocation", "solver"):
            continue
        near, why = anchor(i)
        unrouted = why == "entity unrouted"
        if unrouted and L.day[i] is not None:     # every right item on its date, for review
            near = [j for k in range(L.day[i] + lo, L.day[i] + hi + 1)
                    for j in R_by_day.get(k, ())]
        near = spare(near)
        if not near:
            review[("L", i)] = why
            continue
        for j in near:
            link[("L", i)].add(j)
            link[("R", j)].add(i)
        basis[("L", i)] = "anchor"
        e = L.ent[i]
        strength = max(evidence[e].values(), default=0) if ents == "learn" else min_evidence
        if ents == "learn" and e in carried_only and carried_ok:
            strength = max(strength, min_evidence)     # a carried route that has held up
        if unrouted:
            review[("L", i)] = ("entity unrouted: the one right item on its date" if len(near) == 1
                                else f"entity unrouted: one of {len(near)} right items on its date")
        elif not rule_ok:
            review[("L", i)] = f"anchor rule unproved ({agree} of {tried} on proved items)"
        elif ents == "learn" and e in inferred:
            review[("L", i)] = f"route inferred, not proved ({inferred[e][1]})"
        elif ents == "learn" and e in carried_only and not carried_ok:
            review[("L", i)] = (f"route carried from an earlier period, not seen in this one "
                                f"(carried routes held for {cr_agree} of {cr_tried} entities "
                                f"this period shows)")
        elif len(near) > 1:
            review[("L", i)] = f"one of {len(near)} right items on its date"
        elif strength < min_evidence:
            review[("L", i)] = f"route shown by {strength} group(s)"
        if ents == "learn" and e in contradicted:
            notes[("L", i)].append(f"entity moved: carried route {contradicted[e][0]}, this "
                                   f"period proves {contradicted[e][1]}")
    for j in range(R.n):
        if ("R", j) not in basis and link[("R", j)]:
            basis[("R", j)] = "anchor"

    # a date that finds nothing: an item with no date, or none of whose entity's right items
    # fall on it, is looked for by amount — the right item nearby whose remainder (its value
    # less everything already linked to it alone) equals the item. Always flagged.
    remainder = {j: R.c[j] for j in range(R.n)}
    for grp in groups:
        for (i, j), c in grp["alloc"].items():
            remainder[j] -= c
    for i in range(L.n):
        if basis.get(("L", i)) == "anchor" and len(link[("L", i)]) == 1:
            remainder[next(iter(link[("L", i)]))] -= L.c[i]
    wide = max(split_days, 31)
    lost = [i for i in range(L.n) if not link[("L", i)]
            and review.get(("L", i)) in ("no entity or date", "no right item on its date",
                                         "entity unrouted")]

    def pool_of(i):
        e = L.ent[i]
        rs = (routes.get(e) or ({inferred[e][0]} if e in inferred else None)) \
            if ents == "learn" else None
        return {j for j in range(R.n)
                if (L.day[i] is None or (R.day[j] is not None
                                         and lo - wide <= R.day[j] - L.day[i] <= hi + wide))
                and (not rs or R.ent[j] in rs) and (ents != "equal" or ent_ok(i, j))}
    pools = {i: pool_of(i) for i in lost}
    # what can take a lost item: one right item, or one entity's right items of one day
    # taken together (a deposit credited on two lines), by what is still unexplained on them
    units = defaultdict(list)
    for j in range(R.n):
        if R.day[j] is not None:
            units[(R.ent[j], R.day[j])].append(j)
    targets = {(j,): remainder[j] for j in range(R.n) if remainder[j] > 0}
    for js in units.values():
        if len(js) > 1:                   # a set link counts against the day it lies in
            inside = set(js)
            v = sum(remainder[j] for j in js) - sum(
                L.c[i] for i in {i for j in js for i in link[("R", j)]}
                if basis.get(("L", i)) == "anchor" and len(link[("L", i)]) > 1
                and link[("L", i)] <= inside)
            if v > 0:
                targets[tuple(sorted(js))] = v

    def why_of(i):
        return "no date" if L.day[i] is None else "no right item on its date"

    def span_of(i):
        return "" if L.day[i] is None else f" within {wide} days"

    def take(items, t, how):
        for i in items:
            for j in t:
                link[("L", i)].add(j); link[("R", j)].add(i)
                basis.setdefault(("R", j), "remainder")
            basis[("L", i)] = "remainder"
            review[("L", i)] = f"{why_of(i)}: {how}{span_of(i)}"
        for u in [u for u in targets if set(u) & set(t)]:
            del targets[u]
    for i in sorted(lost, key=lambda x: (-L.c[x], x)):
        if link[("L", i)]:
            continue
        fits = [t for t, v in targets.items() if v == L.c[i] and set(t) <= pools[i]]
        hit = [t for t in fits if len(t) == 1] or fits      # one right item before a day's
        if len(hit) == 1:
            t = hit[0]
            take([i], t, ("the one right item" if len(t) == 1 else
                          f"the {len(t)} right items of one day") +
                 " whose unexplained remainder equals its amount")
        elif len(hit) > 1:
            review[("L", i)] = (f"{why_of(i)}: {len(hit)} right items{span_of(i)} have an "
                                f"unexplained remainder equal to its amount")

    # two or more lost items in one right item: the one set of them that fills it exactly
    for t, v in sorted(targets.items(), key=lambda x: (-x[1], x[0])):
        if t not in targets:
            continue
        cand = [(i, L.c[i]) for i in sorted(lost) if not link[("L", i)] and set(t) <= pools[i]]
        got, how = _unique(cand, v, max_subset)
        if got and len(got) > 1:
            take(list(got), t, f"one of {len(got)} items that together fill the unexplained "
                               f"remainder of " + ("a right item" if len(t) == 1 else
                                                   f"{len(t)} right items of one day"))

    # the output
    rows = []
    alloc_rows = []

    def ids(side, x):
        other = R.id if side == "L" else L.id
        return ";".join(other[k] for k in sorted(link[(side, x)])) or None

    # the text contradicting a link is itself a reason to look
    for i in range(L.n):
        if mL.get(i) and link[("L", i)] and not (mL[i] & link[("L", i)]):
            hints[("L", i)].append("its text names " + ", ".join(R.id[j] for j in sorted(mL[i]))
                                   + "; linked elsewhere")
    for key in list(basis):
        if basis[key] == "solver" and not solver_ok:
            hints[key].append(f"solver allocation untested ({sv_agree} of {sv_tried} agreed "
                              f"on proved groups)")

    def rev(side, x):
        parts = ([review[(side, x)]] if (side, x) in review else []) + hints.get((side, x), [])
        return " | ".join(dict.fromkeys(parts)) or None

    def note(side, x):
        return " | ".join(dict.fromkeys(notes.get((side, x), []))) or None

    def label(x, settled):
        if x not in settled:
            return "ambiguous"
        return "solver" if solved_by.get(x) else "exact"
    for g, grp in enumerate(groups, start=1):
        for i in grp["L"]:
            rows.append(("left", L.id[i], "matched", g, grp["pas"],
                         label(("L", i), {("L", k) for k in grp["sL"]}), None,
                         ids("L", i), basis.get(("L", i)), rev("L", i), note("L", i)))
        for j in grp["R"]:
            rows.append(("right", R.id[j], "matched", g, grp["pas"],
                         label(("R", j), {("R", k) for k in grp["sR"]}), None,
                         ids("R", j), basis.get(("R", j)), rev("R", j), note("R", j)))
        for (i, j), c in sorted(grp["alloc"].items()):
            alloc_rows.append((g, L.id[i], R.id[j], c / 100))
    for i in sorted(openL):
        rows.append(("left", L.id[i], "unmatched", None, None, None, None,
                     ids("L", i), basis.get(("L", i)), rev("L", i), note("L", i)))
    for j in sorted(openR):
        rows.append(("right", R.id[j], "unmatched", None, None, None, None,
                     ids("R", j), basis.get(("R", j)), rev("R", j), note("R", j)))
    items = pl.DataFrame(rows, orient="row", schema={
        "side": pl.Utf8, "id": pl.Utf8, "status": pl.Utf8, "group": pl.Int64,
        "pass": pl.Utf8, "allocation": pl.Utf8, "reason": pl.Utf8, "link": pl.Utf8,
        "link_basis": pl.Utf8, "review": pl.Utf8, "note": pl.Utf8})
    allocations = pl.DataFrame(alloc_rows, orient="row", schema={
        "group": pl.Int64, "left_id": pl.Utf8, "right_id": pl.Utf8, "value": pl.Float64})
    pairs_ = sorted({(k, v) for k in evidence for v in evidence[k]} |
                    {(k, v) for k in carried for v in carried[k]})
    routes_df = pl.DataFrame(
        [(k, v, evidence[k][v], v in routes.get(k, ()), v in named.get(k, ()),
          v in carried.get(k, ()), k in contradicted and v in carried.get(k, ()))
         for k, v in pairs_], orient="row",
        schema={"left_entity": pl.Utf8, "right_entity": pl.Utf8, "groups": pl.Int64,
                "proved": pl.Boolean, "by_name": pl.Boolean, "carried": pl.Boolean,
                "contradicted": pl.Boolean})
    calibration = pl.DataFrame([
        ("anchor", tried, agree, round(precision, 4), rule_ok),
        ("inferred_route", inf_tried, inf_agree,
         round(inf_agree / inf_tried, 4) if inf_tried else 0.0,
         bool(inferred) or (inf_tried >= 20 and inf_agree / inf_tried >= min_precision)),
        ("carried_route", cr_tried, cr_agree, round(cr_agree / cr_tried, 4) if cr_tried else 0.0,
         carried_ok),
        ("solver", sv_tried, sv_agree, round(sv_agree / sv_tried, 4) if sv_tried else 0.0,
         solver_ok)],
                               orient="row", schema={"rule": pl.Utf8, "tried": pl.Int64,
                                                     "agreed": pl.Int64, "precision": pl.Float64,
                                                     "trusted": pl.Boolean})
    return Resolution(items=items, allocations=allocations, routes=routes_df,
                      calibration=calibration)


def _selfcheck() -> int:
    import datetime as dt
    bad: list[str] = []

    def expect(cond, what):
        if not cond:
            bad.append(what)

    D = dt.date(2024, 3, 1)

    def day(n):
        return D + dt.timedelta(days=n)
    L_rows = [  # id, entity, day, value
        ("i1", "c1", 0, 100.00), ("i2", "c1", 0, 250.50),    # d1 = i1 + i2: one remittance
        ("i3", "c2", 0, 75.25),                              # d2 = i3
        ("i4", "c2", 1, 60.00),                              # i4 = d3 + d3b: two bank lines
        ("i5", "c3", 3, 500.00), ("i6", "c3", 3, 40.00),     # i5 or i6 paid partly in d4
        ("i7", "c4", 5, 30.00), ("i8", "c4", 5, 30.00),      # twins in d6
        ("i9", "c5", 0, 999.99),                             # d7, account B
        ("i10", "c1", 9, 81.10), ("i11", "c2", 9, 12.34),    # d8 = i10 + i11
        ("i12", "c3", 20, 55.00),                            # no cash: stays open
        ("i13", "c4", 12, 900.00),                           # 400 on day 10, 500 on day 12
        ("i14", "c1", 32, 110.00), ("i15", "c2", 33, 70.00),  # a chain of parts: S1 on
        ("i16", "c1", 35, 90.00),                            # day 30 feeds i14 and i15
    ]
    R_rows = [
        ("d1", "A", 0, 350.50), ("d2", "A", 0, 75.25), ("d3", "A", 1, 25.00),
        ("d3b", "A", 1, 35.00), ("d4", "A", 1, 200.00), ("d5", "A", 3, 340.00),
        ("d6", "A", 5, 60.00), ("d7", "B", 0, 999.99), ("d8", "A", 9, 93.44),
        ("d9", "A", 10, 400.00), ("d10", "A", 12, 500.00),
        ("s1", "A", 30, 50.00), ("s2", "A", 31, 25.00),     # parts: 30 + 20 in s1, 25 in s2
        ("e14", "A", 32, 80.00), ("e15", "A", 33, 25.00), ("e16", "A", 35, 90.00),
    ]
    left = pl.DataFrame([(a, b, day(c), d) for a, b, c, d in L_rows], orient="row",
                        schema=["id", "entity", "date", "value"])
    right = pl.DataFrame([(a, b, day(c), d) for a, b, c, d in R_rows], orient="row",
                         schema=["id", "entity", "date", "value"])
    res = resolve(left, right, window=(0, 0), split_days=30)
    it = {(r["side"], r["id"]): r for r in res.items.to_dicts()}

    def grp(s, x):
        return it[(s, x)]["group"]
    a = {(r["left_id"], r["right_id"]): r["value"] for r in res.allocations.to_dicts()}
    expect(grp("left", "i1") == grp("left", "i2") == grp("right", "d1"), "d1 = i1 + i2")
    expect(grp("left", "i3") == grp("right", "d2"), "d2 = i3")
    expect(grp("left", "i4") == grp("right", "d3") == grp("right", "d3b"),
           "a left item on two right lines")
    expect(grp("left", "i5") == grp("right", "d4") == grp("right", "d5") == grp("left", "i6"),
           "a part payment joins its two deposits")
    expect(it[("left", "i5")]["allocation"] == "solver" and it[("left", "i5")]["review"],
           "i5 or i6 split: the solver prefers links on each item's own date, flagged")
    expect(grp("left", "i7") == grp("left", "i8") == grp("right", "d6"), "twins tie as a group")
    expect(grp("left", "i9") == grp("right", "d7"), "account B")
    expect(grp("left", "i10") == grp("right", "d8"), "d8 = i10 + i11")
    expect(it[("left", "i12")]["status"] == "unmatched", "an item with no cash stays open")
    expect(grp("left", "i13") == grp("right", "d9") == grp("right", "d10")
           and it[("left", "i13")]["pass"] == "instalment", "i13 in two instalments")
    expect(a.get(("i5", "d4")) == 200.0 and a.get(("i5", "d5")) == 300.0
           and a.get(("i6", "d5")) == 40.0, "i6 stays whole on its date; i5 takes the part")
    expect(a.get(("i13", "d9")) == 400.0 and a.get(("i13", "d10")) == 500.0,
           "a lone split item is allocated exactly")
    expect(grp("left", "i16") == grp("right", "e16"), "e16 = i16")
    chain = {grp("left", x) for x in ("i14", "i15")} | \
        {grp("right", x) for x in ("s1", "s2", "e14", "e15")}
    expect(len(chain) == 1 and None not in chain, "a chain of parts closes on its running balance")
    lv = dict(zip(left["id"], left["value"]))
    rv = dict(zip(right["id"], right["value"]))
    for (g,), sub in res.items.filter(pl.col("status") == "matched").group_by("group"):
        tot = sum(lv[x] if sd == "left" else -rv[x] for sd, x in zip(sub["side"], sub["id"]))
        expect(abs(tot) < 0.005, f"group {g} ties")
    ex = res.items.filter(pl.col("allocation") == "exact")
    for sd, x in zip(ex["side"], ex["id"]):
        col, want = ("left_id", lv[x]) if sd == "left" else ("right_id", rv[x])
        got = res.allocations.filter(pl.col(col) == x)["value"].sum()
        expect(abs(got - want) < 0.005, f"an exact {sd} item {x} is allocated in full")
    expect(res.routes.filter(pl.col("left_entity") == "c5")["right_entity"].to_list() == ["B"],
           "the routing c5 -> B is learned")
    expect(res.routes.filter(pl.col("left_entity") == "c1")["proved"].to_list() == [True],
           "c1 -> A, shown by two groups, is proved")
    ln = {r["id"]: r for r in res.items.filter(pl.col("side") == "left").to_dicts()}
    expect(ln["i1"]["link"] == "d1" and ln["i1"]["link_basis"] == "allocation",
           "a proved item links by allocation")
    expect(ln["i12"]["link"] is None and ln["i12"]["review"] is not None,
           "an item with no right item on its date is flagged, not linked")
    expect(res.calibration["rule"].to_list() == ["anchor", "inferred_route", "carried_route", "solver"],
           "the calibration reports each rule")
    # names that differ in form, and an amount that singles nothing out
    D2 = [day(k) for k in range(6)]
    lft = pl.DataFrame({"id": ["a1", "s1", "s2", "s3"],
                        "entity": ["Acme Corporation", "Subs Co", "Subs Co", "Subs Co"],
                        "date": [D2[0], D2[1], D2[2], D2[3]], "value": [120.0, 19.99, 19.99, 19.99]})
    rgt = pl.DataFrame({"id": ["b1", "t1", "t2", "t3"],
                        "entity": ["ACME CORP.", "SUBS", "SUBS", "SUBS"],
                        "date": [D2[0], D2[1], D2[2], D2[3]], "value": [120.0, 19.99, 19.99, 19.99]})
    r2 = resolve(lft, rgt, entities="equal")
    expect(r2.items.filter(pl.col("id") == "a1")["group"][0] ==
           r2.items.filter(pl.col("id") == "b1")["group"][0], "names agree as keys")
    r3 = resolve(lft, rgt.with_columns(entity=pl.lit("acct-9")))
    ro = r3.routes.filter(pl.col("left_entity") == "Subs Co")
    expect(ro.height == 0 or not ro["proved"][0], "a repeated amount proves no route")
    # free text: a memo that quotes invoice ids, and one whose amounts do not agree
    lt = pl.DataFrame({"id": ["INV-1001", "INV-1002", "INV-1003"],
                       "entity": ["Globex", "Globex", "Initech Ltd"],
                       "date": [D2[0], D2[0], D2[1]], "value": [300.0, 200.0, 99.5]})
    rt = pl.DataFrame({"id": ["m1", "m2"], "entity": ["acct-1", "acct-2"],
                       "date": [D2[0], D2[1]], "value": [500.0, 120.0],
                       "text": ["ACH GLOBEX REMIT INV 1001 INV-1002", "INITECH WIRE REF INV1003"]})
    r4 = resolve(lt, rt)
    t = {r["id"]: r for r in r4.items.to_dicts()}
    expect(t["INV-1001"]["pass"] == "text_ref" and t["INV-1001"]["group"] == t["m1"]["group"]
           == t["INV-1002"]["group"], "a memo quoting two invoices ties them to its deposit")
    expect(t["INV-1003"]["status"] == "unmatched" and "text ties" in (t["INV-1003"]["review"] or ""),
           "a memo whose amounts differ reaches the agent as a review")
    # an item the register left undated is found by what is unexplained on a right item
    und = left.vstack(pl.DataFrame([("i17", "c1", None, 42.42)], orient="row",
                                   schema=left.schema))
    r5 = resolve(und, right.vstack(pl.DataFrame([("x1", "A", day(60), 42.42)], orient="row",
                                                schema=right.schema)), split_days=30)
    u = r5.items.filter(pl.col("id") == "i17").row(0, named=True)
    expect(u["link"] == "x1" and u["link_basis"] == "remainder" and u["review"],
           "an undated item links, flagged, to the one right item whose remainder equals it")
    # a carried route: a prior that this period can contradict, never a lock
    wrong = pl.DataFrame({"left_entity": ["c1", "c5"], "right_entity": ["B", "B"]})
    r6 = resolve(left, right, window=(0, 0), split_days=30, known_routes=wrong)
    ro6 = {(a_, b_): r for a_, b_, *r in r6.routes.select(
        "left_entity", "right_entity", "carried", "contradicted", "proved").iter_rows()}
    expect(ro6[("c1", "B")][1] and ro6[("c1", "A")][2],
           "a carried route the period disproves is marked contradicted; the proved one stands")
    expect(r6.items.filter(pl.col("id") == "i1")["link"][0] == "d1",
           "a wrong carried route does not move a proved link")
    res0 = resolve(left, right, window=(0, 0), split_days=0)
    expect(res0.items.filter(pl.col("id") == "i13")["status"][0] == "unmatched",
           "split_days=0 leaves a part payment open")
    try:
        from matching import check_assignment
        check_assignment(left, right, res.items, left_id="id", right_id="id", amount="value")
    except ImportError:
        pass
    except Exception as e:  # noqa: BLE001
        bad.append(f"check_assignment refused the output: {e}")
    for df, what in ((left.drop("date"), "a stream without a date column"),
                     (left.with_columns(id=pl.lit("x")), "repeated ids")):
        try:
            resolve(df, right)
            bad.append(f"did not refuse {what}")
        except ValueError:
            pass

    for b in bad:
        print("FAIL", b)
    print("resolve.py self-check:", "FAIL" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    sys.exit(_selfcheck())
