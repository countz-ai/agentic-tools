#!/usr/bin/env python3
"""Validate countz-accounting playbook files, and list a playbook library.

A playbook file is a declaration the playbook engine executes and the relay binds; a broken one
fails at its next run, in front of the user. This script is the mechanical gate:
`playbook-save` runs it before leaving a file in the library,
`playbook-next` runs it before deciding a wave, and `check-plugin.py` runs it over the
playbooks the plugin ships.

It is also the single home of the check kind-to-skill map (`KINDS`) and of the
per-kind params contract (`PARAMS`, enforced by `check_params` — run_state.py applies it
at check registration too, so the interactive path and the definition path refuse the
same shapes). The format document (reference/PLAYBOOKS.md) explains the fields; this
file enforces them. Adding a check kind means adding a worker skill and a `KINDS` row —
plus a `PARAMS` row where the kind requires params — in the same change.

Usage:
    check_playbook.py <file.json> [more files...] [--skills-dir DIR]
    check_playbook.py --list <dir> [more dirs...]

Validation exits 0 clean, 1 on any problem, 2 on a usage error. --list prints one line
per playbook found — name, origin, title, steps — flags files that fail validation, and
marks a name shadowed by an earlier directory; it exits 0. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# kind -> the worker skill that performs it. The playbook engine resolves dispatches
# through this map; a kind absent here is not dispatchable anywhere in the plugin.
KINDS = {
    "tieout": "check-tie",
    "recon": "check-recon",
    "completeness": "check-completeness",
    "vouch": "check-vouch",
    "cutoff": "check-cutoff",
    "analysis": "check-analyze",
}

# kind -> the params contract check_params enforces. `required`: keys every step or
# check of the kind must carry; `one_of`: key groups of which at least one must be
# fully present. What each key MEANS lives in the kind's SKILL.md; this table only
# refuses a declaration the dispatched step would refuse anyway, at validation time
# instead of mid-run. A kind absent here has no required params.
PARAMS = {
    "vouch": {"one_of": [["items_from"],
                         ["items_file", "items_sheet", "items_range"]]},
    "cutoff": {"required": ["period_end", "window_days"]},
}

# The most steps one recipe family may be planned as before the definition must say why.
# A family's entities are planned as one step over all of them: each entity needs the same
# recipe section, the same profile, the same binding and the same arithmetic, so one worker
# establishes that once and runs the entities in code (check-plan SKILL.md § 3). Splitting
# on a measured fact is allowed above this count and named in `params.split_reason`;
# splitting on entity count alone is what this refuses. Measured 2026-09-14 on
# cash-demo-dgii: 13 accounts planned as 13 C2 steps, 13 C4, 10 C6 and 6 C5 — 42 dispatches
# and 42 workbook tabs for four families.
FAMILY_STEP_MAX = 4

SCHEMA = "countz-accounting/playbook@1"
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# A playbook is run again, over another company and another period, so its title names the
# work alone. A period in it — `FY2023`, `2023-09-30`, `September 2023` — dates the file.
PERIOD_TOKEN = re.compile(
    r"\b(?:FY|CY)\s?(?:19|20)?\d\d\b|\b(?:19|20)\d\d\b|\b\d{4}-\d{2}-\d{2}\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,4}\b", re.I)


def check_params(kind: str, params, *, after: list | None = None,
                 known_checks: set | None = None) -> list[str]:
    """Problems with one step's or check's params under the kind's PARAMS contract.

    `after`: a definition step's declared dependencies — every key ending `_from` must
    name one, or a list of them (PLAYBOOKS.md: a dependency read is declared, never
    discovered). `known_checks`: for an interactively registered check — every `_from`
    value must name a registered check.
    Pass neither to check shape only (the definition path re-registering steps whose
    references validate() already held)."""
    if kind not in KINDS:
        return []                     # unknown kind is its own, separate problem
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return [f"has non-object `params`: {params!r}"]
    bad: list[str] = []
    spec = PARAMS.get(kind, {})
    for key in spec.get("required", []):
        if not params.get(key):
            bad.append(f"kind `{kind}` requires `params.{key}`")
    groups = spec.get("one_of")
    if groups and not any(all(params.get(k) for k in g) for g in groups):
        alts = " or ".join("+".join(g) for g in groups)
        bad.append(f"kind `{kind}` requires params naming its item source: {alts}")
    wd = params.get("window_days")
    if wd is not None and (isinstance(wd, bool)
                           or not isinstance(wd, (int, float)) or wd <= 0):
        bad.append(f"`params.window_days` must be a positive number of days each side, "
                   f"got {wd!r}")
    pe = params.get("period_end")
    if pe is not None and (not isinstance(pe, str) or not pe.strip()):
        bad.append(f"`params.period_end` must be a date string, got {pe!r}")
    ents = params.get("entities")
    if ents is not None and (not isinstance(ents, list) or not ents
                             or not all(isinstance(e, str) and e.strip() for e in ents)):
        bad.append(f"`params.entities` must be a non-empty list of entity ids, got "
                   f"{ents!r}")
    sr = params.get("split_reason")
    if sr is not None and (not isinstance(sr, str) or not sr.strip()):
        bad.append(f"`params.split_reason` must be the measured fact that split the "
                   f"family, got {sr!r}")
    for key, val in params.items():
        if not key.endswith("_from") or val is None:
            continue
        refs = val if isinstance(val, list) else [val]
        if not refs or not all(isinstance(r, str) and SLUG.match(r) for r in refs):
            bad.append(f"`params.{key}` must be a check id slug or a list of them, "
                       f"got {val!r}")
            continue
        for ref in refs:
            if after is not None and ref not in after:
                bad.append(f"`params.{key}` names `{ref}`, which is not in `after` - "
                           f"a dependency read is declared, never discovered")
            elif known_checks is not None and ref not in known_checks:
                bad.append(f"`params.{key}` names `{ref}`, which is not a registered "
                           f"check")
    return bad


def validate(path: pathlib.Path, skills_dir: pathlib.Path | None) -> list[str]:
    bad: list[str] = []
    try:
        doc = json.loads(path.read_text())
    except Exception as exc:
        return [f"{path}: not valid JSON ({exc})"]
    if not isinstance(doc, dict):
        return [f"{path}: top level is not an object"]

    if doc.get("schema") != SCHEMA:
        bad.append(f"{path}: schema is {doc.get('schema')!r}, expected {SCHEMA!r}")
    name = doc.get("name")
    if not name or not SLUG.match(str(name)):
        bad.append(f"{path}: `name` must be a lowercase slug, got {name!r}")
    elif path.stem != name:
        bad.append(f"{path}: file is named {path.stem!r} but declares name {name!r} - "
                   f"lookup is by name, so the two must match")
    for key, title in (("title", doc.get("title")),
                       ("report.title", (doc.get("report") or {}).get("title") if isinstance(doc.get("report"), dict) else None)):
        if key == "title" and not title:
            bad.append(f"{path}: has no `title`")
        elif title:
            m = PERIOD_TOKEN.search(str(title))
            if m:
                bad.append(f"{path}: `{key}` carries a period (`{m.group(0)}`) - a playbook runs again "
                           f"over another period, and the run carries the period the report prints")

    slots: set[str] = set()
    srcs = doc.get("sources")
    if not isinstance(srcs, list) or not srcs:
        bad.append(f"{path}: `sources` must be a non-empty list")
        srcs = []
    for s in srcs:
        slot = (s or {}).get("slot") if isinstance(s, dict) else None
        if not slot or not SLUG.match(str(slot)):
            bad.append(f"{path}: source entry {s!r} has no valid `slot`")
            continue
        if slot in slots:
            bad.append(f"{path}: slot `{slot}` is declared twice")
        slots.add(slot)
        if not s.get("name"):
            bad.append(f"{path}: slot `{slot}` has no `name` - the binding conversation "
                       f"shows it to the user")

    steps = doc.get("steps")
    if not isinstance(steps, list) or not steps:
        bad.append(f"{path}: `steps` must be a non-empty list")
        steps = []
    ids: set[str] = set()
    referenced_slots: set[str] = set()
    for st in steps:
        if not isinstance(st, dict):
            bad.append(f"{path}: step entry {st!r} is not an object")
            continue
        sid = st.get("id")
        if not sid or not SLUG.match(str(sid)):
            bad.append(f"{path}: step entry has no valid `id`: {st!r}")
            continue
        if sid in ids:
            bad.append(f"{path}: step id `{sid}` is declared twice")
        ids.add(sid)
        kind = st.get("check")
        if kind not in KINDS:
            bad.append(f"{path}: step `{sid}` has check kind {kind!r}; known kinds: "
                       f"{', '.join(sorted(KINDS))}")
        elif skills_dir is not None \
                and not (skills_dir / KINDS[kind] / "SKILL.md").is_file():
            bad.append(f"{path}: step `{sid}` kind `{kind}` maps to skill "
                       f"`{KINDS[kind]}`, which has no SKILL.md under {skills_dir}")
        st_sources = st.get("sources")
        if not isinstance(st_sources, list) or not st_sources:
            bad.append(f"{path}: step `{sid}` names no `sources`")
        else:
            for sl in st_sources:
                referenced_slots.add(sl)
                if sl not in slots:
                    bad.append(f"{path}: step `{sid}` uses slot `{sl}`, which is not "
                               f"declared")
        if not isinstance(st.get("after", []), list):
            bad.append(f"{path}: step `{sid}` has a non-list `after`")

    for st in steps:
        if not isinstance(st, dict) or not st.get("id"):
            continue
        for p in check_params(st.get("check"), st.get("params"),
                              after=st.get("after") or []):
            bad.append(f"{path}: step `{st['id']}` {p}")
        for dep in st.get("after") or []:
            if dep == st["id"]:
                bad.append(f"{path}: step `{st['id']}` depends on itself")
            elif dep not in ids:
                bad.append(f"{path}: step `{st['id']}` is after `{dep}`, which is not a "
                           f"declared step")

    # A family fanned out one step per entity: refused above FAMILY_STEP_MAX unless every
    # step of that family names the measured fact that split it.
    families: dict[str, list[str]] = {}
    for st in steps:
        if not isinstance(st, dict) or not st.get("id"):
            continue
        fam = (st.get("params") or {}).get("family")
        if isinstance(fam, str) and fam.strip():
            families.setdefault(fam, []).append(st["id"])
    for fam, sids in sorted(families.items()):
        if len(sids) <= FAMILY_STEP_MAX:
            continue
        mute = [sid for sid in sids
                if not (next(s for s in steps if s.get("id") == sid).get("params")
                        or {}).get("split_reason")]
        if mute:
            bad.append(f"{path}: family `{fam}` is planned as {len(sids)} steps "
                       f"({', '.join(sids)}); a family's entities go in one step unless a "
                       f"measured fact splits them, and every step of a split family "
                       f"carries `params.split_reason` - missing on: {', '.join(mute)}")

    # Kahn's walk: whatever cannot be ordered sits on a cycle.
    deps = {st["id"]: {d for d in (st.get("after") or []) if d in ids and d != st["id"]}
            for st in steps if isinstance(st, dict) and st.get("id") in ids}
    ready = [s for s, d in deps.items() if not d]
    seen: set[str] = set()
    while ready:
        s = ready.pop()
        seen.add(s)
        for t, d in deps.items():
            if s in d:
                d.discard(s)
                if not d and t not in seen:
                    ready.append(t)
    cyclic = sorted(set(deps) - seen)
    if cyclic:
        bad.append(f"{path}: steps {cyclic} form a dependency cycle")

    for slot in sorted(slots - referenced_slots):
        bad.append(f"{path}: slot `{slot}` is referenced by no step - delete it or use it")

    rep = doc.get("report")
    if rep is not None and not isinstance(rep, dict):
        bad.append(f"{path}: `report` must be an object when present")
    return bad


def list_libraries(dirs: list[pathlib.Path], skills_dir: pathlib.Path | None) -> int:
    seen: dict[str, str] = {}
    rows: list[str] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            problems = validate(f, skills_dir)
            if problems:
                rows.append(f"  {f.stem:<24} {d}  INVALID ({len(problems)} problem(s); "
                            f"run check_playbook.py {f})")
                continue
            doc = json.loads(f.read_text())
            kinds = ",".join(sorted({s.get("check", "?") for s in doc.get("steps", [])}))
            shadow = f"  (shadowed by {seen[doc['name']]})" if doc["name"] in seen else ""
            if doc["name"] not in seen:
                seen[doc["name"]] = str(d)
            rows.append(f"  {doc['name']:<24} {d}  \"{doc.get('title', '')}\"  "
                        f"steps={len(doc.get('steps', []))} kinds={kinds}{shadow}")
    if not rows:
        print("no playbooks found")
        return 0
    print(f"{len(rows)} playbook(s):")
    print("\n".join(rows))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=pathlib.Path)
    ap.add_argument("--list", action="store_true",
                    help="treat the paths as library directories and list them")
    ap.add_argument("--skills-dir", type=pathlib.Path,
                    default=pathlib.Path(__file__).resolve().parent.parent / "skills",
                    help="where the mapped worker skills live (default: the plugin's)")
    a = ap.parse_args()
    skills = a.skills_dir if a.skills_dir.is_dir() else None

    if a.list:
        return list_libraries(a.paths, skills)

    failed = False
    for f in a.paths:
        if not f.is_file():
            print(f"{f}: not a file", file=sys.stderr)
            return 2
        problems = validate(f, skills)
        if problems:
            failed = True
            print(f"{f.name}: {len(problems)} problem(s)", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
        else:
            print(f"{f.name}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
