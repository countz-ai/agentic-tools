#!/usr/bin/env python3
"""Refuse prose whose numbers the figure ledger does not carry.

A metric number typed into a sentence is a second copy of a figure. A text cell has no
formula, so the cell-resolution gate cannot see it, and when a fix re-run moves the
ledger the sentence keeps the old value. Measured on the first critique loop: every
prose-drift finding in rounds two through four was this class — a dollar amount or day
count composed into a sentence instead of interpolated from the ledger.

The rule this enforces (EVIDENCE.md § 4): the code that writes a tab loads the figure
ledger and interpolates values into sentence templates. This gate reads the result. It
extracts every dollar amount, day count, percentage and multiple from text cells (or
markdown lines) and requires each to agree with an admitted value within the rounding
tolerance of the precision displayed (DOCTRINE.md § Number conventions: "$6.3M" tolerates 0.05M,
"44.6 days" tolerates 0.05).

Scanned: string cells of .xlsx targets; lines of any other (text) target. Digits only —
a magnitude spelled out in words is the review's to catch by reading, not this gate's.
Admitted: numbers on value-bearing keys (value, control_total, total_n, lo, hi, ...) in
<run_dir>/workpapers/*.yaml, plus EVERY numeric literal in each --allow file — pass the
file carrying a declared tolerance a sentence legitimately states.
Skipped: day-count ranges ("31-60 days", "90+ days") — bucket labels, not stated figures.

Usage:
    check_prose.py <tab.xlsx|file.md> [more targets...] [--run-dir DIR] [--allow FILE]...
--run-dir defaults to the nearest ancestor of the first target containing workpapers/.
Exit 0 clean, 1 if any number is unbacked, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import html
import pathlib
import re
import sys
import zipfile

NUM = r"\d[\d,]*(?:\.\d+)?"
ANY_NUM = re.compile(f"-?{NUM}")
# One alternative per display convention. Bare-number forms guard their left edge so a
# token cannot start mid-number, and the days form also refuses a range/plus prefix.
TOKEN = re.compile(
    rf"\$\s?(?P<money>{NUM})\s*(?P<suffix>[KMB]\b|thousand\b|million\b|billion\b)?"
    rf"|(?<![\d.,\-–+$])(?P<days>{NUM})[\s-]days?\b"
    rf"|(?<![\d.,])(?P<pct>{NUM})\s?%"
    rf"|(?<![\d.,])(?P<mult>{NUM})x\b")
SCALE = {"K": 1e3, "thousand": 1e3, "M": 1e6, "million": 1e6, "B": 1e9, "billion": 1e9}
# A ledger line admits the first number after each of these keys; anything else on the
# line (row anchors, dates, cell refs) stays out of the admitted set.
VALUE_KEY = re.compile(
    r"\b(?:value|control_total|total_n|included_n|row_count|lo|hi|low|high|min|max"
    r"|amount|days|dollars|usd|pct|percent|target|floor|threshold|materiality"
    r"|de_minimis|window_days|rate|n)\s*:")
SHEET_EL = re.compile(r"<sheet\b[^>]*/?>")
REL_EL = re.compile(r"<Relationship\b[^>]*/?>")
ATTR = lambda name: re.compile(rf'\b{name}="([^"]*)"')


def sheet_names(z: zipfile.ZipFile) -> dict[str, str]:
    """worksheet part name -> display name, so a report names a real tab."""
    try:
        wb = z.read("xl/workbook.xml").decode()
        rels = {}
        for el in REL_EL.findall(z.read("xl/_rels/workbook.xml.rels").decode()):
            rid, target = ATTR("Id").search(el), ATTR("Target").search(el)
            if rid and target:
                rels[rid.group(1)] = target.group(1)
    except KeyError:
        return {}
    out = {}
    for el in SHEET_EL.findall(wb):
        name = ATTR("name").search(el)
        rid = ATTR("r:id").search(el) or ATTR("id").search(el)
        if name and rid:
            target = rels.get(rid.group(1), "")
            out["xl/" + target.lstrip("/").removeprefix("xl/")] = name.group(1)
    return out


def texts(target: pathlib.Path):
    """Yield (location, text) for every prose surface in the target, as stored."""
    if target.suffix.lower() != ".xlsx":
        for i, line in enumerate(target.read_text(errors="replace").splitlines(), 1):
            yield f"{target.name}:{i}", line
        return
    with zipfile.ZipFile(target) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            sst = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            for si in re.findall(r"<si>(.*?)</si>", sst, re.S):
                shared.append(html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))))
        names = sheet_names(z)
        for part in sorted(n for n in z.namelist()
                           if n.startswith("xl/worksheets/") and n.endswith(".xml")):
            xml = z.read(part).decode("utf-8", "replace")
            tab = names.get(part, part.rsplit("/", 1)[-1].removesuffix(".xml"))
            # A styled empty cell is stored self-closing (`<c r="C1" s="1"/>` — openpyxl
            # writes these); a pattern demanding `</c>` swallows the NEXT cell's text
            # from inside one, and every cell after an empty styled cell escapes the scan.
            for m in re.finditer(r"<c\b([^>]*?)(?:/>|>((?:(?!</c>).)*)</c>)", xml, re.S):
                attrs, body = m.group(1), m.group(2) or ""
                ref = ATTR("r").search(attrs)
                loc = f"{tab}!{ref.group(1) if ref else '?'}"
                t = ATTR("t").search(attrs)
                kind = t.group(1) if t else ""
                if kind == "s":
                    v = re.search(r"<v[^>]*>(\d+)</v>", body)
                    if v and int(v.group(1)) < len(shared):
                        yield loc, shared[int(v.group(1))]
                elif kind == "inlineStr":
                    yield loc, html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", body, re.S)))
                elif kind == "str":
                    v = re.search(r"<v[^>]*>(.*?)</v>", body, re.S)
                    if v:
                        yield loc, html.unescape(v.group(1))


def admitted_values(run_dir: pathlib.Path, allow: list[pathlib.Path]) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for y in sorted((run_dir / "workpapers").glob("*.yaml")):
        for line in y.read_text(errors="replace").splitlines():
            for k in VALUE_KEY.finditer(line):
                n = ANY_NUM.search(line[k.end():])
                if n:
                    out.append((float(n.group(0).replace(",", "")), y.name))
    for f in allow:
        for n in ANY_NUM.finditer(f.read_text(errors="replace")):
            out.append((float(n.group(0).replace(",", "")), f.name))
    return out


def tokenize(text: str):
    """Yield (token_text, value, tolerance, variants) per metric number in the text."""
    for m in TOKEN.finditer(text):
        raw = m.group("money") or m.group("days") or m.group("pct") or m.group("mult")
        scale = SCALE.get((m.group("suffix") or "").strip(), 1.0) if m.group("money") else 1.0
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        value = float(raw.replace(",", "")) * scale
        tol = 0.5 * scale * 10 ** -decimals
        variants = (1.0, 100.0) if m.group("pct") else (1.0,)   # a ledger 0.174 backs "17.4%"
        yield m.group(0).strip(), value, tol, variants


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="+", type=pathlib.Path)
    ap.add_argument("--run-dir", type=pathlib.Path)
    ap.add_argument("--allow", action="append", type=pathlib.Path, default=[])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    run_dir = a.run_dir
    if run_dir is None:
        run_dir = next((p for p in a.targets[0].resolve().parents
                        if (p / "workpapers").is_dir()), None)
    if run_dir is None or not (run_dir / "workpapers").is_dir():
        print("no workpapers/ found above the target; pass --run-dir", file=sys.stderr)
        return 2
    for f in [*a.targets, *a.allow]:
        if not f.is_file():
            print(f"{f}: not a file", file=sys.stderr)
            return 2
    admitted = admitted_values(run_dir, a.allow)
    if not admitted:
        print(f"{run_dir}/workpapers holds no admitted values - nothing to bind against",
              file=sys.stderr)
        return 2

    total, unbacked = 0, []
    for target in a.targets:
        for loc, text in texts(target):
            for token, value, tol, variants in tokenize(text):
                total += 1
                if any(abs(abs(av) * f - value) <= tol for av, _ in admitted for f in variants):
                    continue
                gap, near, src = min((abs(abs(av) * f - value), av, s)
                                     for av, s in admitted for f in variants)
                unbacked.append({"target": target.name, "location": loc, "token": token,
                                 "nearest": near, "nearest_in": src, "off_by": gap})
    if a.json:
        import json
        print(json.dumps({"metric_numbers": total, "unbacked": unbacked}, indent=2))
        return 1 if unbacked else 0
    if not unbacked:
        print(f"{', '.join(t.name for t in a.targets)}: {total} metric number(s) in prose, "
              f"every one carried by the ledger.")
        return 0
    print(f"{len(unbacked)} of {total} prose numbers have NO admitted value behind them:\n")
    for u in unbacked:
        print(f"  {u['location']:<28} {u['token']:<16} nearest {u['nearest']:,} "
              f"({u['nearest_in']}), off by {u['off_by']:,.2f}")
    print("\n  A number in a sentence is interpolated from the figure ledger, never typed")
    print("  (EVIDENCE.md § 4). Record the figure the sentence needs, or fix the sentence;")
    print("  a threshold or tie delta a tab legitimately states is admitted with --allow.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
