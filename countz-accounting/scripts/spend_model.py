#!/usr/bin/env python3
"""Estimate what a drafted plan will spend, per step, per family and for the run.

    spend_model.py estimate <run_dir> <definition> [--model <path>] [--json]
    spend_model.py fit <runs_root> [--out <path>]

`estimate` reads the drafted playbook definition and prints the spend table check-plan
puts in plan.md; it writes the same figures to `<run_dir>/plan/spend-estimate.json`.
`fit` learns the model from finished efficacy runs and writes
reference/spend_model.json.

Before any plan exists, recipe_scope.py prices each family in the table the user picks
from (`pick_estimates`, `scope_total`). A family takes its median over the recipe's
earlier runs, kept in the model file's `history`. A family no earlier run covered takes
the model's figure for one step of its kind. On the first fit, held out by run, these
were within 11% (median) of actual cost per family and per run, and 17% of elapsed.

The model is a linear regression on the log of each step's cost and minutes:

    log(y) = intercept[step kind] + b . features + version offset

with the features the plan fixes before anything runs: how many tables the step reads,
how many `_from` params it carries, how many steps the plan has, and whether the step
runs warm (an earlier step of its lane ran in the same holder: lanes.py). Predictions
are back-transformed with the smearing factor (the mean of exp(residual)), so a sum of
step predictions is an unbiased run total.

Data-room size is not a feature. On the 68 runs the first fit used, entity counts,
line counts and bytes read moved the leave-one-run-out error by under one point at
every level (step, family, run), so the model leaves them out.

`fit` measures the ranges: it holds out each run in turn, predicts it from the others,
and stores the 10th and 90th percentile of actual / predicted at each level, families
grouped by their step count. Relative error shrinks as steps are summed. On the first
fit, the median absolute error on cost was 19% for a step, 13% for a family of six or
more steps and 6% for the run.

Elapsed time replays lanes.py's placement over the predicted minutes, then scales it by
the median ratio of actual to replayed elapsed on the held-out lanes runs. The ratio
carries the relay's time between steps, which no step's minutes include.

The review's fix round re-runs checks the plan does not list. `fit` measures their cost
as a share of the first pass, and `estimate` adds that share as its own line.

`fit` reads a run directory per finished efficacy run, at
<runs_root>/<recipe>/<stamp>/trace/run/, using: efficacy-usage.jsonl (cost_usd and
minutes per dispatch, written by the efficacy harness), steps/NNNN-*.json (which check
each dispatch ran), plan/<name>.json (the definition), lanes.json and events.jsonl.
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import math
import pathlib
import re
import sys

import lanes

HERE = pathlib.Path(__file__).resolve()
MODEL = HERE.parent.parent / "reference" / "spend_model.json"
SCHEMA = "countz-accounting/spend-model@1"
FEATURES = ("log_reads", "log_from", "log_steps", "warm")
TARGETS = ("cost_usd", "minutes")
RIDGE = 1.0          # on the feature and version terms only; the kind intercepts are free
RESET_BRIEFS = 6     # lanes.py's default: a holder is replaced after this many briefs
KIND_OF = {"tieout": "tie", "analysis": "analyze"}   # check kind -> dispatch step name


def step_kind(check: str) -> str:
    return KIND_OF.get(check, check)


def features(step: dict | None, n_steps: int, warm: bool) -> dict[str, float]:
    p = (step or {}).get("params") or {}
    reads = p.get("files") if (step or {}).get("check") == "extract" else p.get("reads")
    return {"log_reads": math.log1p(len(reads or [])),
            "log_from": math.log1p(sum(1 for k in p if k.endswith("_from"))),
            "log_steps": math.log1p(n_steps),
            "warm": 1.0 if warm else 0.0}


# ------------------------------------------------------------------ lanes
def lane_order(definition: dict) -> dict[str, list[str]]:
    """Each lane's steps in the order a lanes run starts them: hard steps, then the pool
    steps whose first candidate is the lane."""
    a = lanes.assign(definition)
    order = {lane: list(ids) for lane, ids in a["lanes"].items()}
    for sid, cands in a["pool"].items():
        order.setdefault(cands[0], []).append(sid)
    return order


def warm_steps(definition: dict) -> set[str]:
    return {sid for ids in lane_order(definition).values()
            for i, sid in enumerate(ids) if i % RESET_BRIEFS}


def elapsed_minutes(definition: dict, minutes: dict[str, float]) -> float:
    """Wall-clock of the plan's steps over its lanes, placed as lanes.place places them:
    each free lane takes its own next ready step, then each ready pool step goes to the
    first free lane among its candidates."""
    order = [s["id"] for s in definition["steps"]]
    after = {s["id"]: [d for d in s.get("after") or [] if d in order] for s in definition["steps"]}
    a = lanes.assign(definition)
    own = {sid: lane for lane, ids in a["lanes"].items() for sid in ids}
    t, running, done = 0.0, {}, set()          # running: lane -> (step id, end time)
    while len(done) < len(order):
        started = done | {sid for sid, _ in running.values()}
        ready = [s for s in order if s not in started and all(d in done for d in after[s])]
        free = [lane for lane in a["lanes"] if lane not in running]
        for lane in free:
            sid = next((s for s in ready if own.get(s) == lane), None)
            if sid:
                running[lane] = (sid, t + minutes.get(sid, 0.0))
                ready.remove(sid)
        for sid in [s for s in ready if s in a["pool"]]:
            lane = next((c for c in a["pool"][sid] if c in a["lanes"] and c not in running), None)
            if lane:
                running[lane] = (sid, t + minutes.get(sid, 0.0))
        if not running:
            raise ValueError("steps remain that no lane can start: " + ", ".join(s for s in order if s not in done))
        t = min(end for _, end in running.values())
        for lane in [lane for lane, (_, end) in running.items() if end <= t]:
            done.add(running.pop(lane)[0])
    return t


# ------------------------------------------------------------------ the model
def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        if abs(m[c][c]) < 1e-12:
            raise ValueError("singular system: a kind or version with no rows")
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for c in reversed(range(n)):
        x[c] = (m[c][n] - sum(m[c][k] * x[k] for k in range(c + 1, n))) / m[c][c]
    return x


def _semver(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else x for x in v.split("."))


def fit_model(rows: list[dict]) -> dict:
    """Ridge-regularized least squares on log(target), one fit per target. The newest
    plugin version is the baseline: its rows carry no version term, so a prediction
    without a version is a prediction at that version."""
    kinds = sorted({r["kind"] for r in rows})
    seen = sorted({r["version"] for r in rows if r.get("version")}, key=_semver)
    versions = seen[:-1]
    names = [f"kind:{k}" for k in kinds] + list(FEATURES) + [f"version:{v}" for v in versions]
    xs = [[1.0 if r["kind"] == k else 0.0 for k in kinds] + [r[f] for f in FEATURES]
          + [1.0 if r.get("version") == v else 0.0 for v in versions] for r in rows]
    n = len(names)
    xtx = [[sum(x[i] * x[j] for x in xs) for j in range(n)] for i in range(n)]
    for i in range(len(kinds), n):
        xtx[i][i] += RIDGE
    model = {"kinds": kinds, "versions": versions, "baseline_version": seen[-1] if seen else None,
             "targets": {}}
    for t in TARGETS:
        ys = [math.log(r[t]) for r in rows]
        beta = solve(xtx, [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(n)])
        res = [y - sum(b * v for b, v in zip(beta, x)) for x, y in zip(xs, ys)]
        model["targets"][t] = {"coef": dict(zip(names, beta)),
                               "smear": sum(math.exp(e) for e in res) / len(res),
                               "resid_sd": (sum(e * e for e in res) / len(res)) ** 0.5}
    return model


def predict(row: dict, model: dict, target: str) -> float:
    """A row without a version is predicted at the baseline version. A kind no training
    run had takes the mean of the kind intercepts."""
    c = model["targets"][target]["coef"]
    intercepts = [c[f"kind:{k}"] for k in model["kinds"]]
    log_y = c.get(f"kind:{row['kind']}", sum(intercepts) / len(intercepts))
    log_y += sum(c[f] * row[f] for f in FEATURES) + c.get(f"version:{row.get('version')}", 0.0)
    return math.exp(log_y) * model["targets"][target]["smear"]


def quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def size_bucket(n_steps: int) -> str:
    """Families are ranged by how many steps they sum: error shrinks as steps are added."""
    return "family_1" if n_steps == 1 else "family_2_5" if n_steps <= 5 else "family_6_plus"


# ------------------------------------------------------------------ fit
def _ts(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def training_runs(runs_root: pathlib.Path) -> list[dict]:
    """Each finished efficacy run the usage log priced: its definition, one row per
    dispatch, and on a lanes run the elapsed minutes from its first check step's start to
    its last check step's end."""
    runs = []
    for usage in sorted(runs_root.glob("*/*/trace/run/efficacy-usage.jsonl")):
        run = usage.parent
        definition = None
        for p in sorted(run.glob("plan/*.json"), key=lambda p: p.stat().st_mtime):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and isinstance(d.get("steps"), list):
                definition = d
        if definition is None:
            continue
        try:
            version = json.loads((run / "events.jsonl").open(encoding="utf-8").readline()).get("plugin_version")
        except (OSError, ValueError):
            version = None
        steps = {s["id"]: s for s in definition["steps"]}
        records = {}
        for f in sorted(run.glob("steps/*.json")):
            try:
                records[int(f.name[:4])] = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        rows, seen_session, seen_check = [], set(), set()
        for line in usage.read_text(encoding="utf-8").splitlines():
            u = json.loads(line)
            m = re.match(r"dispatch/(\d+)-(\w+)\.md$", u.get("brief") or "")
            if not m or u.get("rc") not in (0, None) or not u.get("cost_usd") or not u.get("minutes"):
                continue
            seq, kind = int(m.group(1)), m.group(2)
            check = (records.get(seq) or {}).get("check_id")
            step = steps.get(check)
            key = check or kind
            session = u.get("session")
            warm = bool(session) and session in seen_session
            if session:
                seen_session.add(session)
            rows.append({"seq": seq, "step": check if step else None,
                         "kind": step_kind(step["check"]) if step else kind,
                         "family": str(((step or {}).get("params") or {}).get("family") or key),
                         "rerun": key in seen_check, "version": version,
                         "cost_usd": u["cost_usd"], "minutes": u["minutes"],
                         **features(step, len(steps), warm)})
            seen_check.add(key)
        first_runs = {}
        for r in records.values():
            if r.get("check_id") in steps and r.get("started_at") and r.get("completed_at"):
                first_runs.setdefault(r["check_id"], r)
        elapsed = None
        if (run / "lanes.json").is_file() and len(first_runs) == len(steps):
            elapsed = (max(_ts(r["completed_at"]) for r in first_runs.values())
                       - min(_ts(r["started_at"]) for r in first_runs.values())).total_seconds() / 60
        run_id = f"{usage.parents[3].name}/{usage.parents[2].name}"
        for r in rows:
            r["run"] = run_id
        recipe = None
        for rp in sorted(run.glob("recipes/*.md"), key=lambda p: p.stat().st_mtime):
            m = re.search(r"^name:\s*(\S+)", rp.read_text(encoding="utf-8"), re.M)
            recipe = m.group(1).strip("'\"") if m else recipe
        runs.append({"id": run_id, "recipe": recipe, "definition": definition, "rows": rows,
                     "elapsed": elapsed})
    return runs


