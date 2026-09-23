#!/usr/bin/env python3
"""Report a recipe packaged into this plugin by `make zip RECIPES=...`, for the relay
to pin in place of the one the Countz connector serves.

    bundled_recipe.py <recipe name>

A bundled recipe sits at `<plugin root>/bundled-recipes/<name>.md`; the source tree
never carries one (the Makefile stages it into the zip only). When it exists and its
frontmatter `name` is `<name>`, prints

    RECIPE:\t<abs path>
    VERSION:\tbundled+<sha256[:12]>

and exits 0; the relay registers with `--recipe <path> --recipe-version <version>`
(PLAYBOOK_RECIPES.md § Fetch the recipe and register) and calls no recipe tool.
Exit 1 with `NONE` when nothing is bundled under that name: fetch from the connector as
usual. Exit 2 when a file is there but its frontmatter names another recipe.
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLED_DIR = ROOT / "bundled-recipes"


def frontmatter_name(text: str) -> str | None:
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


def main() -> int:
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", sys.argv[1]):
        print("usage: bundled_recipe.py <kebab-case recipe name>", file=sys.stderr)
        return 2
    name = sys.argv[1]
    path = BUNDLED_DIR / f"{name}.md"
    if not path.is_file():
        print("NONE")
        return 1
    data = path.read_bytes()
    held = frontmatter_name(data.decode("utf-8", "replace"))
    if held != name:
        print(f"bundled_recipe: {path} carries frontmatter name {held!r}, not {name!r}",
              file=sys.stderr)
        return 2
    print(f"RECIPE:\t{path}")
    print(f"VERSION:\tbundled+{hashlib.sha256(data).hexdigest()[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
