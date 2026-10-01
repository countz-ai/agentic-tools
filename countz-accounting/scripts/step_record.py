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
`step`, `check_id` and `args` are read from its argument block (`run_state.py`
ARGS_HEAD: one `    <key>=<value>` line per argument, a value that starts with `"` one
JSON string). `started_at` is the `ts` of the step's latest `step_start` line;
`completed_at` and the `step_end` `ts` are the moment the lines are written, and
`duration_s` is their difference. A line of `events.jsonl` that does not parse, is not an
object or carries no readable `ts` is skipped, as every reader of the log skips it.

**The brief is refused**, by every function that reads it, when its argument block holds
a line that is not `    <key>=<value>` (a value spanning lines), a key twice, a `seq`
that is not the file's, a `params` that is not JSON, or a `check` that is not a check id
(`check_playbook.CHECK_ID`, `[a-z0-9][a-z0-9_]*`; RUN_CONTRACT.md § run.json).

**`consumed`** is every file the step opened, with its mtime (UTC), each path absolute
with its directories resolved (a run directory reached through a symlink is one run
directory):
- each citation in `workpapers/evidence-<check>.yaml`, resolved to its data-room file
  through `run.json`'s source paths (the source itself for a `file` source,
  `<path>/<file>` for a folder, the run directory for a `run_artifact`), with the citation
  ids it backs as `used_for`. A citation is refused
  when its `source` is not registered in `run.json`, when a relative `file` has no
  `source` and is not a `run_artifact`, or when YAML reads its `id`, `file` or `source`
  as other than text (e.g. `file: 010` reads as the number 8: quote it). A ledger that is not a YAML
  list of mappings with an `id` is refused;
- the brief, and on a check step the plan definition (`run.json` `playbook.path`) and the
  recipe (`run.json` `plan.recipe`, else `inputs.recipe.path`);
- whatever the step passes in `consumed` — `{path: used_for}`, relative to the run
  directory or absolute, `used_for` in words — for a read no citation records: another
  check's record or item table, a source profile, the cache manifest.
A path that does not exist refuses the record, naming where the path came from.

**`produced`** is the check's own files (`own_files`: `checks/<check>.md`,
`checks/<check>-*.csv`, `workpapers/figures-<check>.yaml`,
`workpapers/evidence-<check>.yaml`, `out/tabs/<check>.xlsx`) that exist and changed since
`step_start`, plus whatever the step passes (a plan, review or report step names its
own), each of which must exist under the run directory. Changed means an mtime at or
after the `step_start` `ts` less MTIME_SLACK; a whole-second mtime (HFS+, FAT, some
network shares) is compared at two-second grain, so a file changed in the tick before
`step_start` counts.

**`finish` refuses** a record the relay could not classify: an outcome outside
`complete | blocked`, `blocked` with no blocker, a blocker without `what` and `effect`,
an empty conclusion, an `error` that is neither None nor a non-empty message, no
`step_start`, a tab still in staging on a `complete` step, or a second record for the
same seq (`rewrite=True` replaces it). It also refuses: `blockers`, `cache_defects`,
`findings` or `produced` that is not a list, an entry of `blockers` or
`cache_defects` that is not a mapping, `notes` that is not a string, `consumed` that is
not a mapping of path to words, and an extra keyword that names a field it derives
(RECORD_FIELDS: `step`, `check_id`, `args`, `started_at`, ...). `error` is only for work
the step could not do at all; a gate that refused is `blocked` with the gate's output as
the blocker's `what`. The record is UTF-8 JSON, written to `.tmp` then renamed; a
character UTF-8 cannot carry (a lone surrogate from a file name that is not UTF-8) is
written as its JSON escape, so it reads back as it was.

**`place_tab`** runs `check_workbook.py` and `check_prose.py` on the staged tab with
`--run-dir` (WORKBOOK.md § 8) and renames it into `out/tabs/` only when both exit 0;
otherwise it raises GateRefused carrying their output, verbatim, and the tab stays
staged for the author to fix. It takes the step's seq (an int) or its check id (a str);
a seq whose brief names no check has no tab and is refused.

