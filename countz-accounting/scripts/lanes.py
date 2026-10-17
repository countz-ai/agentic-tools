#!/usr/bin/env python3
"""Holder lanes: run a plan's steps in a few long-lived worker contexts side by side.

    lanes.py assign <run_dir> <definition> [--lanes N] [--reset-tokens T] [--reset-briefs B]
    lanes.py place <run_dir> <definition> --steps id1,id2      (the playbook-next agent's path)
    lanes.py holder <run_dir> --lane L --agent <agentId>
    lanes.py done <run_dir> --agent <agentId> [--context TOKENS]
    lanes.py fallback <run_dir> --lane L

A lane is one worker sub-agent the relay launches once and continues with SendMessage, so
each step reads in context what the lane's earlier steps read and wrote; the lanes run in
parallel (RUN_CONTRACT.md § Holder lanes). `assign` maps the approved plan's steps (the
run's own steps, so a partial run's scope is what gets mapped) onto lanes from their
`after` lists alone, every step counted as one unit of work:

- Lanes: the most steps that could run at once, capped at N (default 3).
- Lane 1 is the path through the family graph holding the most read edges (a path steps
  from a family to one that reads it; each family counts the families before it on the
  path that it reads); each next lane is the same search over the families left.
- Hard steps have one lane: a single-step family on a lane's path, or a single-step family
  left over, which joins the lane holding most of what it reads.
- Pool steps (each step of a family with several) can run in any of their candidate lanes:
  their own lane first, then the others holding more of their reads, lane 1 only when the
  family is on lane 1 (the chain the last steps wait on). The relay places one on the
  first candidate lane that is free when it is ready.

`place` starts what can start now: each free lane's next ready hard step, then ready pool
steps on free candidate lanes. It writes each brief; a brief for a lane whose holder is
alive gets its handoff block (scripts/handoff.py) without what the holder already holds,
and a holder past the reset (its context above --reset-tokens, measured from its
sub-agent transcript, or --reset-briefs briefs when no transcript is found) is replaced
by a new one with the full block. It prints the RECORD: line and one LANE: line per
launch. `done` closes one lane's brief (`run_state.py record --seqs`), updates what its
holder holds, launches a retry in the same lane on a new holder, and frees the lane.
`fallback` is for a SendMessage that failed: the lane's brief gets the full handoff and
a new holder. State lives in <run_dir>/lanes.json. Standard library only.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import pathlib
import subprocess
import sys

import handoff
import run_state
from run_state import _q

FILE = "lanes.json"
HERE = pathlib.Path(__file__).resolve()


# ------------------------------------------------------------------ the assignment
def _family(step: dict) -> str:
    return str((step.get("params") or {}).get("family") or step["id"])


def assign(definition: dict, max_lanes: int = 3) -> dict:
    """{"lanes": {lane: [hard step ids, plan order]}, "pool": {step id: [candidate lanes]}}."""
    steps = definition["steps"]
    order = [s["id"] for s in steps]
    fam_of = {s["id"]: _family(s) for s in steps}
    fams = list(dict.fromkeys(fam_of[i] for i in order))
    members = collections.defaultdict(list)
    for i in order:
        members[fam_of[i]].append(i)
    reads = {f: set() for f in fams}
    for s in steps:
        for d in s.get("after") or []:
            if d in fam_of and fam_of[d] != fam_of[s["id"]]:
                reads[fam_of[s["id"]]].add(fam_of[d])

    # the most steps that could run at once: steps per dependency level, each one unit
    level: dict[str, int] = {}
    for s in steps:  # plan order is topological
        level[s["id"]] = 1 + max((level[d] for d in s.get("after") or [] if d in level), default=-1)
    width = max(collections.Counter(level.values()).values())
    n = max(1, min(max_lanes, width))

    readers = {f: [g for g in fams if f in reads[g]] for f in fams}

    def best_path(pool: set) -> list:
        best = (-1, 0, [])

        def walk(path: list, score: int) -> None:
            nonlocal best
            if (score, len(path)) > best[:2]:
                best = (score, len(path), list(path))
            for g in readers[path[-1]]:
                if g in pool and g not in path:
                    walk(path + [g], score + len(reads[g] & set(path)))

        for f in fams:
            if f in pool:
                walk([f], 0)
        return best[2]

    pool = set(fams)
    paths: list[list[str]] = []
    for _ in range(n):
        p = best_path(pool)
        if not p:
            break
        paths.append(p)
        pool -= set(p)
    for f in [f for f in fams if f in pool]:
        k = max(range(len(paths)), key=lambda i: (len(reads[f] & set(paths[i])), -len(paths[i])))
        paths[k].append(f)
    home = {f: i for i, p in enumerate(paths) for f in p}

    lanes = {str(i + 1): [] for i in range(len(paths))}
    flex: dict[str, list[str]] = {}
    for f in fams:
        if len(members[f]) == 1:
            lanes[str(home[f] + 1)].append(members[f][0])
            continue
        others = sorted((i for i in range(len(paths)) if i != home[f] and (i != 0 or home[f] == 0)),
                        key=lambda i: (-len(reads[f] & set(paths[i])), i))
        cands = [str(i + 1) for i in [home[f]] + others]
        for sid in members[f]:
            flex[sid] = cands
    return {"lanes": lanes, "pool": flex}


# ------------------------------------------------------------------ the state
def load(run_dir: pathlib.Path) -> dict | None:
    f = run_dir / FILE
    return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None


def save(run_dir: pathlib.Path, st: dict) -> None:
    tmp = run_dir / (FILE + ".tmp")
    tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
    tmp.replace(run_dir / FILE)


def _new_holder() -> dict:
    return {"agent": None, "checks": [], "reads": [], "briefs": 0, "context": None}


def busy_seqs(run_dir: pathlib.Path, st: dict) -> dict[str, int]:
    """Lane -> the seq it is running, for the lanes whose dispatch is still outstanding."""
    run = run_state.load_run(run_dir)
    open_ = {d["seq"] for d in run.get("dispatches", []) if d.get("state") == "dispatched"}
    return {lane: b["seq"] for lane, b in (st.get("busy") or {}).items() if b and b["seq"] in open_}


def context_of(agent: str | None) -> int | None:
    """The agent's context at its last turn, from its sub-agent transcript, when found."""
    if not agent:
        return None
    root = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
    hits = glob.glob(str(root / "projects" / "*" / "*" / "subagents" / f"agent-{agent}.jsonl"))
    if not hits:
        return None
    last = None
    for line in pathlib.Path(max(hits, key=os.path.getmtime)).read_text(errors="ignore").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        u = ((d.get("message") or {}).get("usage") or {}) if d.get("type") == "assistant" else {}
        if u:
            last = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) \
                + u.get("cache_creation_input_tokens", 0)
    return last