def holdout(runs: list[dict]) -> dict:
    """Predict every run from a model fitted without it. Returns actual / predicted per
    target and level, and for lanes runs the elapsed minutes over the simulated lanes."""
    out = {t: collections.defaultdict(list) for t in TARGETS}
    out["elapsed"] = []
    for run in runs:
        test = [r for r in run["rows"] if not r["rerun"]]
        model = fit_model([r for o in runs if o is not run for r in o["rows"] if not r["rerun"]])
        test = [r for r in test if r["kind"] in model["kinds"]]
        if not test:
            continue
        for t in TARGETS:
            pred = [predict(r, model, t) for r in test]
            out[t]["step"] += [r[t] / p for r, p in zip(test, pred)]
            fam = collections.defaultdict(lambda: [0.0, 0.0, 0])
            for r, p in zip(test, pred):
                f = fam[r["family"]]
                f[0] += r[t]
                f[1] += p
                f[2] += 1
            for a, p, n in fam.values():
                out[t][size_bucket(n)].append(a / p)
            out[t]["run"].append(sum(r[t] for r in test) / sum(pred))
        if run["elapsed"]:
            mins = {r["step"]: predict(r, model, "minutes") for r in test if r["step"]}
            sim = elapsed_minutes(run["definition"], mins)
            if sim:
                out["elapsed"].append(run["elapsed"] / sim)
    return out


