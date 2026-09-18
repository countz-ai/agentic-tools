#!/usr/bin/env python3
"""The relay's pen for run.json: every write after setup_run.py goes through here.

RUN_CONTRACT.md names the roles; this script owns the state transitions,
so `run.json`'s shape has one authority and an agent never hand-edits it. Like
`setup_run.py` it reads no client file, writes `run.json` to `.tmp` then rename, and
puts a refusal on stderr with exit 2 — the relay shows it to the user, never works
around it.

Subcommands:

    add-checks <run_dir> --checks '<one-line JSON array>'
        Register checks: [{"id","kind","sources",("goal"),("params")}, ...]. Kind must
        be in check_playbook.KINDS, sources must be registered, ids must be new slugs,
        and params must meet the kind's contract (check_playbook.PARAMS).

    bind-playbook <run_dir> --path <definition> --bound '{"slot":"source_id",...}'
        Record a saved playbook run: validate the definition, record
        {name, path, bound} in run.json.playbook, and register every step whose slots
        are all bound as a check (goal and params verbatim). A step fed by an unbound
        slot is printed as DROPPED and not registered — the engine skips it.

    approve-plan <run_dir> --definition <run_dir>/plan/<name>.json [--recipe <abs>]
        Record the user's approval of a drafted plan: validate the definition, record
        run.json.plan (record, recipe, playbook, approved_at) and run.json.playbook
        (slots are the run's own source ids, so the binding is identity), register the
        steps as checks, append the `plan_approved` event.

    dispatch <run_dir> --checks id1,id2 [--mode fresh|fix] [--extra '<one-line JSON>']
    dispatch <run_dir> --step plan|recipe|review|report --args '<one-line JSON>'
    dispatch <run_dir> --briefs <brief.md> ...
        Open a wave: allocate seqs from next_seq, append one dispatch row per member
        (state "dispatched"), write every member's brief to dispatch/<NNNN>-<step>.md —
        a wave of one and a --step included: the brief is the archived launch
        instruction, whatever form the launch takes — and print the launch imperatives:
        one NEXT: line per member, preceded by a LAUNCH: line with the sub-agent
        protocol when the wave has two or more members (those NEXT lines carry
        brief=); a wave of one is a plain Skill call. --briefs records rows for briefs
        playbook_next.py (or the engine agent) already wrote. Every --checks and --step
        dispatch also prints one SAY: line first — the progress line the relay puts to
        the user as plain chat (RUN_CONTRACT.md § Every wave): what runs, and how many.

    record <run_dir>
        Close a wave: classify every outstanding dispatch from its step record —
        `error` before `outcome`, except that a record claiming `blocked` with a
        non-empty `blockers` is blocked whatever `error` carries (the step finished and
        named what stopped it; a retry re-runs the same work to the same answer);
        absent, mismatched or unparseable means died — fold conclusions and results
        into the check rows, set `degraded` on blocked or failed, and handle retries: a
        first failure or death mints one re-dispatch (same args, new seq, its own
        brief, `attempt_of` set, a `retry` event) printed as a RETRY: line with a THEN:
        to run record again — RETRY lines carry brief= only when two or more are
        minted at once; a second is terminal — the check is marked failed and the
        FAILED: line is for the relay to put to the user. A minted retry wave opens
        with its own SAY: line.

    debug <run_dir> [--off]
        Turn the run's debug mode on or off (OBSERVABILITY.md § 3). While it is on,
        `record` ends every wave with a GATHER: line the relay runs before the sync,
        and preview.py surfaces every artifact rather than only the engagement
        preview, the plan, the workbook and the report deck.

Exit 0 on success; exit 2 on anything refused, with the reason on stderr.
"""
from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import re
import sys

import check_playbook  # sibling: the one home of KINDS, SLUG and definition validation

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN_SCHEMA = "countz-accounting/run@1"

# Steps that are not checks, and the skill each dispatches. Check kinds resolve through
# check_playbook.KINDS.
STEP_SKILLS = {"plan": "check-plan", "recipe": "create-recipe", "review": "check-review",
               "report": "check-report"}

BRIEF = """\
# countz-accounting dispatch {nnnn} — {step}

This file is your entire instruction.

1. Read `{agent}` — your standing instructions.
2. Read `{plug}/skills/{skill}/SKILL.md` — your procedure.
3. Where those files say `${{CLAUDE_PLUGIN_ROOT}}`, use: `{plug}`

Your arguments:

    run_dir={run_dir}
    seq={seq}
{args}"""

