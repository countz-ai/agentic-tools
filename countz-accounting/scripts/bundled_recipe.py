#!/usr/bin/env python3
"""Report a recipe packaged into this plugin by `make zip RECIPES=...` or `make bundle`,
for the relay to pin in place of the one the Countz connector serves, or the packaged
catalog that makes the plugin run offline.

    bundled_recipe.py <recipe name>
    bundled_recipe.py --catalog

A bundled recipe sits at `<plugin root>/bundled-recipes/<name>.md`; the source tree
never carries one (the Makefile stages it into the zip only). When it exists and its
frontmatter `name` is `<name>`, prints

    RECIPE:\t<abs path>
    VERSION:\tbundled+<sha256[:12]>

and exits 0; the relay registers with `--recipe <path> --recipe-version <version>`
(PLAYBOOK_RECIPES.md § Fetch the recipe and register) and calls no recipe tool.
Exit 0 with `NONE` when nothing is bundled under that name, the usual case: fetch from
the connector as usual. It is an answer, not a failure, so it exits 0 and the host shows
no error. Exit 2 when a file is there but its frontmatter names another recipe.

`--catalog` reports `<plugin root>/bundled-recipes/catalog.yaml`, which `make bundle`
writes beside a copy of every recipe it lists. When it is there and every entry has its
recipe, prints

    CATALOG:\t<abs path>
    VERSION:\tbundled+<sha256[:12]>

and exits 0: the plugin is offline, and no skill calls the `countz` server
(RUN_CONTRACT.md § Sign in first). Exit 0 with `NONE` when no catalog is packaged.
Exit 2 when an entry has no recipe, or its file names another one: a partial bundle
stops the run rather than send it to the server for the rest.
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


def catalog_names(text: str) -> list[str]:
    """The `name` of every entry under `recipes:` in a countz-accounting/catalog@1 file."""
    return re.findall(r"^\s*-\s+name:\s*['\"]?([a-z0-9-]+)['\"]?\s*$", text, re.M)


def report_catalog() -> int:
    path = BUNDLED_DIR / "catalog.yaml"
    if not path.is_file():
        print("NONE")
        return 0
    data = path.read_bytes()
    names = catalog_names(data.decode("utf-8", "replace"))
    bad = []
    if not names:
        bad.append(f"{path} lists no recipe")
    for name in names:
        rp = BUNDLED_DIR / f"{name}.md"
        if not rp.is_file():
            bad.append(f"catalog entry {name!r} has no {rp.name} beside it")
        elif frontmatter_name(rp.read_text("utf-8", "replace")) != name:
            bad.append(f"{rp} does not carry frontmatter name {name!r}")
    if bad:
        for line in bad:
            print(f"bundled_recipe: {line}", file=sys.stderr)
        return 2
    print(f"CATALOG:\t{path}")
    print(f"VERSION:\tbundled+{hashlib.sha256(data).hexdigest()[:12]}")
    return 0


def main() -> int:
    if sys.argv[1:] == ["--catalog"]:
        return report_catalog()
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", sys.argv[1]):
        print("usage: bundled_recipe.py <kebab-case recipe name> | --catalog", file=sys.stderr)
        return 2
    name = sys.argv[1]
    path = BUNDLED_DIR / f"{name}.md"
    if not path.is_file():
        print("NONE")
        return 0
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
