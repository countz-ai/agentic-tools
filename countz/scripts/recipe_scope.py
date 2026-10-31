#!/usr/bin/env python3
"""The run's scope: which of a recipe's families it executes (PLAYBOOK_RECIPES.md § Ask
what to run).

    recipe_scope.py ask [<recipe.md>] [--suggest <picks>] [--recipe <name>]   # no path: headers on stdin
    recipe_scope.py resolve <recipe.md> <picks>

`ask` needs only the recipe's `### <F><n> — <title> (kind ..., ...)` header lines: the
relay pipes those from the body it was served, so nothing is written to disk before the
user picks. It prints:

- between `SHOW:` and `END`, the message the relay sends: the recipe's steps as an
  overview, one numbered row per family with its title (`recipe_format.plain_title`)
  and its estimated time and cost, the estimate for the plan, extraction and report
  every run includes and for all steps together, then the prompt under the table. Without `--suggest` it asks what to run — *run 5,
  6* or *run all*. With `--suggest <picks>` (family ids or row numbers, as `resolve`
  reads them: the steps the user's request bears on) it proposes them by row number —
  *Based on your request, steps 5, 6 are relevant, shall we run them?*
- one `KEY:\t<n>\t<family id>\t<title>` line per family, for the relay alone: it maps
  the number or name the user gave to the row number it registers.

No family id reaches the user.

The estimates come from `spend_model.pick_estimates`: each family's median over the
recipe's earlier runs, or the model where no earlier run covered it. `--recipe` names
the recipe whose history applies; a recipe path supplies it from its frontmatter. Where
the model file is missing or unreadable, the table carries no estimate columns.

`resolve` reads `<picks>` — `all`, or row numbers and family ids, comma- or
space-separated (`4,5`, `c4 c5`), a leading `run` ignored (`run 5, 6`) — and prints `SCOPE:\t<ids>`: the picked families and
every family they read from, transitively (`recipe_format.scope_closure`), or `all` when
that is every family. `SAY:` is the line the relay puts to the user, naming in plain
words what runs, what was added because a picked step depends on it, and the estimated
cost and elapsed time of that scope. `setup_run.py
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


def estimates(fams: list[dict], recipe: str | None) -> dict | None:
    """Each family's estimated cost and minutes before the plan (`spend_model.py`); None
    when the model cannot be read."""
    try:
        import spend_model
        model = json.loads(spend_model.MODEL.read_text(encoding="utf-8"))
        return spend_model.pick_estimates(recipe, fams, model)
    except Exception:          # an estimate never blocks the question
        return None


def recipe_name(path: pathlib.Path) -> str | None:
    try:
        return recipe_format.frontmatter(path.read_text(encoding="utf-8")).get("name", "").strip("'\"") or None
    except OSError:
        return None


def usd(x: float) -> str:
    return f"${x:,.0f}" if x >= 1 else "under $1"     # DOCTRINE § Number conventions


def hm(minutes: float) -> str:
    m = max(1, round(minutes))
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def say(fams: list[dict], scope: dict | None, est: dict | None = None) -> str:
    if scope is None:
        line = "This run covers every step of the recipe."
    else:
        title = {f["id"]: recipe_format.plain_title(f["title"]) for f in fams}
        line = "This run covers: " + "; ".join(title[i] for i in scope["picked"]) + "."
        if scope["added"]:
            line += (" Added because the steps you picked depend on them: "
                     + "; ".join(title[i] for i in scope["added"]) + ".")
    if est:
        import spend_model
        tot = spend_model.scope_total(est, fams, scope["families"] if scope else None)
        line += (f" Estimated cost {usd(tot['cost_usd'])}, about "
                 f"{hm(tot['elapsed_minutes'])} from start to report.")
    return line


def suggestion(fams: list[dict], picks: str) -> str:
    """The prompt proposing the steps `picks` names, by row number, in recipe order."""
    toks = [t for t in re.split(r"[,\s]+", picks.strip().lower()) if t and t not in FILLER]
    ids = [f["id"] for f in fams]
    rows: list[int] = []
    for t in toks:
        n = int(t) if t.isdigit() else (ids.index(t) + 1 if t in ids else 0)
        if not 1 <= n <= len(ids):
            raise Refuse(f"--suggest {t!r} names no step: a row number 1-{len(ids)} or a "
                         f"family id ({', '.join(ids)})")
        if n not in rows:
            rows.append(n)
    if not rows:
        raise Refuse("--suggest names no step")
    rows.sort()
    if len(rows) == 1:
        return f"Based on your request, step {rows[0]} is relevant, shall we run it?"
    return (f"Based on your request, steps {', '.join(map(str, rows))} are relevant, "
            f"shall we run them?")


def table(fams: list[dict], suggest: str | None = None, est: dict | None = None) -> list[str]:
    prompt = ["", suggestion(fams, suggest) if suggest else PROMPT]
    if not est:
        rows = [HEAD, "", "| # | Step |", "|--:|---|"]
        rows += [f"| {n} | {recipe_format.plain_title(f['title'])} |"
                 for n, f in enumerate(fams, 1)]
        return rows + prompt
    import spend_model
    fe = est["families"]
    rows = [HEAD, "", "| # | Step | Time | Cost |", "|--:|---|--:|--:|"]
    rows += [f"| {n} | {recipe_format.plain_title(f['title'])} | {hm(fe[f['id']]['minutes'])} "
             f"| {usd(fe[f['id']]['cost_usd'])} |" for n, f in enumerate(fams, 1)]
    over, full = est["overhead"], spend_model.scope_total(est, fams, None)
    basis = (f"from {est['runs']} earlier runs of this analysis" if est["runs"]
             else "from earlier runs of other analyses")
    if est["runs"] and any(v["source"] == "model" for v in fe.values()):
        basis += "; a step none of them ran is priced from its kind"
    notes = [f"Every run also includes the plan, the data extraction and the report: about "
             f"{hm(over['minutes'])} and {usd(over['cost_usd'])}. All steps together: about "
             f"{usd(full['cost_usd'])} and {hm(full['elapsed_minutes'])} from start to report. "
             f"Steps run side by side, so a run takes less time than its steps' times added up.",
             f"Estimates at list rates, {basis}. The plan gives a closer figure once it has read "
             f"your data."]
    return rows + [""] + notes + prompt


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
        if argv[:1] == ["ask"]:
            rest, opts = argv[1:], {}
            for flag in ("--suggest", "--recipe"):
                if flag in rest:
                    i = rest.index(flag)
                    if i + 1 >= len(rest):
                        raise Refuse(f"{flag} needs a value")
                    opts[flag] = rest[i + 1]
                    rest = rest[:i] + rest[i + 2:]
            if len(rest) > 1:
                raise Refuse("ask takes one recipe path at most")
            path = pathlib.Path(rest[0]) if rest else None
            fams = load(path)
            name = opts.get("--recipe") or (recipe_name(path) if path else None)
            shown = table(fams, opts.get("--suggest"), estimates(fams, name))
            print("SHOW:")
            print("\n".join(shown))
            print("END")
            for n, f in enumerate(fams, 1):
                print(f"KEY:\t{n}\t{f['id']}\t{recipe_format.plain_title(f['title'])}")
            return 0
        if len(argv) == 3 and argv[0] == "resolve":
            path = pathlib.Path(argv[1])
            fams = load(path)
            scope = resolve(fams, argv[2])
            print(f"SCOPE:\t{','.join(scope['families']) if scope else 'all'}")
            print(f"SAY:\t{say(fams, scope, estimates(fams, recipe_name(path)))}")
            return 0
    except Refuse as exc:
        print(f"recipe_scope: {exc}", file=sys.stderr)
        return 2
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