OVERHEAD = ("plan", "extract", "report")     # the steps every run pays for, whatever it picks


def recipe_history(runs: list[dict], model: dict) -> dict:
    """Per recipe: the median cost and minutes of each family over its earlier runs, and of
    the plan, extract and report steps together, each run's figures moved to the baseline
    version by the fitted version offsets."""
    out: dict[str, dict] = {}
    by_recipe = collections.defaultdict(list)
    for run in runs:
        if run.get("recipe"):
            by_recipe[run["recipe"]].append(run)
    for recipe, rs in by_recipe.items():
        fams = collections.defaultdict(lambda: {t: [] for t in TARGETS})
        over = {t: [] for t in TARGETS}
        for run in rs:
            first = [r for r in run["rows"] if not r["rerun"]]
            if not first:
                continue
            sums = collections.defaultdict(lambda: dict.fromkeys(TARGETS, 0.0))
            for r in first:
                for t in TARGETS:
                    v = r[t] / math.exp(model["targets"][t]["coef"].get(f"version:{r['version']}", 0.0))
                    sums["" if r["kind"] in OVERHEAD else r["family"]][t] += v
            for fam, v in sums.items():
                for t in TARGETS:
                    (over if fam == "" else fams[fam])[t].append(v[t])
        out[recipe] = {
            "runs": len(rs),
            "families": {f: {**{t: round(quantile(v[t], .5), 3) for t in TARGETS}, "runs": len(v["cost_usd"])}
                         for f, v in fams.items()},
            "overhead": {t: round(quantile(over[t], .5), 3) for t in TARGETS} if over["cost_usd"] else None}
    return out


