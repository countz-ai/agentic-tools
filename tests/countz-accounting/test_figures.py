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

    for b in bad:
        print(f"figures: {b}")
    print("figures: ok" if not bad else "figures: self-check FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
