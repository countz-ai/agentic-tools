#!/usr/bin/env python3
"""Print a built deck as its reader sees it: each slide's words and figures in reading
order, for the deck review (skills/check-deck).

    uv run --project ${CLAUDE_PLUGIN_ROOT} python3 scripts/deck_text.py <deck.pptx>

One block per slide, `=== slide N`, then one line per text shape as `[shape] text`
(build_report.py names the shapes: kicker, title, message, body-text, body-note, ...).
A table prints one line per row, its cells joined by ` | `. A drawn chart prints one line
per bar, `[bar] <category>: <value>`. Gridlines, axis ticks and the footer band are left
out; the footer's source line stays.
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


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    deck = Presentation(argv[1])
    for n, slide in enumerate(deck.slides, 1):
        print(f"=== slide {n}")
        print("\n".join(slide_lines(slide)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