def pick_estimates(recipe: str | None, fams: list[dict], model: dict) -> dict:
    """Before the plan: each family's cost and minutes from the recipe's earlier runs, or,
    for a family none of them ran, from the model at its kind's typical features (one
    step). `fams` are recipe_format.families() entries."""
    hist = (model.get("history") or {}).get(recipe or "") or {}
    out = {}
    for f in fams:
        h = (hist.get("families") or {}).get(f["id"])
        if h:
            out[f["id"]] = {"cost_usd": h["cost_usd"], "minutes": h["minutes"], "source": "history"}
            continue
        kind = step_kind(f.get("kind") or "")
        row = {"kind": kind, **(model.get("typical") or {}).get(kind, dict.fromkeys(FEATURES, 0.0))}
        out[f["id"]] = {**{t: predict(row, model, t) for t in TARGETS}, "source": "model"}
    over = hist.get("overhead")
    if not over:
        over = {t: sum(predict({"kind": k, **model["typical"][k]}, model, t) for k in OVERHEAD
                       if k in model["typical"]) for t in TARGETS}
    return {"families": out, "overhead": over, "runs": hist.get("runs", 0),
            "rerun_share": model["rerun_share"]["mean"], "elapsed_per_work": model.get("elapsed_per_work", 1.0)}


def scope_total(est: dict, fams: list[dict], ids: list[str] | None) -> dict:
    """Cost and elapsed minutes of a run over `ids` (None: every family): the families,
    the plan, extract and report steps, and the expected re-runs. Elapsed is the
    families' minutes times the measured elapsed-per-work ratio, never shorter than the
    longest family, plus the plan, extract and report minutes."""
    ids = [f["id"] for f in fams] if ids is None else ids
    fe, over = est["families"], est["overhead"]
    cost = (sum(fe[i]["cost_usd"] for i in ids) + over["cost_usd"]) * (1 + est["rerun_share"])
    work = sum(fe[i]["minutes"] for i in ids)
    longest = max((fe[i]["minutes"] for i in ids), default=0.0)
    return {"cost_usd": cost,
            "elapsed_minutes": max(work * est["elapsed_per_work"], longest) + over["minutes"]}


def _range(ratios: list[float], fallback: list[float] | None = None) -> list[float]:
    """The 10th and 90th percentile of actual / predicted; the fallback below 20 ratios."""
    if len(ratios) < 20 and fallback or not ratios:
        return fallback or [1.0, 1.0]
    return [round(quantile(ratios, .1), 3), round(quantile(ratios, .9), 3)]


