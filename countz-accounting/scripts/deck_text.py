#!/usr/bin/env python3
"""Print a built deck as its reader sees it: each slide's words and figures in reading
order, for the deck review (skills/check-deck).

    uv run --project ${CLAUDE_PLUGIN_ROOT} python3 scripts/deck_text.py <deck.pptx> [--since <old.pptx>]

One block per slide, `=== slide N`, then one line per text shape as `[shape] text`
(build_report.py names the shapes: kicker, title, message, body-text, body-note, ...).
A table prints one line per row, its cells joined by ` | `. A drawn chart prints one line
per bar, `[bar] <category>: <value>`. Gridlines, axis ticks and the footer band are left
out; the footer's source line stays.

With `--since`, a slide whose lines differ from the slide of the same title in the older
deck, or that has no such slide, is headed `=== slide N (changed)`; the footer's page
number is left out of the comparison.
"""
from __future__ import annotations

import sys

from pptx import Presentation

SKIP = {"chart-grid", "chart-axis", "chart-break", "footer-band", "footer-left", "rect",
        "line", "dot"}


def slide_lines(slide) -> list[str]:
    out: list[str] = []
    cat = None
    for sh in slide.shapes:
        name = sh.name or ""
        if name in SKIP or name.startswith("chartval:"):
            continue
        if getattr(sh, "has_table", False) and sh.has_table:
            out.append(f"[{name}]")
            for row in sh.table.rows:
                out.append("  " + " | ".join(c.text.strip() for c in row.cells))
            continue
        if not (sh.has_text_frame and sh.text_frame.text.strip()):
            continue
        text = " ".join(sh.text_frame.text.split())
        if name == "chart-cat":
            cat = text
        elif name == "chart-value" and cat is not None:
            out.append(f"[bar] {cat}: {text}")
            cat = None
        else:
            out.append(f"[{name}] {text}")
    return out


def title_of(lines: list[str]) -> str:
    return next((ln for ln in lines if ln.startswith("[title] ")), "")


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 4) or (len(argv) == 4 and argv[2] != "--since"):
        print(__doc__, file=sys.stderr)
        return 2
    slides = [slide_lines(s) for s in Presentation(argv[1]).slides]
    old: dict[str, list[list[str]]] = {}
    if len(argv) == 4:
        for lines in (slide_lines(s) for s in Presentation(argv[3]).slides):
            old.setdefault(title_of(lines), []).append(lines)
    for n, lines in enumerate(slides, 1):
        mark = ""
        if len(argv) == 4:
            twins = old.get(title_of(lines)) or []
            mark = "" if lines in twins else " (changed)"
            if lines in twins:
                twins.remove(lines)
        print(f"=== slide {n}{mark}")
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
