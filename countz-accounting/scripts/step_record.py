#!/usr/bin/env python3
"""A step's lifecycle (RUN_CONTRACT.md § The step record, OBSERVABILITY.md § 1): the
`step_start` event, the staged tab placed behind its gates, the step record and the
`step_end` event, as one importable module.

Every step opens and closes through this rather than hand-building the record:

    import sys; sys.path.insert(0, "<${CLAUDE_PLUGIN_ROOT}>/scripts")   # the token expanded
    from step_record import start, place_tab, finish

    start(RUN, 10)                   # first act: appends step_start
    ...                              # the work; figures through figures.Ledger
    place_tab(RUN, 10)               # gates out/.staging/<check>.xlsx, renames it into out/tabs/
    finish(RUN, 10, conclusion="...", blockers=[...], notes="...",
           consumed={"checks/a0_population.md": "roster_from: the A0 contract roster"})

or from the shell: `step_record.py start <run_dir> <seq>`, `step_record.py place-tab
<run_dir> <seq>`, `step_record.py finish <run_dir> <seq> --json <fields.json>`.

**What it reads, so the step does not retype it.** `dispatch/<NNNN>-<step>.md`, the brief
the step was launched with, names the step and carries its arguments: the record's
`step`, `check_id` and `args` are read from it verbatim. `started_at` is the `ts` of
the step's own `step_start` line; `completed_at` and the `step_end` `ts` are the moment
the lines are written, and `duration_s` is their difference.

**`consumed`** is every file the step opened, with its mtime (UTC):
- each citation in `workpapers/evidence-<check>.yaml`, resolved to its data-room file
  through `run.json`'s source paths (a `run_artifact` to the run directory), with the
  citation ids it backs as `used_for` — a read the step cited is a read it made;
- the brief, and on a check step the plan definition and the recipe its procedure names;
- whatever the step passes in `consumed` — `{path: used_for}`, relative to the run
  directory or absolute — for a read no citation records: another check's record or
  item table, a source profile, the cache manifest.

**`produced`** is the check's own files that exist and changed since `step_start`:
`checks/<check>.md`, `checks/<check>-*.csv`, `workpapers/*-<check>.yaml`,
`out/tabs/<check>.xlsx`, plus whatever the step passes (a plan, review or report step
names its own).

**`finish` refuses** a record the relay could not classify: an outcome outside
`complete | blocked`, `blocked` with no blocker, a blocker without `what` and `effect`,
an empty conclusion, no `step_start`, a tab still in staging on a `complete` step, or a
second record for the same seq (`rewrite=True` replaces it). `error` is only for work
the step could not do at all; a gate that refused is `blocked` with the gate's output as
the blocker's `what`.

**`place_tab`** runs `check_workbook.py` and `check_prose.py` on the staged tab with
`--run-dir` (WORKBOOK.md § 8) and renames it into `out/tabs/` only when both exit 0;
otherwise it raises GateRefused carrying their output, verbatim, and the tab stays
staged for the author to fix.

Run with no arguments to self-check. Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys

__all__ = ["start", "finish", "place_tab", "brief", "consumed_from_citations",
           "GateRefused", "OUTCOMES"]

SCHEMA = "countz-accounting/step@1"
OUTCOMES = ("complete", "blocked")
SCRIPTS = pathlib.Path(__file__).resolve().parent
KV = re.compile(r"^    (\w+)=(.*)$", re.M)


class GateRefused(RuntimeError):
    """A deliverable gate refused the staged tab; `.output` is what it printed."""

    def __init__(self, output: str):
        super().__init__(output)
        self.output = output


# --- time ------------------------------------------------------------------------------
def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(t: dt.datetime, spec: str = "milliseconds") -> str:
    return t.isoformat(timespec=spec).replace("+00:00", "Z")


def _parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _mtime(p: pathlib.Path) -> str:
    return _iso(dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc), "seconds")


def _append(run_dir: pathlib.Path, line: dict) -> None:
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


# --- the brief -------------------------------------------------------------------------
def brief(run_dir, seq: int) -> dict:
    """{path, step, check, args} from `dispatch/<NNNN>-<step>.md`. `args` is the brief's
    argument block as handed over: `seq` an int, `params` parsed, `(none)` as None."""
    run_dir = pathlib.Path(run_dir)
    hits = sorted((run_dir / "dispatch").glob(f"{int(seq):04d}-*.md"))
    if len(hits) != 1:
        raise ValueError(f"seq {seq}: {len(hits)} dispatch briefs under {run_dir}/dispatch/ "
                         f"- the step's brief is dispatch/{int(seq):04d}-<step>.md")
    path = hits[0]
    step = path.stem.split("-", 1)[1]
    args: dict = {}
    for k, v in KV.findall(path.read_text(encoding="utf-8")):
        v = v.strip()
        if v == "(none)":
            args[k] = None
        elif k == "seq":
            args[k] = int(v)
        elif k == "params":
            args[k] = json.loads(v)
        else:
            args[k] = v
    return {"path": path, "step": step, "check": args.get("check"), "args": args}


def _started(run_dir: pathlib.Path, seq: int, step: str) -> str | None:
    ts = None
    ev = run_dir / "events.jsonl"
    if not ev.is_file():
        return None
    for line in ev.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event") == "step_start" and e.get("seq") == seq and e.get("step") == step:
            ts = e.get("ts")
    return ts


def start(run_dir, seq: int, *, session_id: str | None = None) -> str:
    """Append this step's `step_start`; returns its `ts`. The first act of a step."""
    run_dir = pathlib.Path(run_dir).resolve()
    b = brief(run_dir, seq)
    a = b["args"]
    line = {"ts": _iso(_now()), "event": "step_start", "seq": int(seq), "step": b["step"]}
    if b["check"]:
        line["check"] = b["check"]
    if a.get("sources"):
        line["source"] = a["sources"]
    if a.get("mode"):
        line["mode"] = a["mode"]
    sid = session_id or os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        line["session_id"] = sid
    _append(run_dir, line)
    return line["ts"]


