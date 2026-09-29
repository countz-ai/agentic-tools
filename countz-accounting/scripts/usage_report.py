#!/usr/bin/env python3
"""What a run spent: wall-clock, tokens, and an estimated dollar cost.

Reads the session transcripts Claude Code writes under ~/.claude/projects/ and the run's
own `events.jsonl`, and reports per-dispatch and per-model totals.

Two properties this exists to hold:

  Tokens are MEASURED, but only after deduplication. The transcript writes one record per
  CONTENT BLOCK, not per API response - a response with a thinking block and two tool calls
  becomes three records, each carrying an identical copy of that response's usage. Summing
  records naively inflates every total by the blocks-per-response ratio (measured: 1.83x on
  one real transcript, 2.12x on another, and the ratio varies by step, so even proportions
  are not safe). Usage is therefore counted ONCE per `message.id`, and the report carries
  both `records` and `responses` per dispatch so the deduplication is itself visible.

  Dollars are DERIVED. The transcript carries no cost figure (verified: 0 of 189
  transcripts on the authoring machine carried one), so cost is computed here from
  reference/rates.json using the CLI's own formula. It is an estimate, it is only as
  current as that file's `captured_at`, and a model absent from the table has its tokens
  reported and its cost withheld rather than priced at a neighbour's rate.

Usage:
    usage_report.py <run_dir> [--json] [--rates <path>]

Runs standalone against a finished or abandoned run - it writes nothing into the run dir.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

TOKEN_FIELDS = ("input_tokens", "output_tokens",
                "cache_creation_input_tokens", "cache_read_input_tokens")


def _iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _blank() -> dict:
    d = {k: 0 for k in TOKEN_FIELDS}
    d.update(thinking_tokens=0, cache_write_1h=0, cache_write_5m=0,
             web_search_requests=0, messages=0)
    return d


def _add(acc: dict, usage: dict) -> None:
    for k in TOKEN_FIELDS:
        acc[k] += usage.get(k) or 0
    acc["thinking_tokens"] += (usage.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0
    cc = usage.get("cache_creation") or {}
    acc["cache_write_1h"] += cc.get("ephemeral_1h_input_tokens", 0) or 0
    acc["cache_write_5m"] += cc.get("ephemeral_5m_input_tokens", 0) or 0
    acc["web_search_requests"] += (usage.get("server_tool_use") or {}).get("web_search_requests", 0) or 0
    acc["messages"] += 1


def read_transcript(path: pathlib.Path) -> tuple[dict[str, dict], datetime | None, datetime | None, int]:
    """Per-model token totals (one count per API RESPONSE), first/last timestamps, raw record count.

    The transcript writes one record per content block; every record of a response repeats
    that response's full `usage`. Records are therefore keyed by `message.id` (falling back
    to `requestId`, then the record's own uuid so an id-less record is never dropped), and
    the LAST record per id wins. Measured on real transcripts, duplicates take two shapes:
    identical copies (main-session files), and PROGRESSIVE usage that grows across a
    response's records (subagent files - 88 of 99 multi-record responses in one file
    differed, and the last record was the componentwise max in all 88). Last-wins is correct
    for both; first-wins would undercount the progressive shape.
    """
    by_id: dict[str, tuple[str, dict]] = {}
    first = last = None
    records = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue                      # a truncated tail is normal on a live file
            if rec.get("type") != "assistant":
                continue
            msg = rec.get("message") or {}
            usage = msg.get("usage")
            if not usage:
                continue
            records += 1
            key = msg.get("id") or rec.get("requestId") or rec.get("uuid") or f"line{records}"
            by_id[key] = (msg.get("model") or "unknown", usage)
            ts = _iso(rec.get("timestamp"))
            if ts:
                first = ts if first is None or ts < first else first
                last = ts if last is None or ts > last else last
    by_model: dict[str, dict] = {}
    for model, usage in by_id.values():
        _add(by_model.setdefault(model, _blank()), usage)
    return by_model, first, last, records


def cost_of(model: str, acc: dict, rates: dict) -> float | None:
    """The CLI's own arithmetic. None when the model is not in the table."""
    tier = rates["models"].get(model)
    r = rates["tiers"].get(tier) if tier else None
    if r is None:
        return None
    # The 1h-cache portion is priced at the 1h rate; the remainder at the 5m rate. Cache
    # creation is the authority on the total - the ephemeral split is a breakdown of it.
    total_write = acc["cache_creation_input_tokens"]
    at_1h = min(acc["cache_write_1h"], total_write)
    return (acc["input_tokens"] / 1e6 * r["input"]
            + acc["output_tokens"] / 1e6 * r["output"]
            + acc["cache_read_input_tokens"] / 1e6 * r["cache_read"]
            + at_1h / 1e6 * r["cache_write_1h"]
            + (total_write - at_1h) / 1e6 * r["cache_write_5m"]
            + acc["web_search_requests"] * r["web_search"])


