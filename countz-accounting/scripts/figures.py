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
later: an id outside the grammar or minted twice in one pass, a unit outside
`usd | pct | count | ratio`, an empty `inputs` or a role-less input, a zero, null or NaN
value with no `zero_basis`, a `measured_zero` with no population. Money is stored to the
cent, a count as an integer, a percentage as a fraction (0.174 is 17.4%).

**Every reference resolves when the ledger is written, not at the report.** `write()`
reads every id the run's `workpapers/*.yaml` declare (as `check_workbook.py --run-dir`
does) plus what this ledger holds, and refuses the whole write, naming each dead end,
when an input, a population, a citation or an `F.`/`P.`/`E.` id in an `expression` does
not resolve — including a range (`E.x.fy2023..fy2025`), a wildcard (`E.x.memos_*`) or a
bare stem (`E.a4.memos`). Cite each id whole; a family written with placeholders
(`F.a4.arr.<dimension>.<column>`, the form `link_workbook.py` links) resolves when at
least one declared id belongs to it.

**Inputs.** `room(role, "E.x")`, `check_output(role, "E.x")`, `figure(role, "F.x")`,
`declared(role, "params.tolerance")`, or a `(role, id)` tuple: an `F.` id is a figure, an
`E.` id a room file (a check output when its citation is `file_role: run_artifact`), and
anything else a declared field.

**Ties** (check-tie SKILL § 4). `tie(id, label, a, b, tolerance=, pct_tolerance=)` reads
the two sides' figures, mints the difference figure `a - b` (default id: the tie's id with
`F.` for `T.` plus `.difference`; population: side a's, else the two sides compared), and
classifies: `tolerance` is an absolute bound in the
tie's unit, `pct_tolerance` a fraction of side `b` (the reference side: `0.005` is 0.5%).
Given both, the tie passes only when **both** hold and fails when either does not; given
one, that one decides; given neither, the difference must be below half the display unit
(`$0.50`, one count, `0.05%`). A tolerance the user did not declare is never passed. The
result is `pass` or `fail` with each test's limit and measure; `warn` (an explained
difference) is the worker's call after resolution. `tie_table(L.ties)` is the Markdown
schedule for `checks/<check>.md`.

**Prose.** `fmt(value, unit)` writes DOCTRINE.md § Number conventions: `$9,438,108`,
`($1,204)` for a negative, `17.4%`, `100%`, `4,171`, `1.3x`; `style="deck"` scales money
(`$9.4m`, `$81k`, REPORT.md § 4); `None` reads *unable to establish*. `L.sub(template)`
(or `load(RUN).sub(...)`) replaces each `{F.id}` or `{F.id:deck}` with the formatted
figure, so a sentence never types a number.

