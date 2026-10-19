#!/usr/bin/env python3
"""What a step's inputs already hold, read from the run directory when its brief is written.

    python3 handoff.py <run_dir> <brief.md>     print the handoff for that brief's arguments

A fresh worker otherwise spends its first turns finding out what its inputs are: which
cache ids exist and their columns, which item tables and figure ids each `_from` check
left, what those checks concluded and carried forward, and the kit's call signatures.
`run_state.render_brief` appends this block to every check brief, so the worker starts
with those facts instead of rediscovering them. It names only what the brief's own
params name (`params.reads`, every `*_from`), as `agents/worker.md` § Your procedure
bounds a step's inputs. Standard library only: the relay runs run_state with plain
python3.
"""
from __future__ import annotations

import ast
import collections
import json
import pathlib
import re
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent

# The kit calls a check script makes, by module: the signature and the first sentence of
# the docstring are rendered from the source, so the block cannot drift from the code.
KIT = {
    "evidence": ["select", "span"],
    "cache": ["read", "scan", "entry"],
    "figures": ["Ledger", "Ledger.cite", "Ledger.population", "Ledger.fig", "Ledger.tie",
                "Ledger.write", "room", "check_output", "figure", "declared", "load", "fmt",
                "md_table"],
    "items": ["read_items", "write_items", "table_path", "manifest_md"],
    "step_record": ["start", "finish", "place_tab"],
    "wbkit": ["styles", "band", "header", "section", "table", "text", "amount", "count",
              "total", "status", "fit_rows", "finish", "save"],
}

HEADING = "## What your inputs already hold"
HEAD = f"""
{HEADING}

Written by `scripts/handoff.py` from the run directory when this brief was written, and
limited to what your params name. Rely on it to know what exists and how to call it: open
a file only for a value this block does not carry, and run the checks your procedure
requires as written.
"""


def _from_checks(params: dict) -> dict[str, list[str]]:
    """check id -> the param keys that name it, in first-mention order."""
    out: dict[str, list[str]] = {}
    for k, v in params.items():
        if not k.endswith("_from") or k == "cache_from":
            continue
        for c in ([v] if isinstance(v, str) else v if isinstance(v, list) else []):
            if isinstance(c, str) and c:
                out.setdefault(c, []).append(k)
    return out


