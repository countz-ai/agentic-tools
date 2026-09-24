#!/usr/bin/env python3
"""Gather a run's execution trace: what every agent was told, did, and got back.

Copies the session transcripts Claude Code wrote under ~/.claude/projects/ - the session
and every sub-agent it dispatched, located from run.json's session ids - into
<run_dir>/debug/, resolves the parts of them that live outside the transcript file, and
distills the views a debugger reads:

    debug/timeline.jsonl     the ordered stream, one line per event, per dispatch:
                             prompt, the context injected around it, thinking (where the
                             model returned any), assistant text, tool_use with its full
                             input, tool_result with its full output, api_error. This is
                             the reading surface.
    debug/tool_calls.jsonl   one line per tool call - the scannable index over the same
                             calls. A call whose `result` is null never returned.
    debug/errors.jsonl       every error-flagged tool result and every API-error record
    debug/client_reads.jsonl every call that named a registered source path: the tool,
                             the bound where the call states one, the result's size,
                             and `whole` where that size crosses the whole-read mark -
                             the measured side of CONDUCT.md § Reading client files
    debug/transcripts/       the copied transcripts, plus the tool-result bodies Claude
                             Code offloaded out of them
    debug/instructions/      every instruction file and script of the plugin that ran,
                             with a sha256 each, the plugin version and the git sha
    debug/traces/            the PreToolUse/PostToolUse hook trace, when one was written
    debug/file_history/      the pre-edit backup of each run file an agent overwrote
    debug/cli/               the CLI's own --debug-file log, when one is handed in
    debug/manifest.json      what was gathered, when, and what was missing

Four properties this exists to hold:

  Content capture is a MODE, not a default. `setup_run.py --debug` (or `run_state.py
  debug <run_dir>`) turns it on for the whole run; `run_state.py record` then ends every
  wave with the GATHER: line that runs this. Nothing else invokes it.

  The gather happens DURING the run, not after it. A sub-agent's transcript is complete
  when it returns, and a cloud container takes every transcript with it when the session
  ends - so the wave, not the close, is when the trace can still be taken.

  What the transcript points at is copied too. A tool result over Claude Code's inline
  limit is written to <session>/tool-results/<id>.txt with a 2KB preview left behind;
  copying only the .jsonl loses the body of exactly the calls worth reading.

  The run's own files are referenced, never re-copied. A Read of anything already under
  run_dir - a dispatch brief above all - is recorded as its path: the run directory
  already carries that file, and a second copy in the log is bytes the reader must
  diff against the first.

Usage:
    gather_debug.py <run_dir> [--json] [--cli-debug-log <path>]

Exit 0 on success (MISSING lines name sessions with no transcript anywhere); 2 when
run_dir carries no run.json or no session left any transcript to gather.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone

from usage_report import transcripts_for

EXCERPT_CHARS = 2000    # result excerpt in tool_calls.jsonl; the timeline holds the whole
ERROR_CHARS = 20000     # error content in errors.jsonl; the transcript holds the whole
CONTEXT_CHARS = 4000    # injected-context payload; the transcript holds the whole
WHOLE_READ_CHARS = 20000  # a client-file result this long is recorded as a whole read
READ_INPUT_CHARS = 300  # input excerpt kept per client read

# Claude Code's offload marker: the body of an over-limit tool result, written beside the
# transcript with only a preview left inline.
OFFLOAD_RE = re.compile(r"Full output saved to:\s*(\S+\.txt)")

# The dispatch brief a sub-agent is launched against; its seq names the dispatch.
BRIEF_RE = re.compile(r"dispatch/(\d{4})-([a-z-]+)\.md")

# Everything the plugin ships that decides what an agent does. Copied per gather so the
# trace answers "which instructions ran" without a checkout of the right commit.
# The recipe a run executed is not here: it is served or generated per run and sits in
# `<run_dir>/recipes/`, which the run carries itself (RUN_CONTRACT.md).
INSTRUCTION_GLOBS = ("agents/*.md", "skills/*/SKILL.md", "reference/*.md",
                     "reference/*.json", "playbooks/*.json",
                     "scripts/*.py", ".claude-plugin/plugin.json")

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def _iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _text(content) -> str:
    """Tool-result content as one string: str stays; block lists keep their text parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "text" \
                    and isinstance(blk.get("text"), str):
                parts.append(blk["text"])
            else:
                parts.append(json.dumps(blk) if isinstance(blk, dict) else str(blk))
        return "\n".join(parts)
    return json.dumps(content)


