#!/usr/bin/env python3
"""Append the plugin documents an agent carries in full to the end of its agent file.

    python3 scripts/build_agents.py           rewrite every agent INCLUDES names
    python3 scripts/build_agents.py --check   exit 1, naming each file that is not current

An agent file's body is its sub-agent's system prompt. A document that every step of the
agent reads goes there, instead of each launch reading it. It is then present from the
first turn, cannot be skipped, and is one cached prefix for every sibling the relay
launches (RUN_CONTRACT.md § Every wave). `agents/<name>.md` is written by hand above
MARKER and generated below it. To change it, edit the charter above the marker or the
included documents, then run `make agents`, which runs this script. `check-plugin.py`
runs `--check`, so a stale file fails the build. Stdlib only.
"""
from __future__ import annotations

import pathlib
import sys

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
# Agent name -> the documents appended whole, in order.
INCLUDES = {
    "worker": ("reference/CONDUCT.md", "reference/DOCTRINE.md", "reference/EVIDENCE.md"),
}
MARKER = ("<!-- Generated below this line by scripts/build_agents.py from the documents it "
          "names. Edit those documents and run the script; never edit below this line. -->")


def render(name: str, root: pathlib.Path = PLUGIN_ROOT) -> tuple[pathlib.Path, str]:
    """Return the agent file and the text it should hold: the hand-written part above
    MARKER, then MARKER, then each included document under a line naming it."""
    path = root / "agents" / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    head = text.split(MARKER, 1)[0].rstrip() + "\n"
    parts = [head, "\n" + MARKER + "\n"]
    for rel in INCLUDES[name]:
        doc = (root / rel).read_text(encoding="utf-8").strip()
        parts.append(f"\n---\n\nThe text from here to the next horizontal rule is "
                     f"`${{CLAUDE_PLUGIN_ROOT}}/{rel}`, in full.\n\n{doc}\n")
    return path, "".join(parts)


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for name in INCLUDES:
        path, want = render(name)
        if path.read_text(encoding="utf-8") == want:
            continue
        if check:
            stale.append(str(path.relative_to(PLUGIN_ROOT)))
        else:
            path.write_text(want, encoding="utf-8")
            print(f"wrote {path.relative_to(PLUGIN_ROOT)}")
    if stale:
        print("not current - run `make agents`: " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
