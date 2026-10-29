---
name: check-deck
description: >-
  Review the sealed report deck as its reader: every title, message and sentence held to
  DOCTRINE.md § Voice and § Number conventions and REPORT.md's writing rules, and every
  claim held to the deck's other pages. Reads the deck only. Never edits it.
context: fork
agent: countz-accounting:reader
background: false
user-invocable: false
---

# Review the deck

Arguments: `run_dir`, `seq`, and optionally `since`: the deck an earlier round reviewed.
With `since`, judge only the slides `deck_text.py` marks `(changed)`; read the others for
the claims they share with a changed slide.

Open the step: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/step_record.py start <run_dir> <seq>`.

## What to read

1. The rules, by section:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py DOCTRINE.md Voice "Number conventions"
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py REPORT.md Tone
   sed -n '/^\*\*Headline and message\.\*\*/,/^\*\*Blocks\*\*/p' ${CLAUDE_PLUGIN_ROOT}/reference/REPORT.md
   ```

2. The deck, as its reader sees it:

   ```
   uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/deck_text.py <run_dir>/out/report.pptx [--since <run_dir>/<since>]
   ```

Read nothing else.

## What to judge

Read each page on its own, then the deck in order. On each page, hold the kicker, the
title, the message and every sentence, bullet, note and stat label to the rules. Then
hold each claim to every other page that states the same measure: a claim another page
contradicts, or a scope wider than the figures show (*on any basis*, *every month*), is a
finding.

A sentence that follows the rules but leaves the reader unable to say what happened, by
how much and why, breaks REPORT.md's **Prose** rule (*says one thing a reader outside
accounting follows on first reading*). Example: *"The adjustments the records support
lower headroom at December 31, 2026 to $238.2M"* gives the end figure without the start,
the change or the adjustments by name.

## Findings

```yaml
- id: R.001
  page: 5                          # the slide number
  page_title: "Headroom before plans"
  field: title                     # kicker | title | message | text | bullet | note | stat
  quote: "Headroom before plans"
  rule: "A sentence resting on one of the run's own nouns says what that noun is."
  problem: >-
    One or two sentences, in the deck's figures: what the reader cannot follow, or what
    the claim gets wrong and which page shows it.
```

A finding states the problem. How to fix it is the report step's to decide.

Most consequential first: a claim another page contradicts, then a sentence the reader
cannot follow, then a Voice or number-convention defect.

## Record

Write the fields to `<run_dir>/out/.staging/deck-findings.json` as
`{"conclusion": "...", "findings": [...]}` and close the step:
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/step_record.py finish <run_dir> <seq> --json <run_dir>/out/.staging/deck-findings.json`.
`conclusion` gives the count of findings and the worst in one clause.
