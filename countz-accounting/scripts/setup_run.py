#!/usr/bin/env python3
"""Register an countz-accounting workspace: create it, or fold new sources in.

The relay runs this before any dispatch (RUN_CONTRACT.md) — it is
mechanical, not a dispatch: no seq, no step record.

    setup_run.py --output-root <abs> --skill <launcher> --company "<the company>" \
        --goal <goal> --session <session id> --sources '<one-line JSON>' \
        [--params '<one-line JSON>']                       # start a run
    setup_run.py <run_dir> --session <session id> --sources '<one-line JSON>' \
        [--params '<one-line JSON>']                       # fold into / join a run
    setup_run.py ... --recipe <path> [--recipe-version <v>]  # pin the run's recipe

A new run's directory is MINTED here, never named by the relay:
`<output_root>/<skill>-<company>.<YYYYMMDD-HHMMSS>` — `--skill` is the launcher skill
the user invoked (it must name one of this plugin's inline skills), `--company` is the
company whose books the run is over in the user's words (stored verbatim; the folder
carries its slug: accents folded, lower-case, runs of anything but letters and digits
become one hyphen, and a name in a script with no Latin letters becomes `co-<hash>`), and the stamp is the machine's local clock at minting. "Output to results" for
a `qoe` run over Demo ZS lands at `results/qoe-demo-zs.20260904-104305`. The first
stdout line is `RUN_DIR:\t<abs path>`; the relay takes every later `<run_dir>` from it.
An existing run is addressed by that path, and a path that carries no `run.json` is
refused — nothing but a mint creates a run directory.

`--sources` is the relay's collected context, verbatim:
`[{"id": "gl", "path": "<abs>", "name": "<what the user called it>"}, ...]`.

`--params` is the run-level parameters the relay collected, verbatim, as one JSON
object (period end, declared options, materiality, ...). Stored at
`run.json.inputs.params`; a later call merges keys in, and a changed value appends a
`params_set` event.

Every successful call also rewrites `<run_dir>/engagement-preview.md` — the collected
parameters, each source's location, and a directory summary of every folder source
(3 levels deep, file count and KB per directory, hidden entries skipped). The walk is
directory metadata only; preview failure never fails the registration.

`--recipe <path>` pins the recipe the run executes (RUN_CONTRACT.md): the file is read,
its frontmatter `name` taken, and its bytes copied to `<run_dir>/recipes/<name>.md`
unchanged; `run.json.inputs.recipe` records `{name, version, path}`. `--recipe-version`
is the `recipe_version` the connector served with the body (`<image>+<sha256[:12]>`);
the sha is recomputed over the file and a mismatch is refused, so a body edited after it
was served cannot pass as the served one. A recipe packaged by `make zip RECIPES=...`
passes `bundled+<sha256[:12]>`, as `scripts/bundled_recipe.py` prints it. Without `--recipe-version` the recipe is a
generated one (the `create-recipe` step wrote it under `<run_dir>/recipes/` already) and
the version is minted as `generated+<sha256[:12]>`. A run pins one recipe; a second
`--recipe` naming a different one is refused. `run_state.py approve-plan` copies name
and version into `run.json.plan`.

`--debug` turns the run's debug mode on (OBSERVABILITY.md § 3): every wave gathers the
session transcripts into `<run_dir>/debug/`, so the run carries its own execution trace,
and `preview.py` surfaces every artifact rather than only the engagement preview, the
plan, the workbook and the report deck.
It is sticky and it can be passed on a later fold to turn a running run's debug on.

Minting (no `<run_dir>` argument): creates the run directory and its subdirs, seeds
`run.json` per RUN_CONTRACT.md, appends `run_created` to `events.jsonl`; creating needs
at least one source. `<run_dir>` given, `run.json` present: folds the new sources in — a
new id is appended; an id already registered at the same path is a no-op; the same id
at a DIFFERENT path is an error for the relay to put to the user — and appends
`sources_added`; `--sources '[]'` is a pure join (nothing to fold). Either way a
`--session` the run has not seen joins it, with a `session_joined` event on an existing
run. A minted path that already exists and is not empty is refused (two mints in one
second; run it again), and so is a `<run_dir>` without `run.json`: that directory holds
something else, and adopting it is not recoverable.

Reads no client file beyond an existence check on each source path. `run.json` is
written to `.tmp` then renamed. Exit 0 on success; exit 2 on anything refused, with the
reason on stderr.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import unicodedata

RUN_SCHEMA = "countz-accounting/run@1"
SUBDIRS = ("steps", "dispatch", "checks", "workpapers", "sources", "recipes", "out")
RECIPES_DIR = "recipes"
PREVIEW_NAME = "engagement-preview.md"
STAMP = "%Y%m%d-%H%M%S"       # the run directory's stamp: the minting machine's local clock
SKILLS_DIR = pathlib.Path(__file__).resolve().parent.parent / "skills"
WALK_DEPTH = 3                # directory levels shown below each folder source's root
WALK_DIR_CAP = 200            # directory rows per source; the cut is stated

DEBUG_ON = ("DEBUG: on - every wave gathers the session transcripts into debug/, and the "
            "preview shows every working paper and the review findings, not only the "
            "engagement preview, the plan, the workbook and the deck. The run directory "
            "will carry prompts, tool arguments and model output; it stays on this "
            "machine (OBSERVABILITY.md § 4). Tell the user once.")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def _write_json(path: pathlib.Path, obj) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_event(run_dir: pathlib.Path, event: str, **fields) -> None:
    line = {"ts": _now(), "event": event, **fields}
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def _entry(s: dict) -> dict:
    path = pathlib.Path(s["path"]).resolve()
    return {"id": s["id"], "name": s["name"], "path": str(path),
            "kind": "folder" if path.is_dir() else "file"}


def fail(msg: str) -> int:
    print(f"setup_run: {msg}", file=sys.stderr)
    return 2


def slug(text: str) -> str:
    """The company as a directory-name segment. Accents are folded to their base letter
    (NFKD: `Société Générale` -> `societe-generale`), lower-cased, and every run of
    anything but a letter or digit is one hyphen. A name with no Latin letter or digit
    left (`株式会社…`, `Газпром`) becomes `co-` and the first 8 hex of its SHA-256, so
    minting never refuses a company for its script."""
    folded = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    if s:
        return s
    return "co-" + hashlib.sha256(str(text).strip().encode("utf-8")).hexdigest()[:8]


# A source that is a multi-member archive is refused: every citation into it would resolve
# to the archive itself (step_record.py records one file and one mtime for all of them), and
# peek/extract read no member of it. The user extracts it and registers the folder. One
# compressed file (`.csv.gz`) is not an archive: polars reads it.
ARCHIVE = re.compile(r"\.(zip|7z|rar|tar|tgz|tbz2?|txz|tzst|tar\.[a-z0-9]+)$", re.I)
# macOS `st_flags` bit for a file whose content is not on disk (an iCloud / File Provider
# placeholder: Dropbox, OneDrive, Google Drive "online-only").
SF_DATALESS = 0x40000000


def placeholder_reason(p: pathlib.Path) -> str | None:
    """Why a file cannot be read now, or None. A cloud-drive placeholder exists and has a
    size, but its bytes are elsewhere: a read either fails offline or blocks on a
    download mid-step."""
    name = p.name
    if name.startswith(".") and name.endswith(".icloud"):
        return "an iCloud placeholder (not downloaded)"
    try:
        st = p.stat()
    except OSError as exc:
        return f"cannot be read ({exc.strerror or exc})"
    if getattr(st, "st_flags", 0) & SF_DATALESS:
        return "a cloud-drive placeholder (online-only; its content is not on this machine)"
    try:
        with p.open("rb") as fh:
            fh.read(1)
    except OSError as exc:
        return f"cannot be read ({exc.strerror or exc})"
    return None


def source_refusal(sid: str, p: pathlib.Path) -> str | None:
    """The refusal for a file source that cannot be registered as it is, or None."""
    if p.is_file():
        if ARCHIVE.search(p.name):
            return (f"source {sid}: {p.name} is an archive - extract it and register the "
                    f"extracted folder; a citation into an archive would name the archive, "
                    f"not the file it came from")
        why = placeholder_reason(p)
        if why:
            return (f"source {sid}: {p} is {why} - make it available offline (download it "
                    f"in the sync client) and register again")
    return None


def inline_skills() -> set[str] | None:
    """The names of this plugin's `context: inline` skills - the launchers a run may be
    minted for - or None when the script runs away from its plugin tree."""
    if not SKILLS_DIR.is_dir():
        return None
    names: set[str] = set()
    for f in SKILLS_DIR.glob("*/SKILL.md"):
        lines = f.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0].strip() != "---":
            continue
        fm: dict[str, str] = {}
        for line in lines[1:]:
            if line.strip() == "---":
                break
            m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
            if m:
                fm[m.group(1)] = m.group(2).strip()
        if fm.get("context") == "inline" and fm.get("name"):
            names.add(fm["name"])
    return names


def mint_run_dir(output_root: pathlib.Path, skill: str, company: str) -> pathlib.Path:
    stamp = datetime.datetime.now().strftime(STAMP)
    return output_root / f"{skill}-{slug(company)}.{stamp}"


def parse_sources(raw: str) -> list[dict] | str:
    """The validated source list, or the refusal reason as a string."""
    try:
        incoming = json.loads(raw)
    except ValueError as exc:
        return f"--sources is not JSON: {exc}"
    if not isinstance(incoming, list):
        return "--sources must be a JSON array"
    seen: set[str] = set()
    for s in incoming:
        if not isinstance(s, dict) or not all(s.get(k) for k in ("id", "path", "name")):
            return f"each source needs id, path and name: {json.dumps(s)}"
        if s["id"] in seen:
            return f"source id {s['id']!r} appears twice"
        seen.add(s["id"])
        p = pathlib.Path(s["path"])
        if not p.is_absolute():
            return f"source {s['id']}: path is not absolute: {p}"
        if not p.exists():
            return f"source {s['id']}: no such file or folder: {p}"
        if (why := source_refusal(s["id"], p)):
            return why
    return incoming


def parse_params(raw: str | None) -> dict | str:
    """The validated params object, or the refusal reason as a string."""
    if raw is None:
        return {}
    try:
        obj = json.loads(raw)
    except ValueError as exc:
        return f"--params is not JSON: {exc}"
    if not isinstance(obj, dict):
        return "--params must be a JSON object"
    return obj


def recipe_name(text: str) -> str | None:
    """The frontmatter `name` of a recipe document, or None."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^name:\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip("'\"")
    return None


