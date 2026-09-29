#!/usr/bin/env python3
"""A check's figures ledger (EVIDENCE.md § 3), its ties, and its prose numbers, as one
importable module.

Every step that mints a figure imports this rather than writing its own `fig()`:

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from evidence import select
    from figures import Ledger, figure, room, check_output, declared, fmt

    L = Ledger(RUN, "a5_bridge_retention")      # resumes workpapers/figures-<check>.yaml
    rows, e = select(RUN, "SELECT ... FROM ...", id="E.a5.cube", control="arr")
    L.cite(e)                                   # -> workpapers/evidence-<check>.yaml
    L.population("P.a5.cohort.fy2025", "Customers with ARR at 30 September 2024",
                 total_n=812, included_n=812, citations=["E.a5.cube"])
    L.fig("F.a5.cohort_arr.fy2025", "Cohort ARR at 30 September 2024", 81_234_567.12,
          "usd", "sum(arr) over E.a5.cube where month = 2024-09", [room("cube", "E.a5.cube")],
          population="P.a5.cohort.fy2025")
    L.fig("F.a5.nrr.fy2025", "Net revenue retention FY2025", nrr, "pct",
          "F.a5.nrr_num.fy2025 / F.a5.cohort_arr.fy2025",
          [("numerator", "F.a5.nrr_num.fy2025"), ("denominator", "F.a5.cohort_arr.fy2025")])
    t = L.tie("T.a1.revenue.fy2025", "Income statement revenue to TB, FY2025",
              "F.a1.is.revenue.fy2025", "F.a1.tb.revenue.fy2025",
              tolerance=params.get("tolerance"), pct_tolerance=params.get("pct_tolerance"))
    L.write()                                   # refuses, writing nothing, on any dead end
    L.sub("Net revenue retention was {F.a5.nrr.fy2025} in FY2025.")   # "... was 104.2% ..."

**One rule per field, the same in every check.** `fig()` refuses what the gates refuse
later, and records nothing when it refuses: an id outside the grammar or minted twice in one pass, a unit outside `UNITS`, an empty `inputs`
or a role-less input, a zero, null or NaN value with no `zero_basis`, a `measured_zero`
with no population or over an empty one, an infinite value, an `extra` field that would
overwrite one of the entry's own, and a value (in `extra`, an exclusion, ...) YAML cannot
write as plain data (numpy scalars are converted). A population's exclusions are each
named with a count, and the counts add up to `total_n - included_n`. Money is stored to
its currency's minor unit, a count as an integer, a percentage or rate as a fraction
(0.174 is 17.4%).

**Units.** A money unit is a currency code from `scripts/style.py` (`usd`, `eur`, `gbp`,
`jpy`, `kwd`, ...): the unit names the currency, stored at its minor units (JPY 0, USD 2,
KWD 3). The others: `pct` (a share, one decimal shown), `rate` (an interest or growth
rate, full precision shown: `4.25%`), `fx_rate` (units of one currency per another,
`1.0679`), `days` (`45.3 days`), `count` (whole), `quantity` (fractional, `12.5`) and
`ratio` (a multiple, `1.3x`). A tie refuses two currencies outright; translating is the
caller's arithmetic, with the rate among the figure's inputs.

**Stated scale.** A passthrough (`disposition="as_stated"`) of a source that presents in
thousands takes `stated_scale="thousands"`: the value passed is the number AS STATED, the
value stored is in units (multiplied out exactly, e.g. 1.001 thousand is 1,001), and the
conversion is appended to the `expression` so the reader re-performs it. A sign flip is
written in the expression (`x * -1`).

**Every reference resolves when the ledger is written, not at the report.** `write()`
reads every id the run's `workpapers/*.yaml` declare (as `check_workbook.py --run-dir`
does) plus what this ledger holds, and refuses the whole write, naming each dead end,
when an input, a population, a citation or an `F.`/`P.`/`E.` id in an `expression` does
not resolve — including a range (`E.x.fy2023..fy2025`), a wildcard (`E.x.memos_*`) or a
bare stem (`E.a4.memos`). Cite each id whole; a family written with placeholders
(`F.a4.arr.<dimension>.<column>`, the form `link_workbook.py` links) resolves when at
least one declared id belongs to it. `*` right after an id is multiplication when an
operand follows it (`F.a*2`, `F.a*F.b`, `F.a*(1+x)`), a wildcard otherwise (`E.x.memos_*`).
It also refuses an input whose kind contradicts its citation (a `room_file` input citing a
`run_artifact` read, a `check_output` citing a room read), a `measured_zero` over a `P.`
whose `included_n` is 0, and a tie whose side has moved since the tie was classified.

**Inputs.** `room(role, "E.x")`, `check_output(role, "E.x")`, `figure(role, "F.x")`,
`declared(role, "params.tolerance")`, or a `(role, id)` tuple: an `F.` id is a figure, an
`E.` id a room file (a check output when its citation, in this ledger or another check's,
is `file_role: run_artifact`; one cited nowhere yet is classified when the ledger is
written), and anything else a declared field.

**Ties** (check-tie SKILL § 4). `tie(id, label, a, b, tolerance=, pct_tolerance=)` reads
the two sides' figures, mints the difference figure `a - b` (default id: the tie's id with
`F.` for `T.` plus `.difference`; population: side a's, else the two sides compared), and
classifies: `tolerance` is an absolute bound in the
tie's unit, `pct_tolerance` a fraction of side `b` (the reference side: `0.005` is 0.5%).
Given both, the tie passes only when **both** hold and fails when either does not; given
one, that one decides; given neither, the difference must be below half the display unit
(`DISPLAY_HALF`: half a whole currency unit, half a count, `0.05%`, `0.05` of a day, a
quantity or a multiple, `0.00005` of a rate or an FX rate). A tolerance the user did not declare is never passed. The
result is `pass` or `fail` with each test's limit and measure; `warn` (an explained
difference) is the worker's call after resolution. The record is kept on the difference
figure (`tie:`), so a resumed ledger's `L.ties` holds the ties of earlier passes too.
`tie_table(L.ties)` is the Markdown schedule for `checks/<check>.md`, each limit shown at
its own precision.

**Prose.** `fmt(value, unit)` writes DOCTRINE.md § Number conventions through
`scripts/style.py`: `$9,438,108`, `($1,204)` for a negative, `€5,000,000`, `17.4%`,
`100%`, `4.25%` (a rate), `1.0679` (an FX rate), `45.3 days`, `4,171`, `12.5`, `1.3x`;
`style="deck"` scales money (`$9.4M`, `$81K`, `$1.2B`, REPORT.md § 4), `style="cell"`
shows its minor units; `None` reads *unable to establish*. `L.sub(template)`
(or `load(RUN).sub(...)`) replaces each `{F.id}` or `{F.id:deck}` with the formatted
figure, so a sentence never types a number; it refuses a `{`, id and `}` it cannot
substitute (an unknown style, a space inside the braces). `load()`'s readers refuse an id
the run's ledgers state with different values (EVIDENCE.md § 0) until the disagreement is
resolved. `md_table(headers, rows, units)` writes a
Markdown table whose numeric cells go through `fmt`.

Requires pyyaml — run as
`uv run --project ${CLAUDE_PLUGIN_ROOT} python3`.
"""
from __future__ import annotations

