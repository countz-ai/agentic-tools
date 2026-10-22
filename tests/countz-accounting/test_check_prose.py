#!/usr/bin/env python3
"""Self-test for scripts/check_prose.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_check_prose.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import pathlib
import sys

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from check_prose import admitted_values, scan  # noqa: E402


def main() -> int:
    import tempfile
    bad = []
    with tempfile.TemporaryDirectory() as td:
        rd = pathlib.Path(td)
        (rd / "workpapers").mkdir()
        (rd / "workpapers" / "figures-t.yaml").write_text(
            "- id: F.a\n  value: 44.6\n- id: F.b\n  value: 6312400.55\n"
            "- id: F.c\n  value: -1204.4\n- id: F.d\n  value: 5000000\n"
            "- id: F.e\n  value: 0.174\n- id: F.f\n  value: -2100000\n"
            "- id: F.g\n  value: 44\n- id: P.h\n  total_n: 372\n", encoding="utf-8")
        admitted = admitted_values(rd, [])
        cases = [
            ("The metric is 44.6 days; $6.3M is unapplied.", 0),
            ("The metric is 44.6 days; $7.1M is unapplied.", 1),
            ("A legacy $6.3m and $6,312,401 are the same figure.", 0),
            ("The euro balance is €5,000,000, or EUR 5.0M, or 5,000,000 EUR.", 0),
            ("Credits were ($1,204), or $1,204.", 0),       # the magnitude: sign unchecked
            ("Revenue fell ($2.1M), a variance of $2.1M.", 0),
            ("Share is 17.4%; -17.4% is too.", 0),
            ("Share is 18.4%.", 1),
            ("Aging buckets 31-60 days and 90+ days.", 0),
        ]
        # counts, with counts=True: a figure's value backs it, a typed one does not
        counts = [
            ("We read 44 lines and 6 new-logo orders.", 1),          # 6 is no figure
            ("All 372 contract lines agree; 1,204 invoices tie.", 1),
            ("Under rule 3 and ASC 718, at December 31 the lines agree.", 0),
            ("Account 1350 holds 2025 postings over 36 months.", 0),
        ]
        for text, want in cases + counts:
            f = rd / "t.md"
            f.write_text(text + "\n", encoding="utf-8")
            _, ub = scan([f], admitted, counts=(text, want) in counts)
            if len(ub) != want:
                bad.append(f"{text!r}: {len(ub)} unbacked, want {want} ({ub})")
        f.write_text("We read 372 lines.\n", encoding="utf-8")
        if scan([f], admitted)[1]:
            bad.append("a count is checked without counts=True")
    for b in bad:
        print(f"check_prose: {b}")
    print("check_prose: ok" if not bad else "check_prose: self-check FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