# The order a check dispatch's arguments render in, before anything --extra adds; a
# step dispatch (plan / review / report) renders its --args in the order given.
CHECK_ARG_ORDER = ("sources", "goal", "params", "mode")

# Printed once per briefed wave, by this script and playbook_next.py. Re-invoking one
# forked skill while an earlier invocation is running waits for it, so a wave run as
# repeated Skill calls silently serializes - hence sub-agents on briefs.
LAUNCH = ("LAUNCH: in ONE message, one general-purpose sub-agent per NEXT line, each "
          "prompted exactly: Read <its brief= path> and do what it says. It is your "
          "entire instruction. - nothing more. Without an Agent tool, run each NEXT "
          "line as its Skill call, one at a time.")

# The SAY: line - one per wave, printed before the launch imperatives by this script and
# playbook_next.py. The relay puts its text to the user as one line of plain chat
# (RUN_CONTRACT.md § Every wave); it never names a file, so nothing about it reaches the
# file preview. KIND_WORDS is the word a check kind takes in that line.
KIND_WORDS = {"tieout": "tie-out", "recon": "reconciliation",
              "completeness": "completeness", "vouch": "vouching",
              "cutoff": "cutoff", "analysis": "analysis"}

# A recipe's family header, as check-plugin.py gates it (PLAYBOOK_RECIPES.md § The body).
FAMILY_HEADER = re.compile(r"^### ([A-Z]\d) — (.+?) \(kind `[a-z]+`, .+\)\s*$", re.M)


def say_line(text: str) -> str:
    return f"SAY: {text}"


def checks_phrase(n: int) -> str:
    return f"{n} check{'s' if n != 1 else ''}{' in parallel' if n > 1 else ''}"


def recipe_families(run: dict) -> dict[str, str]:
    """Family id -> its title, from the recipe a plan-driven run recorded
    (`run.json.plan.recipe`). Empty for a run with no recipe, or one this machine
    cannot read: the SAY line then names members by id and kind."""
    path = (run.get("plan") or {}).get("recipe")
    if not path:
        return {}
    try:
        text = pathlib.Path(path).read_text()
    except OSError:
        return {}
    return {fid.lower(): title for fid, title in FAMILY_HEADER.findall(text)}


def describe_members(members: list[tuple[str, str | None, dict | None]],
                     families: dict[str, str]) -> str:
    """What a wave runs, for its SAY line. `members` are (name, kind, params) in wave
    order. A member whose params.family the recipe titles is counted under
    `<ID> <title>`; any other is `<name> (<kind word>)`, or the name alone for a step
    dispatch (plan / review / report), which has no kind."""
    order: list[str] = []
    counts: dict[str, int] = {}
    for name, kind, params in members:
        fam = str((params or {}).get("family") or "").lower()
        if fam in families:
            key = f"{fam.upper()} {families[fam]}"
        elif kind:
            key = f"{name} ({KIND_WORDS.get(kind, kind)})"
        else:
            key = name
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + 1
    return ", ".join(f"{counts[k]} × {k}" if counts[k] > 1 else k for k in order)


def step_say(step: str, args: dict) -> str:
    """The SAY text for a plan / recipe / review / report dispatch."""
    if step == "plan":
        return ("Redrafting the check plan on your instruction." if args.get("revise")
                else "Drafting the check plan from the data room.")
    if step == "recipe":
        return ("Writing the recipe from your answers." if args.get("answers")
                else "Reading the data room to draft the questions the recipe needs answered.")
    if step == "review":
        ids = args.get("checks") or []
        if isinstance(ids, str):
            ids = [c for c in ids.split(",") if c.strip()]
        what = checks_phrase(len(ids)).replace(" in parallel", "") if ids else "the checks"
        return f"Reviewing {what} against the source files."
    return "Assembling the workbook and the report deck from the check records."


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def _append_event(run_dir: pathlib.Path, event: str, **fields) -> None:
    line = {"ts": _now(), "event": event, **fields}
    with (run_dir / "events.jsonl").open("a") as f:
        f.write(json.dumps(line) + "\n")


