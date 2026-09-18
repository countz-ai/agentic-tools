#!/usr/bin/env python3
"""Validate one recipe document against reference/RECIPE_FORMAT.md — the gate
`create-recipe` runs over what it wrote, and the only gate on a generated recipe.

    validate_recipe.py <recipe.md> [--kinds-from <check_playbook.py>]

Exit 0 when the recipe conforms; 1 with one line per defect, `<rule>: <message>`, so
the failed rule is named; 2 on a usage error. The rules live in `recipe_format.py`
(shared with `check-plugin.py` check 8m); this file adds nothing to them.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import recipe_format  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recipe", type=pathlib.Path)
    ap.add_argument("--kinds-from", type=pathlib.Path, default=HERE / "check_playbook.py",
                    help="the check_playbook.py whose KINDS the family kinds must name")
    a = ap.parse_args()
    if not a.recipe.is_file():
        print(f"validate_recipe: no such file: {a.recipe}", file=sys.stderr)
        return 2
    kinds = recipe_format.kinds_from(a.kinds_from)
    bad = recipe_format.validate(a.recipe.read_text(), kinds)
    for rule, msg in bad:
        print(f"{rule}: {msg}")
    if bad:
        print(f"validate_recipe: {a.recipe.name}: {len(bad)} defect(s) - "
              f"reference/RECIPE_FORMAT.md § The document", file=sys.stderr)
        return 1
    print(f"validate_recipe: {a.recipe.name}: ok ({recipe_format.frontmatter(a.recipe.read_text()).get('name')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
