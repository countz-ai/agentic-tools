#!/usr/bin/env python3
"""Name the run artifacts that are new or changed and worth putting in front of the user.

The relay runs this after every step or wave returns:

    preview.py <run_dir>

and it prints one line per artifact to surface, tab-separated:

    SHOW:\t<abs path>\t<caption>\t<tier>

then, when any `working` line printed, the caption for the one card those files share:

    BUNDLE:\t<caption>

The tier decides how the relay sends (RUN_CONTRACT.md § Every wave). `deliverable` is
what the user rules on or takes away - the plan, the review findings, the sealed
workbook and the report deck, the two deliverables among the final documents - and goes
out as one rendered card each. `working` is everything else - the engagement preview, the source inventory,
the source profiles, the check records, the check schedules, the deck's source
(report.yaml), the run summary - and goes out as ONE attach card per wave carrying every working file the wave
produced, captioned by the BUNDLE line: a run of many checks then costs the conversation
one card per wave, not one per file, and the files stay where they live in the run
directory, which the caption names.

Which entries print depends on the run's debug mode (`run.json.inputs.debug`,
OBSERVABILITY.md § 3). Off - the default - only the engagement preview, the plan, the
sealed workbook and the report deck reach the user (USER_ROSTER); every other entry is
still rendered into the run directory, so the synced copy carries it, but is neither
printed nor recorded as shown - turning debug on mid-run surfaces the working papers
accumulated so far. On, every entry prints.

The lines come out in pipeline order, so the last SHOW line printed - the freshest
artifact - is the one left on the user's screen when the relay sends the bundle first and
the deliverables after it, in order. An artifact is printed once per content version:
what was surfaced is recorded in out/preview/.shown.json keyed by a hash of its sources,
so an unchanged file is never re-named and a rewritten one (a fix round moved a tab or a
check record) is named again. Delete .shown.json to re-surface everything.

Files that read well as they are - the source profiles, the check records, the tabs, the
deck's source, the workbook, the deck - are shown from where they live. Machine records are rendered into
out/preview/ first: the file index becomes room-inventory.md, and the latest review
record becomes findings markdown.

Never exits non-zero and never stops the run: an artifact it cannot read or render is
skipped with a note on stderr, and the rest still print. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
ROOM_FILE_CAP = 120           # rows in the inventory table; the cut is stated

DELIVERABLE = "deliverable"   # one rendered card each
WORKING = "working"           # one attach card per wave, captioned by the BUNDLE line

# The entry kinds that print while the run's debug mode is off: what the user rules on
# or takes away. Debug mode prints every kind.
USER_ROSTER = ("engagement", "plan", "workbook", "report")

# The working tier by entry-key prefix: (singular, plural or None for a one-off, where it
# lives under the run directory). The BUNDLE caption counts each kind present, in
# pipeline order, and names the directories to open.
WORKING_KINDS = {
    "engagement": ("the engagement preview", None, "its root"),
    "room": ("the source inventory", None, "out/preview/"),
    "source": ("source profile", "source profiles", "sources/"),
    "check": ("check record", "check records", "checks/"),
    "tab": ("check schedule", "check schedules", "out/tabs/"),
    "report_plan": ("the deck's plan (report-plan.md)", None, "out/"),
    "report_source": ("the deck's source (report.yaml)", None, "out/"),
    "run_summary": ("the run summary", None, "out/"),
}


def _hash(*parts: bytes) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
        h.update(b"\x00")
    return h.hexdigest()[:16]


def _file_hash(path: pathlib.Path) -> str:
    return _hash(path.read_bytes())


def _load_json(path: pathlib.Path):
    return json.loads(path.read_text())


def _human_bytes(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024
    return ""


def _write_text(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)
    return path


# ---------------------------------------------------------------- renderers

def render_room(run_dir: pathlib.Path) -> pathlib.Path:
    idx = _load_json(run_dir / "file_index.json")
    files = idx.get("files") or []
    totals = idx.get("totals") or {}
    mix = ", ".join(f"{v} {k}" for k, v in sorted((totals.get("by_type") or {}).items(),
                                                  key=lambda kv: -kv[1]))
    lines = ["# Source inventory", "",
             f"{totals.get('files', len(files))} files"
             + (f", {_human_bytes(totals.get('bytes'))}" if totals.get("bytes") else "")
             + (f", {totals['relevant']} relevant" if totals.get("relevant") is not None
                else "")
             + (f", {totals['context']} context" if totals.get("context") else "")
             + (f" — {mix}" if mix else ""), "",
             "| file | folder | type | size | sheets | relevant | why |",
             "|---|---|---|---|---|---|---|"]
    for f in files[:ROOM_FILE_CAP]:
        sheets = ", ".join(f.get("sheets") or [])
        if f.get("unreadable"):
            verdict = "unreadable"
        elif f.get("relevant") == "context":
            verdict = "context"
        elif "relevant" in f:
            verdict = "yes" if f["relevant"] else "set aside"
        else:
            verdict = ""
        lines.append(f"| {f.get('name', '')} | {f.get('folder', '')} | {f.get('ext', '')} "
                     f"| {_human_bytes(f.get('size_bytes'))} | {sheets} "
                     f"| {verdict} | {f.get('why', '')} |")
    if len(files) > ROOM_FILE_CAP:
        lines.append("")
        lines.append(f"…and {len(files) - ROOM_FILE_CAP} more files — the full index is "
                     f"`file_index.json`.")
    return _write_text(run_dir / "out" / "preview" / "room-inventory.md",
                       "\n".join(lines) + "\n")


_SEV_ORDER = {"blocking": 0, "material": 1, "advisory": 2}


def render_findings(rec_path: pathlib.Path, out_path: pathlib.Path,
                    title: str) -> pathlib.Path:
    rec = _load_json(rec_path)
    findings = rec.get("findings") or []
    lines = [f"# {title}", ""]
    if rec.get("conclusion"):
        lines += [str(rec["conclusion"]), ""]
    if not findings:
        lines.append("The review recorded no findings.")
    for sev in ("blocking", "material", "advisory"):
        group = [f for f in findings if f.get("severity") == sev]
        if not group:
            continue
        lines += [f"## {sev.capitalize()} ({len(group)})", ""]
        for f in group:
            tgt = f.get("target") or {}
            where = " · ".join(str(x) for x in (tgt.get("artifact"), tgt.get("locator"))
                               if x)
            head = " — ".join(x for x in (f.get("id"), where) if x)
            lines.append(f"- **{head}**")
            if f.get("observation"):
                lines.append(f"  {str(f['observation']).strip()}")
            routing = ", ".join(str(x) for x in (f.get("fix_kind"), f.get("fix_check"),
                                                 f.get("disposition")) if x)
            if routing:
                lines.append(f"  _{routing}_")
        lines.append("")
    return _write_text(out_path, "\n".join(lines).rstrip() + "\n")


# ---------------------------------------------------------------- the roster

def _latest_record(run_dir: pathlib.Path, pattern: str) -> pathlib.Path | None:
    hits = [p for p in sorted((run_dir / "steps").glob("*.json"))
            if re.fullmatch(pattern, p.name)]
    return hits[-1] if hits else None


def collect(run_dir: pathlib.Path) -> list[tuple]:
    """(key, source hash, render -> path, caption, tier), in pipeline order."""
    entries: list[tuple] = []

    ep = run_dir / "engagement-preview.md"
    if ep.is_file():
        entries.append(("engagement", _file_hash(ep), lambda: ep,
                        "Engagement preview — the collected parameters, the room "
                        "location, and the room's directory shape", WORKING))

    fi = run_dir / "file_index.json"
    if fi.is_file():
        entries.append(("room", _file_hash(fi), lambda: render_room(run_dir),
                        "Source inventory — every file the run indexed, and what was "
                        "judged relevant", WORKING))

    src_dir = run_dir / "sources"
    for prof in sorted(src_dir.glob("*.md")) if src_dir.is_dir() else []:
        entries.append((f"source:{prof.stem}", _file_hash(prof), lambda p=prof: p,
                        f"Source profile — {prof.stem}: what it holds, its grain, and "
                        f"its read-traps", WORKING))

    plan = run_dir / "plan.md"
    if plan.is_file():
        entries.append(("plan", _file_hash(plan), lambda: plan,
                        "The check plan — bindings and the check roster", DELIVERABLE))

    checks_dir = run_dir / "checks"
    for rec in sorted(checks_dir.glob("*.md")) if checks_dir.is_dir() else []:
        entries.append((f"check:{rec.stem}", _file_hash(rec), lambda r=rec: r,
                        f"Check record — {rec.stem}: what was agreed, what differed, "
                        f"and how it resolved", WORKING))

    tabs_dir = run_dir / "out" / "tabs"
    for tab in sorted(tabs_dir.glob("*.xlsx")) if tabs_dir.is_dir() else []:
        entries.append((f"tab:{tab.stem}", _file_hash(tab), lambda t=tab: t,
                        f"Check schedule — {tab.stem}", WORKING))

    rv = _latest_record(run_dir, r"\d+-review\.json")
    if rv is not None:
        entries.append(("review", _file_hash(rv),
                        lambda: render_findings(
                            rv, run_dir / "out" / "preview" / "review-findings.md",
                            "Review findings"),
                        "Review findings — by severity", DELIVERABLE))

    plan_md = run_dir / "out" / "report-plan.md"
    if plan_md.is_file():
        entries.append(("report_plan", _file_hash(plan_md), lambda: plan_md,
                        "The report deck's plan — the story, and the pages that tell it", WORKING))

    spec = run_dir / "out" / "report.yaml"
    if spec.is_file():
        entries.append(("report_source", _file_hash(spec), lambda: spec,
                        "The report deck's source — every figure a reference to the workbook",
                        WORKING))

    summary = run_dir / "out" / "RUN_SUMMARY.md"
    if summary.is_file():
        entries.append(("run_summary", _file_hash(summary), lambda: summary,
                        "Run summary — statuses, open items, and what the run took",
                        WORKING))

    wb = run_dir / "out" / "workbook.xlsx"
    if wb.is_file():
        entries.append(("workbook", _file_hash(wb), lambda: wb,
                        "The deliverable workbook, sealed", DELIVERABLE))

    deck = run_dir / "out" / "report.pptx"
    if deck.is_file():
        entries.append(("report", _file_hash(deck), lambda: deck,
                        "The report deck — executive summary, a page per check, appendices",
                        DELIVERABLE))

    return entries


def bundle_caption(keys: list[str]) -> str:
    """The one caption for this pass's working files: each kind counted, in pipeline
    order, and the run-directory locations to open."""
    counts: dict[str, int] = {}
    for k in keys:
        kind = k.split(":", 1)[0]
        counts[kind] = counts.get(kind, 0) + 1
    parts: list[str] = []
    where: list[str] = []
    for kind, n in counts.items():
        one, many, loc = WORKING_KINDS.get(kind, (kind, None, "."))
        parts.append(one if many is None else f"{n} {one if n == 1 else many}")
        if loc not in where:
            where.append(loc)
    return (f"Working papers: {', '.join(parts)} (in the run directory: "
            f"{', '.join(where)})")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: preview.py <run_dir>", file=sys.stderr)
        return 0
    run_dir = pathlib.Path(sys.argv[1]).resolve()
    if not (run_dir / "run.json").is_file():
        print(f"preview: {run_dir} carries no run.json - nothing to surface",
              file=sys.stderr)
        return 0
    try:
        run = _load_json(run_dir / "run.json")
    except Exception as exc:
        print(f"preview: run.json unreadable ({exc}) - debug mode read as off",
              file=sys.stderr)
        run = {}
    debug = bool(((run.get("inputs") if isinstance(run, dict) else None) or {})
                 .get("debug"))

    state_path = run_dir / "out" / "preview" / ".shown.json"
    try:
        state = _load_json(state_path)
    except Exception:
        state = {}

    dirty = False
    working: list[str] = []
    for key, src_hash, render, caption, tier in collect(run_dir):
        if state.get(key) == src_hash:
            continue
        try:
            path = render()
        except Exception as exc:
            print(f"preview: {key} skipped ({exc})", file=sys.stderr)
            continue
        if not debug and key.split(":", 1)[0] not in USER_ROSTER:
            continue          # rendered for the run directory; not surfaced, not recorded
        print(f"SHOW:\t{path}\t{caption}\t{tier}")
        if tier == WORKING:
            working.append(key)
        state[key] = src_hash
        dirty = True
    if working:
        print(f"BUNDLE:\t{bundle_caption(working)}")

    if dirty:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_name(state_path.name + ".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        tmp.replace(state_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:                       # a preview must never stall the run
        print(f"preview: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
        raise SystemExit(0)