def _spent(st: dict, h: dict) -> bool:
    """A holder past the reset: its next brief starts a new one."""
    if h["context"] is not None:
        return h["context"] > st["reset_tokens"]
    return h["briefs"] >= st["reset_briefs"]


# ------------------------------------------------------------------ placing steps on lanes
def place(run_dir: pathlib.Path, definition: dict, ready: list[dict], bound: dict, run: dict) -> list[str]:
    """Start what can start now; return the printed lines ([] when every candidate lane is
    busy). `ready` is in plan order; each placed step gets its brief written."""
    st = load(run_dir)
    busy = busy_seqs(run_dir, st)
    free = [lane for lane in st["lanes"] if lane not in busy]
    picks: list[tuple[str, dict]] = []
    taken: set[str] = set()
    for lane in free:  # a lane's own next step first
        for s in ready:
            if s["id"] in st["lanes"][lane] and s["id"] not in taken:
                picks.append((lane, s))
                taken.add(s["id"])
                break
    for s in ready:  # then the pool, on the first free candidate lane
        if s["id"] in taken or s["id"] not in st["pool"]:
            continue
        lane = next((c for c in st["pool"][s["id"]] if c in free and c not in {p[0] for p in picks}), None)
        if lane:
            picks.append((lane, s))
            taken.add(s["id"])
    if not picks:
        return []
    seq0 = run["next_seq"]
    lines, briefs = [], []
    for i, (lane, s) in enumerate(picks):
        brief = run_state.write_brief(run_dir, seq0 + i, s, bound)
        h = st["holders"].setdefault(lane, _new_holder())
        if h["agent"] and not _spent(st, h):
            handoff.replace(brief, handoff.render(run_dir, handoff.held_out(
                s.get("params"), h["checks"], h["reads"]), kit=False))
            who = h["agent"]
        else:
            if h["agent"]:
                st.setdefault("retired", []).append({"lane": lane, **h})
            st["holders"][lane] = h = _new_holder()
            who = "new"
        st.setdefault("busy", {})[lane] = {"seq": seq0 + i, "check": s["id"], "brief": str(brief)}
        briefs.append(brief)
        lines.append(f"LANE: lane={lane} holder={who} seq={seq0 + i} check={s['id']} brief={_q(brief)}")
    save(run_dir, st)
    head = (f"RECORD: python3 {_q(pathlib.Path(run_state.__file__).resolve())} dispatch "
            f"{_q(run_dir)} --briefs " + " ".join(_q(b) for b in briefs))
    tail = (f"AWAIT: when a lane's agent reports back, run python3 {_q(HERE)} done {_q(run_dir)} "
            f"--agent <its agentId> and execute what it prints")
    return [head] + lines + [tail]


