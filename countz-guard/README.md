# Countz Guard

Countz Guard controls the data a Claude session sends to the Countz connector (the
`countz` MCP server). It is a hooks-only plugin: no skills, no agents, no MCP server of
its own. It works alongside **countz-accounting**, which calls the connector.

## What it does

Each call to a `countz` tool passes through `hooks/countz_guard.py` before it is sent.
The hook enforces [`policy.json`](policy.json) and nothing else. It refuses the call,
and gives Claude the reason, when:

- `policy.json` names the tool in `blocked_tools`;
- the arguments fall outside what the tool takes: `get_countz_config` takes none, every
  other tool takes a JSON object, and `get_recipe_for_countz_analysis` takes `recipe`
  alone, set to a name no longer than `recipe_name_max` characters.

Every other call goes through unchanged. The hook matches `countz` calls only; calls to
any other MCP server and Claude's built-in tools never reach it.

The refusal holds in the main conversation, in every subagent and in every forked skill.
A refused call is final: Claude tells the user the tool is not allowed in this session
and continues without it.

## The shipped policy

```json
{
  "blocked_tools": ["countz/create_countz_playbook_recipe"],
  "recipe_name_max": 32
}
```

- **`create_countz_playbook_recipe` is blocked.** That tool sends the connector a
  scrubbed description of the user's ask when no catalog recipe matches it. With the
  tool blocked, no text describing the ask leaves the session; on a catalog miss
  Claude tells the user the catalog has no recipe for it.
- **`get_recipe_for_countz_analysis` takes a recipe name of at most 32 characters.**
  The longest catalog name, `stock-based-compensation`, has 24. The cap keeps the
  argument a catalog name; it cannot carry a sentence of the user's ask.

To change the policy, edit `policy.json`:

| Key | Value |
|---|---|
| `blocked_tools` | Entries of the form `countz/<tool>`, `countz/*` (every `countz` tool), or `*`. `get_countz_config` always passes. |
| `recipe_name_max` | The longest recipe name `get_recipe_for_countz_analysis` may carry. Leave the key out to set no cap. |

## Failure behavior

The hook never fails a tool call by crashing. An unreadable `policy.json` lets the call through,
with a note on stderr. The script uses
the Python standard library alone.

## Installation

### Claude Code

```
/plugin marketplace add countz-ai/agentic-tools
/plugin install countz-guard@countz
```

### Claude Cowork

Add the marketplace from Claude Desktop Settings / Plugins (see the
[repository README](../README.md)), search for `countz`, and add **Countz Guard**.

## Checking the hook

```
python3 hooks/countz_guard.py --selftest
```

`make check` runs the selftest on every package.

## License

Apache 2.0 — see [LICENSE](../LICENSE) for details.
