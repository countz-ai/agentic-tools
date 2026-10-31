#!/usr/bin/env python3
"""Self-test for scripts/spend_model.py: the spend estimate check-plan puts in plan.md.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_spend_model.py`
from the repository root. Covers the fit recovering a known cost law from synthetic runs,
re-runs kept out of the fit and measured as a share, the estimate's per-family sums and
ranges, an unseen step kind taking the mean intercept, the lanes simulation's elapsed
time, and the shipped model file loading and estimating.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import tempfile

SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import spend_model  # noqa: E402

FAILS: list[str] = []


def check(cond: bool, what: str) -> None:
    if not cond:
        FAILS.append(what)


def definition(n_fam: int = 3, per_fam: int = 1) -> dict:
    steps = [{"id": "extract_dataroom", "check": "extract", "after": [],
              "params": {"files": [{"id": f"t{i}"} for i in range(4)]}}]
    for f in range(n_fam):
        for k in range(per_fam):
            sid = f"a{f}_{k}"
            steps.append({"id": sid, "check": "analysis", "after": ["extract_dataroom"],
                          "params": {"family": f"a{f}", "reads": ["t0", "t1"],
                                     "cache_from": "extract_dataroom"}})
    return {"steps": steps}


def write_run(root: pathlib.Path, name: str, d: dict, cost: dict, rerun: str | None = None) -> None:
    """A finished efficacy run as `fit` reads it: definition, step records, usage log."""
    run = root / "demo" / name / "trace" / "run"
    (run / "plan").mkdir(parents=True)
    (run / "steps").mkdir()
    (run / "plan" / "demo.json").write_text(json.dumps(d))
    (run / "events.jsonl").write_text(json.dumps({"plugin_version": "0.21.0"}) + "\n")
    lines, seq = [], 0
    order = [s["id"] for s in d["steps"]] + ([rerun] if rerun else [])
    for sid in order:
        seq += 1
        kind = "extract" if sid.startswith("extract") else "analyze"
        (run / "steps" / f"{seq:04d}-{kind}.json").write_text(json.dumps({"check_id": sid}))
        lines.append(json.dumps({"brief": f"dispatch/{seq:04d}-{kind}.md", "rc": 0,
                                 "cost_usd": cost[sid], "minutes": cost[sid] * 2}))
    seq += 1
    report = 4 * (len(d["steps"]) + 1) ** 0.5
    lines.append(json.dumps({"brief": f"dispatch/{seq:04d}-report.md", "rc": 0,
                             "cost_usd": report, "minutes": report * 2}))
    (run / "efficacy-usage.jsonl").write_text("\n".join(lines) + "\n")


def test_fit_and_estimate() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        # an exact law: a step costs its kind's base (extract 1, analyze 2, report 4)
        # x (steps + 1)^0.5 dollars
        for i, n in enumerate([2, 3, 4, 5, 6, 8]):
            d = definition(n_fam=n)
            law = (len(d["steps"]) + 1) ** 0.5
            cost = {s["id"]: (1 if s["check"] == "extract" else 2) * law for s in d["steps"]}
            write_run(root, f"run{i}", d, cost, rerun="a0_0" if i == 0 else None)
        out = root / "model.json"
        args = type("A", (), {"runs_root": root, "out": out})
        # six runs: the shipped ridge would shrink the slope; a tiny one keeps the constant
        # features (warm, log_from) solvable
        ridge, spend_model.RIDGE = spend_model.RIDGE, 1e-6
        check(spend_model.cmd_fit(args) == 0, "fit exits 0")
        spend_model.RIDGE = ridge
        model = json.loads(out.read_text())
        c = model["targets"]["cost_usd"]["coef"]
        check(model["schema"] == spend_model.SCHEMA, "fit writes the schema")
        check(model["training"]["steps"] == sum(n + 2 for n in [2, 3, 4, 5, 6, 8]),
              "fit counts first-pass dispatches only (the re-run left out)")
        check(abs(c["log_steps"] - 0.5) < 0.1, f"fit recovers the steps elasticity: {c['log_steps']}")
        check(model["rerun_share"]["mean"] > 0, "fit measures the re-run share")

        e = spend_model.estimate(definition(n_fam=4), model)
        fam = {f["family"]: f for f in e["families"]}
        check(set(fam) == {"extract", "a0", "a1", "a2", "a3"}, f"families: {sorted(fam)}")
        expect = 2 * (5 + 1) ** 0.5
        got = fam["a0"]["cost_usd"]["value"]
        check(abs(got - expect) / expect < 0.15, f"a family's cost follows the law: {got:.2f} vs {expect:.2f}")
        for f in e["families"]:
            v = f["cost_usd"]
            check(v["low"] <= v["value"] <= v["high"], f"{f['family']}: the range holds the estimate")
        steps_total = sum(s["cost_usd"] for s in e["steps"]) + e["report"]["cost_usd"]["value"]
        check(abs(e["run"]["cost_usd"]["value"] - steps_total - e["reruns"]["cost_usd"]["value"]) < 1e-6,
              "the run is its steps, its report and the expected re-runs")
        table = spend_model.render(e)
        check("| **Run** |" in table and "| A0 |" in table and "| Extract |" in table, "render names each row")


def test_unseen_kind() -> None:
    model = {"kinds": ["analyze", "tie"], "targets": {"cost_usd": {"smear": 1.0, "coef": {
        "kind:analyze": math.log(4), "kind:tie": math.log(16),
        "log_reads": 0.0, "log_from": 0.0, "log_steps": 0.0, "warm": 0.0}}}}
    row = {"kind": "recon", "log_reads": 0.0, "log_from": 0.0, "log_steps": 0.0, "warm": 0.0}
    check(abs(spend_model.predict(row, model, "cost_usd") - 8.0) < 1e-9,
          "an unseen kind takes the mean of the kind intercepts (geometric mean 8)")


def test_elapsed() -> None:
    # extract, then three independent families: three lanes run them side by side
    d = definition(n_fam=3)
    mins = {s["id"]: (5.0 if s["check"] == "extract" else 10.0) for s in d["steps"]}
    check(spend_model.elapsed_minutes(d, mins) == 15.0,
          f"three parallel steps after extract: {spend_model.elapsed_minutes(d, mins)}")
    # a chain: each family reads the one before it
    for i, s in enumerate(d["steps"][2:], start=1):
        s["after"] = [d["steps"][i]["id"]]
        s["params"]["items_from"] = d["steps"][i]["id"]
    check(spend_model.elapsed_minutes(d, mins) == 35.0,
          f"a chain runs end to end: {spend_model.elapsed_minutes(d, mins)}")


def test_pick_estimates() -> None:
    """Before the plan: a family an earlier run of the recipe covered takes that history; one
    no run covered is priced from its kind."""
    model = json.loads(spend_model.MODEL.read_text())
    model = {**model, "history": {"demo": {"runs": 2, "overhead": {"cost_usd": 10.0, "minutes": 30.0},
                                           "families": {"d0": {"cost_usd": 3.0, "minutes": 9.0, "runs": 2}}}}}
    fams = [{"id": "d0", "kind": "analysis", "reads": []}, {"id": "d1", "kind": "tieout", "reads": ["d0"]}]
    e = spend_model.pick_estimates("demo", fams, model)
    check(e["families"]["d0"] == {"cost_usd": 3.0, "minutes": 9.0, "source": "history"}, f"d0: {e['families']['d0']}")
    check(e["families"]["d1"]["source"] == "model" and e["families"]["d1"]["cost_usd"] > 0, f"d1: {e['families']['d1']}")
    check(e["runs"] == 2 and e["overhead"]["cost_usd"] == 10.0, "the recipe's own overhead")
    other = spend_model.pick_estimates("unknown", fams, model)
    check(other["runs"] == 0 and other["overhead"]["cost_usd"] > 0, "an unknown recipe: overhead from the model")
    e = {**e, "rerun_share": 0.1, "elapsed_per_work": 0.5}
    t = spend_model.scope_total(e, fams, ["d0"])
    check(abs(t["cost_usd"] - 13.0 * 1.1) < 1e-9, f"d0 alone: (3 + 10) x 1.1: {t}")
    check(t["elapsed_minutes"] == 9.0 + 30.0, f"one family runs no faster than itself: {t}")


def test_shipped_model() -> None:
    model = json.loads(spend_model.MODEL.read_text())
    check(model["schema"] == spend_model.SCHEMA, "the shipped model carries the schema")
    e = spend_model.estimate(definition(n_fam=3, per_fam=2), model)
    check(e["run"]["cost_usd"]["value"] > 0 and e["run"]["elapsed_minutes"]["value"] > 0,
          "the shipped model estimates a plan")


if __name__ == "__main__":
    for t in (test_fit_and_estimate, test_unseen_kind, test_elapsed, test_pick_estimates,
              test_shipped_model):
        t()
    if FAILS:
        print("\n".join(f"FAIL {f}" for f in FAILS))
        raise SystemExit(1)
    print("ok")