# --- the tab ---------------------------------------------------------------------------
def place_tab(run_dir, seq_or_check) -> pathlib.Path:
    """Gate `out/.staging/<check>.xlsx` and rename it into `out/tabs/` (WORKBOOK.md § 8)."""
    run_dir = pathlib.Path(run_dir).resolve()
    check = brief(run_dir, seq_or_check)["check"] if isinstance(seq_or_check, int) \
        else seq_or_check
    staged = run_dir / "out" / ".staging" / f"{check}.xlsx"
    if not staged.is_file():
        raise FileNotFoundError(f"{staged}: no staged tab")
    out = []
    for gate in ("check_workbook.py", "check_prose.py"):
        r = subprocess.run([sys.executable, str(SCRIPTS / gate), str(staged),
                            "--run-dir", str(run_dir)], capture_output=True, text=True)
        if r.returncode != 0:
            out.append(f"{gate} exit {r.returncode}:\n{(r.stdout + r.stderr).strip()}")
    if out:
        raise GateRefused("\n".join(out))
    dest = run_dir / "out" / "tabs" / staged.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged, dest)
    return dest


# --- consumed and produced ---------------------------------------------------------------
def _run_json(run_dir: pathlib.Path) -> dict:
    p = run_dir / "run.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def _ledger_entries(path: pathlib.Path) -> list[dict]:
    """The entries of an evidence ledger. PyYAML where it is installed (a step run under
    `uv run --project`); otherwise the top-level `id`, `file`, `source` and `file_role`
    read as text, a wrapped plain or quoted value joined back onto its key."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml
        doc = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) or []
        return [e for e in doc if isinstance(e, dict) and e.get("id")]
    except ImportError:
        pass
    out: list[dict] = []
    cur: dict | None = None
    key = None
    for line in text.splitlines():
        m = re.match(r"^(- |  )([a-z_]+):(?:\s(.*))?$", line)
        if m:
            if m.group(1) == "- ":
                cur = {}
                out.append(cur)
            key = m.group(2) if m.group(2) in ("id", "file", "source", "file_role") else None
            if cur is not None and key:
                cur[key] = (m.group(3) or "").strip()
        elif cur is not None and key and line.startswith("    "):
            cur[key] += " " + line.strip()          # a wrapped scalar's continuation
        else:
            key = None
    for e in out:
        for k, v in e.items():
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
                v = v[1:-1].replace("''", "'") if v[0] == "'" else json.loads(v)
            e[k] = None if v in ("null", "~", "") else v
    return [e for e in out if e.get("id")]


def consumed_from_citations(run_dir, check: str) -> dict[pathlib.Path, list[str]]:
    """{absolute path: [citation ids]} for every citation in the check's evidence ledger."""
    run_dir = pathlib.Path(run_dir).resolve()
    roots = {s.get("id"): pathlib.Path(s["path"]) for s in _run_json(run_dir).get("sources", [])
             if s.get("path")}
    out: dict[pathlib.Path, list[str]] = {}
    for e in _ledger_entries(run_dir / "workpapers" / f"evidence-{check}.yaml"):
        f = e.get("file")
        if not f:
            continue
        if e.get("file_role") == "run_artifact" or not e.get("source"):
            p = run_dir / f
        elif e["source"] in roots:
            root = roots[e["source"]]
            p = root / f if root.is_dir() or not root.suffix else root
        else:
            p = pathlib.Path(f)
        out.setdefault(p, []).append(e["id"])
    return out