import copy
import datetime as dt
import decimal
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_workbook  # noqa: E402  sibling: the id grammar and the run's declared ids
import style  # noqa: E402  sibling: currencies and how a number is written
from evidence import write_ledger  # noqa: E402

__all__ = ["Ledger", "FigureSet", "load", "fmt", "tie_table", "room", "check_output",
           "figure", "declared", "UNITS", "MONEY_UNITS", "is_money", "DISPOSITIONS",
           "ZERO_BASES", "md_table"]

# A money unit is a currency code (scripts/style.py); the rest are what a figure measures.
MONEY_UNITS = tuple(style.CURRENCIES)
OTHER_UNITS = ("pct", "count", "ratio", "days", "rate", "fx_rate", "quantity")
UNITS = MONEY_UNITS + OTHER_UNITS
DISPOSITIONS = ("measured", "inferred", "as_stated")
ZERO_BASES = ("measured_zero", "not_measured", "not_applicable")
SOURCE_KEY = {"room_file": "citation_id", "check_output": "citation_id",
              "figure": "figure_id", "declared": "field"}
# Half the display unit (DOCTRINE.md § Number conventions): a whole currency unit, an
# integer count, one decimal of a percentage, one decimal of a day, a quantity's or a
# multiple's shown precision, four places of a rate or an FX rate.
DISPLAY_HALF = {"count": 0.5, "pct": 0.0005, "ratio": 0.05, "days": 0.05,
                "quantity": 0.05, "rate": 0.00005, "fx_rate": 0.00005,
                **{c: 0.5 for c in MONEY_UNITS}}


def is_money(unit) -> bool:
    return style.is_money(unit)


UNABLE = "unable to establish"

LEDGER_ID = check_workbook.LEDGER_ID
ID_TOKEN = check_workbook.ID_TOKEN
# An id written as a set it cannot resolve to: a range (`E.x.fy2023..fy2025`) or a
# wildcard (`E.x.memos_*`). A family written with placeholders (`F.a4.arr.<dimension>`)
# is the convention link_workbook.py links, and resolves when the family has a member.
NOT_WHOLE = re.compile(r"\b[A-Z]{1,2}\.[A-Za-z0-9_-][A-Za-z0-9_.-]*?"
                       r"(?:\.\.|[_.-]\*|\*(?!\s*(?:[\d(.-]|[A-Z]{1,2}\.)))")
TEMPLATE = re.compile(r"\{([A-Z]{1,2}\.[A-Za-z0-9_.-]*[A-Za-z0-9])(?::(prose|deck|cell))?\}")
# Any `{<id>...}`, well formed or not: one left after TEMPLATE substitution is refused.
TEMPLATE_ANY = re.compile(r"\{\s*[A-Z]{1,2}\.[^{}]*\}")
# A ledger's name: the check id (no `-`: check_playbook.CHECK_ID), or `profile-<source>`.
LEDGER_NAME = re.compile(r"[a-z0-9][a-z0-9_]*|profile-[a-z0-9][a-z0-9_-]*")
FIG_FIELDS = frozenset({"id", "label", "value", "unit", "expression", "inputs", "population",
                        "zero_basis", "caveats", "disposition", "stated_scale", "stated_value",
                        "tie"})
POP_FIELDS = frozenset({"id", "label", "total_n", "included_n", "exclusions", "citations"})


# --- inputs --------------------------------------------------------------------------------
def room(role: str, citation_id: str) -> dict:
    return {"role": role, "source_type": "room_file", "citation_id": citation_id}


def check_output(role: str, citation_id: str) -> dict:
    return {"role": role, "source_type": "check_output", "citation_id": citation_id}


def figure(role: str, figure_id: str) -> dict:
    return {"role": role, "source_type": "figure", "figure_id": figure_id}


def declared(role: str, field: str) -> dict:
    return {"role": role, "source_type": "declared", "field": field}


