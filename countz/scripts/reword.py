#!/usr/bin/env python3
"""Wording fixes to the staged workbook, made by the report step: a cell's words change,
its numbers, ids and placeholders do not (check-report SKILL.md § 3).

    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/reword.py <run_dir> <edits.yaml>

`edits.yaml` is a list. Each entry:

    tab:  a tab name, or "*" for every tab
    cell: optional, one cell (`F296`); without it, every text cell on the tab holding `old`
    old:  the text to replace, an exact substring of the cell
    new:  its replacement
    why:  one line: the gate refusal it answers

The edits apply to `<run_dir>/out/.staging/workbook.xlsx` in place, at the XML level, so
cached values, formulas, links and styles stay as they were; run the gates and rebuild the
deck after it. A check's own files (`checks/`, `out/tabs/`, its ledgers) are never
touched: the deliverable carries the corrected words, the check's record keeps its own.

Refused, writing nothing (exit 1): a tab or cell that does not exist; an edit that
matches no cell; a cell that is not plain text (a number, a formula or a formula's
result); a cell whose new text differs from its old text in its numbers, its ledger ids
(`F.`, `P.`, `LK.`, ...) or its `{...}` placeholders. Every applied edit is appended to
`<run_dir>/out/wording.json` (tab, cells, old, new, why), which RUN_SUMMARY.md lists.
Exit 0 applied, 1 refused, 2 usage.
"""
from __future__ import annotations

import collections
import html
import json
import pathlib
import re
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import style  # noqa: E402
from check_report import MACHINE_ID, PERIOD_LIKE, step_tokens  # noqa: E402
from check_workbook import sheet_order  # noqa: E402

CELL = re.compile(r"<c\b([^>]*?)(?:/>|>((?:(?!</c>).)*)</c>)", re.S)
SI = re.compile(r"<si>(.*?)</si>", re.S)
T_TEXT = re.compile(r"<t[^>]*>(.*?)</t>", re.S)
NUMBER = re.compile(style.NUM)
PLACEHOLDER = re.compile(r"\{[^{}]+\}")


class Refused(Exception):
    pass


def run_tokens(run_dir: pathlib.Path) -> list[str]:
    """The families of the run's checks (`r5`): the step tokens its tabs open with."""
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return sorted({str((c.get("params") or {}).get("family") or "") for c in run.get("checks") or []}
                  - {""}, key=len, reverse=True)


def _attr(attrs: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return m.group(1) if m else None


def _text(xml: str) -> str:
    return html.unescape("".join(T_TEXT.findall(xml)))


def _si(text: str) -> str:
    return f'<si><t xml:space="preserve">{html.escape(text, quote=False)}</t></si>'


def invariants(text: str, tokens: list[str] = ()) -> tuple:
    """What a wording fix may not move: the numbers (separators ignored), the ledger ids
    and the placeholders, each as a multiset. A step token (`R5`) is the run's word, not a
    number, so a fix may drop it."""
    for tok in tokens:
        flags = 0 if PERIOD_LIKE.match(tok) else re.I
        text = re.sub(rf"(?<![\w.]){re.escape(tok)}(?![\w.])", " ", text, flags=flags)
    nums = collections.Counter(n.replace(",", "") for n in NUMBER.findall(text))
    ids = collections.Counter(MACHINE_ID.findall(text))
    return nums, ids, collections.Counter(PLACEHOLDER.findall(text))


def _load(path: pathlib.Path) -> list[dict]:
    import yaml
    edits = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(edits, list) or not edits:
        raise Refused(f"{path}: a non-empty list of edits")
    for i, e in enumerate(edits):
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) and e.get(k) for k in
                                              ("tab", "old", "why")) or not isinstance(e.get("new"), str):
            raise Refused(f"{path} entry {i}: needs `tab`, `old`, `new` and `why` as text")
        if e["old"] == e["new"]:
            raise Refused(f"{path} entry {i}: `old` and `new` are the same")
    return edits


