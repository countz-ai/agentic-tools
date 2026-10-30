#!/usr/bin/env python3
"""Write the run's cost report, `out/cost.html`: what each step cost and took, by lane,
against the plan's estimate.

    cost_report.py <run_dir> [--rates <path>] [--json]

`preview.py` runs it when the report deck seals and puts the page in the working bundle,
so the user can open it and the deck stays the card on screen. `--json` prints the
figures the page is drawn from and writes nothing.

Every API response in the run's transcripts is priced once, as `usage_report.py` prices
it (one count per `message.id`, `reference/rates.json`), and given to one step:

- A worker's response goes to the dispatch whose brief (`dispatch/NNNN-<step>.md`) the
  worker was last handed. A lane's worker is handed many briefs, one per step it runs.
- A forked step's sub-agent (plan, review, report) is handed no brief path. Its responses
  go to the unbriefed step whose window overlaps the sub-agent's activity most.
- The main session's responses are the relay's.

A step's first dispatch for its check is its first pass; a later one is a re-run (a
review fix, a report gate, a retry). The plan's estimate (`plan/spend-estimate.json`)
prices each step's first pass, the report and the re-runs; it does not price the plan
or the relay. Elapsed is from plan approval to the last step's end, the span the
estimate covers. The page is self-contained: no script or style is fetched. Stdlib only.
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
from datetime import datetime, timezone

import usage_report

RATES = pathlib.Path(__file__).resolve().parent.parent / "reference" / "rates.json"
BRIEF = re.compile(r"dispatch/(\d{4})-")
FORKED = {"plan": "Plan", "review": "Review", "report": "Report"}


def _ts(s: str | None) -> datetime | None:
    return usage_report._iso(s)


def read(path: pathlib.Path) -> tuple[list[tuple[datetime, str, dict]], list[tuple[datetime, int]]]:
    """The transcript's API responses, (time, model, usage) once per message id with the
    last record's usage, and the briefs it was handed, (time, seq), from user text."""
    by_id: dict[str, list] = {}
    briefs: list[tuple[datetime, int]] = []
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _ts(rec.get("timestamp"))
            msg = rec.get("message") or {}
            if rec.get("type") == "assistant" and msg.get("usage") and ts:
                key = msg.get("id") or rec.get("requestId") or rec.get("uuid") or f"line{n}"
                first = by_id[key][0] if key in by_id else ts
                by_id[key] = [first, msg.get("model") or "unknown", msg["usage"]]
            elif rec.get("type") == "user" and ts:
                c = msg.get("content")
                text = c if isinstance(c, str) else " ".join(
                    b.get("text", "") for b in c or [] if isinstance(b, dict) and b.get("type") == "text")
                m = BRIEF.search(text)
                if m:
                    briefs.append((ts, int(m.group(1))))
    return sorted((tuple(v) for v in by_id.values()), key=lambda r: r[0]), briefs


def price(model: str, usage: dict, rates: dict) -> tuple[float | None, int]:
    acc = usage_report._blank()
    usage_report._add(acc, usage)
    return usage_report.cost_of(model, acc, rates), acc["output_tokens"]


def steps_of(run_dir: pathlib.Path, run: dict) -> dict[int, dict]:
    """seq -> the dispatch with its window, from events.jsonl and the step records."""
    out: dict[int, dict] = {}
    for d in run.get("dispatches") or []:
        out[d["seq"]] = {"seq": d["seq"], "step": d.get("step"), "check": d.get("check_id"),
                         "start": None, "end": None}
    ev = run_dir / "events.jsonl"
    for line in ev.read_text(encoding="utf-8").splitlines() if ev.is_file() else []:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        s = out.get(e.get("seq")) if e.get("event") in ("step_start", "step_end") else None
        if s is not None:
            s["start" if e["event"] == "step_start" else "end"] = _ts(e.get("ts"))
    for s in out.values():
        if s["start"] is None or s["end"] is None:
            rec = next((run_dir / "steps").glob(f"{s['seq']:04d}-*.json"), None)
            try:
                r = json.loads(rec.read_text(encoding="utf-8")) if rec else {}
            except (OSError, json.JSONDecodeError):
                r = {}
            s["start"] = s["start"] or _ts(r.get("started_at"))
            s["end"] = s["end"] or _ts(r.get("completed_at"))
    return out


