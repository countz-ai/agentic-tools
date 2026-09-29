#!/usr/bin/env python3
"""Decide the next wave of a playbook run mechanically, or escalate.

Implements `skills/playbook-next/SKILL.md`'s procedure for every case that is a pure
function of disk — the relay calls this script first, always; a divergence between the
script and that procedure is a bug in the script. Anything the procedure does not cover
exits 3 with `ESCALATE: <reason>` and writes NOTHING — the relay then invokes the
`playbook-next` skill (the playbook-engine agent), which redoes the whole decision from
disk, and the relay returns here for the next one.

Like the agent, this script never opens a file the user supplied, never computes a
figure, and never writes `run.json`: its only writes are the wave's dispatch briefs
under `dispatch/` and one `decision` line in `events.jsonl`, both after the decision is
fully made. The relay records the dispatches — the printed `RECORD:` line is the
`run_state.py dispatch --briefs` call that does it. Every wave also prints one `SAY:`
line ahead of `RECORD:` — the wave's number, how many checks run, and what they are
(the recipe's family titles on a plan-driven run; id and kind otherwise) — which the
relay puts to the user as plain chat (RUN_CONTRACT.md § Every wave).

Classification reads the step record, `error` before `outcome` (a record claiming
`blocked` with a non-empty `blockers` is blocked whatever `error` carries) — the
classifier is `run_state.classify_record`, shared with `record` so the two cannot drift; a record that
is absent or unparseable falls back to the dispatch row's terminal `state`
(`run_state.py record` already classified it — a step that died leaves no record).

Escalated to the agent: an orphan step record (a seq no dispatch row carries), a record
whose seq or step disagrees with its dispatch row, an outcome outside the classifier
vocabulary, a recordless dispatch with no terminal `state` (the relay runs
`run_state.py record` before deciding, so this means a wave was never recorded), a
binding that does not match the definition, and any unexpected error.

Usage:
    playbook_next.py <run_dir> <playbook.json>

Exit 0: decision printed — a wave (briefs written, `decision` event appended) or DONE.
Exit 2: usage error, or a definition that fails check_playbook.py — a broken definition
goes to the user, not the agent. Exit 3: ESCALATE — nothing written.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import sys

import check_playbook  # sibling: the one home of KINDS and of definition validation
import run_state  # sibling: the brief template and the dispatch-row vocabulary
from run_state import _q

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN_SCHEMA = "countz-accounting/run@1"


class Escalate(Exception):
    pass


def classify(run_dir: pathlib.Path, row: dict) -> dict:
    """One dispatch row -> its terminal class. The classification itself — `error`
    before `outcome`, seq/step agreement, the outcome vocabulary — is
    run_state.classify_record, the same function `record` classifies with; this wrapper
    adds the fold's layer. A record that is absent or unparseable (rec None) falls back
    to the row's terminal `state` — run_state.py record already classified it (a step
    that died leaves no record); anything else died-shaped escalates."""
    rel = row.get("record") or f"steps/{row.get('seq'):04d}-{row.get('step')}.json"
    cls, rec, why = run_state.classify_record(run_dir, row)
    if cls in ("ok", "blocked", "failed"):
        return {"cls": cls, "record": rel}
    if rec is None:
        state = row.get("state")
        if state in ("ok", "blocked"):
            return {"cls": state, "record": rel}
        if state in ("failed", "died"):
            return {"cls": "failed", "record": rel}
        raise Escalate(f"step record {rel} is absent or unparseable for dispatch seq "
                       f"{row.get('seq')} - run_state.py record has not classified "
                       f"this wave")
    raise Escalate(f"{rel}: {why}")


def fold(run: dict, run_dir: pathlib.Path, definition: dict) -> dict:
    """Per definition step: latest dispatch's terminal class, or None when undispatched."""
    dispatches = run.get("dispatches", [])
    known = {d.get("seq") for d in dispatches}
    for f in sorted((run_dir / "steps").glob("[0-9]*.json")):
        seq = int(f.name.split("-")[0])
        if seq not in known:
            raise Escalate(f"orphan record steps/{f.name}: no dispatch row carries seq {seq}")
    state: dict[str, dict | None] = {}
    for st in definition["steps"]:
        rows = [d for d in dispatches if d.get("check_id") == st["id"]]
        state[st["id"]] = classify(run_dir, rows[-1]) if rows else None
    return state