def transcripts_for(session_id: str,
                    fallback_root: pathlib.Path | None = None
                    ) -> list[tuple[str, pathlib.Path, dict]]:
    """(label, path, meta) for the session and every subagent it spawned.

    Looks under ~/.claude/projects/, where Claude Code writes on the machine that ran
    the session. When nothing is there and a fallback root is given, reads the copies
    scripts/gather_debug.py gathered into the run (same <sid>.jsonl + <sid>/subagents/
    layout), so a synced run stays priceable off its own directory.
    """
    root = pathlib.Path.home() / ".claude" / "projects"
    mains = sorted(root.glob(f"*/{session_id}.jsonl"))
    if not mains and fallback_root is not None:
        cand = fallback_root / f"{session_id}.jsonl"
        mains = [cand] if cand.is_file() else []
    out: list[tuple[str, pathlib.Path, dict]] = []
    for main in mains:
        out.append(("session", main, {}))
        for sub in sorted((main.parent / session_id / "subagents").glob("agent-*.jsonl")):
            meta_path = sub.with_suffix(".meta.json")
            meta = {}
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            out.append((meta.get("agentType") or sub.stem, sub, meta))
    return out


def collect(run_dir: pathlib.Path, rates: dict) -> dict:
    state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    session_ids = [s["session_id"] for s in state.get("inputs", {}).get("sessions", [])]

    dispatch_rows, totals, unpriced = [], {}, set()
    if not session_ids:   # run_id names the directory, never a session - nothing to look up
        dispatch_rows.append({"label": "no session", "note": "run.json records no session "
                              "id - the run was registered without --session"})
    for sid in session_ids:
        found = transcripts_for(sid, fallback_root=run_dir / "debug" / "transcripts")
        if not found:
            dispatch_rows.append({"label": f"session {sid}", "note": "no transcript found on this machine"})
        for label, path, meta in found:
            by_model, first, last, records = read_transcript(path)
            if not by_model:
                continue
            responses = sum(m["messages"] for m in by_model.values())
            row = {"label": label, "session_id": sid, "transcript": str(path),
                   "records": records, "responses": responses,
                   "description": meta.get("description"), "spawn_depth": meta.get("spawnDepth"),
                   "tool_use_id": meta.get("toolUseId"),
                   "first_at": first.isoformat() if first else None,
                   "last_at": last.isoformat() if last else None,
                   "elapsed_s": (last - first).total_seconds() if first and last else None,
                   "models": {}, "cost_usd": 0.0, "cost_complete": True}
            for model, acc in by_model.items():
                if not any(acc[k] for k in TOKEN_FIELDS):
                    continue      # a pseudo-model with no tokens cannot affect a cost
                c = cost_of(model, acc, rates)
                row["models"][model] = {**acc, "cost_usd": c}
                if c is None:
                    row["cost_complete"] = False
                    unpriced.add(model)
                else:
                    row["cost_usd"] += c
                tot = totals.setdefault(model, _blank())
                for k in tot:
                    tot[k] += acc[k]
            dispatch_rows.append(row)

    grand, complete = 0.0, True
    for model, acc in totals.items():
        c = cost_of(model, acc, rates)
        acc["cost_usd"] = c
        if c is None:
            complete = False
        else:
            grand += c

    starts = [_iso(r.get("first_at")) for r in dispatch_rows if r.get("first_at")]
    ends = [_iso(r.get("last_at")) for r in dispatch_rows if r.get("last_at")]

    # Union of the dispatch intervals: merge overlaps, then total. Bounded above by elapsed.
    spans = sorted((_iso(r["first_at"]), _iso(r["last_at"])) for r in dispatch_rows
                   if r.get("first_at") and r.get("last_at") and r.get("label") != "session")
    merged: list[list] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    active_s = sum((b - a).total_seconds() for a, b in merged)
    return {
        "run_id": state.get("run_id"), "goal": state.get("goal"),
        "run_dir": str(run_dir),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rates_captured_at": rates.get("captured_at"), "rates_source": rates.get("source"),
        "wall": {
            "first_at": min(starts).isoformat() if starts else None,
            "last_at": max(ends).isoformat() if ends else None,
            "elapsed_s": (max(ends) - min(starts)).total_seconds() if starts and ends else None,
            "active_s": active_s or None,
            "model_time_s": sum(r["elapsed_s"] or 0 for r in dispatch_rows
                                if r.get("elapsed_s") and r.get("label") != "session"),
        },
        "dispatches": dispatch_rows,
        "by_model": totals,
        "cost_usd": grand,
        "cost_complete": complete,
        "unpriced_models": sorted(unpriced),
    }