# ------------------------------------------------------------------ commands
def cmd_assign(a) -> int:
    run_dir = a.run_dir.resolve()
    definition = json.loads(a.definition.read_text(encoding="utf-8"))
    m = assign(definition, a.lanes)
    st = {"definition": str(a.definition.resolve()), "reset_tokens": a.reset_tokens,
          "reset_briefs": a.reset_briefs, **m,
          "holders": {lane: _new_holder() for lane in m["lanes"]}, "busy": {}, "retired": []}
    save(run_dir, st)
    for lane, ids in m["lanes"].items():
        pooled = [s for s, c in m["pool"].items() if lane in c]
        print(f"lane {lane}: {' -> '.join(ids)}" + (f"  (+ pool: {len(pooled)} steps may run here)"
                                                    if pooled else ""))
    return 0


def cmd_place(a) -> int:
    import playbook_next  # noqa: PLC0415  sibling: the run state it decides from
    run_dir = a.run_dir.resolve()
    definition = json.loads(a.definition.read_text(encoding="utf-8"))
    run = run_state.load_run(run_dir)
    want = {x for x in a.steps.split(",") if x}
    ready = [s for s in definition["steps"] if s["id"] in want]
    lines = place(run_dir, definition, ready, playbook_next.bound_map(run, definition), run)
    print("\n".join(lines) if lines else "WAIT: every candidate lane is busy")
    return 0


def _lane_of(st: dict, agent: str) -> str | None:
    return next((lane for lane, h in st["holders"].items() if h.get("agent") == agent), None)


def cmd_holder(a) -> int:
    run_dir = a.run_dir.resolve()
    st = load(run_dir)
    h = st["holders"].setdefault(a.lane, _new_holder())
    if h["agent"] and h["agent"] != a.agent:
        st.setdefault("retired", []).append({"lane": a.lane, **h})
        st["holders"][a.lane] = h = _new_holder()
    h["agent"] = a.agent
    save(run_dir, st)
    print(f"lane {a.lane}: holder {a.agent}")
    return 0