def _abs(run_dir: pathlib.Path, p) -> pathlib.Path:
    p = pathlib.Path(p)
    return p if p.is_absolute() else run_dir / p


def _cite_list(ids: list[str]) -> str:
    head = ", ".join(ids[:4])
    return f"cited as {head}" + (f" (+{len(ids) - 4} more)" if len(ids) > 4 else "")


def _consumed(run_dir: pathlib.Path, b: dict, extra) -> list[dict]:
    rows: dict[pathlib.Path, list[str]] = {}

    def add(p: pathlib.Path, why: str):
        rows.setdefault(p, [])
        if why not in rows[p]:
            rows[p].append(why)

    add(b["path"], "dispatch brief")
    if b["check"]:
        run = _run_json(run_dir)
        plan = (run.get("playbook") or {}).get("path")
        if plan:
            p = pathlib.Path(plan)
            add(p if p.is_file() else run_dir / "plan" / p.name, "step params")
        recipe = ((run.get("inputs") or {}).get("recipe") or {}).get("path")
        if recipe:
            p = pathlib.Path(recipe)
            add(p if p.is_file() else run_dir / "recipes" / p.name, "the family's procedure")
        for p, ids in consumed_from_citations(run_dir, b["check"]).items():
            add(p, _cite_list(ids))
    for p, why in (extra or {}).items():
        add(_abs(run_dir, p), why)
    out, missing = [], []
    for p, whys in rows.items():
        if not p.exists():
            missing.append(str(p))
            continue
        out.append({"path": str(p), "mtime": _mtime(p), "used_for": "; ".join(whys)})
    if missing:
        raise FileNotFoundError("consumed files that do not exist - a citation or a "
                                "`consumed` path names the wrong file:\n  "
                                + "\n  ".join(missing))
    return out


def _produced(run_dir: pathlib.Path, check: str | None, since: dt.datetime, extra) -> list[str]:
    found: list[pathlib.Path] = []
    if check:
        found += [run_dir / "checks" / f"{check}.md", run_dir / "out" / "tabs" / f"{check}.xlsx"]
        found += sorted((run_dir / "checks").glob(f"{check}-*.csv"))
        found += sorted((run_dir / "workpapers").glob(f"*-{check}.yaml"))
    cut = since.timestamp() - 1
    out = [str(p.relative_to(run_dir)) for p in found
           if p.is_file() and p.stat().st_mtime >= cut]
    for p in extra or ():
        rel = str(_abs(run_dir, p).relative_to(run_dir)) if _abs(run_dir, p).is_relative_to(
            run_dir) else str(p)
        if not _abs(run_dir, p).exists():
            raise FileNotFoundError(f"produced: {p} does not exist")
        if rel not in out:
            out.append(rel)
    return out