def pin_recipe(run_dir: pathlib.Path, run: dict, src: pathlib.Path,
               version: str | None) -> dict | str:
    """Copy `src` to <run_dir>/recipes/<name>.md unchanged and return the record for
    `run.json.inputs.recipe`, or the refusal reason. A served version's sha must match
    the bytes; a generated recipe is versioned from its bytes."""
    import hashlib
    import shutil
    if not src.is_file():
        return f"--recipe: no such file: {src}"
    data = src.read_bytes()
    name = recipe_name(data.decode("utf-8", "replace"))
    if not name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        return f"--recipe: {src} carries no kebab-case frontmatter `name`"
    digest = hashlib.sha256(data).hexdigest()[:12]
    if version is not None:
        if not version.endswith("+" + digest):
            return (f"--recipe-version {version!r} does not name these bytes "
                    f"(sha256 {digest}) - the file is not the recipe the connector served")
    else:
        version = f"generated+{digest}"
    held = run.get("inputs", {}).get("recipe")
    if held and held.get("name") != name:
        return (f"--recipe: the run already pins {held.get('name')!r}; a run executes one "
                f"recipe")
    dest = run_dir / RECIPES_DIR / f"{name}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.resolve() != src.resolve():
        if dest.exists() and dest.read_bytes() != data:
            return f"--recipe: {dest} exists with different bytes; a pinned recipe is never edited"
        shutil.copyfile(src, dest)
    return {"name": name, "version": version, "path": str(dest)}