def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _in_run(inp, run_dir: pathlib.Path) -> str | None:
    """The run-relative path a tool call reads, when it reads one - else None.

    Only a whole-file read qualifies: its result is a copy of a file the run directory
    already holds. A Bash command that happens to name a run path is computation, and its
    output is kept.
    """
    if not isinstance(inp, dict):
        return None
    raw = inp.get("file_path") or inp.get("notebook_path")
    if not raw:
        return None
    try:
        p = pathlib.Path(str(raw)).resolve()
        return str(p.relative_to(run_dir))
    except (ValueError, OSError):
        return None


def _dispatch_label(first_prompt: str, meta: dict, fallback: str) -> str:
    """`0004-tie` when the launch prompt names a brief; agent type + id otherwise.

    The seq identifies a briefed dispatch. Everything else - a plain Skill call, an
    Explore - is identified by its transcript, because a wave routinely runs several
    agents of the SAME type at once and a bare type would fold them into one lane.
    """
    m = BRIEF_RE.search(first_prompt or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    if fallback == "session":
        return fallback
    ident = fallback.removeprefix("agent-")[:7]
    kind = meta.get("agentType")
    return f"{kind}:{ident}" if kind else fallback


def extract(path: pathlib.Path, session_id: str, meta: dict, fallback: str,
            run_dir: pathlib.Path, offload_dir: pathlib.Path,
            ) -> tuple[str, list[dict], list[dict], list[dict]]:
    """(dispatch label, timeline rows, tool calls, errors) from one transcript.

    The transcript may write one record per content block, so a tool_use id can repeat;
    the first occurrence names the call. A call with no matching result is kept with
    `result` null - a call that never returned is what a stuck dispatch looks like.
    """
    records = [r for r in (_load(line) for line in path.open(encoding="utf-8")) if r]
    prompts = [_text((r.get("message") or {}).get("content"))
               for r in records
               if r.get("type") == "user" and not _has_tool_result(r)]
    dispatch = _dispatch_label(prompts[0] if prompts else "", meta, fallback)

    calls: dict[str, dict] = {}
    order: list[str] = []
    results: dict[str, dict] = {}
    errors: list[dict] = []
    rows: list[dict] = []
    seen_prompt = False

    def row(ts, kind, **fields) -> None:
        rows.append({"ts": ts, "dispatch": dispatch, "session_id": session_id,
                     "kind": kind, **fields})

    for rec in records:
        ts = rec.get("timestamp")
        rtype = rec.get("type")
        msg = rec.get("message") or {}
        content = msg.get("content")
        blocks = content if isinstance(content, list) else []
        if rtype == "attachment":
            att = rec.get("attachment") or {}
            row(ts, "context", attachment=att.get("type"),
                payload=json.dumps(att)[:CONTEXT_CHARS])
        elif rtype == "user":
            if _has_tool_result(rec):
                for blk in blocks:
                    if isinstance(blk, dict) and blk.get("type") == "tool_result":
                        results[blk.get("tool_use_id")] = {
                            "ts": ts, "is_error": bool(blk.get("is_error")),
                            "text": _text(blk.get("content"))}
            else:
                text = _text(content)
                row(ts, "prompt" if not seen_prompt else "user_message", text=text)
                seen_prompt = True
        elif rtype == "assistant":
            head = {"model": msg.get("model"), "message_id": msg.get("id"),
                    "request_id": rec.get("requestId"), "effort": rec.get("effort"),
                    "cli_version": rec.get("version")}
            api_error = bool(rec.get("isApiErrorMessage"))
            for blk in blocks:
                if api_error:
                    break            # the whole record is the error; row it once, below
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "thinking" and blk.get("thinking"):
                    row(ts, "thinking", text=blk["thinking"], **head)
                elif blk.get("type") == "text" and blk.get("text"):
                    row(ts, "text", text=blk["text"], **head)
                elif blk.get("type") == "tool_use" and blk.get("id"):
                    row(ts, "tool_use", tool=blk.get("name"), tool_use_id=blk["id"],
                        input=blk.get("input"), **head)
                    if blk["id"] not in calls:
                        order.append(blk["id"])
                        calls[blk["id"]] = {
                            "ts": ts, "dispatch": dispatch, "session_id": session_id,
                            "tool": blk.get("name"), "tool_use_id": blk["id"],
                            "input": blk.get("input"), "result": None}
            if api_error:
                text = _text(content)
                row(ts, "api_error", text=text, **head)
                errors.append({"ts": ts, "kind": "api_error", "dispatch": dispatch,
                               "session_id": session_id, "content": text[:ERROR_CHARS]})

    for tid in order:
        call, res = calls[tid], results.get(tid)
        if res is None:
            continue
        t0, t1 = _iso(call["ts"]), _iso(res["ts"])
        duration = round((t1 - t0).total_seconds(), 3) if t0 and t1 else None
        text = res["text"]
        body: dict = {}
        held = _in_run(call["input"], run_dir)
        offload = _copy_offload(text, offload_dir)
        if held is not None:
            body = {"elided": "in-run", "path": held}
        elif offload is not None:
            body = {"offloaded_to": offload, "preview": text}
        else:
            body = {"text": text}
        call["result"] = {
            "ts": res["ts"], "duration_s": duration, "is_error": res["is_error"],
            "chars": len(text), "offloaded_to": offload,
            "excerpt": ("(in-run file: %s)" % held) if held else text[:EXCERPT_CHARS]}
        rows.append({"ts": res["ts"], "dispatch": dispatch, "session_id": session_id,
                     "kind": "tool_result", "tool": call["tool"], "tool_use_id": tid,
                     "is_error": res["is_error"], "duration_s": duration,
                     "chars": len(text), **body})
        if res["is_error"]:
            errors.append({"ts": res["ts"], "kind": "tool_error", "dispatch": dispatch,
                           "session_id": session_id, "tool": call["tool"],
                           "tool_use_id": tid, "input": call["input"],
                           "content": text[:ERROR_CHARS]})

    rows.sort(key=lambda r: r.get("ts") or "")
    return dispatch, rows, [calls[t] for t in order], errors


def _load(line: str) -> dict | None:
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        return None                   # a truncated tail is normal on a live file
    return rec if isinstance(rec, dict) else None


def _has_tool_result(rec: dict) -> bool:
    content = (rec.get("message") or {}).get("content")
    return isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def _copy_offload(text: str, dest_dir: pathlib.Path) -> str | None:
    """Copy the offloaded body a result points at; its name under debug/, or None."""
    m = OFFLOAD_RE.search(text[:4000])
    if not m:
        return None
    src = pathlib.Path(m.group(1))
    rel = f"tool-results/{src.name}"
    dest = dest_dir / rel
    if not dest.is_file():
        if not src.is_file():
            return None               # gathered on another machine; the copy is gone
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return rel


def snapshot_instructions(debug: pathlib.Path) -> dict:
    """Copy the plugin's instruction files and scripts, with a sha256 each."""
    dest = debug / "instructions"
    files = {}
    for pattern in INSTRUCTION_GLOBS:
        for src in sorted(PLUGIN_ROOT.glob(pattern)):
            if not src.is_file():
                continue
            rel = src.relative_to(PLUGIN_ROOT)
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
            files[str(rel)] = _sha256(src)
    version = None
    pj = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    if pj.is_file():
        try:
            version = json.loads(pj.read_text(encoding="utf-8")).get("version")
        except json.JSONDecodeError:
            pass
    manifest = {"plugin_root": str(PLUGIN_ROOT), "plugin_version": version,
                "git": _git_state(), "files": files}
    _write_json(dest / "manifest.json", manifest)
    return {"plugin_version": version, "git": manifest["git"], "files": len(files)}


def _git_state() -> dict | None:
    """The plugin's commit and dirty flag, when it sits in a checkout."""
    def run(*args: str) -> str | None:
        try:
            out = subprocess.run(("git", "-C", str(PLUGIN_ROOT), *args),
                                 capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    sha = run("rev-parse", "HEAD")
    if sha is None:
        return None
    status = run("status", "--porcelain", "--", ".")
    return {"sha": sha, "dirty": bool(status)}


def gather_traces(debug: pathlib.Path, session_ids: list[str]) -> list[str]:
    """Copy the hook trace for each session: local tool timing the transcript lacks."""
    src_dir = pathlib.Path.home() / ".claude" / "traces"
    copied = []
    for sid in session_ids:
        src = src_dir / f"{sid}.jsonl"
        if src.is_file():
            dest = debug / "traces" / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append(src.name)
    return copied


def gather_file_history(debug: pathlib.Path, transcripts: list[pathlib.Path],
                        run_dir: pathlib.Path) -> list[dict]:
    """Copy the pre-edit backup of every run file an agent overwrote.

    Claude Code snapshots a file before it edits it, keyed by session under
    ~/.claude/file-history/. Without this a rewritten workpaper leaves only its final
    text, and what the step actually changed is unrecoverable.
    """
    root = pathlib.Path.home() / ".claude" / "file-history"
    index: dict[str, dict] = {}
    for tpath in transcripts:
        for line in tpath.open(encoding="utf-8"):
            if '"trackedFileBackups"' not in line:
                continue
            rec = _load(line)
            if not rec:
                continue
            snap = rec.get("snapshot") or {}
            sid = rec.get("sessionId") or snap.get("sessionId") or tpath.stem
            for key, entry in (snap.get("trackedFileBackups") or {}).items():
                parent = entry.get("realParentDir")
                name = entry.get("backupFileName")
                if not parent or not name:
                    continue
                try:
                    rel = pathlib.Path(parent, pathlib.Path(key).name)\
                        .resolve().relative_to(run_dir)
                except (ValueError, OSError):
                    continue          # outside the run: not this run's history
                src = root / sid / name
                if not src.is_file():
                    continue
                dest = debug / "file_history" / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                index[name] = {"path": str(rel), "backup": name,
                               "version": entry.get("version"),
                               "backup_time": entry.get("backupTime")}
    if index:
        _write_json(debug / "file_history" / "index.json",
                    sorted(index.values(), key=lambda e: (e["path"], e["version"] or 0)))
    return list(index.values())


def _norm(p: str) -> str:
    """A path as matching compares it: NFC (a macOS name typed NFD matches its NFC
    registration), `/` separators (a Windows path, doubled backslashes as JSON writes
    them), `.`/`..` collapsed, no trailing slash."""
    q = unicodedata.normalize("NFC", str(p)).replace("\\\\", "/").replace("\\", "/")
    return os.path.normpath(q).replace("\\", "/") if q else q


def _forms(p: str) -> set[str]:
    """The typed and the resolved form of a path, both normalized: `/tmp/x` and
    `/private/tmp/x`, a symlinked cloud-drive folder and its target."""
    out = {_norm(p)}
    try:
        out.add(_norm(str(pathlib.Path(p).expanduser().resolve())))
    except (OSError, RuntimeError):
        pass
    return out


def _strings(v) -> list[str]:
    """Every string value in a tool input, at any depth."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _strings(x)]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    return []


def _command_paths(cmd: str) -> list[str]:
    """The path-like words of a shell command, a relative one joined to the directory a
    preceding `cd` in the same command moved to (`cd "<room>" && head -5 gl.csv`)."""
    try:
        words = shlex.split(cmd, posix=True)
    except ValueError:
        words = cmd.split()
    out: list[str] = []
    cwd: str | None = None
    for k, w in enumerate(words):
        if k and words[k - 1] == "cd":
            cwd = w if os.path.isabs(os.path.expanduser(w)) or cwd is None \
                else os.path.join(cwd, w)
            out.append(cwd)
            continue
        if w in ("&&", ";", "||", "|") or w.startswith("-"):
            continue
        out.append(w if os.path.isabs(os.path.expanduser(w)) or cwd is None
                   else os.path.join(cwd, w))
    return out


def _source_forms(sources: list[dict]) -> list[tuple[str, set[str], str | None]]:
    """(label, path forms, basename of a file source) per registered source. The label
    is the resolved path, as the record has always named it."""
    out = []
    for s in sources:
        try:
            raw = str(s["path"])
            label = str(pathlib.Path(raw).expanduser().resolve())
        except (KeyError, TypeError, OSError):
            continue
        is_file = pathlib.Path(label).is_file()
        out.append((label, _forms(raw) | _forms(label),
                    unicodedata.normalize("NFC", pathlib.Path(label).name) if is_file else None))
    return out


def _hits(inp: dict, tool: str | None, forms) -> list[str]:
    cands: set[str] = set()
    for v in _strings(inp):
        cands |= _forms(v) if len(v) < 4096 and "\n" not in v else set()
        for w in (_command_paths(v) if tool == "Bash" or "\n" in v or " " in v else []):
            cands |= _forms(w)
    names = {pathlib.PurePosixPath(c).name for c in cands}
    hit = set()
    for label, fs, base in forms:
        if any(c == f or c.startswith(f.rstrip("/") + "/") for c in cands for f in fs) \
                or any(f in _norm(v) for v in _strings(inp) for f in fs) \
                or (base and base in names):
            hit.add(label)
    return sorted(hit)


def client_reads(calls: list[dict], sources: list[dict], tdir: pathlib.Path) -> list[dict]:
    """Every tool call that named a registered source path, with what came back.

    A call names a source when any path in its input — typed or resolved (a symlink,
    `/tmp` vs `/private/tmp`), NFC-normalized, with `/` or `\\` separators, or a relative
    path under a `cd` in the same Bash command — is the source or lies under it, or when
    it names a file source by its file name. Matching errs toward reporting a read.

    `bounded` is read from the call where the tool states its bound - a Read carrying
    `limit` or `pages`, a Bash line that runs peek.py - and null where the transcript
    cannot say. `whole` is measured from the result: the offloaded body's size where
    Claude Code offloaded it, else the inline length, against WHOLE_READ_CHARS. The
    rule this measures is CONDUCT.md § Reading client files.
    """
    forms = _source_forms(sources)
    out: list[dict] = []
    for c in calls:
        inp = c.get("input") or {}
        blob = json.dumps(inp, ensure_ascii=False)
        hit = _hits(inp, c.get("tool"), forms)
        if not hit:
            continue
        tool = c.get("tool")
        bounded = None
        if tool == "Read":
            bounded = bool(inp.get("limit") or inp.get("pages"))
        elif tool == "Bash" and "peek.py" in str(inp.get("command", "")):
            bounded = True
        res = c.get("result") or {}
        chars = int(res.get("chars") or 0)
        if res.get("offloaded_to"):
            body = tdir / str(c.get("session_id")) / res["offloaded_to"]
            if body.is_file():
                chars = max(chars, body.stat().st_size)
        out.append({"ts": c.get("ts"), "dispatch": c.get("dispatch"),
                    "session_id": c.get("session_id"), "tool": tool,
                    "tool_use_id": c.get("tool_use_id"), "sources": hit,
                    "input_excerpt": blob[:READ_INPUT_CHARS], "bounded": bounded,
                    "result_chars": chars, "returned": res != {},
                    "whole": chars >= WHOLE_READ_CHARS})
    return out


def _write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    tmp.replace(path)


def _write_json(path: pathlib.Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_event(run_dir: pathlib.Path, event: str, **fields) -> None:
    line = {"ts": _now(), "event": event, **fields}
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=pathlib.Path)
    ap.add_argument("--json", action="store_true", help="emit the manifest")
    ap.add_argument("--cli-debug-log", type=pathlib.Path, default=None,
                    help="a log written by `claude --debug-file <path>`, copied in")
    a = ap.parse_args()
    run_dir = a.run_dir.expanduser().resolve()

    if not (run_dir / "run.json").is_file():
        print(f"gather_debug: {run_dir} carries no run.json - not a run directory",
              file=sys.stderr)
        return 2
    state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    session_ids = [s["session_id"] for s in state.get("inputs", {}).get("sessions", [])]
    if not session_ids:   # run_id names the directory, never a session - nothing to look up
        print("gather_debug: run.json records no session id - the run was registered "
              "without --session, so there is no transcript to find", file=sys.stderr)
        return 2

    debug = run_dir / "debug"
    tdir = debug / "transcripts"
    sessions, missing = [], []
    timeline, tool_calls, errors = [], [], []
    copied_paths: list[pathlib.Path] = []
    for sid in session_ids:
        found = transcripts_for(sid, fallback_root=tdir)
        if not found:
            missing.append(sid)
            continue
        copied = 0
        for _label, path, meta in found:
            is_sub = path.parent.name == "subagents"
            dest = (tdir / sid / "subagents" / path.name) if is_sub \
                else (tdir / f"{sid}.jsonl")
            if path != dest:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                meta_src = path.with_suffix(".meta.json")
                if meta_src.is_file():
                    shutil.copy2(meta_src, dest.with_suffix(".meta.json"))
            copied += 1
            copied_paths.append(dest)
            fallback = "session" if not is_sub else path.stem
            _d, rows, calls, errs = extract(
                path, sid, meta, fallback, run_dir, tdir / sid)
            timeline += rows
            tool_calls += calls
            errors += errs
        sessions.append({"session_id": sid, "transcripts": copied})

    if not sessions:
        print(f"gather_debug: no transcript for any of {len(missing)} session(s) - "
              f"nothing on this machine and nothing under {tdir}", file=sys.stderr)
        return 2

    timeline.sort(key=lambda r: (r.get("ts") or "", r.get("dispatch") or ""))
    tool_calls.sort(key=lambda c: c.get("ts") or "")
    errors.sort(key=lambda e: e.get("ts") or "")
    _write_jsonl(debug / "timeline.jsonl", timeline)
    _write_jsonl(debug / "tool_calls.jsonl", tool_calls)
    _write_jsonl(debug / "errors.jsonl", errors)
    reads = client_reads(tool_calls, state.get("sources") or [], tdir)
    whole = [r for r in reads if r["whole"]]
    _write_jsonl(debug / "client_reads.jsonl", reads)

    instructions = snapshot_instructions(debug)
    traces = gather_traces(debug, session_ids)
    history = gather_file_history(debug, copied_paths, run_dir)
    cli_log = None
    if a.cli_debug_log and a.cli_debug_log.is_file():
        dest = debug / "cli" / a.cli_debug_log.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a.cli_debug_log, dest)
        cli_log = f"cli/{a.cli_debug_log.name}"

    offloads = sorted(p.name for p in tdir.glob("*/tool-results/*.txt"))
    dispatches = sorted({r["dispatch"] for r in timeline})
    manifest = {"schema": "countz-accounting/debug@2",
                "gathered_at": _now(), "run_id": state.get("run_id"),
                "sessions": sessions, "missing_sessions": missing,
                "dispatches": dispatches, "timeline_rows": len(timeline),
                "tool_calls": len(tool_calls), "errors": len(errors),
                "offloaded_results": len(offloads),
                "client_reads": len(reads), "whole_reads": len(whole),
                "instructions": instructions,
                "traces": traces, "file_history": len(history), "cli_debug_log": cli_log,
                "not_captured": [
                    "the system prompt - Claude Code writes it to no file, and its "
                    "--debug-file log records the request id without the body",
                    "model thinking the API returned without text (a signature only)",
                    "raw API request and response bodies",
                ]}
    _write_json(debug / "manifest.json", manifest)
    _append_event(run_dir, "debug_gathered",
                  sessions=len(sessions), missing=len(missing),
                  tool_calls=len(tool_calls), errors=len(errors),
                  timeline=len(timeline), offloads=len(offloads))

    if a.json:
        print(json.dumps(manifest, indent=2))
        return 0
    n_tr = sum(s["transcripts"] for s in sessions)
    print(f"GATHERED:\t{debug}  ({n_tr} transcript(s), {len(dispatches)} dispatch(es), "
          f"{len(timeline)} timeline row(s), {len(tool_calls)} tool call(s), "
          f"{len(offloads)} offloaded result(s), {len(errors)} error(s), "
          f"{len(reads)} client read(s) of which {len(whole)} whole)")
    for r in whole:
        print(f"WHOLE_READ:\t{r['dispatch']}\t{r['tool']}\t{r['result_chars']} chars\t"
              f"{r['input_excerpt'][:120]}")
    for sid in missing:
        print(f"MISSING:\tsession {sid} - no transcript on this machine or under "
              f"debug/transcripts/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