def cmd_fit(a) -> int:
    runs = training_runs(a.runs_root)
    first = [r for run in runs for r in run["rows"] if not r["rerun"]]
    if not first:
        print(f"{a.runs_root}: no priced efficacy runs found", file=sys.stderr)
        return 2
    model = fit_model(first)
    ho = holdout(runs)
    for t in TARGETS:
        m = model["targets"][t]
        m["coef"] = {k: round(v, 5) for k, v in m["coef"].items()}
        m["smear"], m["resid_sd"] = round(m["smear"], 5), round(m["resid_sd"], 4)
        r = ho[t]
        m["range"] = {"step": _range(r["step"]), "run": _range(r["run"])}
        m["range"]["family_1"] = _range(r["family_1"], m["range"]["step"])
        m["range"]["family_2_5"] = _range(r["family_2_5"], m["range"]["family_1"])
        m["range"]["family_6_plus"] = _range(r["family_6_plus"], m["range"]["run"])
        m["median_abs_error"] = {lvl: round(quantile([abs(x - 1) for x in v], .5), 3)
                                 for lvl, v in r.items() if v}
    el = ho["elapsed"]
    if el:
        factor = quantile(el, .5)
        model["elapsed"] = {"factor": round(factor, 3), "runs": len(el),
                            "range": [round(quantile(el, .1) / factor, 3), round(quantile(el, .9) / factor, 3)]}
    else:      # no lanes run to measure: the simulation stands as is, ranged like the run's minutes
        factor = 1.0
        model["elapsed"] = {"factor": 1.0, "runs": 0, "range": model["targets"]["minutes"]["range"]["run"]}
    shares = []
    for run in runs:
        fp = sum(r["cost_usd"] for r in run["rows"] if not r["rerun"])
        if fp:
            shares.append(sum(r["cost_usd"] for r in run["rows"] if r["rerun"]) / fp)
    model["rerun_share"] = {"mean": round(sum(shares) / len(shares), 4), "p90": round(quantile(shares, .9), 4)}
    model["history"] = recipe_history(runs, model)
    model["typical"] = {k: {f: round(quantile([r[f] for r in first if r["kind"] == k], .5), 4) for f in FEATURES}
                        for k in model["kinds"]}
    ratios = []
    for run in runs:
        work = sum(r["minutes"] for r in run["rows"] if not r["rerun"] and r["step"])
        if run["elapsed"] and work:
            ratios.append(run["elapsed"] / work)
    model["elapsed_per_work"] = round(quantile(ratios, .5), 3) if ratios else 1.0
    model = {"schema": SCHEMA, "fitted_at": datetime.date.today().isoformat(),
             "training": {"runs": len({r["run"] for r in first}), "steps": len(first),
                          "steps_by_version": dict(collections.Counter(r["version"] for r in first))},
             "features": list(FEATURES), **model}
    a.out.write_text(json.dumps(model, indent=1) + "\n", encoding="utf-8")
    e = model["targets"]["cost_usd"]["median_abs_error"]
    print(f"wrote {a.out}: {len(first)} steps of {model['training']['runs']} runs; median abs error "
          f"on cost, held out by run: step {e['step']:.0%}, run {e['run']:.0%}; elapsed factor "
          f"{factor:.2f} from {len(el)} lanes runs")
    return 0


# ------------------------------------------------------------------ estimate
def _with_range(x: float, r: list[float]) -> dict:
    return {"value": x, "low": x * r[0], "high": x * r[1]}