def cmd_done(a) -> int:
    run_dir = a.run_dir.resolve()
    st = load(run_dir)
    lane = _lane_of(st, a.agent)
    if lane is None:
        print(f"lanes: no lane's holder is {a.agent}; run lanes.py holder first", file=sys.stderr)
        return 2
    b = (st.get("busy") or {}).get(lane)
    if not b:
        print(f"lane {lane}: nothing outstanding")
        return 0
    p = subprocess.run([sys.executable, str(HERE.parent / "run_state.py"), "record", str(run_dir),
                        "--seqs", str(b["seq"])], capture_output=True, text=True)
    sys.stdout.write("".join(l + "\n" for l in p.stdout.splitlines()
                             if not l.startswith(("RETRY:", "LAUNCH:", "THEN:", "NEXT:"))))
    if p.returncode:
        sys.stderr.write(p.stderr)
        return p.returncode
    definition = json.loads(pathlib.Path(st["definition"]).read_text(encoding="utf-8"))
    step = next((s for s in definition["steps"] if s["id"] == b["check"]), {})
    h = st["holders"][lane]
    h["checks"].append(b["check"])
    h["reads"] = sorted(set(h["reads"]) | set((step.get("params") or {}).get("reads") or []))
    h["briefs"] += 1
    h["context"] = a.context if a.context is not None else context_of(a.agent)
    st["busy"][lane] = None
    run = run_state.load_run(run_dir)
    retry = next((d for d in run.get("dispatches", []) if d.get("state") == "dispatched"
                  and d.get("attempt_of") == b["seq"]), None)
    if retry:  # the step died or failed: its retry runs in this lane, on a new holder
        st.setdefault("retired", []).append({"lane": lane, **h})
        st["holders"][lane] = _new_holder()
        st["busy"][lane] = {"seq": retry["seq"], "check": b["check"], "brief": str(run_dir / retry["brief"])}
        print(f"LANE: lane={lane} holder=new seq={retry['seq']} check={b['check']} "
              f"brief={_q(run_dir / retry['brief'])}")
    save(run_dir, st)
    print(f"THEN: python3 {_q(HERE.parent / 'playbook_next.py')} {_q(run_dir)} {_q(st['definition'])}")
    return 0


def cmd_fallback(a) -> int:
    run_dir = a.run_dir.resolve()
    st = load(run_dir)
    b = (st.get("busy") or {}).get(a.lane)
    if not b:
        print(f"lane {a.lane}: nothing outstanding", file=sys.stderr)
        return 2
    h = st["holders"].get(a.lane) or _new_holder()
    if h["agent"]:
        st.setdefault("retired", []).append({"lane": a.lane, **h})
    st["holders"][a.lane] = _new_holder()
    definition = json.loads(pathlib.Path(st["definition"]).read_text(encoding="utf-8"))
    step = next((s for s in definition["steps"] if s["id"] == b["check"]), {})
    handoff.replace(b["brief"], handoff.render(run_dir, step.get("params")))
    save(run_dir, st)
    print(f"LANE: lane={a.lane} holder=new seq={b['seq']} check={b['check']} brief={_q(b['brief'])}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("assign")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("definition", type=pathlib.Path)
    p.add_argument("--lanes", type=int, default=3)
    p.add_argument("--reset-tokens", type=int, default=700_000)
    p.add_argument("--reset-briefs", type=int, default=6)
    p.set_defaults(fn=cmd_assign)
    p = sub.add_parser("place")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("definition", type=pathlib.Path)
    p.add_argument("--steps", required=True)
    p.set_defaults(fn=cmd_place)
    p = sub.add_parser("holder")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("--lane", required=True)
    p.add_argument("--agent", required=True)
    p.set_defaults(fn=cmd_holder)
    p = sub.add_parser("done")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("--agent", required=True)
    p.add_argument("--context", type=int, default=None,
                   help="the holder's context in tokens, when the caller measured it")
    p.set_defaults(fn=cmd_done)
    p = sub.add_parser("fallback")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("--lane", required=True)
    p.set_defaults(fn=cmd_fallback)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