def fail(msg: str) -> int:
    print(f"run_state: {msg}", file=sys.stderr)
    return 2


class Refuse(Exception):
    pass


def load_run(run_dir: pathlib.Path) -> dict:
    path = run_dir / "run.json"
    if not path.is_file():
        raise Refuse(f"{run_dir}: no run.json - register the run first (setup_run.py)")
    run = json.loads(path.read_text())
    if run.get("schema") != RUN_SCHEMA:
        raise Refuse(f"run.json schema {run.get('schema')!r} is not {RUN_SCHEMA}")
    return run


def save_run(run_dir: pathlib.Path, run: dict) -> None:
    run["updated_at"] = _now()
    path = run_dir / "run.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(run, indent=2) + "\n")
    tmp.replace(path)


def step_name(kind: str) -> str:
    """A dispatch's step name: `check-tie` performs step `tie` (RUN_CONTRACT § step record)."""
    return check_playbook.KINDS[kind].removeprefix("check-")


def check_args(sources: list[str], goal, params, mode: str,
               extra: dict | None = None) -> dict:
    """A check dispatch's args, in the order the brief and the NEXT line render them."""
    return {"sources": sources, "goal": goal, "params": params or {}, "mode": mode,
            **(extra or {})}


def skill_agent(skill: str) -> pathlib.Path:
    """The agent file a skill forks into, from its SKILL.md frontmatter (`agent:
    countz-accounting:<name>`); a brief points the sub-agent at the same standing
    instructions the Skill call would load. Falls back to the worker."""
    path = PLUGIN_ROOT / "skills" / skill / "SKILL.md"
    try:
        text = path.read_text() if path.is_file() else ""
    except OSError:
        text = ""
    head = text[4:].split("\n---", 1)[0] if text.startswith("---\n") else ""
    m = re.search(r"^agent:\s*(?:[\w-]+:)?([\w-]+)\s*$", head, re.M)
    return PLUGIN_ROOT / "agents" / f"{m.group(1) if m else 'worker'}.md"


def render_brief(run_dir: pathlib.Path, seq: int, step: str, skill: str,
                 check_id: str | None, args: dict) -> str:
    lines = [f"    check={check_id}\n"] if check_id else []
    lines += [f"    {k}={_arg(v)}\n" for k, v in args.items()]
    return BRIEF.format(nnnn=f"{seq:04d}", step=step, plug=PLUGIN_ROOT,
                        agent=skill_agent(skill), skill=skill, run_dir=run_dir, seq=seq,
                        args="".join(lines))


def write_row_brief(run_dir: pathlib.Path, row: dict) -> pathlib.Path:
    """The brief for one dispatch row — every dispatch gets one, whatever form its
    launch takes: `dispatch/` is the archive of what each sub-agent or fork was told."""
    path = run_dir / row["brief"]
    path.parent.mkdir(parents=True, exist_ok=True)
    body = render_brief(run_dir, row["seq"], row["step"], row["skill"],
                        row.get("check_id"), row.get("args") or {})
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text(body)
    tmp.replace(path)
    return path


def write_brief(run_dir: pathlib.Path, seq: int, st: dict, bound: dict,
                mode: str = "fresh", extra: dict | None = None) -> pathlib.Path:
    """One dispatch brief from a definition step (playbook_next.py's path, ahead of the
    dispatch row). `st` is a definition-step shape: id, check, sources (slots), goal,
    params; `bound` maps slots to source ids (identity for relay-rostered checks)."""
    step = step_name(st["check"])
    row = {"seq": seq, "step": step, "skill": check_playbook.KINDS[st["check"]],
           "check_id": st["id"], "brief": brief_rel(seq, step),
           "args": check_args([bound[sl] for sl in st["sources"]], st.get("goal"),
                              st.get("params"), mode, extra)}
    return write_row_brief(run_dir, row)


def brief_rel(seq: int, step: str) -> str:
    return f"dispatch/{seq:04d}-{step}.md"


def _flat(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, separators=(",", ":"))


def _arg(v) -> str:
    """One argument value as the brief prints it: an empty value is `(none)` (the worker
    skills read that spelling), a list is comma-joined, anything else is flat."""
    if v is None or v == {} or v == []:
        return "(none)"
    return ",".join(v) if isinstance(v, list) else _flat(v)