Run with no arguments to self-check. Requires pyyaml — run as
`uv run --project ${CLAUDE_PLUGIN_ROOT} python3`.
"""
from __future__ import annotations

import copy
import decimal
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import check_workbook  # noqa: E402  sibling: the id grammar and the run's declared ids
from evidence import write_ledger  # noqa: E402

__all__ = ["Ledger", "FigureSet", "load", "fmt", "tie_table", "room", "check_output",
           "figure", "declared", "UNITS", "DISPOSITIONS", "ZERO_BASES"]

UNITS = ("usd", "pct", "count", "ratio")
DISPOSITIONS = ("measured", "inferred", "as_stated")
ZERO_BASES = ("measured_zero", "not_measured", "not_applicable")
SOURCE_KEY = {"room_file": "citation_id", "check_output": "citation_id",
              "figure": "figure_id", "declared": "field"}
# Half the display unit (DOCTRINE.md § Number conventions): whole dollars, integer
# counts, one decimal of a percentage, one decimal of a multiple.
DISPLAY_HALF = {"usd": 0.5, "count": 0.5, "pct": 0.0005, "ratio": 0.05}
UNABLE = "unable to establish"

LEDGER_ID = check_workbook.LEDGER_ID
ID_TOKEN = check_workbook.ID_TOKEN
# An id written as a set it cannot resolve to: a range (`E.x.fy2023..fy2025`) or a
# wildcard (`E.x.memos_*`). A family written with placeholders (`F.a4.arr.<dimension>`)
# is the convention link_workbook.py links, and resolves when the family has a member.
NOT_WHOLE = re.compile(r"\b[A-Z]{1,2}\.[A-Za-z0-9_-][A-Za-z0-9_.-]*?(?:\.\.|\*)")
TEMPLATE = re.compile(r"\{([A-Z]{1,2}\.[A-Za-z0-9_.-]*[A-Za-z0-9])(?::(prose|deck|cell))?\}")


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


def _compact(a: float) -> str:
    if a >= 999_500_000:
        return f"${a / 1e9:,.1f}bn"
    if a >= 999_500:
        return f"${a / 1e6:,.1f}m"
    if a >= 999.5:
        return f"${a / 1e3:,.0f}k"
    return f"${a:,.0f}"


def fmt(value, unit: str, style: str = "prose") -> str:
    """One figure as a sentence states it (DOCTRINE.md § Number conventions). `prose`:
    whole dollars; `deck`: scaled money (REPORT.md § 4); `cell`: cents. Negatives in
    parentheses; `None` reads *unable to establish*."""
    if unit not in UNITS:
        raise ValueError(f"unit {unit!r}: one of {', '.join(UNITS)}")
    v = _num(value)
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return UNABLE
    neg = v < 0
    a = abs(v)
    if unit == "usd":
        if style == "deck":
            s = _compact(a)
        elif style == "cell":
            s = f"${a:,.2f}"
        else:
            s = f"${a:,.0f}"
        neg = neg and s.strip("$0.,") != ""
    elif unit == "pct":
        p = round(a * 100, 1)
        s = f"{p:.0f}%" if p.is_integer() else f"{p:.1f}%"
        neg = neg and p != 0
    elif unit == "count":
        s = f"{a:,.0f}"
        neg = neg and round(a) != 0
    else:
        s = f"{a:,.1f}x"
        neg = neg and round(a, 1) != 0
    return f"({s})" if neg else s


def _sub(template: str, lookup) -> str:
    def one(m):
        fid, style = m.group(1), m.group(2) or "prose"
        f = lookup(fid)
        if f is None:
            raise KeyError(f"{fid}: no figure with this id in the run's ledgers")
        return fmt(f.get("value"), f.get("unit"), style)
    return TEMPLATE.sub(one, template)


# --- the run's figures ---------------------------------------------------------------------
def _yaml_load(path: pathlib.Path):
    import yaml
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    doc = yaml.load(path.read_text(encoding="utf-8"), Loader=loader)
    return doc or []


class FigureSet(dict):
    """Every `F.`/`P.` entry in the run's figures ledgers, by id."""

    def value(self, fid: str):
        return self[fid].get("value")

    def fmt(self, fid: str, style: str = "prose") -> str:
        return fmt(self[fid].get("value"), self[fid].get("unit"), style)

    def sub(self, template: str) -> str:
        return _sub(template, self.get)


def load(run_dir, checks=None) -> FigureSet:
    """The figures ledgers of `checks` (all of them when None) as one FigureSet."""
    wp = pathlib.Path(run_dir) / "workpapers"
    out = FigureSet()
    names = sorted(wp.glob("figures-*.yaml")) if checks is None else \
        [wp / f"figures-{c}.yaml" for c in ([checks] if isinstance(checks, str) else checks)]
    for f in names:
        if not f.is_file():
            raise FileNotFoundError(f"{f}: no such ledger")
        doc = _yaml_load(f)
        if not isinstance(doc, list):
            raise ValueError(f"{f.name}: the ledger is not a YAML list (EVIDENCE.md § 0)")
        for e in doc:
            if isinstance(e, dict) and isinstance(e.get("id"), str):
                out.setdefault(e["id"], e)
    return out


def tie_table(ties) -> str:
    """The tie schedule as a Markdown table, for `checks/<check>.md`."""
    lines = ["| tie | side A | side B | difference | test | status |",
             "|---|---|---|---|---|---|"]
    def bound(v, test, u):                 # a tolerance keeps its own precision: 0.01%
        if test != "pct_tolerance":
            return fmt(v, u, "cell")
        return "n/a" if v is None else f"{v * 100:.4g}%"

    for t in ties:
        u = t["unit"]
        tests = "; ".join(
            f"{x['test']} {bound(x['measured'], x['test'], u)} "
            f"{'<=' if x['passed'] else '>'} {bound(x['limit'], x['test'], u)}"
            for x in t["tests"])
        lines.append(f"| {t['id']} {t['label']} | {t['side_a']['figure_id']} "
                     f"{fmt(t['side_a']['value'], u, 'cell')} | {t['side_b']['figure_id']} "
                     f"{fmt(t['side_b']['value'], u, 'cell')} | {t['difference_figure']} "
                     f"{fmt(t['difference'], u, 'cell')} | {tests} | {t['status']} |")
    return "\n".join(lines) + "\n"