Stdlib only (with the sibling `run_state.py` and `check_playbook.py`); PyYAML reads the
evidence ledger where it is installed.
"""
from __future__ import annotations

import argparse
import collections.abc
import datetime as dt
import json
import operator
import os
import pathlib
import re
import subprocess
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import check_playbook  # noqa: E402  sibling: CHECK_ID, the check-id grammar
import run_state  # noqa: E402  sibling: the brief's argument block, written and read back

__all__ = ["start", "finish", "place_tab", "brief", "consumed_from_citations", "own_files",
           "GateRefused", "OUTCOMES", "RECORD_FIELDS"]

SCHEMA = "countz-accounting/step@1"
OUTCOMES = ("complete", "blocked")
# Every field of the record; finish() derives the ones a step does not supply, and refuses an
# extra keyword that would overwrite one.
RECORD_FIELDS = ("schema", "seq", "step", "check_id", "args", "started_at", "completed_at",
                 "outcome", "error", "conclusion", "produced", "consumed", "blockers",
                 "findings", "cache_defects", "notes")
# A file's mtime may trail the wall clock by a kernel tick (Linux stamps files from a
# coarse clock): a file written just after step_start can carry an mtime a few ms before it.
MTIME_SLACK = 0.05


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


def _changed_since(p: pathlib.Path, since: float) -> bool:
    ns = p.stat().st_mtime_ns
    if ns % 1_000_000_000:
        return ns / 1e9 >= since - MTIME_SLACK
    return ns // 1_000_000_000 >= int(since) - 1          # a whole-second filesystem


def _append(run_dir: pathlib.Path, line: dict) -> None:
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


# --- ids and arguments -----------------------------------------------------------------
def _check_id(check) -> str:
    if not isinstance(check, str) or not check_playbook.CHECK_ID.fullmatch(check):
        raise ValueError(f"check id {check!r} is not a check id ([a-z0-9][a-z0-9_]*, no `-`: "
                         f"a check id names its files, and `checks/<check>-<table>.csv` "
                         f"would read a `-` in it as another check's table)")
    return check


def _seq(seq) -> int:
    """A seq as an int: an int (not a bool) or its decimal digits."""
    if isinstance(seq, str) and re.fullmatch(r"[0-9]+", seq):
        return int(seq)
    if isinstance(seq, bool) or not hasattr(seq, "__index__"):
        raise ValueError(f"seq {seq!r} is not a whole number")
    return operator.index(seq)


def _is_list(v) -> bool:
    return isinstance(v, collections.abc.Iterable) and not isinstance(
        v, (str, bytes, os.PathLike, collections.abc.Mapping))


def _mappings(name: str, xs) -> list[dict]:
    if not _is_list(xs):
        raise ValueError(f"`{name}` is a list of mappings, got {type(xs).__name__} {xs!r:.80}")
    out = []
    for x in xs:
        if not isinstance(x, collections.abc.Mapping):
            raise ValueError(f"`{name}` entry {x!r:.80} is not a mapping")
        out.append(dict(x))
    return out


# --- the brief -------------------------------------------------------------------------
def brief(run_dir, seq: int) -> dict:
    """{path, step, check, args} from `dispatch/<NNNN>-<step>.md`. `args` is the brief's
    argument block as handed over: `seq` an int, `params` parsed, `(none)` as None, a
    JSON-string value decoded, any other value its text. Refuses the brief as the module
    docstring states (no brief, two, a malformed block, a `check` outside CHECK_ID)."""
    run_dir = pathlib.Path(run_dir)
    seq = _seq(seq)
    hits = sorted((run_dir / "dispatch").glob(f"{seq:04d}-*.md"))
    if len(hits) != 1:
        raise ValueError(f"seq {seq}: {len(hits)} dispatch briefs under {run_dir}/dispatch/ "
                         f"- the step's brief is dispatch/{seq:04d}-<step>.md")
    path = hits[0]
    step = path.stem.split("-", 1)[1]
    try:
        raw = run_state.parse_brief_args(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from None
    args: dict = {}
    for k, v in raw.items():
        if v is None:
            args[k] = None
        elif k == "seq":
            if not re.fullmatch(r"[0-9]+", v):
                raise ValueError(f"{path}: seq={v!r} is not a whole number")
            args[k] = int(v)
        elif k == "params":
            try:
                args[k] = json.loads(v)
            except ValueError as exc:
                raise ValueError(f"{path}: params is not JSON ({exc})") from None
        else:
            args[k] = v
    if args.get("seq") != seq:
        raise ValueError(f"{path}: carries seq={raw.get('seq')!r}, not {seq}")
    check = args.get("check")
    if check is not None:
        _check_id(check)
    return {"path": path, "step": step, "check": check, "args": args}


def _started(run_dir: pathlib.Path, seq: int, step: str) -> str | None:
    ts = None
    ev = run_dir / "events.jsonl"
    if not ev.is_file():
        return None
    for line in ev.read_bytes().decode("utf-8", errors="replace").split("\n"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict) or e.get("event") != "step_start" \
                or e.get("seq") != seq or e.get("step") != step:
            continue
        try:
            _parse(e["ts"])
        except (KeyError, TypeError, AttributeError, ValueError):
            continue
        ts = e["ts"]
    return ts


def start(run_dir, seq: int, *, session_id: str | None = None) -> str:
    """Append this step's `step_start`; returns its `ts`. The first act of a step. Refuses
    a brief as `brief()` does."""
    run_dir = pathlib.Path(run_dir).resolve()
    seq = _seq(seq)
    b = brief(run_dir, seq)
    a = b["args"]
    line = {"ts": _iso(_now()), "event": "step_start", "seq": seq, "step": b["step"]}
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
    """Gate `out/.staging/<check>.xlsx` and rename it into `out/tabs/` (WORKBOOK.md § 8).
    `seq_or_check` is the step's seq (an int) or its check id (a str, CHECK_ID); a seq
    whose brief names no check is refused."""
    run_dir = pathlib.Path(run_dir).resolve()
    if isinstance(seq_or_check, str):
        check = _check_id(seq_or_check)
    else:
        b = brief(run_dir, _seq(seq_or_check))
        check = b["check"]
        if check is None:
            raise ValueError(f"seq {seq_or_check}: the {b['step']} step names no check, so it "
                             f"has no tab to place")
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
def own_files(run_dir, check: str) -> list[pathlib.Path]:
    """The check's own files that exist, under `run_dir` as given, in this order:
    `checks/<check>.md`, `checks/<check>-*.csv` (sorted), `workpapers/figures-<check>.yaml`,
    `workpapers/evidence-<check>.yaml`, `out/tabs/<check>.xlsx`. Refuses a check id outside
    CHECK_ID."""
    rd = pathlib.Path(run_dir)
    check = _check_id(check)
    found = [rd / "checks" / f"{check}.md"]
    found += sorted((rd / "checks").glob(f"{check}-*.csv"))
    found += [rd / "workpapers" / f"figures-{check}.yaml",
              rd / "workpapers" / f"evidence-{check}.yaml",
              rd / "out" / "tabs" / f"{check}.xlsx"]
    return [p for p in found if p.is_file()]


def _run_json(run_dir: pathlib.Path) -> dict:
    p = run_dir / "run.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


# PyYAML's YAML 1.1 implicit types: a plain scalar spelled like one of these is not text.
_YAML_NULL = re.compile(r"~|null|Null|NULL|")
_YAML_TYPED = re.compile(
    r"yes|Yes|YES|no|No|NO|true|True|TRUE|false|False|FALSE|on|On|ON|off|Off|OFF"
    r"|[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+"
    r"|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+"
    r"|[-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9][0-9_]*(?:[eE][-+][0-9]+)?"
    r"|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)"
    r"|[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}(?:[Tt]|[ \t]+)[0-9]{1,2}:"
    r"[0-9]{2}:[0-9]{2}(?:\.[0-9]*)?(?:[ \t]*(?:Z|[-+][0-9]{1,2}(?::[0-9]{2})?))?")
_DQ_ESC = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v",
           "f": "\f", "r": "\r", "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\",
           "N": "\x85", "_": "\xa0", "L": "\u2028", "P": "\u2029"}
_LEDGER_KEYS = ("id", "file", "source", "file_role")
_TOP_KEY = re.compile(r"(- |  )([A-Za-z_][A-Za-z0-9_]*):(?: (.*))?")


class _Unreadable(ValueError):
    pass


def _fold(lines: list[str], dq: bool) -> str:
    """YAML's line folding of a flow scalar's raw lines: a break between two lines is a
    space, n empty lines are n line feeds, a double-quoted line ending in an escaping `\\`
    joins the next with nothing; each continuation loses its indentation."""
    out, blanks = lines[0], 0
    for line in lines[1:]:
        s = line.strip(" \t")
        if not s:
            blanks += 1
            continue
        tail = len(out) - len(out.rstrip("\\"))
        if dq and tail % 2 and not blanks:
            out = out[:-1] + s
        else:
            out = out.rstrip(" \t") + ("\n" * blanks if blanks else " ") + s
        blanks = 0
    return out


def _dq_decode(body: str) -> str:
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if c == '"':
            raise _Unreadable("an unescaped `\"` inside a double-quoted scalar")
        if c != "\\":
            out.append(c)
            i += 1
            continue
        n = body[i + 1: i + 2]
        width = {"x": 2, "u": 4, "U": 8}.get(n)
        if width:
            hexa = body[i + 2: i + 2 + width]
            if not re.fullmatch(r"[0-9A-Fa-f]+", hexa) or len(hexa) != width:
                raise _Unreadable(f"a bad escape \\{n}{hexa}")
            out.append(chr(int(hexa, 16)))
            i += 2 + width
        elif n in _DQ_ESC:
            out.append(_DQ_ESC[n])
            i += 2
        else:
            raise _Unreadable(f"an unknown escape \\{n}")
    return "".join(out)


def _scalar(key: str, lines: list[str]):
    """One scalar's value from its raw lines, or _Unreadable where YAML reads other than text
    this parser can state."""
    while len(lines) > 1 and not lines[-1].strip():
        lines = lines[:-1]
    first = lines[0].lstrip(" ")
    if first[:1] == '"':
        text = _fold([first] + lines[1:], dq=True).rstrip(" \t")
        if len(text) < 2 or not text.endswith('"') or \
                (len(text[1:-1]) - len(text[1:-1].rstrip("\\"))) % 2:
            raise _Unreadable(f"`{key}` holds a double-quoted scalar that does not close")
        return _dq_decode(text[1:-1])
    if first[:1] == "'":
        text = _fold([first] + lines[1:], dq=False).rstrip(" \t")
        body = text[1:-1]
        if len(text) < 2 or not text.endswith("'") or "'" in body.replace("''", ""):
            raise _Unreadable(f"`{key}` holds a single-quoted scalar that does not close")
        return body.replace("''", "'")
    if first[:1] in ("|", ">", "[", "{", "&", "*", "!"):
        raise _Unreadable(f"`{key}` is a block, flow, anchor or tagged value")
    text = _fold([first] + lines[1:], dq=False).strip(" \t")
    if " #" in text:
        text = text.split(" #", 1)[0].rstrip()
    if _YAML_NULL.fullmatch(text):
        return None
    if _YAML_TYPED.fullmatch(text):
        raise ValueError(f"`{key}: {text}` is read by YAML as a boolean, number or date, not "
                         f"text - quote it")
    return text


def _ledger_text(text: str) -> list[dict]:
    """The top-level `id`, `file`, `source` and `file_role` of each entry, read as text, a
    wrapped scalar folded back onto its key. Raises _Unreadable on a shape it cannot state."""
    out: list[dict] = []
    cur: dict | None = None
    key, buf = None, []

    def close():
        if cur is not None and key:
            cur[key] = _scalar(key, buf)

    for line in text.split("\n"):
        if line.startswith("#") or line in ("---", "...") or (not line.strip() and not key):
            continue
        m = _TOP_KEY.fullmatch(line)
        if m:
            close()
            if m.group(1) == "- ":
                cur = {}
                out.append(cur)
            elif cur is None:
                raise _Unreadable("a key outside a list entry")
            key = m.group(2) if m.group(2) in _LEDGER_KEYS else None
            buf = [m.group(3) or ""]
        elif line.startswith("- ") or line.startswith("-\t") or line == "-":
            raise _Unreadable(f"a list entry that is not `- <key>: ...`: {line[:60]!r}")
        elif key and (line.startswith("    ") or not line.strip()):
            buf.append(line)                        # a wrapped scalar's continuation
        elif line.strip() and not line.startswith(" "):
            raise _Unreadable(f"a top-level line that is not a list entry: {line[:60]!r}")
        else:
            close()
            key = None
    close()
    return out


def _ledger_entries(path: pathlib.Path) -> list[dict]:
    """The entries of an evidence ledger: a YAML list of mappings, each with a text `id`.
    PyYAML where it is installed (a step run under `uv run --project`); otherwise the
    top-level `id`, `file`, `source` and `file_role` read as text by _ledger_text, which
    refuses what it cannot read rather than guess. Refuses a ledger of another shape."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import yaml
    except ImportError:
        try:
            doc = _ledger_text(text)
        except _Unreadable as exc:
            raise ValueError(f"{path}: cannot be read without PyYAML ({exc}) - run the step "
                             f"under `uv run --project ${{CLAUDE_PLUGIN_ROOT}}`") from None
    else:
        try:
            doc = yaml.load(text, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        except yaml.YAMLError as exc:
            raise ValueError(f"{path}: does not parse as YAML: "
                             f"{str(exc).splitlines()[0]}") from None
    if doc is None:
        return []
    if not isinstance(doc, list):
        raise ValueError(f"{path}: the ledger is not a YAML list (EVIDENCE.md § 0)")
    for n, e in enumerate(doc, 1):
        if not isinstance(e, dict) or not isinstance(e.get("id"), str) or not e["id"]:
            raise ValueError(f"{path}: entry {n} is not a mapping with a text `id`")
        for k in ("file", "source"):
            if e.get(k) is not None and not isinstance(e[k], str):
                raise ValueError(f"{path}: {e['id']}: `{k}: {e[k]!r}` is read by YAML as "
                                 f"{type(e[k]).__name__}, not text - quote it")
    return doc


def _abs(run_dir: pathlib.Path, p) -> pathlib.Path:
    """`p` absolute (relative to the run directory), its directories resolved and its own
    name kept, so a run directory reached through a symlink or a `..` is one path."""
    p = pathlib.Path(p)
    p = p if p.is_absolute() else run_dir / p
    if p.name in ("", ".", ".."):
        return p.resolve()
    return p.parent.resolve() / p.name


def consumed_from_citations(run_dir, check: str) -> dict[pathlib.Path, list[str]]:
    """{absolute path: [citation ids]} for every citation in the check's evidence ledger.
    Refuses a check id outside CHECK_ID and a citation it cannot resolve to one file, as
    the module docstring states."""
    run_dir = pathlib.Path(run_dir).resolve()
    check = _check_id(check)
    ledger = run_dir / "workpapers" / f"evidence-{check}.yaml"
    roots = {s.get("id"): s for s in _run_json(run_dir).get("sources", []) if s.get("path")}
    out: dict[pathlib.Path, list[str]] = {}
    for e in _ledger_entries(ledger):
        f = e.get("file")
        if not f:
            continue
        src = e.get("source")
        if e.get("file_role") == "run_artifact":
            p = run_dir / f
        elif not src:
            if not pathlib.Path(f).is_absolute():
                raise ValueError(f"{ledger.name}: {e['id']} cites the relative file {f!r} with "
                                 f"no `source` - name the source it sits under, or "
                                 f"`file_role: run_artifact` for a file the run wrote")
            p = pathlib.Path(f)
        elif src in roots:
            root, kind = pathlib.Path(roots[src]["path"]), roots[src].get("kind")
            is_file = kind == "file" if kind in ("file", "folder") else root.is_file()
            p = root if is_file else root / f
        else:
            raise ValueError(f"{ledger.name}: {e['id']} names source {src!r}, which run.json "
                             f"does not register (registered: {sorted(roots) or 'none'})")
        out.setdefault(_abs(run_dir, p), []).append(e["id"])
    return out


def _cite_list(ids: list[str]) -> str:
    head = ", ".join(ids[:4])
    return f"cited as {head}" + (f" (+{len(ids) - 4} more)" if len(ids) > 4 else "")


def _consumed(run_dir: pathlib.Path, b: dict, extra) -> list[dict]:
    if extra is not None and not isinstance(extra, collections.abc.Mapping):
        raise ValueError(f"`consumed` is a mapping {{path: used_for}}, got "
                         f"{type(extra).__name__}")
    rows: dict[pathlib.Path, list[str]] = {}
    origin: dict[pathlib.Path, str] = {}

    def add(p: pathlib.Path, why: str, where: str):
        rows.setdefault(p, [])
        origin.setdefault(p, where)
        if why not in rows[p]:
            rows[p].append(why)

    add(_abs(run_dir, b["path"]), "dispatch brief", "the brief")
    if b["check"]:
        run = _run_json(run_dir)
        plan = (run.get("playbook") or {}).get("path")
        if plan:
            p = pathlib.Path(plan)
            add(_abs(run_dir, p if p.is_file() else run_dir / "plan" / p.name), "step params",
                f"run.json playbook.path {plan}, nor plan/{p.name}")
        recipe = (run.get("plan") or {}).get("recipe") or \
            ((run.get("inputs") or {}).get("recipe") or {}).get("path")
        if recipe:
            p = pathlib.Path(recipe)
            add(_abs(run_dir, p if p.is_file() else run_dir / "recipes" / p.name),
                "the family's procedure", f"run.json's recipe {recipe}, nor recipes/{p.name}")
        for p, ids in consumed_from_citations(run_dir, b["check"]).items():
            add(p, _cite_list(ids), f"a citation ({', '.join(ids[:4])})")
    for p, why in (extra or {}).items():
        if not isinstance(why, str) or not why.strip():
            raise ValueError(f"`consumed` {p}: `used_for` is what the read was for, in words")
        add(_abs(run_dir, p), why.strip(), "`consumed`")
    out, missing = [], []
    for p, whys in rows.items():
        if not p.exists():
            missing.append(f"{p} (from {origin[p]})")
            continue
        out.append({"path": str(p), "mtime": _mtime(p), "used_for": "; ".join(whys)})
    if missing:
        raise FileNotFoundError("consumed files that do not exist:\n  " + "\n  ".join(missing))
    return out


def _produced(run_dir: pathlib.Path, check: str | None, since: dt.datetime, extra) -> list[str]:
    if not _is_list(extra):
        raise ValueError(f"`produced` is a list of paths, got {type(extra).__name__} "
                         f"{extra!r:.80}")
    cut = since.timestamp()
    out = [str(p.relative_to(run_dir)) for p in (own_files(run_dir, check) if check else [])
           if _changed_since(p, cut)]
    for p in extra:
        q = _abs(run_dir, p)
        if not q.exists():
            raise FileNotFoundError(f"produced: {p} does not exist")
        try:
            rel = str(q.relative_to(run_dir))
        except ValueError:
            raise ValueError(f"produced: {p} is outside the run directory {run_dir} - a step "
                             f"writes only under it") from None
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
    carried into the record as given, each JSON-serializable; one that names a field
    finish() derives (RECORD_FIELDS) is refused. Every refusal is in the module docstring;
    a refused call writes nothing."""
    run_dir = pathlib.Path(run_dir).resolve()
    seq = _seq(seq)
    clash = sorted(set(extra) & set(RECORD_FIELDS))
    if clash:
        raise ValueError(f"{', '.join(clash)}: derived by finish() from the brief, "
                         f"events.jsonl and the files - a step passes only what no file "
                         f"records")
    b = brief(run_dir, seq)
    step, check = b["step"], b["check"]
    path = run_dir / "steps" / f"{seq:04d}-{step}.json"
    if path.exists() and not rewrite:
        raise FileExistsError(f"{path} exists - one record per seq; rewrite=True replaces it")
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome {outcome!r}: one of {', '.join(OUTCOMES)}; the relay "
                         f"classifies, the step never marks itself successful")
    if error is not None and (not isinstance(error, str) or not error.strip()):
        raise ValueError(f"`error` {error!r}: None, or what stopped the step from doing its "
                         f"work at all, in words - never empty")
    blockers = _mappings("blockers", blockers)
    for x in blockers:
        if not str(x.get("what", "")).strip() or not str(x.get("effect", "")).strip():
            raise ValueError(f"blocker {x}: each carries `what` and `effect`")
    if outcome == "blocked" and not blockers:
        raise ValueError("`blocked` names what stopped the work in `blockers`")
    if not isinstance(conclusion, str) or not conclusion.strip():
        raise ValueError("`conclusion`: what the step established, in at most two sentences")
    if not isinstance(notes, str):
        raise ValueError(f"`notes` is text, got {type(notes).__name__}")
    cache_defects = _mappings("cache_defects", cache_defects)
    for x in cache_defects:
        if not x.get("id") or not x.get("what") or not isinstance(x.get("fix"), str) \
                or not x["fix"].strip():
            raise ValueError(f"cache defect {x}: {{id, what, fix}} - `fix` says in words what "
                             f"the extract step's script must do differently")
    if not _is_list(findings):
        raise ValueError(f"`findings` is a list, got {type(findings).__name__}")
    findings = list(findings)
    staged = run_dir / "out" / ".staging" / f"{check}.xlsx"
    if check and outcome == "complete" and error is None and staged.exists():
        raise ValueError(f"{staged} is still staged - place_tab() gates it and renames it "
                         f"into out/tabs/ before the record")
    started = _started(run_dir, seq, step)
    if started is None:
        raise ValueError(f"no step_start for seq {seq} step {step} in events.jsonl - "
                         f"start() is the step's first act")
    rec = {"schema": SCHEMA, "seq": seq, "step": step, "check_id": check,
           "args": b["args"], "started_at": started, "completed_at": None,
           "outcome": outcome, "error": error, "conclusion": conclusion.strip(),
           "produced": _produced(run_dir, check, _parse(started), produced),
           "consumed": _consumed(run_dir, b, consumed),
           "blockers": blockers, "findings": findings,
           "cache_defects": cache_defects, "notes": notes}
    rec.update(extra)
    end = _now()
    rec["completed_at"] = _iso(end)
    data = json.dumps(rec, indent=1, ensure_ascii=False).encode("utf-8", "backslashreplace")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    line = {"ts": rec["completed_at"], "event": "step_end", "seq": seq, "step": step,
            "outcome": outcome,
            "duration_s": round((end - _parse(started)).total_seconds(), 1),
            "produced": rec["produced"], "blockers_n": len(blockers)}
    if error:
        line["error"] = error[:200]
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
            if not isinstance(fields, dict):
                raise ValueError(f"{a.json}: a JSON object of finish()'s fields")
            rec = finish(a.run_dir, a.seq, rewrite=a.rewrite, **fields)
            print(f"steps/{rec['seq']:04d}-{rec['step']}.json: {rec['outcome']}, "
                  f"{len(rec['produced'])} produced, {len(rec['consumed'])} consumed")
    except GateRefused as exc:
        print(exc.output, file=sys.stderr)
        return 1
    except (ValueError, OSError, TypeError) as exc:
        print(f"step_record: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