def _args_text(args: dict) -> str:
    parts = []
    for k, v in args.items():
        if v is None or v == {} or v == []:
            continue
        parts.append(f"{k}={','.join(v) if isinstance(v, list) else _flat(v)}")
    return " ".join(parts)


def next_line(run_dir: pathlib.Path, row: dict, brief: pathlib.Path | None,
              label: str = "NEXT") -> str:
    line = (f"{label}: Skill {row['skill']} run_dir={run_dir} seq={row['seq']}"
            + (f" check={row['check_id']}" if row.get("check_id") else "")
            + (f" {t}" if (t := _args_text(row.get("args") or {})) else ""))
    return line + (f" brief={brief}" if brief else "")


def gather_line(run_dir: pathlib.Path, run: dict) -> str | None:
    """The debug gather imperative, when the run's debug mode is on.

    The wave is the only moment the trace is certainly complete AND certainly still on
    disk: a sub-agent's transcript is finished when it returns, and a cloud container
    takes every transcript with it when the session ends (OBSERVABILITY.md § 3).
    """
    if not run.get("inputs", {}).get("debug"):
        return None
    return (f"GATHER: python3 {pathlib.Path(__file__).resolve().parent}/gather_debug.py "
            f"{run_dir}   # debug mode - run it BEFORE sync_run.py")


def check_row(run: dict, check_id: str) -> dict | None:
    for c in run.get("checks", []):
        if c.get("id") == check_id:
            return c
    return None


def register_checks(run: dict, entries: list[dict],
                    check_refs: bool = True) -> list[str]:
    """Validate and append check rows; the registered ids, or raises Refuse.

    `check_refs=False` (the definition path) skips the referential `*_from` check:
    validate_definition already held it against the step's `after`, and a dropped
    dependency is the engine's to skip at decision time, not a registration error."""
    sources = {s["id"] for s in run.get("sources", [])}
    known = {c["id"] for c in run.get("checks", [])} | \
        {e.get("id") for e in entries if e.get("id")}
    added = []
    for e in entries:
        cid, kind = e.get("id"), e.get("kind")
        if not cid or not check_playbook.SLUG.match(str(cid)):
            raise Refuse(f"check id {cid!r} is not a slug")
        if check_row(run, cid):
            raise Refuse(f"check id {cid!r} is already registered")
        if kind not in check_playbook.KINDS:
            raise Refuse(f"check {cid}: kind {kind!r} is not in KINDS "
                         f"({', '.join(sorted(check_playbook.KINDS))})")
        srcs = e.get("sources")
        if not isinstance(srcs, list) or not srcs:
            raise Refuse(f"check {cid}: names no sources")
        for s in srcs:
            if s not in sources:
                raise Refuse(f"check {cid}: source {s!r} is not registered")
        problems = check_playbook.check_params(
            kind, e.get("params"), known_checks=known if check_refs else None)
        if problems:
            raise Refuse(f"check {cid}: " + "; ".join(problems))
        run.setdefault("checks", []).append(
            {"id": cid, "kind": kind, "sources": srcs, "goal": e.get("goal") or None,
             "params": e.get("params") or {}, "seq": None, "status": "pending",
             "record": None})
        added.append(cid)
    return added


def steps_as_checks(run: dict, definition: dict, bound: dict) -> tuple[list[str], list[str]]:
    """Register the definition's bound steps as checks; (registered, DROPPED lines)."""
    entries, dropped = [], []
    for st in definition["steps"]:
        unbound = [sl for sl in st["sources"] if sl not in bound]
        if unbound:
            dropped.append(f"DROPPED: {st['id']} — slot {unbound[0]} unbound")
            continue
        entries.append({"id": st["id"], "kind": st["check"],
                        "sources": [bound[sl] for sl in st["sources"]],
                        "goal": st.get("goal"), "params": st.get("params") or {}})
    return register_checks(run, entries, check_refs=False), dropped


def validate_definition(path: pathlib.Path) -> dict:
    skills = PLUGIN_ROOT / "skills"
    problems = check_playbook.validate(path, skills if skills.is_dir() else None)
    if problems:
        raise Refuse(f"{path.name}: {len(problems)} problem(s) - a broken definition "
                     f"goes to the user, not around this gate:\n  " + "\n  ".join(problems))
    return json.loads(path.read_text())


# ---------------------------------------------------------------- subcommands