# --- formatting ----------------------------------------------------------------------------
def _num(v):
    """A plain Python number (numpy, polars and Decimal scalars included), or None."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError(f"a figure value is a number, not {v!r}")
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, decimal.Decimal):
        return float(v)
    if hasattr(v, "item"):                       # numpy scalar
        return _num(v.item())
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"a figure value is a number, not {type(v).__name__} {v!r}")


def _plain(x, where: str):
    """`x` as the plain data YAML writes (dicts, lists, str, int, float, bool, None, dates):
    numpy and polars scalars and Decimals converted, tuples as lists; anything else, or a
    non-finite number, refused naming `where`."""
    if x is None or isinstance(x, (str, bool, int, dt.date)):
        return x
    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError(f"{where}: {x!r} is not a finite number")
        return x
    if isinstance(x, dict):
        return {str(k): _plain(v, f"{where}.{k}") for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v, f"{where}[{i}]") for i, v in enumerate(x)]
    if isinstance(x, decimal.Decimal):
        return _plain(float(x), where)
    if hasattr(x, "item") and not hasattr(x, "__len__"):   # numpy / polars scalar
        return _plain(x.item(), where)
    raise ValueError(f"{where}: {type(x).__name__} {x!r} is not plain data (a number, text, "
                     f"a date, a list or a mapping)")


def _trim(s: str) -> str:
    """`4.2500` -> `4.25`, `12.50` -> `12.5`, `3.00` -> `3`."""
    return s.rstrip("0").rstrip(".") if "." in s else s


def fmt(value, unit: str, style: str = "prose", precision: int | None = None) -> str:
    """One figure as a sentence states it (DOCTRINE.md § Number conventions). Money goes
    through `scripts/style.py`: `prose` whole units, `deck` scaled (`$9.4M`), `cell` the
    currency's minor units. `precision` overrides the decimals of a `ratio` (1), an
    `fx_rate` (4), `days` (1) or a `quantity` (up to 2). Negatives in parentheses; a value
    that rounds to zero as shown is never parenthesized; `None` reads *unable to
    establish*."""
    if unit not in UNITS:
        raise ValueError(f"unit {unit!r}: a currency code (scripts/style.py) or one of "
                         f"{', '.join(OTHER_UNITS)}")
    if style not in ("prose", "deck", "cell"):
        raise ValueError(f"style {style!r}: prose, deck or cell")
    v = _num(value)
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return UNABLE
    if isinstance(v, float) and math.isinf(v):
        raise ValueError(f"{v!r} is not a figure: a division by zero is not_applicable, "
                         f"value None")
    if unit in MONEY_UNITS:
        return style_money(v, unit, style)
    neg = v < 0
    # A count keeps an int whole (no float rounding past 2**53); every other unit is a float.
    a = abs(v) if unit == "count" and isinstance(v, int) else abs(float(v))
    if unit == "pct":
        p = round(a * 100, 1)
        s = f"{p:.0f}%" if p.is_integer() else f"{p:.1f}%"
        neg = neg and p != 0
    elif unit == "rate":
        p = round(a * 100, 6 if precision is None else precision)
        s = _trim(f"{p:.6f}") + "%"
        neg = neg and p != 0
    elif unit == "count":
        s = f"{a:,}" if isinstance(a, int) else f"{a:,.0f}"
        neg = neg and round(a) != 0
    elif unit == "fx_rate":
        d = 4 if precision is None else precision
        s = f"{a:,.{d}f}"
        neg = neg and round(a, d) != 0
    elif unit == "days":
        d = 1 if precision is None else precision
        s = f"{a:,.{d}f} days"
        neg = neg and round(a, d) != 0
    elif unit == "quantity":
        d = 2 if precision is None else precision
        s = _trim(f"{a:,.{d}f}")
        neg = neg and round(a, d) != 0
    else:
        d = 1 if precision is None else precision
        s = f"{a:,.{d}f}x"
        neg = neg and round(a, d) != 0
    return f"({s})" if neg else s


style_money = style.money


def md_table(headers, rows, units, style_: str = "prose") -> str:
    """A Markdown table whose numeric cells are written by `fmt` in `style_`
    (`prose`, `deck` or `cell`): `units` names each column's unit, `None` for text.
    Numeric columns are right-aligned. A `None` value reads empty."""
    headers, units = list(headers), list(units)
    if len(units) != len(headers):
        raise ValueError(f"{len(units)} units for {len(headers)} columns")
    for u in units:
        if u is not None and str(u).lower() not in UNITS:
            raise ValueError(f"unit {u!r} is not a figures unit")
    esc = lambda s: str(s).replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")  # noqa: E731
    out = ["| " + " | ".join(esc(h) for h in headers) + " |",
           "|" + "|".join("---:" if u else "---" for u in units) + "|"]
    for i, r in enumerate(rows, 1):
        r = list(r)
        if len(r) != len(headers):
            raise ValueError(f"row {i}: {len(r)} values for {len(headers)} columns")
        cells = ["" if v is None else fmt(v, str(u).lower(), style_) if u else esc(v)
                 for v, u in zip(r, units)]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def _sub(template: str, lookup) -> str:
    def one(m):
        fid, style = m.group(1), m.group(2) or "prose"
        f = lookup(fid)
        if f is None:
            raise KeyError(f"{fid}: no figure with this id in the run's ledgers")
        return fmt(f.get("value"), f.get("unit"), style)
    out = TEMPLATE.sub(one, template)
    left = TEMPLATE_ANY.search(out)
    if left:
        raise ValueError(f"{left.group(0)!r} is no figure reference this substitutes - "
                         f"`{{F.id}}` or `{{F.id:deck}}` (prose, deck or cell), no spaces")
    return out


# --- the run's figures ---------------------------------------------------------------------
def _yaml_load(path: pathlib.Path):
    import yaml
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    doc = yaml.load(path.read_text(encoding="utf-8"), Loader=loader)
    return doc or []


def _statement(e: dict):
    """What an entry states, to compare two ledgers' copies of one id."""
    if str(e.get("id", "")).startswith("P."):
        return ("population", e.get("total_n"), e.get("included_n"))
    return (e.get("value"), e.get("unit"))