def _record(run_dir: pathlib.Path, check: str) -> dict:
    """The latest terminal step record of a check, or {}."""
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = [d for d in run.get("dispatches", []) if d.get("check_id") == check
            and d.get("state") in ("ok", "blocked")]
    for d in reversed(rows):
        try:
            return json.loads((run_dir / d["record"]).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            continue
    return {}


def _csv_head(path: pathlib.Path) -> tuple[list[str], int]:
    import csv
    with path.open(newline="", encoding="utf-8") as fh:
        r = csv.reader(fh)
        cols = next(r, [])
        return cols, sum(1 for _ in r)


def _figure_ids(path: pathlib.Path) -> list[str]:
    """Top-level `- id:` entries of a figures ledger, read without a YAML parser."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return re.findall(r"^- id:\s*['\"]?([^'\"\s]+)", text, re.M)


def _prefixes(ids: list[str], width: int = 3, examples: int = 2, most: int = 20) -> list[str]:
    """Figure ids grouped by their first `width` segments, largest groups first."""
    groups: dict[str, list[str]] = collections.OrderedDict()
    for i in ids:
        groups.setdefault(".".join(i.split(".")[:width]), []).append(i)
    ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    out = [f"`{p}` {len(v)}" + (f" (e.g. {', '.join('`' + x + '`' for x in v[:examples])})"
                                 if len(v) > 1 or v[0] != p else "")
           for p, v in ranked[:most]]
    if len(ranked) > most:
        out.append(f"{len(ranked) - most} smaller prefixes holding "
                   f"{sum(len(v) for _, v in ranked[most:])} ids")
    return out


def cache_block(run_dir: pathlib.Path, reads: list[str]) -> list[str]:
    try:
        m = json.loads((run_dir / "cache" / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    files = {e.get("id"): e for e in m.get("files", [])}
    out = ["### Cache tables your params read (`cache/manifest.json`)", "",
           "The manifest's `files` is a list of entries keyed by `id`; read a table with "
           "`evidence.select(run_dir, sql, id=...)` (the SQL names the id as its table) or "
           "`cache.read(run_dir, id)`.", ""]
    for rid in reads:
        e = files.get(rid)
        if e is None:
            out.append(f"- `{rid}` — not in the manifest (it holds "
                       f"{', '.join('`' + k + '`' for k in files)})")
            continue
        cols = ", ".join(f"{c['name']} ({c.get('dtype', '?')})" for c in e.get("columns", []))
        ct = e.get("control_total") or {}
        tot = f"; control total {ct.get('column')} = {ct.get('value')}" if ct.get("column") else ""
        out.append(f"- `{rid}` — {e.get('what', '')}. `{e.get('file', '')}`"
                   f"{' sheet ' + str(e['sheet']) if e.get('sheet') else ''}; "
                   f"{e.get('row_count', '?')} rows{tot}. Columns: {cols}")
    notx = m.get("not_extracted") or []
    if notx:
        out += ["", "Read as passages, not tables (`not_extracted`):"]
        out += [f"- `{n.get('file')}` {n.get('where', '')}: {n.get('what', '')}" for n in notx]
    return out + [""]


def checks_block(run_dir: pathlib.Path, froms: dict[str, list[str]]) -> list[str]:
    if not froms:
        return []
    out = ["### Your input checks (the `_from` params)", ""]
    for check, keys in froms.items():
        rec = _record(run_dir, check)
        out.append(f"#### `{check}` ({', '.join('`' + k + '`' for k in keys)}) — "
                   f"{rec.get('outcome', 'no terminal record')}")
        if rec.get("conclusion"):
            out.append(f"Conclusion: {rec['conclusion']}")
        if rec.get("notes"):
            out.append(f"Notes: {rec['notes']}")
        tables = sorted((run_dir / "checks").glob(f"{check}-*.csv"))
        if tables:
            out.append(f"Item tables (`items.read_items(run_dir, \"{check}\", <name>)`):")
            for t in tables:
                cols, n = _csv_head(t)
                out.append(f"- `{t.stem[len(check) + 1:]}`: {n} rows; {', '.join(cols)}")
        ids = _figure_ids(run_dir / "workpapers" / f"figures-{check}.yaml")
        if ids:
            out.append(f"Figures (`figures.load(run_dir, \"{check}\")`, {len(ids)} ids), by "
                       f"prefix: " + "; ".join(_prefixes(ids)))
        md = run_dir / "checks" / f"{check}.md"
        if md.is_file():
            out.append(f"Narrative: `checks/{check}.md` "
                       f"({md.read_text(encoding='utf-8').count(chr(10))} lines)")
        out.append("")
    return out


def scripts_block(run_dir: pathlib.Path, froms: dict[str, list[str]]) -> list[str]:
    """Scripts this run's terminal checks wrote: working examples of the kit in use."""
    try:
        run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    done = {d["check_id"] for d in run.get("dispatches", [])
            if d.get("check_id") and d.get("state") == "ok"}
    wp = run_dir / "workpapers"
    # the input checks' own tabs first: the layout this step's tab most resembles
    tabs = sorted(p for p in wp.glob("tab-*.py") if p.stem[4:] in done)
    tabs = [p for p in tabs if p.stem[4:] in froms] + [p for p in tabs if p.stem[4:] not in froms]
    own = sorted(p for c in froms for p in wp.glob(f"*{c}*.py") if not p.name.startswith("tab-"))
    if not tabs and not own:
        return []
    out = ["### Scripts that passed their gates in this run", ""]
    if tabs:
        out.append("Tab scripts (the workbook layout in working code): "
                   + ", ".join(f"`workpapers/{p.name}`" for p in tabs[:4]))
    if own:
        out.append("Your input checks' scripts: " + ", ".join(f"`workpapers/{p.name}`" for p in own))
    return out + [""]


def _args(node) -> str:
    a = node.args
    if a.args and a.args[0].arg == "self":
        a = ast.arguments(posonlyargs=a.posonlyargs, args=a.args[1:], vararg=a.vararg,
                          kwonlyargs=a.kwonlyargs, kw_defaults=a.kw_defaults, kwarg=a.kwarg,
                          defaults=a.defaults)
    return ast.unparse(a)


def _sig(node) -> str:
    a = _args(node)
    doc = (ast.get_docstring(node) or "").strip().split("\n\n")[0].replace("\n", " ")
    doc = re.split(r"(?<=[.;])\s", doc, maxsplit=1)[0]
    return f"`{node.name}({a})`" + (f" — {doc}" if doc else "")


def kit_block() -> list[str]:
    out = ["### Kit calls (from `scripts/`, imported with `sys.path` on that directory)", ""]
    for mod, names in KIT.items():
        try:
            tree = ast.parse((SCRIPTS / f"{mod}.py").read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        top = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        lines = []
        for name in names:
            cls, _, meth = name.partition(".")
            node = top.get(cls)
            if node is not None and meth:
                node = next((n for n in node.body if isinstance(n, ast.FunctionDef)
                             and n.name == meth), None)
                if node is not None:
                    lines.append(f"  - {cls}.{_sig(node)}")
                continue
            if isinstance(node, ast.ClassDef):
                init = next((n for n in node.body if isinstance(n, ast.FunctionDef)
                             and n.name == "__init__"), None)
                lines.append(f"  - `{node.name}" + (f"({_args(init)})`" if init else "`"))
            elif node is not None:
                lines.append(f"  - {_sig(node)}")
        if lines:
            out.append(f"- `{mod}`:")
            out += lines
    return out + [""]


def held_out(params, held_checks=(), held_reads=()) -> dict:
    """`params` less what an agent already holds in context: the `_from` checks it ran and
    the cache tables those read. A holder lane's next brief hands over only the rest
    (scripts/lanes.py)."""
    if not isinstance(params, dict):
        return {}
    held_checks, held_reads = set(held_checks), set(held_reads)
    out = {}
    for k, v in params.items():
        if k.endswith("_from") and k != "cache_from":
            vs = [c for c in ([v] if isinstance(v, str) else v if isinstance(v, list) else [])
                  if c not in held_checks]
            if vs:
                out[k] = vs
        elif k == "reads":
            rs = [r for r in v or [] if isinstance(r, str) and r not in held_reads]
            if rs:
                out[k] = rs
    return out


def replace(path, block: str) -> None:
    """Swap a brief's handoff block (from HEADING to the end of the file) for `block`."""
    path = pathlib.Path(path)
    t = path.read_text(encoding="utf-8")
    i = t.find("\n" + HEADING)
    body = (t[:i] if i >= 0 else t).rstrip() + "\n"
    path.write_text(body + block, encoding="utf-8")


def render(run_dir, params, kit: bool = True) -> str:
    """The handoff block for a brief whose params are `params`; '' when it names nothing.
    `kit=False` leaves out the kit calls, for an agent that already has them in context."""
    run_dir = pathlib.Path(run_dir)
    if not isinstance(params, dict):
        return ""
    reads = [r for r in params.get("reads") or [] if isinstance(r, str)]
    froms = _from_checks(params)
    if not reads and not froms:
        return ""
    parts = cache_block(run_dir, reads) + checks_block(run_dir, froms) \
        + scripts_block(run_dir, froms) + (kit_block() if kit else [])
    return HEAD + "\n" + "\n".join(parts).rstrip() + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    run_dir, brief = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    m = re.search(r"^\s*params=(.*)$", brief.read_text(encoding="utf-8"), re.M)
    params = json.loads(m.group(1)) if m else {}
    sys.stdout.write(render(run_dir, params))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
