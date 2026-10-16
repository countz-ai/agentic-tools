#!/usr/bin/env python3
"""Refuse the MCP tools the Countz account blocks, for the rest of the session.

`get_countz_config` returns `blocked_tools`, the tenant's list of MCP tool calls the
session must not make (the user cannot change it; empty by default, so nothing is
blocked). This one script serves two hook events (hooks/hooks.json):

    PostToolUse on the `countz` server's `get_countz_config`: records that list, and
        nothing else from the result, for this session, in
        `${CLAUDE_PLUGIN_DATA}/sessions/<session_id>.json` (falls back to
        `~/.countz-accounting/sessions/`).
    PreToolUse on every MCP tool (`mcp__*`): refuses a call the recorded list names,
        a `get_countz_config` call with any argument, and a
        `get_recipe_for_countz_analysis` call whose arguments are anything but `recipe`
        set to a name of 1 to 32 characters, each with the reason Claude reads, and lets
        everything else through. The argument checks need no recorded state.

An entry is `<server>/<tool>`, `<server>/*`, or `*` alone. `<server>` is the
server's short name (`countz`); the host prefixes it (`mcp__plugin_countz-accounting_countz__…`,
`mcp__claude_ai_countz__…`), so a wire server name matches the entry when it is the
short name or ends in `_<short name>`.

Once a session has called `get_countz_config`, the list holds for the rest of it: the
main thread, every subagent and every forked skill. A plugin hook fires inside
subagents, and a subagent's hook input carries its parent's `session_id`, so all of them
read the one state file. `get_countz_config` itself always passes: the list comes from
it. A session that has not called it holds no list, so nothing is refused there: the
plugin's hooks load in every session, Countz or not.

Never fails a tool call by crashing: an unreadable payload or state file lets the call
through, with a note on stderr. Stdlib only.

    mcp_blocklist.py            read the hook input on stdin (the hook entry point)
    mcp_blocklist.py --selftest
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

SERVER = "countz"
CONFIG_TOOL = "get_countz_config"
RECIPE_TOOL = "get_recipe_for_countz_analysis"
RECIPE_NAME_MAX = 32     # the catalog's longest name, stock-based-compensation, is 24
_WIRE = re.compile(r"^mcp__(.+)__([^_].*)$")


def split_wire(name: str) -> tuple[str, str] | None:
    """(wire server, tool) of an MCP tool name, or None for a built-in tool."""
    m = _WIRE.match(name or "")      # greedy: the tool follows the LAST double underscore
    return (m.group(1), m.group(2)) if m else None


def server_is(wire_server: str, short: str) -> bool:
    return wire_server == short or wire_server.endswith("_" + short)


def listed(wire_server: str, tool: str, entries: list[str]) -> bool:
    for entry in entries:
        entry = str(entry).strip()
        if entry == "*":
            return True
        short, sep, want = entry.partition("/")
        if sep and server_is(wire_server, short) and want in ("*", tool):
            return True
    return False


def state_dir() -> pathlib.Path:
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    base = pathlib.Path(data) if data else pathlib.Path.home() / ".countz-accounting"
    return base / "sessions"


def state_path(session_id: str) -> pathlib.Path:
    return state_dir() / (re.sub(r"[^A-Za-z0-9_.-]", "_", session_id) + ".json")


def payload(resp, depth: int = 0) -> dict | None:
    """The tool's result object out of whatever wrapping the host hands the hook: the
    dict itself, its JSON text, a list of content blocks, or `structuredContent`."""
    if depth > 4:
        return None
    if isinstance(resp, str):
        try:
            return payload(json.loads(resp), depth + 1)
        except ValueError:
            return None
    if isinstance(resp, list):
        for block in resp:
            got = payload(block.get("text") if isinstance(block, dict) else block, depth + 1)
            if got is not None:
                return got
        return None
    if isinstance(resp, dict):
        if "blocked_tools" in resp:
            return resp
        for key in ("structuredContent", "result", "content", "text"):
            if key in resp:
                got = payload(resp[key], depth + 1)
                if got is not None:
                    return got
    return None


def record(event: dict) -> None:
    split = split_wire(event.get("tool_name", ""))
    if not split or not server_is(split[0], SERVER) or split[1] != CONFIG_TOOL:
        return
    got = payload(event.get("tool_response"))
    sid = event.get("session_id")
    if got is None or not isinstance(got.get("blocked_tools"), list) or not sid:
        print(f"mcp_blocklist: {split[1]} result not readable - blocked tools unchanged",
              file=sys.stderr)
        return
    state = {"blocked_tools": [str(e) for e in got["blocked_tools"]]}
    path = state_path(sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def args_reason(tool: str, args) -> str | None:
    """The refusal reason for a `countz` call whose arguments the server would not
    accept; None lets it through."""
    args = args if isinstance(args, dict) else {}
    if tool == CONFIG_TOOL and args:
        return f"Not sent: `{CONFIG_TOOL}` takes no arguments. Call it again with none."
    if tool == RECIPE_TOOL:
        recipe = args.get("recipe")
        if (set(args) != {"recipe"} or not isinstance(recipe, str) or not recipe
                or len(recipe) > RECIPE_NAME_MAX):
            return (f"Not sent: `{RECIPE_TOOL}` takes one argument, `recipe`, set to a "
                    f"catalog `name` from `{CONFIG_TOOL}`. When no catalog entry matches "
                    f"the ask, call `create_countz_playbook_recipe` instead.")
    return None


def decide(event: dict) -> str | None:
    """The refusal reason for a call the blocked list names or a `countz` call with
    arguments the server would not accept; None lets it through."""
    split = split_wire(event.get("tool_name", ""))
    if not split:
        return None
    server, tool = split
    if server_is(server, SERVER):
        reason = args_reason(tool, event.get("tool_input"))
        if reason or tool == CONFIG_TOOL:
            return reason
    sid = event.get("session_id")
    path = state_path(sid) if sid else None
    if path is None or not path.is_file():
        return None
    try:
        blocked = json.loads(path.read_text()).get("blocked_tools")
    except ValueError:
        print(f"mcp_blocklist: {path} unreadable - call let through", file=sys.stderr)
        return None
    if not isinstance(blocked, list) or not listed(server, tool, blocked):
        return None
    return (f"Not allowed: this Countz account blocks `{tool}` on the `{server}` server. "
            f"Do not call it again or reach its result another way. Tell the user it is "
            f"not allowed for their account, and continue without it.")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if event.get("hook_event_name") == "PostToolUse":
        record(event)
        return 0
    reason = decide(event)
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))
    return 0


def selftest() -> int:
    import tempfile
    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        os.environ["CLAUDE_PLUGIN_DATA"] = td
        cfg = "mcp__plugin_countz-accounting_countz__get_countz_config"
        recipe = "mcp__claude_ai_countz__get_recipe_for_countz_analysis"
        drive = "mcp__claude_ai_Google_Drive__search_files"
        pre = {"hook_event_name": "PreToolUse", "session_id": "s1"}
        post = {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": cfg}
        ok = {"recipe": "stock-based-compensation"}
        if decide({**pre, "tool_name": drive}) or decide({**pre, "tool_name": recipe,
                                                         "tool_input": ok}):
            bad.append("a session with no list refused a call")
        if decide({**pre, "tool_name": cfg, "tool_input": {}}):
            bad.append("get_countz_config with no arguments was refused")
        if not decide({**pre, "tool_name": cfg, "tool_input": {"tenant": "t1"}}):
            bad.append("get_countz_config with an argument passed")
        for args, what in (({}, "no arguments"), (None, "no tool input"),
                           ({"recipe": ""}, "an empty name"),
                           ({"recipe": 7}, "a name that is not text"),
                           ({"recipe": "x" * 33}, "a 33-character name"),
                           ({**ok, "ask": "prove cash"}, "an extra `ask`"),
                           ({"ask": "prove cash"}, "`ask` alone")):
            if not decide({**pre, "tool_name": recipe, "tool_input": args}):
                bad.append(f"a recipe call with {what} passed")
        if decide({**pre, "tool_name": recipe, "tool_input": {"recipe": "x" * 32}}):
            bad.append("a 32-character name was refused")
        record({**post, "tool_response": [{"type": "text", "text": json.dumps(
            {"blocked_tools": [], "catalog_yaml": "analyses: []"})}]})
        if "catalog_yaml" in json.loads(state_path("s1").read_text()):
            bad.append("the config result's catalog was recorded")
        if not state_path("s1").is_file():
            bad.append("the config result was not recorded")
        if decide({**pre, "tool_name": drive}) or decide({**pre, "tool_name": recipe,
                                                         "tool_input": ok}):
            bad.append("an empty list refused a call")
        record({**post, "tool_response": {"blocked_tools": ["Google_Drive/*"]}})
        if not decide({**pre, "tool_name": drive}):
            bad.append("a blocked tool passed")
        if decide({**pre, "tool_name": recipe, "tool_input": ok}):
            bad.append("a tool the list does not name was refused")
        if not decide({**pre, "tool_name": drive, "agent_id": "a1",
                       "agent_type": "general-purpose"}):
            bad.append("a subagent's call to a blocked tool passed")
        if decide({**pre, "tool_name": "Bash"}):
            bad.append("a built-in tool was refused")
        record({**post, "tool_response": {"blocked_tools": ["*"]}})
        if decide({**pre, "tool_name": cfg}):
            bad.append("get_countz_config was refused")
        if not decide({**pre, "tool_name": recipe, "tool_input": ok}):
            bad.append("`*` let a call through")
        record({"hook_event_name": "PostToolUse", "session_id": "s1",
                "tool_name": recipe,
                "tool_response": json.dumps({"blocked_tools": []})})
        st = json.loads(state_path("s1").read_text())
        if st != {"blocked_tools": ["*"]}:
            bad.append(f"a recipe result changed the state: {st}")
        if split_wire(cfg) != ("plugin_countz-accounting_countz", "get_countz_config"):
            bad.append("split_wire mis-split a plugin tool name")
        if not listed("claude_ai_countz", "get_recipe_for_countz_analysis",
                      ["countz/get_recipe_for_countz_analysis"]):
            bad.append("a `<server>/<tool>` entry did not match its tool")
    for b in bad:
        print(f"mcp_blocklist selftest: {b}", file=sys.stderr)
    print(f"mcp_blocklist selftest: {len(bad)} defect(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if sys.argv[1:] == ["--selftest"] else main())