class FigureSet(dict):
    """Every `F.`/`P.` entry in the run's figures ledgers, by id. An id two ledgers state
    differently is in `conflicts` (id -> [(ledger, statement), ...]), and reading it
    raises: a disagreement is a finding (EVIDENCE.md § 0)."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.conflicts: dict[str, list] = {}
        self.origin: dict[str, str] = {}

    def _agreed(self, fid: str) -> None:
        if fid in self.conflicts:
            said = "; ".join(f"{n} states {v!r}" for n, v in self.conflicts[fid])
            raise ValueError(f"{fid}: the run's ledgers disagree ({said}) - a disagreement "
                             f"is a finding (EVIDENCE.md § 0); resolve it before stating it")

    def __getitem__(self, fid: str):
        self._agreed(fid)
        return super().__getitem__(fid)

    def get(self, fid: str, default=None):
        if fid in self:
            self._agreed(fid)
        return super().get(fid, default)

    def value(self, fid: str):
        return self[fid].get("value")

    def fmt(self, fid: str, style: str = "prose") -> str:
        return fmt(self[fid].get("value"), self[fid].get("unit"), style)

    def sub(self, template: str) -> str:
        return _sub(template, self.get)


def load(run_dir, checks=None, *, exclude=()) -> FigureSet:
    """The figures ledgers of `checks` (all of them when None, less the file names in
    `exclude`) as one FigureSet."""
    wp = pathlib.Path(run_dir) / "workpapers"
    out = FigureSet()
    names = sorted(wp.glob("figures-*.yaml")) if checks is None else \
        [wp / f"figures-{c}.yaml" for c in ([checks] if isinstance(checks, str) else checks)]
    for f in names:
        if f.name in exclude:
            continue
        if not f.is_file():
            raise FileNotFoundError(f"{f}: no such ledger")
        doc = _yaml_load(f)
        if not isinstance(doc, list):
            raise ValueError(f"{f.name}: the ledger is not a YAML list (EVIDENCE.md § 0)")
        for e in doc:
            if not (isinstance(e, dict) and isinstance(e.get("id"), str)):
                continue
            fid = e["id"]
            if fid not in out:
                dict.__setitem__(out, fid, e)
                out.origin[fid] = f.name
            elif _statement(e) != _statement(dict.__getitem__(out, fid)):
                out.conflicts.setdefault(
                    fid, [(out.origin[fid], _statement(dict.__getitem__(out, fid)))]
                ).append((f.name, _statement(e)))
    return out


def _limit(v, test: str, unit: str) -> str:
    """A tie test's limit or measure at its own precision, e.g. a 0.05% limit reads 0.05%
    where the unit's display rounding would show 0.1%."""
    if v is None:
        return "n/a"
    if test == "pct_tolerance" or unit in ("pct", "rate"):
        return _trim(f"{v * 100:,.8f}") + "%"
    if unit in MONEY_UNITS:
        return fmt(v, unit, "cell")
    return _trim(f"{v:,.10f}") + {"ratio": "x", "days": " days"}.get(unit, "")


def tie_table(ties) -> str:
    """The tie schedule as a Markdown table, for `checks/<check>.md`."""
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    lines = ["| tie | side A | side B | difference | test | status |",
             "|---|---|---|---|---|---|"]
    for t in ties:
        u = t["unit"]
        tests = "; ".join(
            f"{x['test']} {_limit(x['measured'], x['test'], u)} "
            f"{'<=' if x['passed'] else '>'} {_limit(x['limit'], x['test'], u)}"
            for x in t["tests"])
        lines.append(f"| {t['id']} {esc(t['label'])} | {t['side_a']['figure_id']} "
                     f"{fmt(t['side_a']['value'], u, 'cell')} | {t['side_b']['figure_id']} "
                     f"{fmt(t['side_b']['value'], u, 'cell')} | {t['difference_figure']} "
                     f"{fmt(t['difference'], u, 'cell')} | {tests} | {t['status']} |")
    return "\n".join(lines) + "\n"