def apply(workbook: pathlib.Path, edits: list[dict], tokens: list[str] = ()) -> list[dict]:
    """Apply `edits` to `workbook` in place; return one log row per edit. Raises Refused,
    leaving the file unchanged, on any refusal. `tokens` adds step tokens to the ones the
    workbook's tab names carry (the run's families, `run_tokens`)."""
    with zipfile.ZipFile(workbook) as z:
        infos = z.infolist()
        parts = {i.filename: z.read(i.filename) for i in infos}
        order = sheet_order(z)
    by_name = {name: part for part, name in order}
    tokens = sorted(set(step_tokens(list(by_name))) | set(tokens), key=len, reverse=True)
    sst_xml = parts.get("xl/sharedStrings.xml", b"").decode("utf-8")
    shared = SI.findall(sst_xml)
    shared_text = [_text(s) for s in shared]
    added: list[str] = []
    sheets = {part: parts[part].decode("utf-8") for part, _ in order}
    log = []
    for i, e in enumerate(edits):
        tabs = list(by_name) if e["tab"] == "*" else [e["tab"]]
        for t in tabs:
            if t not in by_name:
                raise Refused(f"edit {i}: no tab `{t}`")
        touched: list[str] = []
        for t in tabs:
            part = by_name[t]

            def one(m: re.Match, t=t) -> str:
                attrs, body = m.group(1), m.group(2) or ""
                ref = _attr(attrs, "r")
                if e.get("cell") and ref != e["cell"]:
                    return m.group(0)
                kind = _attr(attrs, "t") or ""
                if kind == "s":
                    v = re.search(r"<v[^>]*>(\d+)</v>", body)
                    idx = int(v.group(1)) if v else -1
                    old = (shared_text + added)[idx] if 0 <= idx < len(shared_text) + len(added) else None
                elif kind == "inlineStr":
                    old = _text(body)
                else:
                    old = None
                if old is None or e["old"] not in old:
                    if e.get("cell") and ref == e["cell"]:
                        raise Refused(f"edit {i}: {t}!{ref} is not a text cell holding `{e['old']}`")
                    return m.group(0)
                if "<f" in body:
                    raise Refused(f"edit {i}: {t}!{ref} is a formula")
                new = old.replace(e["old"], e["new"])
                if invariants(new, tokens) != invariants(old, tokens):
                    raise Refused(f"edit {i}: {t}!{ref} — the new text moves a number, an id or a "
                                  f"placeholder: `{old}` -> `{new}`; that is the owning check's fix")
                touched.append(f"{t}!{ref}")
                if kind == "s":
                    added.append(new)
                    nb = re.sub(r"<v[^>]*>\d+</v>", f"<v>{len(shared_text) + len(added) - 1}</v>", body, 1)
                else:
                    nb = f'<is><t xml:space="preserve">{html.escape(new, quote=False)}</t></is>'
                return f"<c{attrs}>{nb}</c>"

            sheets[part] = CELL.sub(one, sheets[part])
        if not touched:
            raise Refused(f"edit {i}: `{e['old']}` matches no text cell on {e['tab']}")
        log.append({"tab": e["tab"], "cells": touched, "old": e["old"], "new": e["new"], "why": e["why"]})
    if added:
        body = "".join(f"<si>{s}</si>" for s in shared) + "".join(_si(s) for s in added)
        head = re.match(r"(.*?<sst\b[^>]*>)", sst_xml, re.S).group(1)
        head = re.sub(r'uniqueCount="\d+"', f'uniqueCount="{len(shared) + len(added)}"', head)
        parts["xl/sharedStrings.xml"] = (head + body + "</sst>").encode("utf-8")
    for part, xml in sheets.items():
        parts[part] = xml.encode("utf-8")
    tmp = workbook.with_suffix(".reword.tmp")
    with zipfile.ZipFile(tmp, "w") as out:
        for info in infos:
            out.writestr(info, parts[info.filename], compress_type=info.compress_type)
    tmp.replace(workbook)
    return log


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    run_dir, edits_path = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    wb = run_dir / "out" / ".staging" / "workbook.xlsx"
    if not wb.is_file() or not edits_path.is_file():
        print(f"reword: needs {wb} and {edits_path}", file=sys.stderr)
        return 2
    try:
        log = apply(wb, _load(edits_path), run_tokens(run_dir))
    except Refused as exc:
        print(f"reword: refused, nothing written: {exc}", file=sys.stderr)
        return 1
    rec = run_dir / "out" / "wording.json"
    prior = json.loads(rec.read_text(encoding="utf-8")) if rec.is_file() else []
    rec.write_text(json.dumps(prior + log, indent=1), encoding="utf-8")
    for row in log:
        print(f"reword: {row['tab']}: {len(row['cells'])} cell(s) `{row['old']}` -> `{row['new']}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