# --- one check's ledger --------------------------------------------------------------------
class Ledger:
    """One check's `workpapers/figures-<check>.yaml` and `evidence-<check>.yaml`.

    `resume=True` (the default) starts from what the two files hold, so a step split
    across scripts keeps adding to one ledger; an id this pass mints again replaces the
    stored entry. `fresh=True` starts empty: a fix re-run that rebuilds every figure
    drops the ids it no longer mints."""

    def __init__(self, run_dir, check: str, *, fresh: bool = False):
        self.run_dir = pathlib.Path(run_dir).resolve()
        self.check = check
        wp = self.run_dir / "workpapers"
        self.figures_path = wp / f"figures-{check}.yaml"
        self.evidence_path = wp / f"evidence-{check}.yaml"
        self.entries: dict[str, dict] = {}
        self.citations: dict[str, dict] = {}
        self.minted: set[str] = set()
        self.ties: list[dict] = []
        self._run: FigureSet | None = None
        if not fresh:
            for path, into in ((self.figures_path, self.entries),
                               (self.evidence_path, self.citations)):
                if path.is_file():
                    doc = _yaml_load(path)
                    if not isinstance(doc, list):
                        raise ValueError(f"{path}: the ledger is not a YAML list "
                                         f"(EVIDENCE.md § 0) - pass fresh=True to rebuild it")
                    for e in doc:
                        into[e["id"]] = e

    # -- minting ---------------------------------------------------------------------------
    def _mint(self, eid: str, prefix: str) -> None:
        if not isinstance(eid, str) or not LEDGER_ID.fullmatch(eid) or not eid.startswith(prefix):
            raise ValueError(f"id {eid!r}: `{prefix}` then dot-joined segments of "
                             f"[A-Za-z0-9_-]; a period is its slug (`fy2025`, "
                             f"`ltm_2026-07`), never its label (EVIDENCE.md § 0)")
        if eid in self.minted:
            raise ValueError(f"{eid} is minted twice in this pass - one entry per figure")
        self.minted.add(eid)

    def cite(self, *entries: dict) -> list[str]:
        """Add citation entries (from `evidence.select` / `span`, or a cell or passage)."""
        ids = []
        for e in entries:
            if isinstance(e, list):
                ids += self.cite(*e)
                continue
            self._mint(e.get("id"), "E.")
            self.citations[e["id"]] = copy.deepcopy(e)
            ids.append(e["id"])
        return ids

    def population(self, pid: str, label: str, total_n: int, included_n: int,
                   exclusions=(), citations=(), **extra) -> str:
        """A `P.` entry. `exclusions` is `[{"what": ..., "n": ...}, ...]`, one per named
        exclusion, required when `included_n < total_n`."""
        self._mint(pid, "P.")
        total_n, included_n = _count(total_n, "total_n"), _count(included_n, "included_n")
        exclusions = [dict(x) for x in exclusions]
        _check_population(pid, total_n, included_n, exclusions)
        e = {"id": pid, "label": _label(pid, label), "total_n": total_n,
             "included_n": included_n, "exclusions": exclusions,
             "citations": list(citations)}
        e.update(copy.deepcopy(extra))
        self.entries[pid] = e
        return pid

    def fig(self, fid: str, label: str, value, unit: str, expression: str, inputs,
            *, population=None, disposition: str = "measured", zero_basis: str | None = None,
            caveats=(), **extra) -> str:
        """One `F.` entry, checked field by field; returns the id."""
        self._mint(fid, "F.")
        if unit not in UNITS:
            raise ValueError(f"{fid}: unit {unit!r} - one of {', '.join(UNITS)}")
        if disposition not in DISPOSITIONS:
            raise ValueError(f"{fid}: disposition {disposition!r} - one of "
                             f"{', '.join(DISPOSITIONS)}")
        v = _num(value)
        if isinstance(v, float) and math.isinf(v):
            raise ValueError(f"{fid}: value is infinite - a division by zero is "
                             f"`not_applicable`, value None")
        if isinstance(v, float) and math.isnan(v):
            v = None
        if v is not None:
            if unit == "usd":
                v = round(float(v), 2)
            elif unit == "count":
                if float(v) != round(float(v)):
                    raise ValueError(f"{fid}: a count of {v} is not a whole number")
                v = int(round(v))
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
        ins = [self._input(fid, i) for i in (inputs or [])]
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
                if "included_n" in pop and not pop["included_n"] > 0:
                    raise ValueError(f"{fid}: `measured_zero` over an empty population is "
                                     f"not_measured")
        elif zero_basis is not None:
            raise ValueError(f"{fid}: `zero_basis` belongs on a zero, null or blank value; "
                             f"this one is {v}")
        for c in caveats:
            if not LEDGER_ID.fullmatch(str(c)):
                raise ValueError(f"{fid}: caveat {c!r} is not an id")
        e = {"id": fid, "label": _label(fid, label), "value": v, "unit": unit,
             "expression": expression.strip(), "inputs": ins, "population": pop,
             "zero_basis": zero_basis, "caveats": list(caveats), "disposition": disposition}
        e.update(copy.deepcopy(extra))
        self.entries[fid] = e
        return fid

    def _input(self, fid: str, i) -> dict:
        if isinstance(i, (tuple, list)) and len(i) == 2:
            role, ref = i
            if str(ref).startswith("F."):
                i = figure(role, ref)
            elif str(ref).startswith("E."):
                c = self.citations.get(ref) or {}
                i = (check_output if c.get("file_role") == "run_artifact" else room)(role, ref)
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
        if not i.get(SOURCE_KEY[st]):
            raise ValueError(f"{fid}: a `{st}` input carries `{SOURCE_KEY[st]}`")
        return i

    # -- ties ------------------------------------------------------------------------------
    def tie(self, tid: str, label: str, a: str, b: str, *, tolerance=None,
            pct_tolerance=None, diff_id: str | None = None, diff_label: str | None = None,
            population=None, tolerance_field: str = "params.tolerance",
            pct_tolerance_field: str = "params.pct_tolerance") -> dict:
        """Tie figure `a` to figure `b` (the reference side). Mints the difference figure
        and returns the tie record; appended to `self.ties`."""
        if not isinstance(tid, str) or not LEDGER_ID.fullmatch(tid) or not tid.startswith("T."):
            raise ValueError(f"tie id {tid!r}: `T.` then dot-joined segments (EVIDENCE.md § 0)")
        if any(t["id"] == tid for t in self.ties):
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
            raise ValueError(f"{tid}: {a} is {unit}, {b} is {fb.get('unit')} - a tie "
                             f"agrees the same quantity")
        va, vb = float(fa["value"]), float(fb["value"])
        diff = va - vb
        if unit == "usd":
            diff = round(diff, 2)
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
        self.ties.append(rec)
        return rec

    # -- reading ---------------------------------------------------------------------------
    def run_figures(self) -> FigureSet:
        if self._run is None:
            self._run = load(self.run_dir) if (self.run_dir / "workpapers").is_dir() \
                else FigureSet()
        return self._run

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
    def dead_ends(self) -> list[str]:
        """Every reference in this ledger that no ledger of the run declares."""
        # What the run's OTHER ledgers declare, read as check_workbook.py reads them, plus
        # what this ledger holds: its own files are about to be replaced, so an id they
        # declared on disk and this pass no longer mints resolves nothing.
        known = set(self.entries) | set(self.citations)
        own = {self.figures_path.name, self.evidence_path.name}
        wp = self.run_dir / "workpapers"
        for f in sorted(wp.glob("*.yaml")) if wp.is_dir() else ():
            if f.name in own:
                continue
            for m in check_workbook.ID_LINE.finditer(f.read_text(errors="replace")):
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
                ref = i.get(SOURCE_KEY.get(i.get("source_type"), ""), "")
                if i.get("source_type") != "declared":
                    need(ref, f"{eid}.inputs[{i.get('role')}]")
            pop = e.get("population") or {}
            if pop.get("ref"):
                need(pop["ref"], f"{eid}.population")
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
        return out

    def write(self) -> tuple[pathlib.Path, pathlib.Path | None]:
        """Write both ledgers, or nothing: refuses with every dead end named."""
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
        self._run = None
        return fp, ep