def _kb(n: int) -> str:
    return f"{max(1, round(n / 1024)):,}" if n else "0"


def _cell(v) -> str:
    s = v if isinstance(v, str) else json.dumps(v)
    return s.replace("|", "\\|").replace("\n", " ")


def _walk_dirs(root: pathlib.Path) -> tuple[list[tuple[str, int, int]], int]:
    """(rel dir, subtree file count, subtree bytes) rows to WALK_DEPTH, sorted;
    plus how many directories lie deeper. Hidden entries are skipped; stat only."""
    totals: dict[pathlib.Path, list[int]] = {root: [0, 0]}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        d = pathlib.Path(dirpath)
        totals.setdefault(d, [0, 0])
        nfiles = nbytes = 0
        for f in filenames:
            if f.startswith("."):
                continue
            try:
                nbytes += (d / f).stat().st_size
            except OSError:
                continue
            nfiles += 1
        cur = d
        while True:
            t = totals.setdefault(cur, [0, 0])
            t[0] += nfiles
            t[1] += nbytes
            if cur == root:
                break
            cur = cur.parent
    rows, deeper = [], 0
    for d in sorted(totals, key=lambda p: str(p).lower()):
        rel = d.relative_to(root)
        if len(rel.parts) > WALK_DEPTH:
            deeper += 1
            continue
        rows.append(("." if d == root else str(rel) + "/", *totals[d]))
    return rows, deeper