def cmd_add_checks(a) -> int:
    run_dir = a.run_dir.resolve()
    run = load_run(run_dir)
    try:
        entries = json.loads(a.checks)
    except ValueError as exc:
        raise Refuse(f"--checks is not JSON: {exc}")
    if not isinstance(entries, list) or not entries:
        raise Refuse("--checks must be a non-empty JSON array")
    added = register_checks(run, entries)
    save_run(run_dir, run)
    for cid in added:
        c = check_row(run, cid)
        print(f"registered {cid} kind={c['kind']} sources={','.join(c['sources'])}")
    return 0


def cmd_bind_playbook(a) -> int:
    run_dir = a.run_dir.resolve()
    run = load_run(run_dir)
    if run.get("playbook"):
        raise Refuse(f"run.json.playbook is already {run['playbook'].get('name')!r} - "
                     f"one playbook per run")
    pb_path = a.path.resolve()
    definition = validate_definition(pb_path)
    try:
        bound = json.loads(a.bound)
    except ValueError as exc:
        raise Refuse(f"--bound is not JSON: {exc}")
    slots = {s["slot"] for s in definition["sources"]}
    sources = {s["id"] for s in run.get("sources", [])}
    for sl, sid in bound.items():
        if sl not in slots:
            raise Refuse(f"bound slot {sl!r} is not declared by {definition['name']}")
        if sid not in sources:
            raise Refuse(f"slot {sl}: source {sid!r} is not registered")
    run["playbook"] = {"name": definition["name"], "path": str(pb_path), "bound": bound}
    added, dropped = steps_as_checks(run, definition, bound)
    save_run(run_dir, run)
    print(f"playbook {definition['name']} bound; {len(added)} step(s) registered as checks")
    for line in dropped:
        print(line)
    return 0


def cmd_approve_plan(a) -> int:
    run_dir = a.run_dir.resolve()
    run = load_run(run_dir)
    if (run.get("plan") or {}).get("approved_at"):
        raise Refuse("the plan is already approved")
    def_path = a.definition.resolve()
    definition = validate_definition(def_path)
    # A plan-driven step's worker resolves its procedure from the recipe section
    # `params.family` names (each check-* SKILL.md § Resolve the procedure); without
    # it the worker runs on the goal sentence alone, so the plan is refused here.
    unfamilied = [st["id"] for st in definition["steps"]
                  if not (st.get("params") or {}).get("family")]
    if unfamilied:
        raise Refuse("every plan-driven step carries params.family - the recipe family "
                     "slug its worker executes; missing on: " + ", ".join(unfamilied))
    rows = [d for d in run.get("dispatches", [])
            if d.get("step") == "plan" and d.get("state") == "ok"]
    if not rows:
        raise Refuse("no plan dispatch has ended ok - approval records a drafted plan")
    row = rows[-1]
    recipe = a.recipe or (row.get("args") or {}).get("recipe")
    if not recipe:
        raise Refuse("the plan dispatch args carry no recipe - pass --recipe")
    bound = {sl: sl for sl in (s["slot"] for s in definition["sources"])}
    sources = {s["id"] for s in run.get("sources", [])}
    for sl in bound:
        if sl not in sources:
            raise Refuse(f"definition slot {sl!r} is not a registered source id - a "
                         f"planned playbook's slots are the run's own source ids")
    try:
        rel = str(def_path.relative_to(run_dir))
    except ValueError:
        rel = str(def_path)
    pinned = (run.get("inputs") or {}).get("recipe") or {}
    if pinned and pathlib.Path(str(recipe)).resolve() != pathlib.Path(pinned["path"]).resolve():
        raise Refuse(f"the plan was drafted against {recipe}, not the pinned recipe "
                     f"{pinned['path']} - a run executes the recipe it pinned")
    run["plan"] = {"record": row.get("record"), "recipe": str(recipe),
                   "recipe_name": pinned.get("name"), "recipe_version": pinned.get("version"),
                   "playbook": rel, "approved_at": _now()}
    run["playbook"] = {"name": definition["name"], "path": str(def_path), "bound": bound}
    added, dropped = steps_as_checks(run, definition, bound)
    save_run(run_dir, run)
    _append_event(run_dir, "plan_approved", seq=row.get("seq"),
                  playbook=definition["name"])
    print(f"plan {definition['name']} approved; {len(added)} step(s) registered as checks")
    for line in dropped:
        print(line)
    return 0