def bound_map(run: dict, definition: dict) -> dict:
    pb = run.get("playbook") or {}
    if not pb.get("bound"):
        raise Escalate("run.json.playbook carries no binding - it is recorded at slot "
                       "binding, before any wave is decided")
    if pb.get("name") and pb["name"] != definition["name"]:
        raise Escalate(f"run.json.playbook names {pb['name']!r} but the definition passed "
                       f"is {definition['name']!r}")
    return pb["bound"]


def decide(definition: dict, state: dict, bound: dict, sources: dict, run: dict) -> dict:
    steps = definition["steps"]
    skipped: dict[str, str] = {}
    changed = True
    while changed:  # a skip propagates to every step downstream of it
        changed = False
        for st in steps:
            sid = st["id"]
            if sid in skipped or state[sid] is not None:
                continue
            reason = None
            unbound = [sl for sl in st["sources"] if sl not in bound]
            if unbound:
                reason = f"slot {unbound[0]} unbound"
            else:
                for dep in st.get("after") or []:
                    if (state.get(dep) or {}).get("cls") == "failed":
                        reason = f"dependency {dep} failed"
                        break
                    if dep in skipped:
                        reason = f"dependency {dep} skipped"
                        break
            if reason:
                skipped[sid] = reason
                changed = True

    wave = []
    for st in steps:
        sid = st["id"]
        if sid in skipped or state[sid] is not None:
            continue
        if any((state.get(dep) or {}).get("cls") not in ("ok", "blocked")
               for dep in st.get("after") or []):
            continue
        for sl in st["sources"]:
            if bound[sl] not in sources:
                raise Escalate(f"step {sid}: slot {sl} is bound to source "
                               f"{bound[sl]!r}, which run.json.sources does not carry")
        wave.append(st)

    if wave:
        return {"kind": "wave", "members": wave, "skipped": skipped}
    if all(state[st["id"]] is not None or st["id"] in skipped for st in steps):
        return {"kind": "done", "skipped": skipped}
    waiting = [st["id"] for st in steps if state[st["id"]] is None and st["id"] not in skipped]
    raise Escalate(f"no step is dispatchable and {', '.join(waiting)} are not terminal")


def wave_number(run_dir: pathlib.Path) -> int:
    n = 0
    p = run_dir / "events.jsonl"
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                n += json.loads(line).get("event") == "decision"
            except ValueError:
                pass
    return n + 1


def wave_why(members: list[dict], state: dict) -> str:
    deps = sorted({d for st in members for d in st.get("after") or []})
    facts = "; ".join(f"{d} terminal {state[d]['cls']}" for d in deps)
    names = ", ".join(st["id"] for st in members)
    verb = "has" if len(members) == 1 else "have"
    if facts:
        return f"{facts}; {names} {verb} no dispatch and dependencies are terminal."
    return f"{names} {verb} no dispatch and no dependencies."