def estimate(definition: dict, model: dict) -> dict:
    """Predicted cost and minutes per step, summed per family, with the run's total and
    elapsed. Every figure carries the low and high of its measured range."""
    rc, rm = (model["targets"][t]["range"] for t in TARGETS)
    warm = warm_steps(definition)
    n_steps = len(definition["steps"])
    steps, fams = [], {}
    for s in definition["steps"]:
        row = {"kind": step_kind(s["check"]), **features(s, n_steps, s["id"] in warm)}
        fam = str((s.get("params") or {}).get("family") or row["kind"])
        steps.append({"id": s["id"], "family": fam, "kind": row["kind"], "warm": s["id"] in warm,
                      "known_kind": row["kind"] in model["kinds"],
                      **{t: predict(row, model, t) for t in TARGETS}})
        f = fams.setdefault(fam, {"family": fam, "steps": 0, "cost_usd": 0.0, "minutes": 0.0})
        f["steps"] += 1
        f["cost_usd"] += steps[-1]["cost_usd"]
        f["minutes"] += steps[-1]["minutes"]
    for f in fams.values():
        b = size_bucket(f["steps"])
        f["cost_usd"], f["minutes"] = _with_range(f["cost_usd"], rc[b]), _with_range(f["minutes"], rm[b])
    report = {t: predict({"kind": "report", **features(None, n_steps, False)}, model, t) for t in TARGETS}
    first_pass = sum(s["cost_usd"] for s in steps) + report["cost_usd"]
    share = model["rerun_share"]
    lanes_sim = elapsed_minutes(definition, {s["id"]: s["minutes"] for s in steps})
    el = model["elapsed"]
    return {"model_fitted_at": model["fitted_at"], "training": model["training"],
            "steps": steps, "families": list(fams.values()),
            "report": {"cost_usd": _with_range(report["cost_usd"], rc["step"]),
                       "minutes": _with_range(report["minutes"], rm["step"])},
            "reruns": {"cost_usd": {"value": first_pass * share["mean"], "low": 0.0,
                                    "high": first_pass * share["p90"]}},
            "run": {"steps": n_steps + 1, "lanes": len(lane_order(definition)),
                    "cost_usd": _with_range(first_pass * (1 + share["mean"]), rc["run"]),
                    "work_minutes": _with_range(sum(s["minutes"] for s in steps) + report["minutes"], rm["run"]),
                    "elapsed_minutes": _with_range(lanes_sim * el["factor"] + report["minutes"], el["range"])}}


def _usd(x: float) -> str:
    return f"${x:,.0f}"          # DOCTRINE § Number conventions: money in whole units


def _hm(m: float) -> str:
    m = round(m)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def _cell(v: dict, fmt) -> str:
    return f"{fmt(v['value'])} ({fmt(v['low'])} to {fmt(v['high'])})"


def render(e: dict) -> str:
    lines = ["| Family | Steps | Cost | Minutes of work |", "|---|---|---|---|"]
    for f in e["families"]:
        lines.append(f"| {f['family'].upper() if f['family'][1:].isdigit() else f['family'].capitalize()} "
                     f"| {f['steps']} | {_cell(f['cost_usd'], _usd)} | {_cell(f['minutes'], _hm)} |")
    lines.append(f"| Report | 1 | {_cell(e['report']['cost_usd'], _usd)} | {_cell(e['report']['minutes'], _hm)} |")
    lines.append(f"| Re-runs after review | | {_cell(e['reruns']['cost_usd'], _usd)} | |")
    run = e["run"]
    lines.append(f"| **Run** | {run['steps']} | **{_cell(run['cost_usd'], _usd)}** | {_cell(run['work_minutes'], _hm)} |")
    tr = e["training"]
    fitted = datetime.date.fromisoformat(e["model_fitted_at"])
    notes = [f"Elapsed after this plan: {_cell(run['elapsed_minutes'], _hm)}, with the steps over "
             f"{run['lanes']} lanes.",
             f"Costs are at list rates. Each range spans the 10th to 90th percentile of the "
             f"model's error when it predicted {tr['runs']:,} earlier runs ({tr['steps']:,} steps) "
             f"from fits that left each one out; the model was fitted on "
             f"{fitted:%B} {fitted.day}, {fitted.year}. The run's range is narrower than a "
             f"family's because step errors partly cancel in a sum."]
    unseen = sorted({s["kind"] for s in e["steps"] if not s["known_kind"]})
    if unseen:
        notes.append(f"No earlier run had a step of kind {', '.join(unseen)}; the model prices "
                     f"those steps at the average step.")
    return "\n".join(lines) + "\n\n" + "\n".join(notes) + "\n"


def cmd_estimate(a) -> int:
    model = json.loads(a.model.read_text(encoding="utf-8"))
    if model.get("schema") != SCHEMA:
        print(f"{a.model}: not a {SCHEMA} file", file=sys.stderr)
        return 2
    definition = json.loads(a.definition.read_text(encoding="utf-8"))
    e = estimate(definition, model)
    out = a.run_dir / "plan" / "spend-estimate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(e, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(e, indent=1) if a.json else render(e))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("estimate")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("definition", type=pathlib.Path)
    p.add_argument("--model", type=pathlib.Path, default=MODEL)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_estimate)
    p = sub.add_parser("fit")
    p.add_argument("runs_root", type=pathlib.Path)
    p.add_argument("--out", type=pathlib.Path, default=MODEL)
    p.set_defaults(fn=cmd_fit)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
