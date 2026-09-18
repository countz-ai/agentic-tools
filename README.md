# Countz Agentic Tools

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Agentic skills and tools for accounting analysis, backed by the Countz Accounting platform.

## What is this?

This repo packages the Countz accounting tools and skills that run accounting analysis:
tie out ledgers, sub-ledgers and schedules; reconcile cash to bank; prove out cash ahead
of an audit; build a quality-of-earnings EBITDA bridge; test ASC 606 revenue recognition
and ASC 842 lease accounting; trace revenue leakage from invoice to cash etc. Each run reads
your files, drafts a check plan you confirm before anything runs, executes the checks in
parallel, and hands you a workbook and a report deck with every figure traceable to its
source file.

The skills follow the open Agent Skills model: each skill has a `SKILL.md` plus supporting
files loaded on demand. The plugin is self-contained — its agents, reference documents and
helper scripts ship in the package — and connects to the Countz platform through the
`countz` MCP connector (sign in with Google) for the analysis catalog and recipes.

Ask for `countz` inside a session to list the analyses and how to start one.

## Installation

### Claude Cowork

Cowork installs a plugin from a zip. Build it from this repository:

```bash
make zip
```

This validates the plugin with the Claude Code CLI (`claude plugin validate`), runs the
structural checks, and writes `dist/countz-accounting-<version>.zip`.

Then in Cowork: **Customize → Plugins → upload**, and select the zip.

On first use, connect the Countz connector when prompted; every analysis signs in before
it reads a file.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
