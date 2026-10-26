#!/usr/bin/env python3
"""Self-test for scripts/recipe_scope.py: a run over some of a recipe's families.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_recipe_scope.py`
from the repository root. Covers the family parse and its reads (recipe_format.families),
the picks resolved into a scope, the table the user sees, the plan approval's scope filter
(run_state.out_of_scope) and the deck gate's reach (check_report.in_run).
"""
from __future__ import annotations

import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import check_report  # noqa: E402
import recipe_format  # noqa: E402
import recipe_scope  # noqa: E402
import run_state  # noqa: E402

RECIPE = """---
name: demo-substantiation
objective: >-
  establish the demo balance
headline: d3
lead: [d3, d2]
---

## The families

### D0 — the population, drawn from the balance sheet (kind `analysis`, one check)

**Reads:** the data room.

### D1 — the books agree internally (kind `tieout`, per GL account)

**Reads:** D0 (`params.roster_from`).

### D2 — the `cash_ledger` reconciled to the bank (kind `recon`, per bank account)

The ledger against the statement (`params.roster_from` names D0). D3 reads what this
family leaves open.

### D3 — the walk (kind `analysis`, one check)

**Reads:** D1 (`params.ties_from`), D2 (`params.items_from`).

## Exec summary
"""


def main() -> int:
    bad: list[str] = []

    def expect(cond, what):
        if not cond:
            bad.append(what)

    fams = recipe_format.families(RECIPE)
    expect([f["id"] for f in fams] == ["d0", "d1", "d2", "d3"], f"ids: {fams}")
    reads = {f["id"]: f["reads"] for f in fams}
    expect(reads["d0"] == [], f"d0 reads the data room only: {reads['d0']}")
    expect(reads["d1"] == ["d0"], f"d1 from its Reads paragraph: {reads['d1']}")
    # no Reads paragraph: the ids in its `_from` sentences, not a downstream mention
    expect(reads["d2"] == ["d0"], f"d2 from its _from sentence: {reads['d2']}")
    expect(reads["d3"] == ["d1", "d2"], f"d3: {reads['d3']}")

    expect(recipe_format.plain_title("the `cash_ledger` reconciled to the bank")
           == "The cash ledger reconciled to the bank", "plain_title strips markup")

    expect(recipe_scope.resolve(fams, "all") is None, "all is a full run")
    expect(recipe_scope.resolve(fams, "4") is None, "the walk reads everything: a full run")
    s = recipe_scope.resolve(fams, "3")
    expect(s == {"picked": ["d2"], "families": ["d0", "d2"], "added": ["d0"]}, f"pick 3: {s}")
    s = recipe_scope.resolve(fams, "d1, 3")
    expect(s and s["families"] == ["d0", "d1", "d2"], f"ids and numbers mix: {s}")
    try:
        recipe_scope.resolve(fams, "9")
        bad.append("a pick naming no row is refused")
    except recipe_scope.Refuse:
        pass
    say = recipe_scope.say(fams, recipe_scope.resolve(fams, "3"))
    expect("The cash ledger reconciled to the bank" in say and "The population" in say, say)

    shown = "\n".join(recipe_scope.table(fams))
    expect("| 3 | The cash ledger reconciled to the bank |" in shown, f"numbered rows:\n{shown}")
    expect("☐" not in shown and "☑" not in shown and "Run everything" not in shown,
           "an overview: no checkbox, no run-everything row")
    expect(shown.rstrip().endswith(recipe_scope.PROMPT), "the prompt sits under the table")
    expect("D2" not in shown and "_" not in shown and "`" not in shown,
           f"no family id, underscore or markup reaches the user:\n{shown}")
    # a specific request: the prompt proposes the steps it bears on, by row number
    proposed = "\n".join(recipe_scope.table(fams, "d3, d2"))
    expect(proposed.rstrip().endswith(
        "Based on your request, steps 3, 4 are relevant, shall we run them?"),
        f"two steps proposed, in row order:\n{proposed}")
    expect(recipe_scope.PROMPT not in proposed, "a proposal replaces the open prompt")
    expect(recipe_scope.suggestion(fams, "2")
           == "Based on your request, step 2 is relevant, shall we run it?", "one step")
    try:
        recipe_scope.suggestion(fams, "d7")
        bad.append("a proposal naming no step is refused")
    except recipe_scope.Refuse:
        pass
    expect(recipe_scope.resolve(fams, "run 3") == recipe_scope.resolve(fams, "3"),
           "`run 3` reads as the pick 3")
    expect(recipe_scope.resolve(fams, "run all") is None, "`run all` is a full run")
    # with estimates: a time and a cost per row, the run's estimate above the prompt
    est = {"families": {f["id"]: {"cost_usd": 4.4, "minutes": 75.0, "source": "history"} for f in fams},
           "overhead": {"cost_usd": 15.0, "minutes": 40.0}, "runs": 3, "rerun_share": 0.0,
           "elapsed_per_work": 0.5}
    priced = "\n".join(recipe_scope.table(fams, None, est))
    expect("| 3 | The cash ledger reconciled to the bank | 1h 15m | $4 |" in priced,
           f"a row carries its time and cost:\n{priced}")
    expect("about 40m and $15" in priced and "from 3 earlier runs" in priced, f"the notes:\n{priced}")
    expect("about $33 and 3h 10m from start to report" in priced,
           f"all steps: 4 x $4.40 + $15, max(300m x 0.5, 75m) + 40m:\n{priced}")
    expect(priced.rstrip().endswith(recipe_scope.PROMPT), "the prompt stays last")
    expect("_" not in priced and "D2" not in priced, "no id or underscore with estimates")
    line = recipe_scope.say(fams, recipe_scope.resolve(fams, "3"), est)
    expect(line.endswith("Estimated cost $24, about 1h 55m from start to report."),
           f"the scope's estimate: 2 x $4.40 + $15, 75m + 40m: {line}")
    # the headers alone are enough to ask: the relay pipes them, writing no file
    heads = "\n".join(line for line in RECIPE.splitlines() if line.startswith("### "))
    expect([f["id"] for f in recipe_format.families(heads)] == ["d0", "d1", "d2", "d3"],
           "family headers alone parse")

    definition = {"steps": [
        {"id": "extract_gl", "check": "extract", "params": {}},
        {"id": "d0_population", "params": {"family": "d0"}, "after": ["extract_gl"]},
        {"id": "d1_accounts", "params": {"family": "d1"}, "after": ["d0_population"]},
        {"id": "d2_accounts", "params": {"family": "d2"}, "after": ["d0_population", "d1_accounts"]},
        {"id": "d3_walk", "params": {"family": "d3"}, "after": ["d1_accounts", "d2_accounts"]},
    ]}
    # d2 reads d1 although the recipe's text did not say so: d1 runs; the walk does not
    out = run_state.out_of_scope(definition, {"families": ["d0", "d2"]})
    expect(out == ["d3_walk"], f"out of scope: {out}")

    fm = recipe_format.frontmatter(RECIPE)
    schedules = [{"title": "Walk", "from": "d3"}, {"title": "Items", "from": "d2"}]
    partial = {"checks": [{"id": "d0_population", "params": {"family": "d0"}},
                          {"id": "d2_accounts", "params": {"family": "d2"}}]}
    sc, m = check_report.in_run(partial, fm, schedules, {"title": "Demo as substantiated"})
    expect([x["from"] for x in sc] == ["d2"], f"a schedule from a family not run drops: {sc}")
    expect(m is None, "no key-metrics page when the headline family did not run")
    full = {"checks": partial["checks"] + [{"id": "d3_walk", "params": {"family": "d3"}}]}
    sc, m = check_report.in_run(full, fm, schedules, {"title": "Demo as substantiated"})
    expect(len(sc) == 2 and m, "a full run is held to every schedule and the metrics page")

    # progress counts the recipe steps the run performs, a middle one left out included
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rp = pathlib.Path(td) / "demo.md"
        rp.write_text(RECIPE)
        run = {"plan": {"recipe": str(rp)}, "dispatches": [], "inputs": {}, "checks": [
            {"id": "extract_gl", "kind": "extract", "params": {}},
            {"id": "d0_population", "kind": "analysis", "params": {"family": "d0"}},
            {"id": "d2_large", "kind": "recon", "params": {"family": "d2"}},
            {"id": "d2_rest", "kind": "recon", "params": {"family": "d2"}}]}
        pos = run_state.say_position(run, [("d2_large", None, {"family": "d2"}),
                                           ("d2_rest", None, {"family": "d2"})])
        expect(pos == ([2], 2), f"a split family is one step, d1 left out of the count: {pos}")
        line = run_state.at_step(run, "x", *run_state.say_position(run, [("extract_gl", None, {})]))
        expect(line == "x", f"the extract step carries no position: {line}")
        line = run_state.at_step(run, "x", *run_state.say_position(run, [(None, "review", None)]))
        expect(line == "x", f"the review carries no position: {line}")
        what = run_state.describe_members([("d2_large", "recon", {"family": "d2"})],
                                          run_state.recipe_families(run))
        expect(what == "The cash ledger reconciled to the bank", f"a family by its title: {what}")

    for b in bad:
        print(f"FAIL: {b}")
    print(f"test_recipe_scope: {'ok' if not bad else f'{len(bad)} failure(s)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
