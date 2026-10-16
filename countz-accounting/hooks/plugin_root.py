#!/usr/bin/env python3
"""SessionStart hook: tell the session where this plugin's files are.

    plugin_root.py               # run by the hook, CLAUDE_PLUGIN_ROOT set
    plugin_root.py --selftest

The skills write their paths as `${CLAUDE_PLUGIN_ROOT}/...`. The Bash tool's commands do
not carry that variable, and a host that loads a skill from a copy of the skill folder
alone can leave the model without the plugin's `reference/` and `scripts/`, so it goes
looking for them. This hook runs where the variable is set, and:

- prints one line naming the folder, which the host adds to the session's context;
- appends `export COUNTZ_PLUGIN_ROOT=<folder>` to `$CLAUDE_ENV_FILE` where the host
  provides one, so every later Bash command carries it (the recipe skills' first
  command reads it).

Never fails the session: exit 0 whatever happens.
"""
from __future__ import annotations

import os
import pathlib
import shlex
import sys


def root() -> str:
    return os.environ.get("CLAUDE_PLUGIN_ROOT") or str(pathlib.Path(__file__).resolve().parent.parent)


def run() -> int:
    folder = root()
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        try:
            with open(env_file, "a", encoding="utf-8") as fh:
                fh.write(f"export COUNTZ_PLUGIN_ROOT={shlex.quote(folder)}\n")
        except OSError:
            pass
    print(f"countz-accounting plugin root: {folder}. Wherever a countz-accounting skill "
          f"writes ${{CLAUDE_PLUGIN_ROOT}}, it means this folder: read reference/ and run "
          f"scripts/ from here, and never search the filesystem for it.")
    return 0


def selftest() -> int:
    import subprocess
    import tempfile
    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        env_file = pathlib.Path(td) / "env.sh"
        folder = pathlib.Path(td) / "my plugins" / "countz-accounting"
        r = subprocess.run([sys.executable, __file__], capture_output=True, text=True,
                           env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(folder),
                                "CLAUDE_ENV_FILE": str(env_file)})
        if r.returncode != 0 or f"plugin root: {folder}." not in r.stdout:
            bad.append(f"the context line does not name the folder: {r.stdout.strip()[:120]}")
        got = env_file.read_text() if env_file.is_file() else ""
        if got != f"export COUNTZ_PLUGIN_ROOT={shlex.quote(str(folder))}\n":
            bad.append(f"the env file is not one quoted export: {got!r}")
        echo = subprocess.run(["sh", "-c", f'. "{env_file}"; printf %s "$COUNTZ_PLUGIN_ROOT"'],
                              capture_output=True, text=True)
        if echo.stdout != str(folder):
            bad.append(f"the export does not read back in a shell: {echo.stdout!r}")
        r = subprocess.run([sys.executable, __file__], capture_output=True, text=True,
                           env={k: v for k, v in os.environ.items()
                                if k not in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_ENV_FILE")})
        if r.returncode != 0 or str(pathlib.Path(__file__).resolve().parent.parent) not in r.stdout:
            bad.append("without the variable it must name the folder it sits in")
    for b in bad:
        print(f"plugin_root selftest: {b}", file=sys.stderr)
    print(f"plugin_root selftest: {len(bad)} defect(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        raise SystemExit(selftest())
    try:
        raise SystemExit(run())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - a session never fails on this hook
        raise SystemExit(0)