def write_preview(run_dir: pathlib.Path, run: dict) -> None:
    inputs = run.get("inputs", {})
    params = inputs.get("params") or {}
    lines = ["# Engagement preview", ""]
    if inputs.get("company"):
        lines.append(f"**Company:** {inputs['company']}  ")
    lines += [f"**Goal:** {run.get('goal')} — run directory `{run_dir}`.", "",
              "## Parameters", ""]
    if params:
        lines += ["| parameter | value |", "|---|---|"]
        lines += [f"| {_cell(k)} | {_cell(v)} |" for k, v in params.items()]
    else:
        lines.append("None collected.")
    lines += ["", "## Data room"]
    for s in run.get("sources", []):
        path = pathlib.Path(s["path"])
        lines += ["", f"### {s['id']} — {s['name']}", ""]
        if s.get("kind") != "folder":
            size = path.stat().st_size if path.is_file() else 0
            lines.append(f"`{path}` — file, {_kb(size)} KB")
            continue
        rows, deeper = _walk_dirs(path)
        _, files, nbytes = rows[0]
        lines += [f"`{path}` — folder, {files:,} files, {_kb(nbytes)} KB", "",
                  "| directory | files | size (KB) |", "|---|---|---|"]
        lines += [f"| {_cell(rel)} | {n:,} | {_kb(b)} |"
                  for rel, n, b in rows[:WALK_DIR_CAP]]
        def _dirs(n: int) -> str:
            return f"{n:,} director{'y' if n == 1 else 'ies'}"
        notes = []
        if len(rows) > WALK_DIR_CAP:
            notes.append(f"{_dirs(len(rows) - WALK_DIR_CAP)} not listed")
        if deeper:
            notes.append(f"{_dirs(deeper)} deeper than {WALK_DEPTH} levels")
        if notes:
            lines += ["", f"…{'; '.join(notes)} — counted in the rows above."]
    lines += ["", f"Each directory row counts everything beneath it; the listing stops "
                  f"{WALK_DEPTH} levels below each source root."]
    tmp = run_dir / (PREVIEW_NAME + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(run_dir / PREVIEW_NAME)


def refresh_preview(run_dir: pathlib.Path, run: dict) -> None:
    try:
        write_preview(run_dir, run)
        print(f"engagement preview -> {run_dir / PREVIEW_NAME}")
    except Exception as exc:              # the preview never fails the registration
        print(f"setup_run: preview skipped ({type(exc).__name__}: {exc})",
              file=sys.stderr)


def touch_session(run: dict, session_id: str | None, ts: str) -> bool:
    """True when the session is new to this run."""
    if not session_id:
        return False
    sessions = run.setdefault("inputs", {}).setdefault("sessions", [])
    for entry in sessions:
        if entry.get("session_id") == session_id:
            entry["last_seen"] = ts
            return False
    sessions.append({"session_id": session_id, "first_seen": ts, "last_seen": ts})
    return True


# The instructions and code that govern a run.
STAMP_GLOBS = ("reference/*.md", "agents/*.md", "skills/*/SKILL.md", "scripts/*.py",
               "playbook-recipes/*.md", "bundled-recipes/*.md", ".claude-plugin/plugin.json", "plugin.json")


def plugin_stamp() -> dict:
    """The plugin root's version and a content digest per governing file."""
    root = pathlib.Path(__file__).resolve().parent.parent
    version = None
    manifest = root / ".claude-plugin" / "plugin.json"
    if manifest.is_file():
        try:
            version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
        except ValueError:
            pass
    files = {}
    for pat in STAMP_GLOBS:
        for f in sorted(root.glob(pat)):
            if f.is_file():
                files[str(f.relative_to(root))] = hashlib.sha256(f.read_bytes()).hexdigest()[:12]
    tree = hashlib.sha256(
        "".join(f"{k}:{v}\n" for k, v in sorted(files.items())).encode()).hexdigest()[:12]
    return {"version": version, "root": str(root), "tree": tree, "files": files}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=pathlib.Path, nargs="?", default=None,
                    help="an existing run to fold sources into or join; omitted to "
                         "start a run (the directory is minted from --output-root, "
                         "--skill and --company)")
    ap.add_argument("--output-root", default=None,
                    help="where a new run's directory is minted (absolute)")
    ap.add_argument("--skill", default=None,
                    help="the launcher skill the user invoked - one of this plugin's "
                         "inline skills; the first half of the run directory's name")
    ap.add_argument("--company", default=None,
                    help="the company whose books the run is over, in the user's words; "
                         "its slug is the second half of the run directory's name")
    ap.add_argument("--goal", default="checks")
    ap.add_argument("--session", default=None)
    ap.add_argument("--sources", required=True)
    ap.add_argument("--params", default=None,
                    help="run-level parameters collected from the user, one JSON object")
    ap.add_argument("--debug", action="store_true",
                    help="capture the run's execution trace (OBSERVABILITY.md § 3)")
    ap.add_argument("--recipe", type=pathlib.Path, default=None,
                    help="the recipe document to pin: copied unchanged to "
                         "<run_dir>/recipes/<name>.md")
    ap.add_argument("--recipe-version", default=None,
                    help="the recipe_version the connector served with the body; its "
                         "sha must match the file")
    a = ap.parse_args()
    if a.recipe_version and not a.recipe:
        return fail("--recipe-version needs --recipe")

    incoming = parse_sources(a.sources)
    if isinstance(incoming, str):
        return fail(incoming)
    incoming_params = parse_params(a.params)
    if isinstance(incoming_params, str):
        return fail(incoming_params)

    ts = _now()

    if a.run_dir is not None:
        run_dir = a.run_dir.resolve()
        run_path = run_dir / "run.json"
        if not run_path.is_file():
            return fail(f"{run_dir} carries no run.json - an existing run is named by its "
                        f"path, and a new one is minted: leave the path off and pass "
                        f"--output-root, --skill and --company")
        run = json.loads(run_path.read_text(encoding="utf-8"))
        if run.get("schema") != RUN_SCHEMA:
            return fail(f"run.json schema {run.get('schema')!r} is not {RUN_SCHEMA}")
        existing = {s["id"]: s for s in run.get("sources", [])}
        added = []
        for s in incoming:
            cur, new = existing.get(s["id"]), _entry(s)
            if cur is None:
                run.setdefault("sources", []).append(new)
                added.append(new)
            elif cur.get("path") != new["path"]:
                return fail(f"source id {s['id']!r} is already registered at "
                            f"{cur.get('path')} - a different path needs a new id, or "
                            f"the user's say-so")
        if a.goal != run.get("goal"):
            print(f"goal stays {run.get('goal')!r} - the run already carries it")
        for key, val in (("skill", a.skill), ("company", a.company)):
            held = run.get("inputs", {}).get(key)
            if val is not None and val != held:
                print(f"{key} stays {held!r} - the run already carries it")
        joined = touch_session(run, a.session, ts)
        debug_on = a.debug and not run.get("inputs", {}).get("debug")
        if debug_on:
            run.setdefault("inputs", {})["debug"] = True
        params = run.setdefault("inputs", {}).setdefault("params", {})
        params_changed = [k for k, v in incoming_params.items() if params.get(k) != v]
        params.update(incoming_params)
        pinned = None
        if a.recipe is not None:
            pinned = pin_recipe(run_dir, run, a.recipe.resolve(), a.recipe_version)
            if isinstance(pinned, str):
                return fail(pinned)
            run["inputs"]["recipe"] = pinned
        run["updated_at"] = ts
        _write_json(run_path, run)
        if pinned:
            _append_event(run_dir, "recipe_pinned", name=pinned["name"], version=pinned["version"])
            print(f"recipe {pinned['name']} ({pinned['version']}) pinned at {pinned['path']}")
        if added:
            _append_event(run_dir, "sources_added", ids=[s["id"] for s in added])
        if params_changed:
            _append_event(run_dir, "params_set", keys=params_changed)
        if joined:
            _append_event(run_dir, "session_joined", session_id=a.session)
            print(f"session {a.session} joined the run")
        if debug_on:
            _append_event(run_dir, "debug_enabled", by="setup_run")
            print(DEBUG_ON)
        for s in added:
            print(f"registered {s['id']} -> {s['path']} ({s['kind']})")
        print(f"{len(added)} source(s) folded into {run_path}"
              if added else f"nothing new: every source already registered in {run_path}")
        refresh_preview(run_dir, run)
        return 0

    missing = [f for f, v in (("--output-root", a.output_root), ("--skill", a.skill),
                              ("--company", a.company)) if not v]
    if missing:
        return fail(f"a new run needs {', '.join(missing)} - the directory is minted "
                    f"from them; an existing run is named by its path instead")
    output_root = pathlib.Path(a.output_root)
    if not output_root.is_absolute():
        return fail(f"--output-root is not absolute: {output_root}")
    known = inline_skills()
    if known is not None and a.skill not in known:
        return fail(f"--skill {a.skill!r} is not one of this plugin's launchers "
                    f"({', '.join(sorted(known))}) - pass the skill the user invoked, "
                    f"not the goal")
    if known is None and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", a.skill):
        return fail(f"--skill {a.skill!r} is not a skill name")
    if not str(a.company).strip():
        return fail("--company is empty - pass the company's name in the user's words")
    if not incoming:
        return fail("a new run needs at least one source")
    run_dir = mint_run_dir(output_root.resolve(), a.skill, a.company)
    run_path = run_dir / "run.json"
    if run_dir.exists() and any(run_dir.iterdir()):
        return fail(f"{run_dir} already exists and is not empty - a run minted this "
                    f"same second; run the registration again")
    if a.recipe is not None and not a.recipe.is_file():
        return fail(f"--recipe: no such file: {a.recipe}")
    for d in SUBDIRS:
        (run_dir / d).mkdir(parents=True, exist_ok=True)
    print(f"RUN_DIR:\t{run_dir}")
    run = {
        "schema": RUN_SCHEMA,
        "run_id": run_dir.name,
        "goal": a.goal,
        "created_at": ts,
        "updated_at": ts,
        "degraded": False,
        "inputs": {"output_root": str(output_root.resolve()),
                   "run_dir": str(run_dir),
                   "skill": a.skill,
                   "company": a.company,
                   "debug": bool(a.debug),
                   "params": incoming_params,
                   "sessions": []},
        "sources": [_entry(s) for s in incoming],
        "checks": [],
        "playbook": None,
        "plan": None,
        "plugin": plugin_stamp(),
        "dispatches": [],
        "next_seq": 1,
    }
    touch_session(run, a.session, ts)
    pinned = None
    if a.recipe is not None:
        pinned = pin_recipe(run_dir, run, a.recipe.resolve(), a.recipe_version)
        if isinstance(pinned, str):
            return fail(pinned)
        run["inputs"]["recipe"] = pinned
    _write_json(run_path, run)
    _append_event(run_dir, "run_created", run_id=run["run_id"],
                  output_root=run["inputs"]["output_root"],
                  plugin_version=run["plugin"]["version"], plugin_tree=run["plugin"]["tree"])
    if pinned:
        _append_event(run_dir, "recipe_pinned", name=pinned["name"], version=pinned["version"])
        print(f"recipe {pinned['name']} ({pinned['version']}) pinned at {pinned['path']}")
    if a.debug:
        _append_event(run_dir, "debug_enabled", by="setup_run")
        print(DEBUG_ON)
    for s in run["sources"]:
        print(f"registered {s['id']} -> {s['path']} ({s['kind']})")
    print(f"run.json seeded at {run_path}")
    refresh_preview(run_dir, run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
