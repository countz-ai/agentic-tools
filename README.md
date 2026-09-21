# Countz Agentic Tools

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Agentic skills and tools for accounting analysis, backed by the Countz Accounting platform.

## What is this?

This repo packages the Countz accounting tools and skills that run accounting analysis:
tie out ledgers, sub-ledgers and schedules; reconcile cash to bank; prove out cash ahead
of an audit; build a quality-of-earnings EBITDA bridge; test ASC 606 revenue recognition
and ASC 842 lease accounting; trace revenue leakage from invoice to cash and many more. 
Each run reads your files, drafts a plan you confirm, executes the plan steps in
parallel, and hands you a workbook and a report deck with every figure traceable to its
source file.

The skills use Countz mcp to fetch the up-to-date playbooks, which are then executed
in your AI environment using your own AI tokens. No financial data goes to Countz server.

## Installation

### Claude Cowork

From Claude Desktop Settings / Plugins, add a marketplace using this repository's URL:

```
https://github.com/countz-ai/agentic-tools
```

Adding the marketplace only makes its plugins searchable. Search for `countz` in the
plugin browser and add the **Countz Accounting** plugin.

### Claude Code

Add this repository as a plugin marketplace, then install the plugin from it:

```
/plugin marketplace add countz-ai/agentic-tools
/plugin install countz-accounting@countz
```

### ChatGPT

In the ChatGPT desktop app, open the **Plugins** tab and choose **Add a marketplace**:

- Marketplace: `countz-ai/agentic-tools`

Then search for `countz` in the plugin directory and add **countz-accounting**.

From the Codex CLI the same two steps are:

```
codex plugin marketplace add countz-ai/agentic-tools
codex plugin install countz-accounting@countz
```

On first use the plugin asks you to sign in to the Countz connector.

### First use

Ask for `countz` inside a session to list the analyses and see how to start one.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