# --- the record ------------------------------------------------------------------------
def finish(run_dir, seq: int, *, conclusion: str, outcome: str = "complete",
           error: str | None = None, blockers=(), notes: str = "", consumed=None,
           produced=(), findings=(), cache_defects=(), rewrite: bool = False,
           **extra) -> dict:
    """Write `steps/<NNNN>-<step>.json` and append `step_end`: the last act of a step.
    Extra keyword fields (`fix` on a fix run, per check-tie SKILL § mode: fix) are
    carried into the record as given."""
    run_dir = pathlib.Path(run_dir).resolve()
    b = brief(run_dir, seq)
    step, check = b["step"], b["check"]
    path = run_dir / "steps" / f"{int(seq):04d}-{step}.json"
    if path.exists() and not rewrite:
        raise FileExistsError(f"{path} exists - one record per seq; rewrite=True replaces it")
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome {outcome!r}: one of {', '.join(OUTCOMES)}; the relay "
                         f"classifies, the step never marks itself successful")
    blockers = [dict(x) for x in blockers]
    for x in blockers:
        if not str(x.get("what", "")).strip() or not str(x.get("effect", "")).strip():
            raise ValueError(f"blocker {x}: each carries `what` and `effect`")
    if outcome == "blocked" and not blockers:
        raise ValueError("`blocked` names what stopped the work in `blockers`")
    if not isinstance(conclusion, str) or not conclusion.strip():
        raise ValueError("`conclusion`: what the step established, in at most two sentences")
    for x in cache_defects:
        if not x.get("id") or not x.get("what") or not isinstance(x.get("fix"), str) \
                or not x["fix"].strip():
            raise ValueError(f"cache defect {x}: {{id, what, fix}} - `fix` says in words what "
                             f"the extract step's script must do differently")
    staged = run_dir / "out" / ".staging" / f"{check}.xlsx"
    if check and outcome == "complete" and error is None and staged.exists():
        raise ValueError(f"{staged} is still staged - place_tab() gates it and renames it "
                         f"into out/tabs/ before the record")
    started = _started(run_dir, int(seq), step)
    if started is None:
        raise ValueError(f"no step_start for seq {seq} step {step} in events.jsonl - "
                         f"start() is the step's first act")
    rec = {"schema": SCHEMA, "seq": int(seq), "step": step, "check_id": check,
           "args": b["args"], "started_at": started, "completed_at": None,
           "outcome": outcome, "error": error, "conclusion": conclusion.strip(),
           "produced": _produced(run_dir, check, _parse(started), produced),
           "consumed": _consumed(run_dir, b, consumed),
           "blockers": blockers, "findings": list(findings),
           "cache_defects": [dict(x) for x in cache_defects], "notes": notes}
    rec.update(extra)
    end = _now()
    rec["completed_at"] = _iso(end)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    line = {"ts": rec["completed_at"], "event": "step_end", "seq": int(seq), "step": step,
            "outcome": outcome,
            "duration_s": round((end - _parse(started)).total_seconds(), 1),
            "produced": rec["produced"], "blockers_n": len(blockers)}
    if error:
        line["error"] = str(error)[:200]
    _append(run_dir, line)
    return rec