def _hms(sec: float | None) -> str:
    if not sec:
        return "—"
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}h {m:02d}m" if h else (f"{m}m {s:02d}s" if m else f"{s}s")


def render(rep: dict) -> str:
    L = [f"Run {rep['run_id']}  ({rep['goal']})", ""]
    w = rep["wall"]
    L.append(f"  Elapsed          {_hms(w['elapsed_s'])}"
             + (f"   (from {w['first_at'][:16].replace('T', ' ')} UTC)" if w["first_at"] else ""))
    if w["active_s"] and w["elapsed_s"]:
        L.append(f"    of which active  {_hms(w['active_s'])}"
                 f" ({w['active_s'] / w['elapsed_s'] * 100:.0f}%)   work actually in flight")
    if w["model_time_s"]:
        note = ""
        if w["active_s"] and w["model_time_s"] > w["active_s"] * 1.05:
            note = f"   summed across dispatches; {w['model_time_s'] / w['active_s']:.1f}x active, so they overlapped"
        L.append(f"    dispatch time    {_hms(w['model_time_s'])}{note}")
    if rep["cost_complete"]:
        L.append(f"  Estimated cost   ${rep['cost_usd']:,.2f}")
    else:
        L.append(f"  Estimated cost   ${rep['cost_usd']:,.2f} for priced models; "
                 f"NOT PRICED: {', '.join(rep['unpriced_models'])}")
    L += ["", "  Where the time and money went", ""]
    L.append(f"    {'step':<26}{'elapsed':>9}{'resp':>7}{'output tok':>12}{'cost':>10}")
    for r in sorted((d for d in rep["dispatches"] if d.get("models")),
                    key=lambda d: d["cost_usd"], reverse=True):
        msgs = r.get("responses") or sum(m["messages"] for m in r["models"].values())
        out = sum(m["output_tokens"] for m in r["models"].values())
        flag = "" if r["cost_complete"] else " *"
        L.append(f"    {r['label'][:26]:<26}{_hms(r['elapsed_s']):>9}{msgs:>7}{out:>12,}"
                 f"{'$' + format(r['cost_usd'], ',.2f') + flag:>10}")
    L += ["", "  By model", ""]
    for model, acc in sorted(rep["by_model"].items(), key=lambda kv: -(kv[1].get("cost_usd") or 0)):
        c = acc.get("cost_usd")
        L.append(f"    {model:<22}{acc['input_tokens']:>10,} in {acc['output_tokens']:>10,} out"
                 f" {acc['cache_read_input_tokens']:>12,} cache read"
                 f" {acc['cache_creation_input_tokens']:>11,} cache write"
                 + (f"   ${c:,.2f}" if c is not None else "   cost not priced"))
    L += ["",
          "  Tokens are counted once per API response (the transcript stores one record per",
          "  content block; duplicates are folded by message id). The dollar figure is computed",
          f"  locally at standard list rates captured {rep['rates_captured_at']}, so it does not",
          "  reflect promotional pricing or contracted discounts and may differ from your",
          "  actual bill. For authoritative billing, see your provider's usage console."]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir", type=pathlib.Path)
    ap.add_argument("--json", action="store_true", help="emit the machine report")
    ap.add_argument("--rates", type=pathlib.Path,
                    default=pathlib.Path(__file__).resolve().parent.parent / "reference" / "rates.json")
    a = ap.parse_args()

    if not (a.run_dir / "run.json").is_file():
        print(f"{a.run_dir}: no run.json — not an countz-accounting run directory", file=sys.stderr)
        return 2
    rep = collect(a.run_dir, json.loads(a.rates.read_text(encoding="utf-8")))
    print(json.dumps(rep, indent=2) if a.json else render(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
