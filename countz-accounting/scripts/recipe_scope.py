#!/usr/bin/env python3
"""The run's scope: which of a recipe's families it executes (PLAYBOOK_RECIPES.md § Ask
what to run).

    recipe_scope.py ask [<recipe.md>]          # no path: the family headers on stdin
    recipe_scope.py resolve <recipe.md> <picks>

`ask` needs only the recipe's `### <F><n> — <title> (kind ..., ...)` header lines: the
relay pipes those from the body it was served, so nothing is written to disk before the
user picks. It prints:

- between `SHOW:` and `END`, the message the relay sends: the recipe's steps as an
  overview, one numbered row per family with its title (`recipe_format.plain_title`),
  then the prompt under the table — *run 5, 6* or *run all*.
- one `KEY:\t<n>\t<family id>\t<title>` line per family, for the relay alone: it maps
  the number or name the user gave to the row number it registers.

No family id reaches the user.

`resolve` reads `<picks>` — `all`, or row numbers and family ids, comma- or
space-separated (`4,5`, `c4 c5`), a leading `run` ignored (`run 5, 6`) — and prints `SCOPE:\t<ids>`: the picked families and
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

HEAD = "**The steps in this analysis**"
PROMPT = ("Tell me what you want to run, e.g. *run 5, 6* or *run all*. Any earlier step "
          "a pick depends on is added for you.")
FILLER = {"run", "and", "step", "steps"}     # `run 5 and 6`: words around the picks


class Refuse(Exception):
    pass


def resolve(fams: list[dict], picks: str) -> dict | None:
    """`{"picked", "families", "added"}` for `picks`, every list of family ids in recipe
    order; None for a run over every family. Refuses a pick naming no row and no id."""
    toks = [t for t in re.split(r"[,\s]+", picks.strip().lower()) if t and t not in FILLER]
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
    rows = [HEAD, "", "| # | Step |", "|--:|---|"]
    rows += [f"| {n} | {recipe_format.plain_title(f['title'])} |"
             for n, f in enumerate(fams, 1)]
    return rows + ["", PROMPT]


def load(path: pathlib.Path | None) -> list[dict]:
    """The recipe's families, from `path` or, with None, from stdin."""
    try:
        text = sys.stdin.read() if path is None else path.read_text(encoding="utf-8")
    except OSError as exc:
        raise Refuse(f"cannot read {path}: {exc}")
    fams = recipe_format.families(text)
    if not fams:
        raise Refuse(f"{'stdin' if path is None else path.name} carries no "
                     f"`### <F><n> — <title> (kind `<kind>`, <grain>)` family header")
    return fams


def main(argv: list[str]) -> int:
    try:
        if len(argv) in (1, 2) and argv[0] == "ask":
            fams = load(pathlib.Path(argv[1]) if len(argv) == 2 else None)
            print("SHOW:")
            print("\n".join(table(fams)))
            print("END")
            for n, f in enumerate(fams, 1):
                print(f"KEY:\t{n}\t{f['id']}\t{recipe_format.plain_title(f['title'])}")
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