# --- field checks --------------------------------------------------------------------------
def _label(eid: str, label) -> str:
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"{eid}: `label` is required - what the number is, in words")
    return label.strip()


def _count(v, name: str) -> int:
    v = _num(v)
    if v is None or float(v) != round(float(v)) or v < 0:
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
    if included_n > total_n:
        raise ValueError(f"{pid}: included_n {included_n} exceeds total_n {total_n}")
    if included_n < total_n:
        if not exclusions:
            raise ValueError(f"{pid}: {total_n - included_n} excluded and no exclusion "
                             f"named - each with its count (EVIDENCE.md § 3)")
        for x in exclusions:
            if not x.get("what") and not x.get("reason") or x.get("n", x.get("count")) is None:
                raise ValueError(f"{pid}: exclusion {x} needs `what` and `n`")


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
        _check_population(fid, p["total_n"], p["included_n"], p["exclusions"])
        return p
    raise ValueError(f"{fid}: population {p!r} - a `P.` id or {{total_n, included_n, "
                     f"exclusions}}")


# --- self-check ----------------------------------------------------------------------------
def _selfcheck() -> int:
    import tempfile
    bad: list[str] = []

    def expect_error(what: str, fn):
        try:
            fn()
            bad.append(f"accepted {what}")
        except (ValueError, KeyError):
            pass

    for got, want in ((fmt(9438108.22, "usd"), "$9,438,108"), (fmt(-1204.4, "usd"), "($1,204)"),
                      (fmt(-0.2, "usd"), "$0"), (fmt(0.174, "pct"), "17.4%"),
                      (fmt(1.0, "pct"), "100%"), (fmt(4171, "count"), "4,171"),
                      (fmt(1.26, "ratio"), "1.3x"), (fmt(None, "usd"), UNABLE),
                      (fmt(9_438_108, "usd", "deck"), "$9.4m"),
                      (fmt(81_234, "usd", "deck"), "$81k")):
        if got != want:
            bad.append(f"fmt: got {got!r}, want {want!r}")

    with tempfile.TemporaryDirectory() as d:
        run = pathlib.Path(d)
        (run / "workpapers").mkdir()
        up = Ledger(run, "k0")
        up.cite({"id": "E.k0.tb", "kind": "cell", "file": "tb.xlsx", "value": 1000.0})
        up.fig("F.k0.tb.revenue", "TB revenue", 1000.0, "usd", "as stated at E.k0.tb "
               "(passthrough)", [("tb", "E.k0.tb")])
        up.write()

        L = Ledger(run, "k1")
        L.cite({"id": "E.k1.lines", "kind": "span", "file": "lines.csv"})
        L.population("P.k1.lines", "Invoice lines", 10, 9, [{"what": "voided", "n": 1}],
                     citations=["E.k1.lines"])
        L.fig("F.k1.revenue", "Billed revenue", 1000.004, "usd", "sum(amount) over E.k1.lines",
              [room("lines", "E.k1.lines")], population="P.k1.lines")
        L.fig("F.k1.revenue_hi", "Billed revenue, restated", 1003.0, "usd",
              "sum(amount) over E.k1.lines", [("lines", "E.k1.lines")])
        L.fig("F.k1.revenue_far", "Billed revenue, other", 1020.0, "usd",
              "sum(amount) over E.k1.lines", [("lines", "E.k1.lines")])
        t0 = L.tie("T.k1.exact", "Billed to TB", "F.k1.revenue", "F.k0.tb.revenue")
        t1 = L.tie("T.k1.both_pass", "both", "F.k1.revenue_hi", "F.k0.tb.revenue",
                   tolerance=5, pct_tolerance=0.005)
        t2 = L.tie("T.k1.abs_fails", "abs fails", "F.k1.revenue_hi", "F.k0.tb.revenue",
                   tolerance=1, pct_tolerance=0.005)
        t3 = L.tie("T.k1.pct_fails", "pct fails", "F.k1.revenue_far", "F.k0.tb.revenue",
                   tolerance=50, pct_tolerance=0.01)
        t4 = L.tie("T.k1.pct_only", "pct only", "F.k1.revenue_far", "F.k0.tb.revenue",
                   pct_tolerance=0.05)
        t5 = L.tie("T.k1.rounding", "rounding", "F.k1.revenue_hi", "F.k0.tb.revenue")
        t6 = L.tie("T.k1.described", "described", "F.k1.revenue_hi", "F.k0.tb.revenue",
                   tolerance={"kind": "absolute", "amount": 5, "unit": "usd"})
        for t, want in ((t0, "pass"), (t1, "pass"), (t2, "fail"), (t3, "fail"), (t4, "pass"),
                        (t5, "fail"), (t6, "pass")):
            if t["status"] != want:
                bad.append(f"{t['id']}: {t['status']}, want {want} ({t['tests']})")
        if L.entries["F.k1.exact.difference"]["zero_basis"] != "measured_zero":
            bad.append("a zero difference carries no measured_zero")
        if L.sub("Billed {F.k1.revenue} against {F.k0.tb.revenue:deck}.") != \
                "Billed $1,000 against $1k.":
            bad.append(f"sub: {L.sub('Billed {F.k1.revenue} against {F.k0.tb.revenue:deck}.')}")
        if "T.k1.pct_fails" not in tie_table(L.ties):
            bad.append("tie_table lost a tie")
        L.write()
        back = load(run)
        if back.value("F.k1.revenue") != 1000.0 or back["F.k1.revenue"]["population"] != \
                {"ref": "P.k1.lines"}:
            bad.append(f"round trip: {back['F.k1.revenue']}")
        if "&id" in (run / "workpapers/figures-k1.yaml").read_text():
            bad.append("the ledger carries YAML anchors")

        expect_error("a label in the id", lambda: L.fig("F.k1.x.LTM Dec 2025", "x", 1, "usd",
                                                        "e", [("a", "E.k1.lines")]))
        expect_error("a duplicate id", lambda: L.fig("F.k1.revenue", "x", 1, "usd", "e",
                                                     [("a", "E.k1.lines")]))
        expect_error("no inputs", lambda: L.fig("F.k1.n1", "x", 1, "usd", "e", []))
        expect_error("a zero with no basis", lambda: L.fig("F.k1.n2", "x", 0, "usd", "e",
                                                           [("a", "E.k1.lines")]))
        expect_error("measured_zero with no population",
                     lambda: L.fig("F.k1.n3", "x", 0, "usd", "e", [("a", "E.k1.lines")],
                                   zero_basis="measured_zero"))
        expect_error("a fractional count", lambda: L.fig("F.k1.n4", "x", 2.5, "count", "e",
                                                         [("a", "E.k1.lines")]))
        expect_error("a wildcard", lambda: L.fig("F.k1.n5", "x", 1, "usd",
                                                 "sum of E.k1.memos_*", [("a", "E.k1.lines")]))
        expect_error("a range", lambda: L.fig("F.k1.n6", "x", 1, "usd",
                                              "E.k1.x_fy2023..fy2025", [("a", "E.k1.lines")]))
        L.fig("F.k1.family_sum", "Sum over the family", 1000.0, "usd",
              "sum over accounts of F.k0.tb.<account>",
              [("tb", "F.k0.tb.revenue")])
        expect_error("pct_tolerance as a percent",
                     lambda: L.tie("T.k1.p", "x", "F.k1.revenue", "F.k0.tb.revenue",
                                   pct_tolerance=5))
        expect_error("a negative tolerance",
                     lambda: L.tie("T.k1.q", "x", "F.k1.revenue", "F.k0.tb.revenue",
                                   tolerance=-1))

        if L.dead_ends():
            bad.append(f"placeholder family flagged: {L.dead_ends()}")
        N = Ledger(run, "k4")
        N.fig("F.k4.x", "x", 1.0, "usd", "sum over F.k9.nothing.<member>",
              [("a", "F.k1.revenue")])
        if not any("family" in d for d in N.dead_ends()):
            bad.append("a family with no member resolved")
        M = Ledger(run, "k2")
        M.fig("F.k2.memos", "Credit memos", 5.0, "usd", "F.k1.revenue - E.k2.memos",
              [("revenue", "F.k1.revenue"), ("memos", "E.k2.memos")])
        try:
            M.write()
            bad.append("wrote a ledger citing an undeclared id")
        except ValueError as exc:
            if "E.k2.memos" not in str(exc):
                bad.append(f"dead end not named: {exc}")
        if (run / "workpapers/figures-k2.yaml").exists():
            bad.append("a refused write left a file")

        R = Ledger(run, "k1")                 # resume: a second script adds to the ledger
        if "F.k1.revenue" not in R.entries:
            bad.append("resume lost the stored ledger")
        F = Ledger(run, "k1", fresh=True)
        F.cite({"id": "E.k1.lines", "kind": "span", "file": "lines.csv"})
        F.fig("F.k1.only", "Only", 1.0, "usd", "E.k1.lines", [("lines", "E.k1.lines")])
        F.write()
        Z = Ledger(run, "k3")
        Z.fig("F.k3.uses_dropped", "x", 1.0, "usd", "F.k1.revenue",
              [("r", "F.k1.revenue")])
        expect_error("an id the rebuilt ledger dropped", Z.write)

    for b in bad:
        print(f"figures: {b}")
    print("figures: ok" if not bad else "figures: self-check FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