def _alloc(run: dict) -> int:
    seq = run["next_seq"]
    run["next_seq"] = seq + 1
    return seq


def _append_dispatch(run: dict, seq: int, step: str, skill: str, args: dict,
                     check_id: str | None, attempt_of: int | None = None) -> dict:
    row = {"seq": seq, "step": step, "check_id": check_id, "skill": skill,
           "args": args, "state": "dispatched", "brief": brief_rel(seq, step),
           "record": f"steps/{seq:04d}-{step}.json", "conclusion": None}
    if attempt_of is not None:
        row["attempt_of"] = attempt_of
    run.setdefault("dispatches", []).append(row)
    return row


def cmd_dispatch(a) -> int:
    run_dir = a.run_dir.resolve()
    run = load_run(run_dir)
    picked = sum(bool(x) for x in (a.checks, a.step, a.briefs))
    if picked != 1:
        raise Refuse("pass exactly one of --checks, --step, --briefs")

    if a.checks:
        ids = [c.strip() for c in a.checks.split(",") if c.strip()]
        extra = json.loads(a.extra) if a.extra else None
        rows: list[tuple[dict, pathlib.Path | None]] = []
        members = []
        for cid in ids:
            c = check_row(run, cid)
            if c is None:
                raise Refuse(f"check {cid!r} is not registered - add-checks first")
            if any(d.get("check_id") == cid and d.get("state") == "dispatched"
                   for d in run.get("dispatches", [])):
                raise Refuse(f"check {cid!r} has an outstanding dispatch - record the "
                             f"wave before dispatching it again")
            members.append(c)
        for c in members:
            seq = _alloc(run)
            args = check_args(c["sources"], c.get("goal"), c.get("params"), a.mode, extra)
            row = _append_dispatch(run, seq, step_name(c["kind"]),
                                   check_playbook.KINDS[c["kind"]], args, c["id"])
            brief = write_row_brief(run_dir, row)
            c["seq"], c["status"] = seq, "pending"
            # A wave of one is a plain Skill call: its NEXT line carries no brief=, and
            # the brief written above is the archived instruction only.
            rows.append((row, brief if len(members) > 1 else None))
        save_run(run_dir, run)
        what = describe_members([(c["id"], c["kind"], c.get("params")) for c in members],
                                recipe_families(run))
        verb = ("Re-running", " on the review's findings") if a.mode == "fix" \
            else ("Running", "")
        print(say_line(f"{verb[0]} {checks_phrase(len(members))}{verb[1]}: {what}."))
        if len(members) > 1:
            print(LAUNCH)
        for row, brief in rows:
            print(next_line(run_dir, row, brief))

    elif a.step:
        if a.step not in STEP_SKILLS:
            raise Refuse(f"--step must be one of {', '.join(STEP_SKILLS)}")
        args = json.loads(a.args) if a.args else {}
        if not isinstance(args, dict):
            raise Refuse("--args must be a JSON object")
        seq = _alloc(run)
        row = _append_dispatch(run, seq, a.step, STEP_SKILLS[a.step], args, None)
        write_row_brief(run_dir, row)
        save_run(run_dir, run)
        print(say_line(step_say(a.step, args)))
        print(next_line(run_dir, row, None))

    else:
        parsed = sorted((parse_brief(p.resolve()) for p in a.briefs),
                        key=lambda b: b["seq"])
        seq0 = run["next_seq"]
        for i, b in enumerate(parsed):
            if b["seq"] != seq0 + i:
                raise Refuse(f"{b['path'].name}: seq {b['seq']} does not continue "
                             f"next_seq={seq0} - stale briefs; re-decide the wave")
        for b in parsed:
            c = check_row(run, b["check"])
            if c is None:
                raise Refuse(f"{b['path'].name}: check {b['check']!r} is not registered "
                             f"- bind-playbook or approve-plan registers the steps")
            _append_dispatch(run, b["seq"], b["step"], b["skill"], b["args"], b["check"])
            c["seq"], c["status"] = b["seq"], "pending"
        run["next_seq"] = seq0 + len(parsed)
        save_run(run_dir, run)
        print(f"recorded {len(parsed)} dispatch(es); next_seq={run['next_seq']}")
    return 0


