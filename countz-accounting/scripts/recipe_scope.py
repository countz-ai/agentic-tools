#!/usr/bin/env python3
"""The run's scope: which of a recipe's families it executes (PLAYBOOK_RECIPES.md § Ask
what to run).

    recipe_scope.py table <recipe.md>
    recipe_scope.py resolve <recipe.md> <picks>

`table` prints the block the relay puts to the user, between `SHOW:` and `END`: a note,
then one row per family with a checkbox and its title (`recipe_format.plain_title`),
under a first row, *Run everything*, ticked. No family id reaches the user. Then one
`KEY:\t<n>\t<family id>` line per row, for the relay alone: it maps the number or the
title the user picked to the id it registers.

`resolve` reads `<picks>` — `all`, or row numbers and family ids, comma- or
space-separated (`4,5`, `c4 c5`) — and prints `SCOPE:\t<ids>`: the picked families and
every family they read from, transitively (`recipe_format.scope_closure`), or `all` when
that is every family. `SAY:` is the line the relay puts to the user, naming in plain
words what runs and what was added because a picked step depends on it. `setup_run.py
--scope <picks>` records the same resolution in `run.json.inputs.scope`.

Stdlib only. Exit 0; 2 on an unreadable recipe or a pick naming no row.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import recipe_format  # noqa: E402

NOTE = ("**What should this run cover?** *Run everything* is selected. To run less, "
        "pick only the steps you want, by number or by name. Any earlier step a pick "
        "depends on is added for you.")


class Refuse(Exception):
    pass


def resolve(fams: list[dict], picks: str) -> dict | None:
    """`{"picked", "families", "added"}` for `picks`, every list of family ids in recipe
    order; None for a run over every family. Refuses a pick naming no row and no id."""
    toks = [t for t in re.split(r"[,\s]+", picks.strip().lower()) if t]
    if not toks or toks == ["all"] or "0" in toks:
        return None
    ids = [f["id"] for f in fams]
    picked: list[str] = []
    for t in toks:
        fid = ids[int(t) - 1] if t.isdigit() and 1 <= int(t) <= len(ids) else t
        if fid not in ids:
            raise Refuse(f"pick {t!r} names no step: give `all`, a row number 1-{len(ids)} "
                         f"or a family id ({', '.join(ids)})")
        if fid not in picked:
            picked.append(fid)
    families = recipe_format.scope_closure(fams, picked)
    if families == ids:
        return None
    return {"picked": [i for i in ids if i in picked], "families": families,
            "added": [i for i in families if i not in picked]}


def say(fams: list[dict], scope: dict | None) -> str:
    if scope is None:
        return "This run covers every step of the recipe."
    title = {f["id"]: recipe_format.plain_title(f["title"]) for f in fams}
    line = "This run covers: " + "; ".join(title[i] for i in scope["picked"]) + "."
    if scope["added"]:
        line += (" Added because the steps you picked depend on them: "
                 + "; ".join(title[i] for i in scope["added"]) + ".")
    return line


def table(fams: list[dict]) -> list[str]:
    rows = [NOTE, "", "| | # | Step |", "|:-:|--:|---|", "| ☑ | | **Run everything** |"]
    rows += [f"| ☐ | {n} | {recipe_format.plain_title(f['title'])} |"
             for n, f in enumerate(fams, 1)]
    return rows


def load(path: pathlib.Path) -> list[dict]:
    try:
        fams = recipe_format.families(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise Refuse(f"cannot read {path}: {exc}")
    if not fams:
        raise Refuse(f"{path.name} carries no `### <F><n> — ...` family under `## The families`")
    return fams


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 2 and argv[0] == "table":
            fams = load(pathlib.Path(argv[1]))
            print("SHOW:")
            print("\n".join(table(fams)))
            print("END")
            for n, f in enumerate(fams, 1):
                print(f"KEY:\t{n}\t{f['id']}")
            return 0
        if len(argv) == 3 and argv[0] == "resolve":
            fams = load(pathlib.Path(argv[1]))
            scope = resolve(fams, argv[2])
            print(f"SCOPE:\t{','.join(scope['families']) if scope else 'all'}")
            print(f"SAY:\t{say(fams, scope)}")
            return 0
    except Refuse as exc:
        print(f"recipe_scope: {exc}", file=sys.stderr)
        return 2
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