def lanes_of(run_dir: pathlib.Path) -> dict[str, str]:
    """Sub-agent id -> `Lane <n>`, for every holder lanes.json recorded, retired ones too."""
    f = run_dir / "lanes.json"
    try:
        st = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except json.JSONDecodeError:
        st = {}
    held = [{"lane": k, **h} for k, h in (st.get("holders") or {}).items()] + list(st.get("retired") or [])
    return {h["agent"]: f"Lane {h['lane']}" for h in held if h.get("agent")}


def collect(run_dir: pathlib.Path, rates: dict) -> dict:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    steps = steps_of(run_dir, run)
    lane_of = lanes_of(run_dir)
    for s in steps.values():
        s.update(cost=0.0, responses=0, output_tokens=0, by_agent={})
    relay = {"cost": 0.0, "responses": 0, "output_tokens": 0}
    loose = {"cost": 0.0, "responses": 0, "output_tokens": 0}
    unpriced: set[str] = set()

    def add(acc: dict, model: str, usage: dict, who: str | None = None) -> None:
        c, out = price(model, usage, rates)
        if c is None:
            unpriced.add(model)
        acc["cost"] += c or 0.0
        acc["responses"] += 1
        acc["output_tokens"] += out
        if who is not None:
            acc["by_agent"][who] = acc["by_agent"].get(who, 0.0) + (c or 0.0)

    forks = []
    for sid in [s["session_id"] for s in (run.get("inputs") or {}).get("sessions") or []]:
        for label, path, _meta in usage_report.transcripts_for(
                sid, fallback_root=run_dir / "debug" / "transcripts"):
            resp, briefs = read(path)
            if label == "session":
                for _, model, usage in resp:
                    add(relay, model, usage)
                continue
            agent = path.stem.removeprefix("agent-")
            briefs = [b for b in briefs if b[1] in steps]
            if not briefs:
                forks.append((agent, resp))
                continue
            for ts, model, usage in resp:
                seq = next((q for t, q in reversed(briefs) if t <= ts), briefs[0][1])
                add(steps[seq], model, usage, agent)

    briefed = {s["seq"] for s in steps.values() if s["by_agent"]}
    for agent, resp in forks:
        if not resp:
            continue
        a, b = resp[0][0], resp[-1][0]

        def fit(s: dict) -> tuple:
            if s["start"] is None or s["end"] is None:
                return (0.0, float("-inf"))
            overlap = (min(b, s["end"]) - max(a, s["start"])).total_seconds()
            return (max(overlap, 0.0), -abs((s["start"] - a).total_seconds()))

        open_ = [s for s in steps.values() if s["seq"] not in briefed]
        best = max(open_, key=fit, default=None)
        for _, model, usage in resp:
            if best is None:
                add(loose, model, usage)
            else:
                add(best, model, usage, agent)

    est = {}
    ef = run_dir / "plan" / "spend-estimate.json"
    try:
        est = json.loads(ef.read_text(encoding="utf-8")) if ef.is_file() else {}
    except json.JSONDecodeError:
        pass
    est_step = {s["id"]: s for s in est.get("steps") or []}

    rows, seen = [], set()
    for s in sorted(steps.values(), key=lambda s: s["seq"]):
        key = (s["step"], s["check"])
        first = key not in seen
        seen.add(key)
        top = max(s["by_agent"], key=s["by_agent"].get) if s["by_agent"] else None
        lane = lane_of.get(top) or FORKED.get(s["step"]) or ("Worker" if top else "—")
        e = None
        if first and s["check"] in est_step:
            e = est_step[s["check"]]
            e = {"cost": e.get("cost_usd"), "minutes": e.get("minutes")}
        elif first and s["step"] == "report" and est.get("report"):
            e = {"cost": est["report"]["cost_usd"]["value"], "minutes": est["report"]["minutes"]["value"]}
        rows.append({
            "seq": s["seq"], "step": s["step"], "check": s["check"],
            "name": s["check"] or s["step"], "lane": lane,
            "pass": "First pass" if first else "Re-run",
            "start": s["start"].isoformat() if s["start"] else None,
            "end": s["end"].isoformat() if s["end"] else None,
            "minutes": (s["end"] - s["start"]).total_seconds() / 60 if s["start"] and s["end"] else None,
            "cost": s["cost"], "responses": s["responses"], "output_tokens": s["output_tokens"],
            "est_cost": e and e["cost"], "est_minutes": e and e["minutes"]})

    total = sum(r["cost"] for r in rows) + relay["cost"] + loose["cost"]
    plan = [r for r in rows if r["step"] == "plan"]
    after = [r for r in rows if r["step"] != "plan"]
    approved = next((_ts(json.loads(line).get("ts")) for line in
                     (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
                     if '"plan_approved"' in line), None) if (run_dir / "events.jsonl").is_file() else None
    starts = [_ts(r["start"]) for r in after if r["start"]]
    ends = [_ts(r["end"]) for r in after if r["end"]]
    t0 = approved or (min(starts) if starts else None)
    run_est = est.get("run") or {}
    est_elapsed = None
    if run_est.get("elapsed_minutes"):
        est_elapsed = run_est["elapsed_minutes"]["value"] + ((est.get("report") or {}).get("minutes") or {}).get("value", 0)
    reruns = [r for r in rows if r["pass"] == "Re-run"]
    priced = [r for r in rows if r["step"] != "plan"]
    lanes: dict[str, dict] = {}
    for r in rows:
        ln = lanes.setdefault(r["lane"], {"lane": r["lane"], "steps": 0, "first": 0.0, "rerun": 0.0})
        ln["steps"] += 1
        ln["first" if r["pass"] == "First pass" else "rerun"] += r["cost"]
    lanes["Relay"] = {"lane": "Relay", "steps": 0, "first": relay["cost"], "rerun": 0.0}
    top = max(after or rows, key=lambda r: r["cost"], default=None)
    return {
        "run_id": run.get("run_id"), "goal": run.get("goal"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rates_captured_at": rates.get("captured_at"),
        "unpriced_models": sorted(unpriced),
        "steps": rows, "lanes": list(lanes.values()), "relay": relay, "unattributed": loose,
        "total_cost": total,
        "plan_cost": sum(r["cost"] for r in plan),
        "priced_cost": sum(r["cost"] for r in priced),
        "est_cost": (run_est.get("cost_usd") or {}).get("value"),
        "est_low": (run_est.get("cost_usd") or {}).get("low"),
        "est_high": (run_est.get("cost_usd") or {}).get("high"),
        "elapsed_minutes": (max(ends) - t0).total_seconds() / 60 if t0 and ends else None,
        "est_elapsed_minutes": est_elapsed,
        "rerun_cost": sum(r["cost"] for r in reruns), "rerun_count": len(reruns),
        "est_rerun_cost": ((est.get("reruns") or {}).get("cost_usd") or {}).get("value"),
        "top": top,
    }


# ------------------------------------------------------------------ the page
def _usd(x: float | None) -> str:
    return "—" if x is None else f"${x:,.2f}"


def _dur(m: float | None) -> str:
    if m is None:
        return "—"
    return f"{m / 60:.1f} h" if m >= 60 else f"{m:.0f} min"


def _e(s) -> str:
    return html.escape(str(s), quote=True)


CSS = """
:root { --bg:#fbfaf7; --panel:#ffffff; --fg:#1f1e1c; --muted:#6b6862; --line:#e4e1da;
  --first:#3f6fb5; --rerun:#d08a2e; --bad:#c2453a; --est:#1f1e1c; --relay:#b9b5ac; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#1b1a18; --panel:#24231f; --fg:#ecebe6; --muted:#a19d94; --line:#3a3833;
  --first:#79a3e0; --rerun:#e3a456; --bad:#e2766b; --est:#ecebe6; --relay:#5e5b55; } }
:root[data-theme="dark"] { --bg:#1b1a18; --panel:#24231f; --fg:#ecebe6; --muted:#a19d94;
  --line:#3a3833; --first:#79a3e0; --rerun:#e3a456; --bad:#e2766b; --est:#ecebe6; --relay:#5e5b55; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font:15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width:1100px; margin:0 auto; padding:24px 16px 48px; display:flex; flex-direction:column; gap:20px; }
h1 { font:400 28px/1.2 Georgia, "Times New Roman", serif; margin:0; }
h2 { font-size:16px; font-weight:600; margin:0; }
.lede { margin:0; max-width:75ch; }
.lede b, .big, td.num { font-variant-numeric:tabular-nums; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 12rem), 1fr)); gap:12px; }
.tile, .card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; min-width:0; }
.card { display:flex; flex-direction:column; gap:8px; }
.lbl, .sub, .note, .legend { font-size:13px; color:var(--muted); }
.big { font:400 28px/1.2 Georgia, "Times New Roman", serif; margin:4px 0; }
.bad { color:var(--bad); }
.note { margin:0; max-width:85ch; }
.legend { display:flex; flex-wrap:wrap; gap:14px; align-items:center; }
.sw { display:inline-block; width:11px; height:11px; border-radius:2px; margin-right:5px; vertical-align:-1px; }
svg { width:100%; height:auto; display:block; }
svg text { font-size:12px; fill:var(--muted); }
svg text.strong { fill:var(--fg); }
.box { overflow:auto; max-height:36rem; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { position:sticky; top:0; background:var(--panel); text-align:left; color:var(--muted); font-weight:600;
  border-bottom:1px solid var(--line); padding:6px 8px; cursor:pointer; white-space:nowrap; }
td { padding:6px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }
th.num, td.num { text-align:right; }
footer { font-size:12px; color:var(--muted); max-width:85ch; }
"""

SORT = """
document.querySelectorAll('table.sortable').forEach(function (t) {
  t.querySelectorAll('th').forEach(function (th, i) {
    th.addEventListener('click', function () {
      var dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
      t.querySelectorAll('th').forEach(function (h) { delete h.dataset.dir; });
      th.dataset.dir = dir;
      var body = t.tBodies[0];
      Array.from(body.rows).sort(function (a, b) {
        var x = a.cells[i].dataset.v, y = b.cells[i].dataset.v;
        var nx = parseFloat(x), ny = parseFloat(y);
        var c = (!isNaN(nx) && !isNaN(ny)) ? nx - ny : String(x).localeCompare(String(y));
        return dir === 'asc' ? c : -c;
      }).forEach(function (r) { body.appendChild(r); });
    });
  });
});
"""

W = 960


def _bar_chart(items: list[tuple[str, list[tuple[float, str]], str, str]], mark=None) -> str:
    """Horizontal bars: (label, [(value, colour var)...] stacked, end text, tooltip).
    `mark` gives each row an estimate tick: list of float|None aligned to items."""
    if not items:
        return '<p class="note">Nothing to draw.</p>'
    row, left, right = 30, 230, 90
    top = max([sum(v for v, _ in segs) for _, segs, _, _ in items]
              + [m for m in (mark or []) if m] + [1e-9])
    x = lambda v: left + v / top * (W - left - right)
    h = len(items) * row + 6
    out = [f'<svg viewBox="0 0 {W} {h}" role="img">']
    for i, (label, segs, end, tip) in enumerate(items):
        y = 4 + i * row
        short = label if len(label) <= 32 else label[:31] + "…"
        out.append(f'<g><title>{_e(tip)}</title>'
                   f'<rect x="0" y="{y}" width="{W}" height="{row}" fill="transparent"/>'
                   f'<text class="strong" x="{left - 10}" y="{y + row / 2 + 4}" text-anchor="end">{_e(short)}</text>')
        at = 0.0
        for v, colour in segs:
            if v > 0:
                out.append(f'<rect x="{x(at):.1f}" y="{y + 7}" width="{max(x(at + v) - x(at), 1):.1f}" '
                           f'height="{row - 14}" rx="2" fill="var({colour})"/>')
            at += v
        m = (mark or [None] * len(items))[i]
        if m:
            out.append(f'<line x1="{x(m):.1f}" x2="{x(m):.1f}" y1="{y + 3}" y2="{y + row - 3}" '
                       f'stroke="var(--est)" stroke-width="2"/>')
        out.append(f'<text x="{max(x(at), x(m or 0)) + 6:.1f}" y="{y + row / 2 + 4}">{_e(end)}</text></g>')
    out.append("</svg>")
    return "".join(out)


def _timeline(rows: list[dict], tz) -> str:
    spans = [(r, _ts(r["start"]), _ts(r["end"])) for r in rows if r["start"] and r["end"]]
    if not spans:
        return '<p class="note">The run recorded no step times.</p>'
    order = ["Plan"] + sorted({r["lane"] for r, _, _ in spans} - set(FORKED.values()) - {"Worker", "—"}) \
        + ["Worker", "Review", "Report", "—"]
    lanes = [ln for ln in order if any(r["lane"] == ln for r, _, _ in spans)]
    t0, t1 = min(a for _, a, _ in spans), max(b for _, _, b in spans)
    span = max((t1 - t0).total_seconds(), 1)
    row, left, right, axis = 32, 90, 12, 26
    x = lambda t: left + (t - t0).total_seconds() / span * (W - left - right)
    h = len(lanes) * row + axis + 6
    out = [f'<svg viewBox="0 0 {W} {h}" role="img">']
    hours = span / 3600
    step = next(s for s in (0.25, 0.5, 1, 2, 3, 4, 6, 12, 24, 48) if hours / s <= 10)
    tick = t0.replace(minute=0, second=0, microsecond=0)
    while tick <= t1:
        if tick >= t0:
            out.append(f'<line x1="{x(tick):.1f}" x2="{x(tick):.1f}" y1="4" y2="{len(lanes) * row + 4}" '
                       f'stroke="var(--line)"/><text x="{x(tick):.1f}" y="{h - 8}" text-anchor="middle">'
                       f'{_e(tick.astimezone(tz).strftime("%H:%M"))}</text>')
        tick = datetime.fromtimestamp(tick.timestamp() + step * 3600, tz=timezone.utc)
    for i, ln in enumerate(lanes):
        out.append(f'<text class="strong" x="{left - 10}" y="{4 + i * row + row / 2 + 4}" '
                   f'text-anchor="end">{_e(ln)}</text>')
    for r, a, b in spans:
        y = 4 + lanes.index(r["lane"]) * row
        colour = "--first" if r["pass"] == "First pass" else "--rerun"
        tip = (f"#{r['seq']} {r['name']} ({r['lane']}, {r['pass'].lower()})\n"
               f"{a.astimezone(tz):%H:%M} to {b.astimezone(tz):%H:%M}, {_dur(r['minutes'])}, {_usd(r['cost'])}")
        out.append(f'<g><title>{_e(tip)}</title><rect x="{x(a):.1f}" y="{y + 6}" '
                   f'width="{max(x(b) - x(a), 2):.1f}" height="{row - 12}" rx="2" fill="var({colour})" '
                   f'stroke="var(--panel)"/></g>')
    out.append("</svg>")
    return "".join(out)


def render(rep: dict) -> str:
    tz = datetime.now().astimezone().tzinfo
    rows, top = rep["steps"], rep["top"]
    total = rep["total_cost"]
    mult = rep["priced_cost"] / rep["est_cost"] if rep["est_cost"] else None
    est_line = (f"{mult:.1f}× the plan's estimate of {_usd(rep['est_cost'])}" if mult else
                "no plan estimate was recorded")
    lede = (f"This run cost <b>{_usd(total)}</b> over <b>{_dur(rep['elapsed_minutes'])}</b> from plan "
            f"approval to the last step. The steps the plan priced cost {est_line}.")
    if top and total:
        lede += (f" The costliest step, <b>{_e(top['name'])}</b>, cost <b>{_usd(top['cost'])}</b>, "
                 f"{top['cost'] / total:.0%} of the total.")
    if not rep["relay"]["responses"] and not any(r["responses"] for r in rows):
        lede = ("No session transcript of this run was found on this machine, so its cost "
                "cannot be stated. The step times below come from the run's own records.")
    elif rep["rerun_count"]:
        lede += (f" {rep['rerun_count']} re-run{'s' if rep['rerun_count'] != 1 else ''} after the "
                 f"review and the report's gates cost <b>{_usd(rep['rerun_cost'])}</b>.")

    over = bool(mult and rep["est_high"] and rep["priced_cost"] > rep["est_high"])
    top_over = bool(top and top.get("est_cost") and top["cost"] > 2 * top["est_cost"])
    tiles = [
        ("Total spend", _usd(total), f"Relay {_usd(rep['relay']['cost'])} · plan {_usd(rep['plan_cost'])}", False),
        ("Elapsed, plan approval to last step", _dur(rep["elapsed_minutes"]),
         f"Estimate {_dur(rep['est_elapsed_minutes'])}", False),
        ("Against the plan's estimate", f"{mult:.1f}×" if mult else "—",
         f"{_usd(rep['priced_cost'])} actual · estimate {_usd(rep['est_cost'])} "
         f"({_usd(rep['est_low'])} to {_usd(rep['est_high'])})", over),
        ("Costliest step", _usd(top["cost"]) if top else "—",
         (f"{top['name']} · {_dur(top['minutes'])} · estimate {_usd(top.get('est_cost'))}" if top else ""),
         top_over),
        ("Re-runs", _usd(rep["rerun_cost"]),
         f"{rep['rerun_count']} re-run{'s' if rep['rerun_count'] != 1 else ''} · estimate "
         f"{_usd(rep['est_rerun_cost'])}", False),
    ]
    tile_html = "".join(
        f'<div class="tile"><div class="lbl">{_e(a)}</div><div class="big{" bad" if bad else ""}">{_e(b)}</div>'
        f'<div class="sub">{_e(c)}</div></div>' for a, b, c, bad in tiles)

    lane_items = [(ln["lane"], [(ln["first"], "--first" if ln["lane"] != "Relay" else "--relay"),
                                (ln["rerun"], "--rerun")],
                   _usd(ln["first"] + ln["rerun"]),
                   f"{ln['lane']}: first pass {_usd(ln['first'])}, re-runs {_usd(ln['rerun'])}")
                  for ln in sorted(rep["lanes"], key=lambda l: -(l["first"] + l["rerun"]))]
    firsts = [r for r in rows if r["pass"] == "First pass" and r["est_cost"]]
    vs_items = [(f"#{r['seq']} {r['name']}",
                 [(r["cost"], "--bad" if r["cost"] > 2 * r["est_cost"] else "--first")],
                 _usd(r["cost"]),
                 f"{r['name']}: actual {_usd(r['cost'])}, estimate {_usd(r['est_cost'])}; "
                 f"{_dur(r['minutes'])}, estimate {_dur(r['est_minutes'])}") for r in firsts]

    def cell(v, shown, num=False):
        return f'<td{" class=num" if num else ""} data-v="{_e(v)}">{_e(shown)}</td>'

    body = "".join(
        "<tr>" + cell(r["seq"], r["seq"], True) + cell(r["lane"], r["lane"]) + cell(r["name"], r["name"])
        + cell(r["step"], r["step"]) + cell(r["pass"], r["pass"])
        + cell(r["minutes"] or 0, f"{r['minutes']:.1f}" if r["minutes"] is not None else "—", True)
        + cell(r["cost"], _usd(r["cost"]), True)
        + cell(r["est_cost"] if r["est_cost"] is not None else -1, _usd(r["est_cost"]) if r["est_cost"] else "", True)
        + cell(r["responses"], f"{r['responses']:,}", True)
        + cell(r["output_tokens"], f"{r['output_tokens']:,}", True) + "</tr>" for r in rows)
    if rep["relay"]["responses"]:
        body += ("<tr>" + cell(9999, "—", True) + cell("Relay", "Relay") + cell("relay", "the main session")
                 + cell("relay", "relay") + cell("", "") + cell(0, "—", True)
                 + cell(rep["relay"]["cost"], _usd(rep["relay"]["cost"]), True) + cell(-1, "", True)
                 + cell(rep["relay"]["responses"], f"{rep['relay']['responses']:,}", True)
                 + cell(rep["relay"]["output_tokens"], f"{rep['relay']['output_tokens']:,}", True) + "</tr>")
    if rep["unattributed"]["responses"]:
        u = rep["unattributed"]
        body += ("<tr>" + cell(9999, "—", True) + cell("—", "—") + cell("unattributed", "not matched to a step")
                 + cell("", "") + cell("", "") + cell(0, "—", True) + cell(u["cost"], _usd(u["cost"]), True)
                 + cell(-1, "", True) + cell(u["responses"], f"{u['responses']:,}", True)
                 + cell(u["output_tokens"], f"{u['output_tokens']:,}", True) + "</tr>")

    unpriced = (f" Not priced, tokens counted only: {', '.join(rep['unpriced_models'])}."
                if rep["unpriced_models"] else "")
    tzname = datetime.now().astimezone().tzname()
    sw = lambda v, label: f'<span><i class="sw" style="background:var({v})"></i>{_e(label)}</span>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Run cost report</title><style>{CSS}</style></head>
<body><main>
<header><h1>What this run cost</h1>
<p class="note">{_e(rep['run_id'])} · {_e(rep['goal'] or '')}</p></header>
<p class="lede">{lede}</p>
<section class="tiles">{tile_html}</section>
<section class="card"><h2>When each lane was working</h2>
<p class="note">Each bar is one step, from its start to its end, in {_e(tzname)}. A lane is one worker that keeps its context from step to step. The relay, the main session, runs throughout and is not drawn. Hover a bar for its time and cost.</p>
<div class="legend">{sw('--first', 'First pass')}{sw('--rerun', 'Re-run')}</div>
{_timeline(rows, tz)}</section>
<section class="card"><h2>Spend by lane</h2>
<p class="note">The relay is the main session that dispatched every step.</p>
<div class="legend">{sw('--first', 'First pass')}{sw('--rerun', 'Re-runs')}{sw('--relay', 'Relay')}</div>
{_bar_chart(lane_items)}</section>
<section class="card"><h2>First pass against the plan's estimate</h2>
<p class="note">Each bar is a step's first pass; the mark is the plan's estimate for it. A bar more than twice its estimate is red.</p>
<div class="legend">{sw('--first', 'Actual')}{sw('--bad', 'Over twice the estimate')}<span><i class="sw" style="background:var(--est);width:2px"></i>Estimate</span></div>
{_bar_chart(vs_items, [r['est_cost'] for r in firsts])}</section>
<section class="card"><h2>Every step</h2>
<p class="note">Cost is each step's own model usage. Click a column to sort.</p>
<div class="box"><table class="sortable"><thead><tr>
<th class="num">#</th><th>Lane</th><th>Check</th><th>Step</th><th>Pass</th><th class="num">Minutes</th>
<th class="num">Cost</th><th class="num">Estimate</th><th class="num">Responses</th><th class="num">Output tokens</th>
</tr></thead><tbody>{body}</tbody></table></div></section>
<footer>Tokens are counted once per API response from the session transcripts. Dollars are computed at standard list rates captured {_e(rep['rates_captured_at'])}, so they do not reflect promotional pricing or contracted discounts and may differ from your bill; your provider's usage console is the authority.{_e(unpriced)} Generated {_e(rep['generated_at'])}.</footer>
</main><script>{SORT}</script></body></html>
"""


def write(run_dir: pathlib.Path, rates_path: pathlib.Path = RATES) -> pathlib.Path:
    """Write out/cost.html and return its path."""
    rep = collect(run_dir, json.loads(rates_path.read_text(encoding="utf-8")))
    out = run_dir / "out" / "cost.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(render(rep), encoding="utf-8")
    tmp.replace(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", type=pathlib.Path)
    ap.add_argument("--rates", type=pathlib.Path, default=RATES)
    ap.add_argument("--json", action="store_true", help="print the figures; write nothing")
    a = ap.parse_args()
    if not (a.run_dir / "run.json").is_file():
        print(f"{a.run_dir}: no run.json, not a countz run directory", file=sys.stderr)
        return 2
    if a.json:
        rep = collect(a.run_dir, json.loads(a.rates.read_text(encoding="utf-8")))
        print(json.dumps(rep, indent=2, default=str))
    else:
        print(write(a.run_dir, a.rates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
