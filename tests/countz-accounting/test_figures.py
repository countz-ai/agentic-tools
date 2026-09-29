#!/usr/bin/env python3
"""Self-test for scripts/figures.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_figures.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import pathlib
import sys

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from figures import Ledger, UNABLE, fmt, load, md_table, room, tie_table  # noqa: E402


def main() -> int:
    import tempfile
    bad: list[str] = []

    def expect_error(what: str, fn):
        try:
            fn()
            bad.append(f"accepted {what}")
        except (ValueError, KeyError):
            pass

    t = md_table(["item", "amount", "share", "n"],
                 [["Deposits | net", 1204.4, 0.174, 12], ["Loss", -9_438_108, None, 3]],
                 [None, "usd", "pct", "count"])
    want_t = ("| item | amount | share | n |\n|---|---:|---:|---:|\n"
              "| Deposits \\| net | $1,204 | 17.4% | 12 |\n| Loss | ($9,438,108) |  | 3 |\n")
    if t != want_t:
        bad.append(f"md_table:\n{t}")
    if md_table(["x"], [[9_438_108]], ["usd"], "deck").splitlines()[-1] != "| $9.4M |":
        bad.append("md_table deck style")
    expect_error("an md_table unit outside figures", lambda: md_table(["a"], [[1]], ["dollars"]))
    for got, want in ((fmt(9438108.22, "usd"), "$9,438,108"), (fmt(-1204.4, "usd"), "($1,204)"),
                      (fmt(-0.2, "usd"), "$0"), (fmt(0.174, "pct"), "17.4%"),
                      (fmt(1.0, "pct"), "100%"), (fmt(4171, "count"), "4,171"),
                      (fmt(1.26, "ratio"), "1.3x"), (fmt(None, "usd"), UNABLE),
                      (fmt(9_438_108, "usd", "deck"), "$9.4M"),
                      (fmt(81_234, "usd", "deck"), "$81K"),
                      (fmt(1_204_000_000, "usd", "deck"), "$1.2B"),
                      (fmt(-5_000_000, "eur"), "(€5,000,000)"),
                      (fmt(120_000.4, "jpy", "cell"), "¥120,000"),
                      (fmt(1234.5678, "kwd", "cell"), "KWD 1,234.568"),
                      (fmt(45.26, "days"), "45.3 days"), (fmt(0.0425, "rate"), "4.25%"),
                      (fmt(1.06789, "fx_rate"), "1.0679"), (fmt(12.5, "quantity"), "12.5"),
                      (fmt(0.97, "ratio", precision=2), "0.97x"),
                      (fmt(-0.00001, "fx_rate"), "0.0000")):
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
                "Billed $1,000 against $1K.":
            bad.append(f"sub: {L.sub('Billed {F.k1.revenue} against {F.k0.tb.revenue:deck}.')}")
        if "T.k1.pct_fails" not in tie_table(L.ties):
            bad.append("tie_table lost a tie")
        L.write()
        back = load(run)
        if back.value("F.k1.revenue") != 1000.0 or back["F.k1.revenue"]["population"] != \
                {"ref": "P.k1.lines"}:
            bad.append(f"round trip: {back['F.k1.revenue']}")
        if "&id" in (run / "workpapers/figures-k1.yaml").read_text(encoding="utf-8"):
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

        # Currencies: stored at their minor units, never tied across.
        C = Ledger(run, "k5")
        C.cite({"id": "E.k5.bank", "kind": "span", "file": "bank.csv"})
        C.fig("F.k5.jpy", "Yen balance", 120_000.4, "jpy", "E.k5.bank", [("b", "E.k5.bank")])
        C.fig("F.k5.kwd", "Dinar balance", 1234.5678, "kwd", "E.k5.bank", [("b", "E.k5.bank")])
        C.fig("F.k5.eur", "Euro balance", 1000.0, "eur", "E.k5.bank", [("b", "E.k5.bank")])
        C.fig("F.k5.eur_gl", "Euro GL", 1000.0, "eur", "E.k5.bank", [("b", "E.k5.bank")])
        C.fig("F.k5.rate", "EUR/USD closing rate", 1.0679, "fx_rate", "E.k5.bank",
              [("b", "E.k5.bank")])
        C.fig("F.k5.usd", "Euro balance in USD", 1067.90, "usd", "F.k5.eur * F.k5.rate",
              [("amount", "F.k5.eur"), ("rate", "F.k5.rate")])
        C.fig("F.k5.usd_sum", "Sum of translated", 1067.90, "usd", "F.k5.usd",
              [("a", "F.k5.usd")])
        C.fig("F.k5.usd_gl", "USD GL", 1067.9, "usd", "E.k5.bank", [("b", "E.k5.bank")])
        C.fig("F.k5.rate_b", "EUR/USD per bank", 1.0400, "fx_rate", "E.k5.bank",
              [("b", "E.k5.bank")])
        if C.entries["F.k5.jpy"]["value"] != 120_000.0 or \
                C.entries["F.k5.kwd"]["value"] != 1234.568:
            bad.append(f"minor units: {C.entries['F.k5.jpy']['value']}, "
                       f"{C.entries['F.k5.kwd']['value']}")
        expect_error("a tie across currencies",
                     lambda: C.tie("T.k5.cross", "x", "F.k5.eur", "F.k5.usd_gl"))
        if C.tie("T.k5.translated", "x", "F.k5.usd", "F.k5.usd_gl")["status"] != "pass":
            bad.append("a translated figure did not tie")
        if C.tie("T.k5.eur", "x", "F.k5.eur", "F.k5.eur_gl")["status"] != "pass":
            bad.append("two equal euro figures did not tie")
        if C.tie("T.k5.rates", "x", "F.k5.rate", "F.k5.rate_b")["status"] != "fail":
            bad.append("FX rates 1.0679 and 1.0400 tied under display rounding")
        C.fig("F.k5.stated", "Revenue as stated in $000s", 9438.1, "usd",
              "as stated at E.k5.bank (passthrough)", [("b", "E.k5.bank")],
              disposition="as_stated", stated_scale="thousands")
        st = C.entries["F.k5.stated"]
        if st["value"] != 9_438_100.0 or "x 1,000" not in st["expression"] or \
                st["stated_value"] != 9438.1:
            bad.append(f"stated scale: {st}")
        expect_error("stated_scale on a measured figure",
                     lambda: C.fig("F.k5.s2", "x", 1.0, "usd", "E.k5.bank",
                                   [("b", "E.k5.bank")], stated_scale="thousands"))
        expect_error("an unknown currency", lambda: C.fig("F.k5.xyz", "x", 1.0, "xyz",
                                                          "E.k5.bank", [("b", "E.k5.bank")]))

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

    corner_cases(bad, expect_error)
    for b in bad:
        print(f"figures: {b}")
    print("figures: ok" if not bad else "figures: self-check FAILED")
    return 0 if not bad else 1


def corner_cases(bad: list[str], expect_error) -> None:
    """Inputs inside the documented contract that once gave a wrong answer or a crash."""
    import tempfile

    import numpy as np
    import yaml

    # numbers as a caller hands them: ints for a share, huge counts, no NaN/inf in prose
    for got, want in ((fmt(1, "pct"), "100%"), (fmt(0, "pct"), "0%"), (fmt(2, "ratio"), "2.0x"),
                      (fmt(3, "days"), "3.0 days"), (fmt(1, "rate"), "100%"),
                      (fmt(12_345_678_901_234_567, "count"), "12,345,678,901,234,567"),
                      (fmt(np.int64(7), "count"), "7"), (fmt(np.float64(0.5), "pct"), "50%")):
        if got != want:
            bad.append(f"fmt: got {got!r}, want {want!r}")
    if md_table(["share"], [[1]], ["pct"]).splitlines()[-1] != "| 100% |":
        bad.append("md_table: an int share")
    if "\r" in md_table(["a"], [["x\ry"]], [None]):
        bad.append("md_table left a carriage return in a cell")
    expect_error("an infinite value in prose", lambda: fmt(float("inf"), "usd"))
    expect_error("an unknown style on a None value", lambda: fmt(None, "usd", "bogus"))

    with tempfile.TemporaryDirectory() as d:
        run = pathlib.Path(d)
        (run / "workpapers").mkdir()
        expect_error("a check id with a `-` (it names another check's files)",
                     lambda: Ledger(run, "a5-bridge"))
        Ledger(run, "profile-bank-1")                      # a profile's ledger is named so

        L = Ledger(run, "c1")
        L.cite({"id": "E.c1.src", "kind": "cell", "file": "x.xlsx"})
        src = [room("s", "E.c1.src")]
        # stated at a scale: multiplied out exactly, as written
        for k in range(1, 2001):
            L.fig(f"F.c1.n{k}", "n", k / 1000, "count", "as stated at E.c1.src", src,
                  disposition="as_stated", stated_scale="thousands")
            if L.entries[f"F.c1.n{k}"]["value"] != k:
                bad.append(f"stated scale: {k / 1000} thousand stored as "
                           f"{L.entries[f'F.c1.n{k}']['value']}")
                break
        L.fig("F.c1.m", "m", 1.005, "usd", "as stated at E.c1.src", src,
              disposition="as_stated", stated_scale="thousands")
        if L.entries["F.c1.m"]["value"] != 1005.0:
            bad.append(f"stated scale money: {L.entries['F.c1.m']['value']}")
        # a refused call holds nothing: the corrected call mints the same id
        expect_error("a unit in upper case", lambda: L.fig("F.c1.r", "r", 5, "USD", "E.c1.src", src))
        try:
            L.fig("F.c1.r", "r", 5, "usd", "as stated at E.c1.src", src)
        except ValueError as e:
            bad.append(f"a corrected call after a refusal: {e}")
        # multiplication is not a wildcard; a wildcard or a range still is
        for expr in ("F.c1.r*2", "F.c1.r*F.c1.m", "F.c1.r*(1+F.c1.m)", "F.c1.r * -1"):
            try:
                L.fig(f"F.c1.x{abs(hash(expr)) % 10**6}", "x", 1, "usd", expr,
                      [("a", "F.c1.r"), ("b", "F.c1.m")])
            except ValueError as e:
                bad.append(f"expression {expr!r} refused: {e}")
        for k, expr in enumerate(("sum over E.c1.memos_*", "E.c1.*", "E.c1.memo* rows",
                                  "E.c1.fy2023..fy2025")):
            expect_error(f"expression {expr!r}",
                         lambda: L.fig(f"F.c1.w{k}", "w", 1, "usd", expr, src))
        # extras: never an entry's own field; plain data only, numpy converted
        expect_error("an extra `id`", lambda: L.fig("F.c1.e1", "e", 1, "usd", "E.c1.src", src,
                                                     id="F.other"))
        expect_error("an extra `tie`", lambda: L.fig("F.c1.e2", "e", 1, "usd", "E.c1.src", src,
                                                      tie={}))
        expect_error("an extra YAML cannot write", lambda: L.fig("F.c1.e3", "e", 1, "usd",
                                                                 "E.c1.src", src, obj=object()))
        expect_error("inputs as one dict", lambda: L.fig("F.c1.e4", "e", 1, "usd", "E.c1.src",
                                                         room("s", "E.c1.src")))
        expect_error("a figure input citing an E. id",
                     lambda: L.fig("F.c1.e5", "e", 1, "usd", "E.c1.src",
                                   [{"role": "s", "source_type": "figure", "figure_id": "E.c1.src"}]))
        L.fig("F.c1.np", "n", np.float64(12.5), "usd", "as stated at E.c1.src", src,
              sample=np.int64(3))
        # populations: every excluded item named once, with its count
        expect_error("exclusions that do not add up",
                     lambda: L.population("P.c1.bad", "x", 100, 50,
                                          exclusions=[{"what": "credits", "n": 3}]))
        expect_error("an exclusion when nothing is excluded",
                     lambda: L.population("P.c1.bad2", "x", 10, 10,
                                          exclusions=[{"what": "credits", "n": 3}]))
        expect_error("citations as one string",
                     lambda: L.population("P.c1.bad3", "x", 1, 1, citations="E.c1.src"))
        L.population("P.c1.ok", "x", 10, 7, citations=["E.c1.src"],
                     exclusions=[{"what": "credits", "n": np.int64(2)}, {"what": "voids", "n": 1}])
        L.population("P.c1.empty", "empty", 0, 0, citations=["E.c1.src"])
        expect_error("measured_zero over an empty P.",
                     lambda: L.fig("F.c1.z", "z", 0, "usd", "E.c1.src", src,
                                   population="P.c1.empty", zero_basis="measured_zero"))
        L.fig("F.c1.z", "z", 0, "usd", "as stated at E.c1.src", src, population="P.c1.ok",
              zero_basis="measured_zero")
        L.write()
        text = (run / "workpapers" / "figures-c1.yaml").read_text()
        if "numpy" in text or yaml.safe_load(text) is None:
            bad.append("numpy scalars reached the ledger")

        # fresh: what this pass does not mint again resolves nowhere, even in prose
        F = Ledger(run, "c1", fresh=True)
        F.fig("F.c1.keep", "k", 1, "usd", "F.c1.r", [("r", "F.c1.r")])
        if F.get("F.c1.r") is not None:
            bad.append("fresh ledger still reads its own dropped figure")
        expect_error("prose citing a figure the fresh pass dropped",
                     lambda: F.sub("It was {F.c1.r}."))
        # a pass that cites nothing leaves no stale evidence ledger behind
        G = Ledger(run, "c2")
        G.cite({"id": "E.c2.gone", "kind": "cell", "file": "x.xlsx"})
        G.fig("F.c2.x", "x", 1, "usd", "as stated at E.c2.gone", [("s", "E.c2.gone")])
        G.write()
        G2 = Ledger(run, "c2", fresh=True)
        G2.fig("F.c2.y", "y", 2, "usd", "F.c1.m", [("m", "F.c1.m")])
        G2.write()
        if (run / "workpapers" / "evidence-c2.yaml").exists():
            bad.append("a fresh pass with no citations left the old evidence ledger")

        # ties survive a resume; a side that moved refuses the write until tied again
        T = Ledger(run, "t1")
        T.fig("F.t1.a", "a", 100, "usd", "F.c1.m", [("m", "F.c1.m")])
        T.fig("F.t1.b", "b", 100, "usd", "F.c1.m", [("m", "F.c1.m")])
        T.tie("T.t1.x", "a | b", "F.t1.a", "F.t1.b")
        T.write()
        T2 = Ledger(run, "t1")
        if [t["id"] for t in T2.ties] != ["T.t1.x"] or "a \\| b" not in tie_table(T2.ties):
            bad.append(f"ties after a resume: {T2.ties}")
        T2.fig("F.t1.a", "a", 150, "usd", "F.c1.m", [("m", "F.c1.m")])
        expect_error("a tie whose side moved since it was classified", T2.write)
        T2.tie("T.t1.x", "a to b", "F.t1.a", "F.t1.b")
        T2.write()
        if len(Ledger(run, "t1").ties) != 1 or Ledger(run, "t1").ties[0]["status"] != "fail":
            bad.append("a re-tie did not replace the earlier record")
        # a limit is shown at its own precision, never the display rounding's
        P = Ledger(run, "t2")
        P.fig("F.t2.p1", "p", 0.1234, "pct", "F.c1.m", [("m", "F.c1.m")])
        P.fig("F.t2.p2", "p", 0.1236, "pct", "F.c1.m", [("m", "F.c1.m")])
        P.tie("T.t2.p", "p", "F.t2.p1", "F.t2.p2")
        if "0.02% <= 0.05%" not in tie_table(P.ties):
            bad.append(f"tie_table limit: {tie_table(P.ties)}")

        # an E. input's kind follows its citation, wherever and whenever it is cited
        K = Ledger(run, "k1")
        K.fig("F.k1.x", "x", 3, "usd", "sum over E.k1.out", [("rows", "E.k1.out")])
        K.cite({"id": "E.k1.out", "kind": "span", "file_role": "run_artifact",
                "file": "checks/c1-items.csv"})
        K.write()
        if Ledger(run, "k1").entries["F.k1.x"]["inputs"][0]["source_type"] != "check_output":
            bad.append("a tuple input cited later as a run artifact stayed room_file")
        K2 = Ledger(run, "k2")
        K2.fig("F.k2.x", "x", 3, "usd", "sum over E.k1.out", [("rows", "E.k1.out")])
        if K2.entries["F.k2.x"]["inputs"][0]["source_type"] != "check_output":
            bad.append("another check's run-artifact citation read as room_file")
        K3 = Ledger(run, "k3")
        K3.fig("F.k3.x", "x", 3, "usd", "sum over E.k1.out", [room("rows", "E.k1.out")])
        expect_error("a room_file input citing a run_artifact read", K3.write)

        # prose: a malformed reference is refused, never left in the sentence
        expect_error("an unknown style", lambda: L.sub("Share {F.c1.m:pct}."))
        expect_error("a space inside the braces", lambda: L.sub("Share { F.c1.m }."))

        # the same id in two ledgers: agreeing is fine, disagreeing is a finding
        (run / "workpapers" / "figures-zz.yaml").write_text(
            "- id: F.c1.m\n  value: 1005.0\n  unit: usd\n- id: F.c1.r\n  value: 999\n  unit: usd\n")
        S = load(run)
        if S.value("F.c1.m") != 1005.0:
            bad.append("an id two ledgers agree on")
        expect_error("an id two ledgers disagree on", lambda: S.value("F.c1.r"))
        expect_error("prose citing a disagreed id", lambda: S.sub("{F.c1.r}"))


if __name__ == "__main__":
    raise SystemExit(main())