# --- one check's ledger --------------------------------------------------------------------
class Ledger:
    """One check's `workpapers/figures-<check>.yaml` and `evidence-<check>.yaml`.

    `resume=True` (the default) starts from what the two files hold, so a step split
    across scripts keeps adding to one ledger; an id this pass mints again replaces the
    stored entry, and the ties of earlier passes come back in `ties`. `fresh=True` starts
    empty: a fix re-run that rebuilds every figure drops the ids it no longer mints, and an
    id it does not mint again never resolves, not even to the entry still on disk.
    `check` is the check id (no `-`) or `profile-<source>`."""

    def __init__(self, run_dir, check: str, *, fresh: bool = False):
        if not isinstance(check, str) or not LEDGER_NAME.fullmatch(check):
            raise ValueError(f"check {check!r}: the check id ([a-z0-9][a-z0-9_]*, no `-`) or "
                             f"`profile-<source>` - it names the ledger files")
        self.run_dir = pathlib.Path(run_dir).resolve()
        self.check = check
        wp = self.run_dir / "workpapers"
        self.figures_path = wp / f"figures-{check}.yaml"
        self.evidence_path = wp / f"evidence-{check}.yaml"
        self.entries: dict[str, dict] = {}
        self.citations: dict[str, dict] = {}
        self.minted: set[str] = set()
        self.ties: list[dict] = []
        self._tied: set[str] = set()
        self._pending: dict[str, list[int]] = {}   # fid -> inputs classified at write()
        self._run: FigureSet | None = None
        self._run_cits: dict[str, dict] | None = None
        if not fresh:
            for path, into in ((self.figures_path, self.entries),
                               (self.evidence_path, self.citations)):
                if path.is_file():
                    doc = _yaml_load(path)
                    if not isinstance(doc, list):
                        raise ValueError(f"{path}: the ledger is not a YAML list "
                                         f"(EVIDENCE.md § 0) - pass fresh=True to rebuild it")
                    for e in doc:
                        if not isinstance(e, dict) or not isinstance(e.get("id"), str):
                            raise ValueError(f"{path}: entry {e!r} is no `- id:` mapping "
                                             f"(EVIDENCE.md § 0) - pass fresh=True to rebuild it")
                        into[e["id"]] = e
            self.ties = [copy.deepcopy(e["tie"]) for e in self.entries.values()
                         if isinstance(e.get("tie"), dict)]

    # -- minting ---------------------------------------------------------------------------
    def _check_id(self, eid: str, prefix: str) -> None:
        """Refuse an id outside the grammar or minted already in this pass; records
        nothing."""
        if not isinstance(eid, str) or not LEDGER_ID.fullmatch(eid) or not eid.startswith(prefix):
            raise ValueError(f"id {eid!r}: `{prefix}` then dot-joined segments of "
                             f"[A-Za-z0-9_-]; a period is its slug (`fy2025`, "
                             f"`ltm_2026-07`), never its label (EVIDENCE.md § 0)")
        if eid in self.minted:
            raise ValueError(f"{eid} is minted twice in this pass - one entry per figure")

    def cite(self, *entries: dict) -> list[str]:
        """Add citation entries (from `evidence.select` / `span`, or a cell or passage)."""
        flat: list[dict] = []

        def walk(xs):
            for e in xs:
                if isinstance(e, list):
                    walk(e)
                elif not isinstance(e, dict):
                    raise ValueError(f"citation {e!r} is not a mapping")
                else:
                    flat.append(e)
        walk(entries)
        seen: set[str] = set()
        for e in flat:
            self._check_id(e.get("id"), "E.")
            if e["id"] in seen:
                raise ValueError(f"{e['id']} is cited twice in this call")
            seen.add(e["id"])
        plain = [_plain(e, e["id"]) for e in flat]
        for e in plain:
            self.minted.add(e["id"])
            self.citations[e["id"]] = e
        self._run_cits = None
        return [e["id"] for e in plain]

    def population(self, pid: str, label: str, total_n: int, included_n: int,
                   exclusions=(), citations=(), **extra) -> str:
        """A `P.` entry. `exclusions` is `[{"what": ..., "n": ...}, ...]`, one per named
        exclusion, required when `included_n < total_n`; their counts add up to
        `total_n - included_n`."""
        self._check_id(pid, "P.")
        total_n, included_n = _count(total_n, "total_n"), _count(included_n, "included_n")
        if isinstance(exclusions, (str, dict)) or isinstance(citations, (str, dict)):
            raise ValueError(f"{pid}: `exclusions` and `citations` are lists")
        exclusions = [_plain(x, f"{pid}.exclusions") for x in exclusions]
        _check_population(pid, total_n, included_n, exclusions)
        if clash := sorted(POP_FIELDS & set(extra)):
            raise ValueError(f"{pid}: {clash} are the entry's own fields, not extras")
        e = {"id": pid, "label": _label(pid, label), "total_n": total_n,
             "included_n": included_n, "exclusions": exclusions,
             "citations": _plain(list(citations), f"{pid}.citations")}
        e.update(_plain(extra, pid))
        self.minted.add(pid)
        self.entries[pid] = e
        return pid

    def fig(self, fid: str, label: str, value, unit: str, expression: str, inputs,
            *, population=None, disposition: str = "measured", zero_basis: str | None = None,
            caveats=(), stated_scale: str | None = None, **extra) -> str:
        """One `F.` entry, checked field by field; returns the id. A refused call records
        nothing.

        `stated_scale` (an `as_stated` figure only): `value` is the number as the source
        states it; the stored value is multiplied out of the scale exactly, with the
        conversion appended to `expression`."""
        self._check_id(fid, "F.")
        label = _label(fid, label)
        if unit not in UNITS:
            raise ValueError(f"{fid}: unit {unit!r} - a currency code (scripts/style.py) "
                             f"or one of {', '.join(OTHER_UNITS)}")
        if disposition not in DISPOSITIONS:
            raise ValueError(f"{fid}: disposition {disposition!r} - one of "
                             f"{', '.join(DISPOSITIONS)}")
        v = _num(value)
        conversion = []
        if stated_scale is not None:
            if disposition != "as_stated":
                raise ValueError(f"{fid}: stated_scale describes a passthrough - "
                                 f"disposition `as_stated`")
            if stated_scale not in style.SCALES:
                raise ValueError(f"{fid}: stated_scale {stated_scale!r} - one of "
                                 f"{', '.join(style.SCALES)}")
            if stated_scale != "units":
                if unit not in MONEY_UNITS and unit not in ("count", "quantity"):
                    raise ValueError(f"{fid}: a {unit} is not stated at a scale")
                n = int(style.SCALES[stated_scale])
                conversion.append(f"x {n:,} (stated in {stated_scale})")
                if v is not None and not (isinstance(v, float) and not math.isfinite(v)):
                    # in Decimal, e.g. 1.001 thousand is 1,001 (a float product gives
                    # 1000.9999999999999)
                    v = v * n if isinstance(v, int) else \
                        float(decimal.Decimal(repr(float(v))) * n)
        if isinstance(v, float) and math.isinf(v):
            raise ValueError(f"{fid}: value is infinite - a division by zero is "
                             f"`not_applicable`, value None")
        if isinstance(v, float) and math.isnan(v):
            v = None
        if v is not None:
            if unit in MONEY_UNITS:
                v = round(float(v), style.minor_units(unit))
            elif unit == "count":
                if float(v) != round(float(v)):
                    raise ValueError(f"{fid}: a count of {v} is not a whole number")
                v = int(v) if isinstance(v, int) else int(round(v))
            else:
                v = round(float(v), 10)
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError(f"{fid}: `expression` is required - the arithmetic, or "
                             f"`as stated at E.x (passthrough)`")
        m = NOT_WHOLE.search(expression)
        if m:
            raise ValueError(f"{fid}: expression cites `{m.group(0)}...` - a range or "
                             f"wildcard is a dead end; cite each id whole, or the family "
                             f"with placeholders (`F.x.<period>`)")
        if conversion:
            expression = f"{expression.strip()} {' '.join(conversion)}"
        if isinstance(inputs, (str, dict)):
            raise ValueError(f"{fid}: `inputs` is a list of inputs, not one {type(inputs).__name__}")
        ins, pending = [], []
        for k, i in enumerate(inputs or []):
            one, later = self._input(fid, i)
            ins.append(one)
            if later:
                pending.append(k)
        if not ins:
            raise ValueError(f"{fid}: `inputs` is never empty (EVIDENCE.md § 3)")
        pop = _population_ref(fid, population)
        if v is None or v == 0:
            if zero_basis not in ZERO_BASES:
                raise ValueError(f"{fid}: value {v!r} needs `zero_basis` - measured_zero "
                                 f"(a population measured and found empty of it), "
                                 f"not_measured, or not_applicable with a reason")
            if zero_basis == "measured_zero":
                if v is None:
                    raise ValueError(f"{fid}: `measured_zero` states a measured 0, not None")
                if pop is None:
                    raise ValueError(f"{fid}: `measured_zero` requires the population it "
                                     f"was measured over (`population=`)")
                n = pop.get("included_n") if "ref" not in pop else \
                    (self._population(pop["ref"]) or {}).get("included_n", 1)
                if not n > 0:
                    raise ValueError(f"{fid}: `measured_zero` over an empty population is "
                                     f"not_measured")
        elif zero_basis is not None:
            raise ValueError(f"{fid}: `zero_basis` belongs on a zero, null or blank value; "
                             f"this one is {v}")
        if isinstance(caveats, str):
            raise ValueError(f"{fid}: `caveats` is a list of ids, not one string")
        caveats = list(caveats)
        for c in caveats:
            if not LEDGER_ID.fullmatch(str(c)):
                raise ValueError(f"{fid}: caveat {c!r} is not an id")
        if clash := sorted(FIG_FIELDS & set(extra)):
            raise ValueError(f"{fid}: {clash} are the entry's own fields, not extras")
        e = {"id": fid, "label": label, "value": v, "unit": unit,
             "expression": expression.strip(), "inputs": _plain(ins, f"{fid}.inputs"),
             "population": _plain(pop, f"{fid}.population"), "zero_basis": zero_basis,
             "caveats": [str(c) for c in caveats], "disposition": disposition}
        if stated_scale is not None:
            e["stated_scale"] = stated_scale
        if conversion:
            e["stated_value"] = _num(value)
        e.update(_plain(extra, fid))
        self.minted.add(fid)
        self.entries[fid] = e
        if pending:
            self._pending[fid] = pending
        else:
            self._pending.pop(fid, None)
        return fid

    def _input(self, fid: str, i) -> tuple[dict, bool]:
        """One input as its dict, and whether its kind waits for write() (an `E.` id given
        as a tuple and cited nowhere yet)."""
        later = False
        if isinstance(i, (tuple, list)) and len(i) == 2:
            role, ref = i
            if str(ref).startswith("F."):
                i = figure(role, ref)
            elif str(ref).startswith("E."):
                c = self._citation(ref)
                later = c is None
                i = (check_output if (c or {}).get("file_role") == "run_artifact" else room)(role, ref)
            else:
                i = declared(role, ref)
        if not isinstance(i, dict):
            raise ValueError(f"{fid}: input {i!r} - a dict, or a (role, id) tuple")
        i = dict(i)
        if not i.get("role"):
            raise ValueError(f"{fid}: input {i} has no `role`")
        st = i.get("source_type")
        if st not in SOURCE_KEY:
            raise ValueError(f"{fid}: input source_type {st!r} - one of "
                             f"{', '.join(SOURCE_KEY)}")
        ref = i.get(SOURCE_KEY[st])
        if not ref:
            raise ValueError(f"{fid}: a `{st}` input carries `{SOURCE_KEY[st]}`")
        want = {"figure": "F.", "room_file": "E.", "check_output": "E."}.get(st)
        if want and not str(ref).startswith(want):
            raise ValueError(f"{fid}: a `{st}` input cites a `{want}` id, not {ref!r}")
        return i, later

    # -- ties ------------------------------------------------------------------------------
    def tie(self, tid: str, label: str, a: str, b: str, *, tolerance=None,
            pct_tolerance=None, diff_id: str | None = None, diff_label: str | None = None,
            population=None, tolerance_field: str = "params.tolerance",
            pct_tolerance_field: str = "params.pct_tolerance") -> dict:
        """Tie figure `a` to figure `b` (the reference side). Mints the difference figure,
        which keeps the tie record (`tie:`), and returns the record; appended to
        `self.ties` (replacing an earlier pass's record of the same tie)."""
        if not isinstance(tid, str) or not LEDGER_ID.fullmatch(tid) or not tid.startswith("T."):
            raise ValueError(f"tie id {tid!r}: `T.` then dot-joined segments (EVIDENCE.md § 0)")
        if tid in self._tied:
            raise ValueError(f"{tid} is tied twice in this pass")
        tol = _bound(tid, "tolerance", tolerance)
        ptol = _bound(tid, "pct_tolerance", pct_tolerance)
        if ptol is not None and ptol >= 1:
            raise ValueError(f"{tid}: pct_tolerance {ptol} is a fraction of side b - "
                             f"0.005 is 0.5%")
        fa, fb = self.get(a), self.get(b)
        for side, f in ((a, fa), (b, fb)):
            if f is None:
                raise ValueError(f"{tid}: side {side} is no figure in this ledger or the "
                                 f"run's - mint it first")
            if f.get("value") is None:
                raise ValueError(f"{tid}: side {side} has no value ({f.get('zero_basis')}) "
                                 f"- the tie is not_run; record it so, with the reason")
        unit = fa.get("unit")
        if fb.get("unit") != unit:
            if unit in MONEY_UNITS and fb.get("unit") in MONEY_UNITS:
                raise ValueError(f"{tid}: {a} is {unit}, {b} is {fb.get('unit')} - two "
                                 f"currencies never tie; translate one side through an "
                                 f"`fx_rate` figure and tie the translation")
            raise ValueError(f"{tid}: {a} is {unit}, {b} is {fb.get('unit')} - a tie "
                             f"agrees the same quantity")
        va, vb = float(fa["value"]), float(fb["value"])
        diff = va - vb
        if unit in MONEY_UNITS:
            diff = round(diff, style.minor_units(unit))
        elif unit == "count":
            diff = int(round(diff))
        else:
            diff = round(diff, 10)
        rel = abs(diff) / abs(vb) if vb else (0.0 if diff == 0 else math.inf)
        tests = []
        if tol is not None:
            tests.append({"test": "tolerance", "limit": tol, "measured": abs(diff),
                          "passed": abs(diff) <= tol + 1e-9})
        if ptol is not None:
            tests.append({"test": "pct_tolerance", "limit": ptol,
                          "measured": rel if math.isfinite(rel) else None,
                          "passed": rel <= ptol + 1e-12})
        if not tests:
            tests.append({"test": "display_rounding", "limit": DISPLAY_HALF[unit],
                          "measured": abs(diff), "passed": abs(diff) < DISPLAY_HALF[unit]})
        status = "pass" if all(t["passed"] for t in tests) else "fail"
        did = diff_id or "F." + tid[2:] + ".difference"
        # A difference is measured over the two sides compared, unless a population is
        # given or side a carries one.
        pop = population if population is not None else (
            fa.get("population") or {"total_n": 2, "included_n": 2, "exclusions": []})
        self.fig(did, diff_label or f"{_label(tid, label)} - difference", diff, unit,
                 f"{a} - {b}", [figure("side_a", a), figure("side_b", b)],
                 population=pop, zero_basis="measured_zero" if diff == 0 else None,
                 caveats=[tid])
        rec = {"id": tid, "label": label, "unit": unit,
               "side_a": {"figure_id": a, "value": fa["value"]},
               "side_b": {"figure_id": b, "value": fb["value"]},
               "difference": diff, "difference_figure": did,
               "pct_difference": rel if math.isfinite(rel) else None,
               "basis": "declared" if (tol is not None or ptol is not None) else
                        "display_rounding",
               "declared": [f for f, x in ((tolerance_field, tol),
                                           (pct_tolerance_field, ptol)) if x is not None],
               "tests": tests, "status": status}
        self.entries[did]["tie"] = copy.deepcopy(rec)
        self._tied.add(tid)
        self.ties = [t for t in self.ties if t.get("id") != tid] + [rec]
        return rec

    # -- reading ---------------------------------------------------------------------------
    def run_figures(self) -> FigureSet:
        """The run's other checks' figures. This check's own on-disk ledger is excluded:
        this pass replaces it."""
        if self._run is None:
            self._run = load(self.run_dir, exclude=(self.figures_path.name,)) \
                if (self.run_dir / "workpapers").is_dir() else FigureSet()
        return self._run

    def _population(self, pid: str) -> dict | None:
        return self.entries.get(pid) or dict.get(self.run_figures(), pid)

    def _citation(self, eid: str) -> dict | None:
        """A citation from this ledger, else from the run's other evidence ledgers."""
        if eid in self.citations:
            return self.citations[eid]
        if self._run_cits is None:
            self._run_cits = {}
            wp = self.run_dir / "workpapers"
            for f in sorted(wp.glob("evidence-*.yaml")) if wp.is_dir() else ():
                if f.name == self.evidence_path.name:
                    continue
                doc = _yaml_load(f)
                for e in doc if isinstance(doc, list) else ():
                    if isinstance(e, dict) and isinstance(e.get("id"), str):
                        self._run_cits.setdefault(e["id"], e)
        return self._run_cits.get(eid)

    def get(self, fid: str) -> dict | None:
        """A figure from this ledger, else from the run's other ledgers."""
        return self.entries.get(fid) or self.run_figures().get(fid)

    def fmt(self, fid: str, style: str = "prose") -> str:
        f = self.get(fid)
        if f is None:
            raise KeyError(f"{fid}: no figure with this id")
        return fmt(f.get("value"), f.get("unit"), style)

    def sub(self, template: str) -> str:
        return _sub(template, self.get)

    # -- writing ---------------------------------------------------------------------------
    def _classify(self) -> None:
        """Settle each `E.` input given as a tuple and cited nowhere when it was minted."""
        for fid, ks in list(self._pending.items()):
            ins = self.entries.get(fid, {}).get("inputs") or []
            left = []
            for k in ks:
                c = self._citation(ins[k].get("citation_id")) if k < len(ins) else None
                if c is None:
                    left.append(k)                 # still cited nowhere: a dead end below
                else:
                    ins[k]["source_type"] = "check_output" \
                        if c.get("file_role") == "run_artifact" else "room_file"
            if left:
                self._pending[fid] = left
            else:
                self._pending.pop(fid)

    def dead_ends(self) -> list[str]:
        """Every reference in this ledger that no ledger of the run declares, every input
        whose kind contradicts its citation, every `measured_zero` over an empty `P.`, and
        every tie whose side has moved since it was classified."""
        # What the run's OTHER ledgers declare, read as check_workbook.py reads them, plus
        # what this ledger holds: its own files are about to be replaced, so an id they
        # declared on disk and this pass no longer mints resolves nothing.
        known = set(self.entries) | set(self.citations)
        own = {self.figures_path.name, self.evidence_path.name}
        wp = self.run_dir / "workpapers"
        for f in sorted(wp.glob("*.yaml")) if wp.is_dir() else ():
            if f.name in own:
                continue
            for m in check_workbook.ID_LINE.finditer(f.read_text(encoding="utf-8",
                                                                     errors="replace")):
                known.add(check_workbook._id_value(m.group(1)))
        out: list[str] = []

        def need(ref: str, where: str):
            if ref not in known:
                out.append(f"{where}: `{ref}` resolves in no ledger of the run")

        for eid, e in self.entries.items():
            for c in e.get("citations") or ():
                need(c, f"{eid}.citations")
            if not eid.startswith("F."):
                continue
            for i in e.get("inputs") or ():
                st = i.get("source_type")
                ref = i.get(SOURCE_KEY.get(st, ""), "")
                if st == "declared":
                    continue
                need(ref, f"{eid}.inputs[{i.get('role')}]")
                if st in ("room_file", "check_output"):
                    c = self._citation(ref)
                    art = (c or {}).get("file_role") == "run_artifact"
                    if c is not None and art != (st == "check_output"):
                        out.append(f"{eid}.inputs[{i.get('role')}]: a `{st}` input cites "
                                   f"{ref}, a {'run_artifact' if art else 'room'} read - "
                                   f"{'check_output' if art else 'room_file'} (EVIDENCE.md § 3)")
            pop = e.get("population") or {}
            if pop.get("ref"):
                need(pop["ref"], f"{eid}.population")
                p = self._population(pop["ref"])
                if e.get("zero_basis") == "measured_zero" and p is not None \
                        and not (p.get("included_n") or 0) > 0:
                    out.append(f"{eid}: `measured_zero` over {pop['ref']}, an empty "
                               f"population - not_measured")
            expr = str(e.get("expression", ""))
            bad = NOT_WHOLE.search(expr)
            if bad:
                out.append(f"{eid}.expression: `{bad.group(0)}...` is a range or wildcard - "
                           f"cite each id whole, or the family with placeholders")
            for m in ID_TOKEN.finditer(expr):
                ref = m.group(0)
                if ref[0] not in "FPE" or ref[1] != ".":
                    continue
                if expr[m.end():m.end() + 2] == ".<":        # a family stem: one member
                    if not any(k.startswith(ref + ".") for k in known):
                        out.append(f"{eid}.expression: family `{ref}.<...>` has no member "
                                   f"in any ledger of the run")
                    continue
                need(ref, f"{eid}.expression")
        for t in self.ties:
            for side in ("side_a", "side_b"):
                fid, was = t[side]["figure_id"], t[side]["value"]
                f = self.entries.get(fid) or dict.get(self.run_figures(), fid)
                now = None if f is None else f.get("value")
                if now is None or float(now) != float(was):
                    out.append(f"{t['id']}: side {fid} is now {now!r}, {was!r} when the tie "
                               f"was classified - tie it again")
        return out

    def write(self) -> tuple[pathlib.Path, pathlib.Path | None]:
        """Write both ledgers, or nothing: refuses with every dead end named. A pass that
        cites nothing removes an evidence ledger left by an earlier one."""
        self._classify()
        bad = self.dead_ends()
        if bad:
            raise ValueError(f"{len(bad)} reference(s) resolve nowhere - nothing written:\n  "
                             + "\n  ".join(bad))
        pops = [e for k, e in self.entries.items() if k.startswith("P.")]
        figs = [e for k, e in self.entries.items() if not k.startswith("P.")]
        fp = write_ledger(self.figures_path, [copy.deepcopy(e) for e in pops + figs],
                          merge=False)
        ep = None
        if self.citations:
            ep = write_ledger(self.evidence_path,
                              [copy.deepcopy(e) for e in self.citations.values()], merge=False)
        elif self.evidence_path.is_file():
            self.evidence_path.unlink()
        self._run = None
        return fp, ep


