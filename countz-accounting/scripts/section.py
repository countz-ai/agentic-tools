#!/usr/bin/env python3
"""Print named sections of a plugin document, so a `FILE.md § Section` citation costs
its section and not its file.

    python3 scripts/section.py reference/VALIDATION.md "The validation scope" Findings

The file is taken as the citation writes it: an absolute path; a path under the plugin
root (`reference/VALIDATION.md`); or a bare name (`VALIDATION.md`), found by a unique
basename match in the plugin tree - an ambiguous name (`SKILL.md`) lists its candidates
and exits non-zero. A heading argument
matches case-insensitively against the heading text, ignoring any leading `N.` number;
a unique substring is enough. Several bare words are tried joined as one heading first
(`The validation scope` unquoted), and read as one heading each only when the joined
form matches nothing. A section runs from its heading to the next heading at the
same or a shallower level. An unmatched or ambiguous name prints the document's headings
and exits non-zero — never a silent miss, and never a reason to read the file whole.

For a client file the user supplied, use peek.py. This script reads plugin documents.
"""
import pathlib
import re
import sys

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
NUMBER = re.compile(r"^\d+[.)]?\s+")


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, text) for every heading, fenced code skipped."""
    out, fence = [], False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fence = not fence
        elif not fence and (m := HEADING.match(line)):
            out.append((i, len(m.group(1)), m.group(2)))
    return out


def keys(text: str) -> set[str]:
    """The names one heading answers to: its whole text, the part before an em dash,
    its leading number, and its text with that number stripped."""
    out = {text, text.split(" \u2014 ")[0], NUMBER.sub("", text)}
    if m := NUMBER.match(text):
        out.add(m.group(0).strip().rstrip(".)"))
    return {k.strip().casefold() for k in out if k.strip()}


SKIP = {"dist", ".venv", "__pycache__", "node_modules"}


def locate(name: str) -> pathlib.Path:
    path = pathlib.Path(name)
    if path.is_absolute():
        if path.is_file():
            return path
        raise SystemExit(f"section: no such file: {path}")
    under = PLUGIN_ROOT / path
    if under.is_file():
        return under
    hits = [p for p in PLUGIN_ROOT.rglob(path.name)
            if p.is_file() and not SKIP & set(p.relative_to(PLUGIN_ROOT).parts)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SystemExit(f"section: no file named {path.name!r} under {PLUGIN_ROOT}")
    raise SystemExit(f"section: {path.name!r} is ambiguous; give the path:\n"
                     + "\n".join(f"  {p.relative_to(PLUGIN_ROOT)}" for p in sorted(hits)))


def resolves(heads: list[tuple[int, int, str]], name: str) -> bool:
    try:
        select(heads, name)
    except SystemExit:
        return False
    return True


def select(heads: list[tuple[int, int, str]], name: str) -> tuple[int, int, str]:
    key = name.strip().lstrip("\u00a7").strip().casefold()
    exact = [h for h in heads if key in keys(h[2])]
    hits = exact or [h for h in heads if key in h[2].casefold()]
    if len(hits) != 1:
        raise SystemExit(
            f"section: {'no' if not hits else 'ambiguous'} heading {name!r}. "
            "Headings:\n" + "\n".join(f"  {'#' * lv} {t}" for _, lv, t in heads))
    return hits[0]


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("usage: section.py <file> <heading> [<heading> ...]")
    path = locate(sys.argv[1])
    lines = path.read_text().splitlines()
    heads = headings(lines)
    names = sys.argv[2:]
    if len(names) > 1 and resolves(heads, " ".join(names)):
        names = [" ".join(names)]
    for n, name in enumerate(names):
        start, level, _ = select(heads, name)
        end = next((i for i, lv, _ in heads if i > start and lv <= level), len(lines))
        if n:
            print()
        print("\n".join(lines[start:end]).rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
