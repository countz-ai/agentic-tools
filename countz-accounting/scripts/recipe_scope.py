#!/usr/bin/env python3
"""The run's scope: which of a recipe's families it executes (PLAYBOOK_RECIPES.md § Ask
what to run).

    recipe_scope.py ask [<recipe.md>]          # no path: the family headers on stdin
    recipe_scope.py resolve <recipe.md> <picks>

`ask` needs only the recipe's `### <F><n> — <title> (kind ..., ...)` header lines: the
relay pipes those from the body it was served, so nothing is written to disk before the
user picks. It prints:

- `ASK:\t<one-line JSON>` — `{"questions": [...]}` for the AskUserQuestion tool,
  verbatim: multi-select questions of at most four options each, the first option *Run
  everything (Recommended)*, then one option per family, labeled with its title
  (`recipe_format.plain_title`). Absent when the families do not fit in four questions.
- the same choice as a markdown table between `SHOW:` and `END`, for a surface with no
  AskUserQuestion tool: a note, then one row per family with a checkbox, a number and
  its title, under a first row, *Run everything*, ticked.
- one `KEY:\t<n>\t<family id>\t<title>` line per family, for the relay alone: it maps
  the label, number or name the user picked to the row number it registers.

No family id reaches the user.

`resolve` reads `<picks>` — `all`, or row numbers and family ids, comma- or
space-separated (`4,5`, `c4 c5`) — and prints `SCOPE:\t<ids>`: the picked families and
every family they read from, transitively (`recipe_format.scope_closure`), or `all` when
that is every family. `SAY:` is the line the relay puts to the user, naming in plain
words what runs and what was added because a picked step depends on it. `setup_run.py
--scope <picks>` records the same resolution in `run.json.inputs.scope`.

Stdlib only. Exit 0; 2 on an unreadable recipe or a pick naming no row.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import recipe_format  # noqa: E402

NOTE = ("**What should this run cover?** *Run everything* is selected. To run less, "
        "pick only the steps you want, by number or by name. Any earlier step a pick "
        "depends on is added for you.")


ASK_MAX = 4          # AskUserQuestion: at most four questions, of two to four options each
RUN_ALL = "Run everything (Recommended)"


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


def describe(cardinality: str) -> str:
    """A family's grain as an option's description: `per bank account` -> `Per bank
    account`."""
    c = recipe_format.plain_title(cardinality)
    return c if len(c) <= 80 else c[:79].rstrip() + "…"


def questions(fams: list[dict]) -> list[dict] | None:
    """The AskUserQuestion `questions`: *Run everything* and every family, split into at
    most four multi-select questions of two to four options; None when they do not fit."""
    n = len(fams)
    items = [{"label": RUN_ALL, "description": f"All {n} steps of the recipe"}]
    items += [{"label": recipe_format.plain_title(f["title"]),
               "description": describe(f["cardinality"])} for f in fams]
    k = -(-len(items) // ASK_MAX)
    if k > ASK_MAX or len({i["label"] for i in items}) != len(items):
        return None
    sizes = [len(items) // k + (1 if i < len(items) % k else 0) for i in range(k)]
    out, at = [], 0
    for qi, size in enumerate(sizes):
        chunk = items[at:at + size]
        first = at if qi else 1                 # row numbers: Run everything has none
        last = at + size - 1
        at += size
        span = f"{first}–{last}" if first != last else f"{first}"
        if qi == 0:
            text = ("Which steps should this run cover? Pick only the steps you want; any "
                    "earlier step they depend on is added for you.")
        else:
            text = f"Which of steps {span} should the run also cover?"
        out.append({"question": text, "header": f"Steps {span}", "multiSelect": True,
                    "options": chunk})
    return out


def table(fams: list[dict]) -> list[str]:
    rows = [NOTE, "", "| | # | Step |", "|:-:|--:|---|", "| ☑ | | **Run everything** |"]
    rows += [f"| ☐ | {n} | {recipe_format.plain_title(f['title'])} |"
             for n, f in enumerate(fams, 1)]
    return rows


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
            if (qs := questions(fams)) is not None:
                print("ASK:\t" + json.dumps({"questions": qs}, ensure_ascii=False))
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