def parse_brief(path: pathlib.Path) -> dict:
    m = re.fullmatch(r"(\d{4})-([a-z]+)\.md", path.name)
    if not m or not path.is_file():
        raise Refuse(f"{path}: not a dispatch brief (dispatch/<NNNN>-<step>.md)")
    text = path.read_text()
    sk = re.search(r"skills/([a-z-]+)/SKILL\.md", text)
    kv = dict(re.findall(r"^    (\w+)=(.*)$", text, re.M))
    if not sk or "check" not in kv or int(kv.get("seq", -1)) != int(m.group(1)):
        raise Refuse(f"{path}: does not carry the brief template's skill and args")
    args = {"sources": [s for s in kv.get("sources", "").split(",") if s],
            "goal": None if kv.get("goal") in (None, "(none)") else kv["goal"],
            "params": {} if kv.get("params") in (None, "(none)")
            else json.loads(kv["params"]),
            "mode": kv.get("mode", "fresh")}
    return {"path": path, "seq": int(m.group(1)), "step": m.group(2),
            "skill": sk.group(1), "check": kv["check"], "args": args}


def classify_record(run_dir: pathlib.Path, row: dict) -> tuple[str, dict | None, str | None]:
    """(class, record, why): ok | blocked | failed | died, `error` before `outcome` —
    except a record that claims `blocked` AND names its `blockers`, which is blocked
    whatever `error` carries: the step finished and said what stopped it, and a retry
    would re-run the same work (a gate, a missing input) to the same answer.

    The one classifier. `record` classifies outstanding dispatches with it directly;
    playbook_next.py folds terminal ones through it, layering its absent-record
    fallback on top. For died, `record` is None exactly when the file was absent or
    unparseable - the fallback keys on that."""
    rel = row.get("record") or f"steps/{row['seq']:04d}-{row['step']}.json"
    try:
        rec = json.loads((run_dir / rel).read_text())
    except (OSError, ValueError):
        return "died", None, "step record absent or unparseable"
    if rec.get("seq") != row["seq"] or rec.get("step") != row["step"]:
        return "died", rec, (f"record carries seq={rec.get('seq')} "
                             f"step={rec.get('step')!r}, not this dispatch's")
    outcome = rec.get("outcome")
    if rec.get("error"):
        if outcome == "blocked" and rec.get("blockers"):
            return "blocked", rec, None
        return "failed", rec, str(rec["error"])
    if outcome == "complete":
        return "ok", rec, None
    if outcome == "blocked":
        return "blocked", rec, None
    return "died", rec, f"outcome {outcome!r} outside the vocabulary"


def _retry(run_dir: pathlib.Path, run: dict, row: dict) -> dict:
    """Mint the one re-dispatch: same args, new seq, its own brief, attempt_of set."""
    seq = _alloc(run)
    new = _append_dispatch(run, seq, row["step"], row["skill"], row.get("args") or {},
                           row.get("check_id"), attempt_of=row["seq"])
    write_row_brief(run_dir, new)
    if row.get("check_id"):
        c = check_row(run, row["check_id"])
        if c is not None:
            c["seq"], c["status"] = seq, "pending"
    return new