def append_decision(run_dir: pathlib.Path, wave: int, steps: list[str], why: str) -> None:
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")
    line = {"ts": ts, "event": "decision", "wave": wave, "steps": steps, "why": why}
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def emit_wave(run_dir, pb_path, definition, decision, state, bound, run) -> None:
    members, skipped = decision["members"], decision["skipped"]
    wave = wave_number(run_dir)
    why = wave_why(members, state)
    seq0 = run["next_seq"]
    briefs = [run_state.write_brief(run_dir, seq0 + i, st, bound)
              for i, st in enumerate(members)]
    append_decision(run_dir, wave, [st["id"] for st in members], why)
    k = len(members)
    run_state_py = pathlib.Path(run_state.__file__).resolve()
    print(f"playbook {definition['name']}  wave={wave}  {k} dispatch{'es' if k != 1 else ''}")
    print(why)
    what = run_state.describe_members(
        [(st["id"], st["check"], st.get("params")) for st in members],
        run_state.recipe_families(run))
    print(run_state.say_line(
        f"Wave {wave} — running {run_state.checks_phrase(k)}: {what}."))
    print(f"RECORD: python3 {_q(run_state_py)} dispatch {_q(run_dir)} --briefs "
          + " ".join(_q(b) for b in briefs))
    print(run_state.LAUNCH)
    for i, st in enumerate(members):
        print(f"NEXT: Skill {check_playbook.KINDS[st['check']]} run_dir={_q(run_dir)} "
              f"seq={seq0 + i} check={st['id']} "
              f"sources={','.join(bound[sl] for sl in st['sources'])} "
              f"goal={st.get('goal') or '(none)'} mode=fresh brief={_q(briefs[i])}")
    for sid, reason in skipped.items():
        print(f"SKIPPED: {sid} — {reason}")
    print(f"THEN: python3 {_q(run_state_py)} record {_q(run_dir)}")
    print(f"THEN: python3 {_q(pathlib.Path(__file__).resolve())} {_q(run_dir)} {_q(pb_path)}")


def emit_done(definition, decision, state) -> None:
    skipped = decision["skipped"]
    counts: dict[str, int] = {}
    for st in definition["steps"]:
        cls = "skipped" if st["id"] in skipped else state[st["id"]]["cls"]
        counts[cls] = counts.get(cls, 0) + 1
    summary = ", ".join(f"{n} {cls}" for cls, n in counts.items())
    print(f"playbook {definition['name']}  done  {summary}")
    print(f"every step terminal or skipped: {summary}.")
    non_ok = [st for st in definition["steps"]
              if st["id"] in skipped or state[st["id"]]["cls"] != "ok"]
    if not non_ok:
        print(f"DONE: all {len(definition['steps'])} steps ok")
        return
    for st in non_ok:
        sid = st["id"]
        if sid in skipped:
            print(f"DONE: {sid} skipped — {skipped[sid]}")
        elif state[sid]["cls"] == "failed":
            print(f"DONE: {sid} failed — error recorded in {state[sid]['record']}")
        else:
            print(f"DONE: {sid} blocked — see {state[sid]['record']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=pathlib.Path)
    ap.add_argument("playbook", type=pathlib.Path)
    a = ap.parse_args()
    run_dir, pb_path = a.run_dir.resolve(), a.playbook.resolve()
    if not (run_dir / "run.json").is_file():
        print(f"{run_dir}: no run.json", file=sys.stderr)
        return 2
    if not pb_path.is_file():
        print(f"{pb_path}: not a file", file=sys.stderr)
        return 2
    skills = PLUGIN_ROOT / "skills"
    problems = check_playbook.validate(pb_path, skills if skills.is_dir() else None)
    if problems:
        print(f"{pb_path.name}: {len(problems)} problem(s)", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 2

    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    if run.get("schema") != RUN_SCHEMA:
        raise Escalate(f"run.json schema {run.get('schema')!r} is not {RUN_SCHEMA}")
    definition = json.loads(pb_path.read_text(encoding="utf-8"))
    bound = bound_map(run, definition)
    sources = {s["id"]: s for s in run.get("sources", [])}
    state = fold(run, run_dir, definition)
    decision = decide(definition, state, bound, sources, run)
    if decision["kind"] == "wave":
        emit_wave(run_dir, pb_path, definition, decision, state, bound, run)
    else:
        emit_done(definition, decision, state)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Escalate as exc:
        print(f"ESCALATE: {exc}")
        raise SystemExit(3)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"ESCALATE: unexpected {type(exc).__name__}: {exc}")
        raise SystemExit(3)
