#!/usr/bin/env python3
"""Collapse every figure's input chain to its room-file roots.

The Sources tab's `root source` and `To reperform` columns state where each figure lands
once passthrough and figure-to-figure hops are collapsed (EVIDENCE.md § 4). The collapse
is mechanical, so it runs here, not in per-run report code: check-report renders what
this emits, and a re-assembly cannot drift from the ledgers it was rendered from.

For each figure in workpapers/figures-*.yaml, follow inputs depth-first:
  - `room_file` / `check_output` -> the citation id, kept as a root (`check_output` roots
    also continue THROUGH the producing check where the citation names `from_check` and
    that check's figures are in the ledger — the room basis behind the derived read is
    the producing check's own roots; the derived citation is still reported, marked);
  - `figure`   -> recurse into that figure's inputs;
  - `declared` -> a declared field, reported apart (no room basis to reach).

Output (JSON, stdout): per figure id — `roots` (citation ids, in first-reach order),
`via_check_output` (derived citations crossed on the way), `declared` (fields relied on),
`depth` (longest hop count collapsed), `passthrough` (true when the figure restates
exactly one other figure or citation). Plus `unresolved`: every citation or figure id an
input names that NO ledger defines — each is a blocker against the check that cited it,
found here at the ledger, before a reader finds it as a dead link. Plus `ledgers`: every
file read, with the entries it contributed — the denominator, so a ledger that
contributed nothing is visible.

A ledger outside EVIDENCE.md § 0's shape is REFUSED, never skipped: a file whose top
level is not a list (a mapping keyed by id, or a list wrapped under a key), an entry that
is not a mapping carrying a string `id`, an id outside the grammar (a space, as in
`F.q6.ebit.LTM July 2023`), or an id whose prefix is not the file's kind (`F.`/`P.` in
figures-*, `E.` in evidence-*). Measured before this refusal existed: a figures ledger
written as a top-level mapping iterated as its keys, matched nothing, and 749 of 1,802
figures reached the Sources tab with no root and no reperformance recipe. The refusal
names the file and the entry; the owning check rewrites its ledger.

Usage:
    resolve_roots.py <run_dir> [--json]      # --json is the default and only form
Exit 0 when every reference resolves, 1 when `unresolved` is non-empty, 2 on a usage
error or a refused ledger (the reasons on stderr, nothing on stdout).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

# The id grammar of EVIDENCE.md § 0, whole: a one- or two-letter prefix, then dot-joined
# segments of [A-Za-z0-9_-]. The body mirrors ID_TOKEN in check_workbook.py and
# link_workbook.py - what those scripts read as one token is what a ledger may declare.
LEDGER_ID = re.compile(r"[A-Z]{1,2}\.(?:\d+|[A-Za-z0-9_][A-Za-z0-9_.-]*[A-Za-z0-9])")
KIND_PREFIXES = {"figures": ("F.", "P."), "evidence": ("E.",)}


def load_yaml(path: pathlib.Path):
    try:
        import yaml
    except ImportError:
        print("resolve_roots.py needs PyYAML. Without an installed copy, run it as:\n"
              "  uv run --with pyyaml python3 scripts/resolve_roots.py <run_dir>",
              file=sys.stderr)
        raise SystemExit(2)
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or []


def ledger_entries(path: pathlib.Path, kind: str, refusals: list[str]) -> list[dict]:
    """The entries of one ledger, or [] with the reasons appended to `refusals`.

    Refuses rather than skips: every entry a ledger holds is meant to reach the Sources
    or Evidence tab, so a shape this walk cannot read is the owning check's defect, not a
    file to pass over."""
    doc = load_yaml(path)
    if not isinstance(doc, list):
        shape = "a mapping" if isinstance(doc, dict) else f"a {type(doc).__name__}"
        keys = ""
        if isinstance(doc, dict):
            keys = " (keys: " + ", ".join(str(k) for k in list(doc)[:3]) + \
                   (", …" if len(doc) > 3 else "") + ")"
        refusals.append(f"{path.name}: top level is {shape}{keys}, not a list - a ledger "
                        f"is a YAML list, one `- id:` entry per record (EVIDENCE.md § 0)")
        return []
    out = []
    for i, entry in enumerate(doc):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            refusals.append(f"{path.name}: entry {i} is not a mapping with a string `id`")
            continue
        fid = entry["id"]
        if not LEDGER_ID.fullmatch(fid):
            refusals.append(f"{path.name}: id `{fid}` is outside the id grammar - "
                            f"dot-joined segments of [A-Za-z0-9_-], no spaces; a period "
                            f"is its slug (`fy2025`, `ltm_2026-07`), never its label "
                            f"(EVIDENCE.md § 0)")
            continue
        if not fid.startswith(KIND_PREFIXES[kind]):
            refusals.append(f"{path.name}: id `{fid}` does not belong in a {kind} ledger "
                            f"({' / '.join(KIND_PREFIXES[kind])} only)")
            continue
        out.append(entry)
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--json"]
    if len(args) != 1:
        print(__doc__.split("Usage:")[1].strip(), file=sys.stderr)
        return 2
    run_dir = pathlib.Path(args[0])
    wp = run_dir / "workpapers"
    if not wp.is_dir():
        print(f"{run_dir}: no workpapers/ directory", file=sys.stderr)
        return 2

    figures: dict[str, dict] = {}
    citations: dict[str, dict] = {}
    ledgers: dict[str, int] = {}
    refusals: list[str] = []
    for f in sorted(wp.glob("figures-*.yaml")):
        entries = ledger_entries(f, "figures", refusals)
        ledgers[f.name] = len(entries)
        for entry in entries:
            figures.setdefault(entry["id"], entry)
    for f in sorted(wp.glob("evidence-*.yaml")):
        entries = ledger_entries(f, "evidence", refusals)
        ledgers[f.name] = len(entries)
        for entry in entries:
            citations.setdefault(entry["id"], entry)
    if refusals:
        print(f"{len(refusals)} ledger record(s) refused - the owning check rewrites its "
              f"ledger; nothing is collapsed until every ledger reads:", file=sys.stderr)
        for r in refusals:
            print(f"  {r}", file=sys.stderr)
        return 2

    unresolved: dict[str, str] = {}   # missing id -> first figure that cites it

    def walk(fid: str, seen: tuple) -> dict:
        fig = figures[fid]
        roots: list[str] = []
        via: list[str] = []
        declared: list[str] = []
        depth = 0
        for inp in fig.get("inputs") or []:
            st = inp.get("source_type")
            if st in ("room_file", "check_output"):
                cid = inp.get("citation_id")
                if not cid:
                    unresolved.setdefault(f"{fid}.inputs[{inp.get('role')}]",
                                          f"{fid}: {st} input with no citation_id")
                    continue
                cit = citations.get(cid)
                if cit is None:
                    unresolved.setdefault(cid, fid)
                    continue
                derived = st == "check_output" or cit.get("file_role") == "run_artifact"
                if derived:
                    if cid not in via:
                        via.append(cid)
                elif cid not in roots:
                    roots.append(cid)
            elif st == "figure":
                sub = inp.get("figure_id")
                if not sub or sub not in figures:
                    unresolved.setdefault(sub or f"{fid}.inputs[{inp.get('role')}]", fid)
                    continue
                if sub in seen:
                    unresolved.setdefault(sub, f"{fid} (cycle)")
                    continue
                r = walk(sub, seen + (sub,))
                roots.extend(x for x in r["roots"] if x not in roots)
                via.extend(x for x in r["via_check_output"] if x not in via)
                declared.extend(x for x in r["declared"] if x not in declared)
                depth = max(depth, r["depth"] + 1)
            elif st == "declared":
                fld = inp.get("field", "?")
                if fld not in declared:
                    declared.append(fld)
        # By the recorded convention only (EVIDENCE.md § 3): guessing from input
        # counts flags a single-span aggregation, which is a measurement.
        expr = str(fig.get("expression", "")).lower()
        passthrough = ("passthrough" in expr or expr.startswith(("as stated", "as recorded")))
        return {"roots": roots, "via_check_output": via, "declared": declared,
                "depth": depth, "passthrough": passthrough}

    out = {fid: walk(fid, (fid,)) for fid in sorted(figures)}
    print(json.dumps({"figures": out,
                      "unresolved": {k: f"first cited by {v}"
                                     for k, v in sorted(unresolved.items())},
                      "ledgers": ledgers},
                     indent=2))
    if unresolved:
        print(f"{len(unresolved)} reference(s) no ledger defines — each is a blocker "
              f"against the check that cited it:", file=sys.stderr)
        for k, v in sorted(unresolved.items()):
            print(f"  {k}  (first cited by {v})", file=sys.stderr)
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