def cmd_record(a) -> int:
    run_dir = a.run_dir.resolve()
    run = load_run(run_dir)
    outstanding = [d for d in run.get("dispatches", []) if d.get("state") == "dispatched"]
    if not outstanding:
        print("nothing outstanding")
        return 0
    lines: list = []          # str, or a minted dispatch row rendered as its RETRY line
    retries: list[dict] = []
    for row in outstanding:
        cls, rec, why = classify_record(run_dir, row)
        row["state"] = cls
        who = row.get("check_id") or row["step"]
        if cls in ("ok", "blocked"):
            row["conclusion"] = (rec or {}).get("conclusion")
            c = check_row(run, row.get("check_id") or "")
            if c is not None:
                c["status"] = "ok" if cls == "ok" else "blocked"
                c["record"] = row["record"]
            if cls == "blocked":
                run["degraded"] = True
            head = "OK" if cls == "ok" else "BLOCKED"
            nb = len((rec or {}).get("blockers") or [])
            lines.append(f"{head}: seq={row['seq']} {who}"
                         + (f" blockers={nb}" if cls == "blocked" else "")
                         + f" — {row['conclusion'] or '(no conclusion)'}")
        elif row.get("attempt_of") is not None:  # the retry itself died: terminal
            run["degraded"] = True
            c = check_row(run, row.get("check_id") or "")
            if c is not None:
                c["status"] = "failed"
            lines.append(f"FAILED: seq={row['seq']} {who} — {why}; second attempt, not "
                         f"retried — tell the user what died and what it blocks")
        else:
            new = _retry(run_dir, run, row)
            retries.append({"seq": new["seq"], "attempt_of": row["seq"],
                            "step": row["step"]})
            lines.append(f"{cls.upper()}: seq={row['seq']} {who} — {why}")
            lines.append(new)
    save_run(run_dir, run)
    for r in retries:
        _append_event(run_dir, "retry", **r)
    # The retries are a wave of their own: two or more launch as sub-agents on their
    # briefs, one is a plain Skill call - the same rule as dispatch.
    briefed = len(retries) > 1
    if retries:
        skill_kind = {v: k for k, v in check_playbook.KINDS.items()}
        minted = [line for line in lines if isinstance(line, dict)]
        what = describe_members(
            [(d.get("check_id") or f"the {d['step']} step", skill_kind.get(d["skill"]),
              (d.get("args") or {}).get("params")) for d in minted],
            recipe_families(run))
        print(say_line(f"Retrying {checks_phrase(len(minted))} that failed: {what}."))
    if briefed:
        print(LAUNCH.replace("NEXT line", "RETRY line"))
    for line in lines:
        print(line if isinstance(line, str) else
              next_line(run_dir, line, run_dir / line["brief"] if briefed else None,
                        label="RETRY"))
    if (g := gather_line(run_dir, run)):
        print(g)
    if retries:
        print(f"THEN: python3 {pathlib.Path(__file__).resolve()} record {run_dir}")
    return 0


def cmd_debug(a) -> int:
    run_dir = a.run_dir.resolve()
    run = load_run(run_dir)
    want = not a.off
    if run.get("inputs", {}).get("debug", False) == want:
        print(f"debug mode is already {'on' if want else 'off'}")
        return 0
    run.setdefault("inputs", {})["debug"] = want
    save_run(run_dir, run)
    _append_event(run_dir, "debug_enabled" if want else "debug_disabled", by="run_state")
    if want:
        print("DEBUG: on - every wave gathers the session transcripts into debug/, and "
              "the preview shows every working paper and the review findings, not only "
              "the engagement preview, the plan, the workbook and the deck. The run "
              "directory will carry prompts, tool arguments and model output; it stays "
              "on this machine (OBSERVABILITY.md § 4). Tell the user once.")
        print(gather_line(run_dir, run))
    else:
        print("DEBUG: off - no further gather. What debug/ already holds stays. The "
              "preview shows only the engagement preview, the plan, the workbook and "
              "the deck from here.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add-checks")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("--checks", required=True)
    p.set_defaults(fn=cmd_add_checks)

    p = sub.add_parser("bind-playbook")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("--path", required=True, type=pathlib.Path)
    p.add_argument("--bound", required=True)
    p.set_defaults(fn=cmd_bind_playbook)

    p = sub.add_parser("approve-plan")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("--definition", required=True, type=pathlib.Path)
    p.add_argument("--recipe", default=None)
    p.set_defaults(fn=cmd_approve_plan)

    p = sub.add_parser("dispatch")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("--checks", default=None)
    p.add_argument("--step", default=None)
    p.add_argument("--args", default=None)
    p.add_argument("--briefs", nargs="*", type=pathlib.Path, default=None)
    p.add_argument("--mode", default="fresh", choices=("fresh", "fix"))
    p.add_argument("--extra", default=None)
    p.set_defaults(fn=cmd_dispatch)

    p = sub.add_parser("record")
    p.add_argument("run_dir", type=pathlib.Path)
    p.set_defaults(fn=cmd_record)

    p = sub.add_parser("debug")
    p.add_argument("run_dir", type=pathlib.Path)
    p.add_argument("--off", action="store_true", help="turn debug mode off")
    p.set_defaults(fn=cmd_debug)

    a = ap.parse_args()
    try:
        return a.fn(a)
    except Refuse as exc:
        return fail(str(exc))
    except ValueError as exc:
        return fail(f"bad JSON argument: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
