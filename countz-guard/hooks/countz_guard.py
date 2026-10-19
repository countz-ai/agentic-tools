#!/usr/bin/env python3
"""Refuse the `countz` MCP calls policy.json blocks.

policy.json, at the plugin root, holds `blocked_tools`, the tool calls the session must
not make, and `recipe_name_max`, the longest recipe name a
`get_recipe_for_countz_analysis` call may carry. This script is the PreToolUse hook on
every `countz` tool (hooks/hooks.json). It refuses a call `blocked_tools` names, a
`get_countz_config` call with any argument, any other `countz` call whose arguments are
not a JSON object, and a `get_recipe_for_countz_analysis` call whose arguments are
anything but `recipe` set to a name of 1 to `recipe_name_max` characters, each with the
reason Claude reads, and lets everything else through.

An entry is `<server>/<tool>`, `<server>/*`, or `*` alone. `<server>` is the
server's short name (`countz`); the host prefixes it (`mcp__plugin_countz-accounting_countz__…`,
`mcp__claude_ai_countz__…`), so a wire server name matches the entry when it is the
short name or ends in `_<short name>`. A call to any other server passes.

A plugin hook fires in the main thread, in every subagent and in every forked skill, so
the policy holds in all of them. `get_countz_config` itself always passes.

Never fails a tool call by crashing: an unreadable payload or policy file lets the call
through, with a note on stderr. Stdlib only.

    countz_guard.py            read the hook input on stdin (the hook entry point)
    countz_guard.py --selftest
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

SERVER = "countz"
CONFIG_TOOL = "get_countz_config"
RECIPE_TOOL = "get_recipe_for_countz_analysis"
CREATE_TOOL = "create_countz_playbook_recipe"
POLICY = pathlib.Path(__file__).resolve().parent.parent / "policy.json"
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


def args_reason(tool: str, args, policy: dict) -> str | None:
    """The refusal reason for a `countz` call whose arguments the policy or the server
    would not accept; None lets it through."""
    if tool == CONFIG_TOOL:
        if args:
            return f"Not sent: `{CONFIG_TOOL}` takes no arguments. Call it again with none."
        return None
    if not isinstance(args, dict):
        return f"Not sent: the arguments of `{tool}` are not a JSON object."
    if tool == RECIPE_TOOL:
        recipe, most = args.get("recipe"), policy.get("recipe_name_max")
        if (set(args) != {"recipe"} or not isinstance(recipe, str) or not recipe
                or (isinstance(most, int) and len(recipe) > most)):
            if listed(SERVER, CREATE_TOOL, policy.get("blocked_tools") or []):
                miss = "tell the user the catalog has no recipe for it"
            else:
                miss = f"call `{CREATE_TOOL}` instead"
            return (f"Not sent: `{RECIPE_TOOL}` takes one argument, `recipe`, set to a "
                    f"catalog `name` from `{CONFIG_TOOL}`. When no catalog entry matches "
                    f"the ask, {miss}.")
    return None


def decide(event: dict) -> str | None:
    """The refusal reason for a `countz` call the policy blocks or whose arguments the
    policy or the server would not accept; None lets it through."""
    split = split_wire(event.get("tool_name", ""))
    if not split or not server_is(split[0], SERVER):
        return None
    server, tool = split
    try:
        policy = json.loads(POLICY.read_text())
    except (OSError, ValueError):
        print(f"countz_guard: {POLICY} unreadable - call let through", file=sys.stderr)
        return None
    reason = args_reason(tool, event.get("tool_input"), policy)
    if reason or tool == CONFIG_TOOL:
        return reason
    blocked = policy.get("blocked_tools")
    if not isinstance(blocked, list) or not listed(server, tool, blocked):
        return None
    return (f"Not allowed: the countz-guard policy blocks `{tool}` on the `{server}` "
            f"server. Do not call it again or reach its result another way. Tell the user "
            f"it is not allowed in this session, and continue without it.")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
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
    global POLICY
    bad: list[str] = []
    cfg = "mcp__plugin_countz-accounting_countz__get_countz_config"
    recipe = "mcp__claude_ai_countz__get_recipe_for_countz_analysis"
    create = "mcp__claude_ai_countz__create_countz_playbook_recipe"
    drive = "mcp__claude_ai_Google_Drive__search_files"
    pre = {"hook_event_name": "PreToolUse", "session_id": "s1"}
    ok = {"recipe": "stock-based-compensation"}
    if not decide({**pre, "tool_name": create, "tool_input": {"ask": "prove cash"}}):
        bad.append("the shipped policy let create_countz_playbook_recipe through")
    if not decide({**pre, "tool_name": recipe, "tool_input": {"recipe": "x" * 33}}):
        bad.append("the shipped policy let a 33-character name through")
    if decide({**pre, "tool_name": recipe, "tool_input": {"recipe": "x" * 32}}):
        bad.append("the shipped policy refused a 32-character name")
    if CREATE_TOOL in (decide({**pre, "tool_name": recipe, "tool_input": {}}) or ""):
        bad.append("a recipe refusal pointed at the blocked create tool")
    with tempfile.TemporaryDirectory() as td:
        POLICY = pathlib.Path(td) / "policy.json"

        def policy(**kw) -> None:
            POLICY.write_text(json.dumps(kw))

        if decide({**pre, "tool_name": recipe, "tool_input": ok}):
            bad.append("a missing policy refused a call")
        policy()
        if decide({**pre, "tool_name": create, "tool_input": {"ask": "prove cash"}}) \
                or decide({**pre, "tool_name": recipe, "tool_input": ok}):
            bad.append("an empty policy refused a call")
        if decide({**pre, "tool_name": recipe, "tool_input": {"recipe": "x" * 99}}):
            bad.append("a policy with no `recipe_name_max` capped the name")
        if decide({**pre, "tool_name": cfg, "tool_input": {}}):
            bad.append("get_countz_config with no arguments was refused")
        if CREATE_TOOL not in (decide({**pre, "tool_name": recipe, "tool_input": {}}) or ""):
            bad.append("a recipe refusal did not point at the allowed create tool")
        for args in (None, [], "", "recipe=debt", ["debt"]):
            if not decide({**pre, "tool_name": recipe, "tool_input": args}):
                bad.append(f"a recipe call with tool input {args!r} passed")
        for args in (None, [], ""):
            if decide({**pre, "tool_name": cfg, "tool_input": args}):
                bad.append(f"get_countz_config with empty tool input {args!r} was refused")
        for args in ("recipe=debt", ["debt"]):
            if not decide({**pre, "tool_name": cfg, "tool_input": args}):
                bad.append(f"get_countz_config with tool input {args!r} passed")
        if not decide({**pre, "tool_name": cfg, "tool_input": {"tenant": "t1"}}):
            bad.append("get_countz_config with an argument passed")
        for args, what in (({}, "no arguments"),
                           ({"recipe": ""}, "an empty name"),
                           ({"recipe": 7}, "a name that is not text"),
                           ({**ok, "ask": "prove cash"}, "an extra `ask`"),
                           ({"ask": "prove cash"}, "`ask` alone")):
            if not decide({**pre, "tool_name": recipe, "tool_input": args}):
                bad.append(f"a recipe call with {what} passed")
        policy(blocked_tools=["countz/create_countz_playbook_recipe", "Google_Drive/*"])
        if not decide({**pre, "tool_name": create, "tool_input": {}}):
            bad.append("a blocked tool passed")
        if decide({**pre, "tool_name": recipe, "tool_input": ok}):
            bad.append("a tool the policy does not name was refused")
        if not decide({**pre, "tool_name": create, "tool_input": {}, "agent_id": "a1",
                       "agent_type": "general-purpose"}):
            bad.append("a subagent's call to a blocked tool passed")
        if decide({**pre, "tool_name": drive}):
            bad.append("a call to another server was refused")
        if decide({**pre, "tool_name": "Bash"}):
            bad.append("a built-in tool was refused")
        policy(blocked_tools=["*"])
        if decide({**pre, "tool_name": cfg, "tool_input": {}}):
            bad.append("get_countz_config was refused")
        if not decide({**pre, "tool_name": recipe, "tool_input": ok}):
            bad.append("`*` let a call through")
        if split_wire(cfg) != ("plugin_countz-accounting_countz", "get_countz_config"):
            bad.append("split_wire mis-split a plugin tool name")
        if not listed("claude_ai_countz", "get_recipe_for_countz_analysis",
                      ["countz/get_recipe_for_countz_analysis"]):
            bad.append("a `<server>/<tool>` entry did not match its tool")
    for b in bad:
        print(f"countz_guard selftest: {b}", file=sys.stderr)
    print(f"countz_guard selftest: {len(bad)} defect(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if sys.argv[1:] == ["--selftest"] else main())