# --- command line ----------------------------------------------------------------------
def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start", help="append this step's step_start")
    s.add_argument("run_dir", type=pathlib.Path)
    s.add_argument("seq", type=int)
    s.add_argument("--session-id")
    t = sub.add_parser("place-tab", help="gate the staged tab and rename it into out/tabs/")
    t.add_argument("run_dir", type=pathlib.Path)
    t.add_argument("seq", type=int)
    f = sub.add_parser("finish", help="write the step record and append step_end")
    f.add_argument("run_dir", type=pathlib.Path)
    f.add_argument("seq", type=int)
    f.add_argument("--json", type=pathlib.Path, required=True,
                   help="a JSON object of finish()'s fields: conclusion, outcome, blockers, ...")
    f.add_argument("--rewrite", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "start":
            print(start(a.run_dir, a.seq, session_id=a.session_id))
        elif a.cmd == "place-tab":
            print(place_tab(a.run_dir, a.seq))
        else:
            fields = json.loads(a.json.read_text(encoding="utf-8"))
            rec = finish(a.run_dir, a.seq, rewrite=a.rewrite, **fields)
            print(f"steps/{rec['seq']:04d}-{rec['step']}.json: {rec['outcome']}, "
                  f"{len(rec['produced'])} produced, {len(rec['consumed'])} consumed")
    except GateRefused as exc:
        print(exc.output, file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError, FileExistsError, TypeError) as exc:
        print(f"step_record: {exc}", file=sys.stderr)
        return 2
    return 0


# --- self-check --------------------------------------------------------------------------
def _selfcheck() -> int:
    import tempfile
    import time
    bad: list[str] = []
    with tempfile.TemporaryDirectory() as d:
        run = pathlib.Path(d) / "run"
        room = pathlib.Path(d) / "room"
        for sub in ("dispatch", "steps", "checks", "workpapers", "out/.staging", "plan"):
            (run / sub).mkdir(parents=True)
        room.mkdir()
        (room / "gl.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (run / "plan" / "p.json").write_text("{}", encoding="utf-8")
        (run / "run.json").write_text(json.dumps({
            "sources": [{"id": "gl", "path": str(room)}],
            "playbook": {"path": "/elsewhere/plan/p.json"}}), encoding="utf-8")
        (run / "dispatch" / "0007-tie.md").write_text(
            "Your arguments:\n\n    run_dir=/x\n    seq=7\n    check=k1\n    sources=gl\n"
            "    goal=(none)\n    params={\"tolerance\": 1}\n    mode=fresh\n", encoding="utf-8")
        (run / "workpapers" / "evidence-k1.yaml").write_text(
            "- id: E.k1.gl\n  kind: span\n  file: gl.csv\n  source: gl\n"
            "  file_role: system_export\n- id: E.k1.a0\n  kind: span\n"
            "  file: checks/k0.md\n  source: null\n  file_role: run_artifact\n", encoding="utf-8")
        (run / "checks" / "k0.md").write_text("k0", encoding="utf-8")
        (run / "checks" / "k1-old.csv").write_text("x", encoding="utf-8")
        old = time.time() - 3600
        for f in ("checks/k1-old.csv", "workpapers/evidence-k1.yaml"):
            os.utime(run / f, (old, old))

        b = brief(run, 7)
        if (b["step"], b["check"], b["args"]["params"], b["args"]["goal"]) != \
                ("tie", "k1", {"tolerance": 1}, None):
            bad.append(f"brief: {b}")
        try:
            finish(run, 7, conclusion="x")
            bad.append("finished with no step_start")
        except ValueError:
            pass
        start(run, 7)
        (run / "checks" / "k1.md").write_text("record", encoding="utf-8")
        (run / "checks" / "k1-ties.csv").write_text("t", encoding="utf-8")
        (run / "out" / ".staging" / "k1.xlsx").write_text("not a workbook", encoding="utf-8")
        try:
            finish(run, 7, conclusion="x")
            bad.append("finished with the tab still staged")
        except ValueError:
            pass
        try:
            place_tab(run, 7)
            bad.append("placed a tab the gates refuse")
        except GateRefused:
            pass
        (run / "out" / ".staging" / "k1.xlsx").unlink()
        for kw in ({"conclusion": ""}, {"conclusion": "x", "outcome": "ok"},
                   {"conclusion": "x", "outcome": "blocked"},
                   {"conclusion": "x", "blockers": [{"what": "gate"}]},
                   {"conclusion": "x", "consumed": {"sources/none.md": "profile"}}):
            try:
                finish(run, 7, **kw)
                bad.append(f"accepted {kw}")
            except (ValueError, FileNotFoundError):
                pass
        rec = finish(run, 7, conclusion="Tied.", consumed={"checks/k0.md": "roster_from"},
                     notes="n")
        if rec["produced"] != ["checks/k1.md", "checks/k1-ties.csv"]:
            bad.append(f"produced: {rec['produced']}")
        got = {pathlib.Path(c["path"]).name: c["used_for"] for c in rec["consumed"]}
        want = {"0007-tie.md": "dispatch brief", "p.json": "step params",
                "gl.csv": "cited as E.k1.gl", "k0.md": "cited as E.k1.a0; roster_from"}
        if got != want:
            bad.append(f"consumed: {got}")
        ev = [json.loads(x) for x in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        if [e["event"] for e in ev] != ["step_start", "step_end"] or \
                ev[1]["duration_s"] < 0 or ev[0]["check"] != "k1":
            bad.append(f"events: {ev}")
        try:
            finish(run, 7, conclusion="again")
            bad.append("wrote a second record for one seq")
        except FileExistsError:
            pass
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()):
            code = main(["finish", str(run), "7", "--json", str(run / "missing.json")])
        if code == 0:
            bad.append("the CLI finished from a missing file")
    for x in bad:
        print(f"step_record: {x}")
    print("step_record: ok" if not bad else "step_record: self-check FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(_selfcheck() if len(sys.argv) == 1 else main(sys.argv[1:]))