# --- field checks --------------------------------------------------------------------------
def _label(eid: str, label) -> str:
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"{eid}: `label` is required - what the number is, in words")
    return label.strip()


def _count(v, name: str) -> int:
    v = _num(v)
    if v is None or (isinstance(v, float) and not math.isfinite(v)) \
            or float(v) != round(float(v)) or v < 0:
        raise ValueError(f"`{name}` is a non-negative whole number, got {v!r}")
    return int(v)


def _bound(tid: str, name: str, v):
    if v is None:
        return None
    if isinstance(v, dict):                  # a described tolerance: {kind, amount, ...}
        kind = str(v.get("kind", "absolute")).lower()
        want = "absolute" if name == "tolerance" else ("relative", "pct", "percent")
        if kind not in (want if isinstance(want, tuple) else (want,)) or "amount" not in v:
            raise ValueError(f"{tid}: {name} {v!r} - pass the number, or "
                             f"{{kind: absolute, amount: n}} for `tolerance`")
        v = v["amount"]
    v = _num(v)
    if v is None or v < 0 or (isinstance(v, float) and not math.isfinite(v)):
        raise ValueError(f"{tid}: {name} {v!r} is a non-negative number")
    return float(v)


def _check_population(pid: str, total_n: int, included_n: int, exclusions: list) -> None:
    """`exclusions` as given; each count is normalized to an int in place."""
    if included_n > total_n:
        raise ValueError(f"{pid}: included_n {included_n} exceeds total_n {total_n}")
    if included_n < total_n and not exclusions:
        raise ValueError(f"{pid}: {total_n - included_n} excluded and no exclusion "
                         f"named - each with its count (EVIDENCE.md § 3)")
    named = 0
    for x in exclusions:
        if not isinstance(x, dict):
            raise ValueError(f"{pid}: exclusion {x!r} is a mapping {{what, n}}")
        key = "n" if "n" in x else "count"
        if not (x.get("what") or x.get("reason")) or x.get(key) is None:
            raise ValueError(f"{pid}: exclusion {x} needs `what` and `n`")
        x[key] = _count(x[key], f"{pid} exclusion n")
        named += x[key]
    if exclusions and named != total_n - included_n:
        raise ValueError(f"{pid}: the exclusions name {named} item(s), and {total_n} total "
                         f"less {included_n} included is {total_n - included_n} - every "
                         f"excluded item is named once, with its count")


def _population_ref(fid: str, p):
    if p is None:
        return None
    if isinstance(p, str):
        if not p.startswith("P.") or not LEDGER_ID.fullmatch(p):
            raise ValueError(f"{fid}: population {p!r} is not a `P.` id")
        return {"ref": p}
    if isinstance(p, dict):
        p = copy.deepcopy(p)
        if "ref" in p:
            return _population_ref(fid, p["ref"])
        for k in ("total_n", "included_n"):
            if k not in p:
                raise ValueError(f"{fid}: an inline population carries total_n and included_n")
            p[k] = _count(p[k], k)
        p.setdefault("exclusions", [])
        if isinstance(p["exclusions"], (str, dict)):
            raise ValueError(f"{fid}: population exclusions are a list")
        p["exclusions"] = [_plain(x, f"{fid}.population.exclusions") for x in p["exclusions"]]
        _check_population(fid, p["total_n"], p["included_n"], p["exclusions"])
        return p
    raise ValueError(f"{fid}: population {p!r} - a `P.` id or {{total_n, included_n, "
                     f"exclusions}}")
