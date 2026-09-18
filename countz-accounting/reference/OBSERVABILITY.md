# OBSERVABILITY — what a run records about itself

A run keeps three records:

- `events.jsonl` (§ 1): what the machinery did. Append-only, written as the run goes.
- `scripts/usage_report.py` (§ 2): what the run took in time, tokens and dollars. Read
  from the session transcripts after the fact.
- `<run_dir>/debug/` (§ 3): what each dispatch was told, did and got back. Written by
  `scripts/gather_debug.py` every wave while debug mode is on.

`run.json` is state, rewritten in place. It is not a history.

## 1. `<run_dir>/events.jsonl`

One JSON object per line. Append only: never rewrite, reorder or compact. Any writer may
append. Readers skip a line that fails to parse.

Every line carries `ts` (ISO 8601 UTC, ms) and `event` from the table below. Add a row
before writing a new event.

| `event` | written by | carries |
|---|---|---|
| `run_created` | `scripts/setup_run.py` | `run_id`, `output_root` |
| `sources_added` | `scripts/setup_run.py` | `ids[]`: sources folded into an existing run |
| `params_set` | `scripts/setup_run.py` | `keys[]`: run parameters set or changed on an existing run |
| `session_joined` | `scripts/setup_run.py` | `session_id`: another session picked this run up |
| `decision` | the playbook engine (`scripts/playbook_next.py`, or the agent on escalation) | `wave`, `steps[]`, `why`: one line per wave decision on a playbook run |
| `plan_approved` | `scripts/run_state.py` (approve-plan) | `seq`, `playbook`: the user accepted the drafted plan; the definition it names is what runs |
| `step_start` | the step | `seq`, `step`, `check?`, `source?`, `mode?`, `session_id?` |
| `step_end` | the step | `seq`, `step`, `outcome`, `duration_s`, `produced[]`, `blockers_n`, `error?` |
| `retry` | `scripts/run_state.py` (record) | `seq`, `attempt_of`, `step`: the one re-dispatch minted for a failed or dead step |
| `playbook_saved` | the save step | `name`, `path`, `steps_n` |
| `debug_enabled` | `scripts/setup_run.py` (`--debug`), `scripts/run_state.py` (`debug`) | `by`: debug mode is on for this run (§ 3) |
| `debug_disabled` | `scripts/run_state.py` (`debug --off`) | `by` |
| `debug_gathered` | `scripts/gather_debug.py` | `sessions`, `missing`, `tool_calls`, `errors`, `timeline`, `offloads`: counts only; the content lands under `debug/` |
| `note` | anyone | `text`: something a reader would want that no other event carries |

**`step_start` and `step_end`.** Write `step_start` before any work and `step_end` as the
last act before returning. An unmatched `step_start` is a step that died; the relay's
classifier reads it as one.

**`ts`.** `ts` is the time the line is appended, never a time captured earlier or
reconstructed later. `duration_s` is the difference between the step's two `ts` values;
compute it from them. Where file order and `ts` disagree, file order governs.

### What never goes in it

- Client data: a figure, a customer name, a workbook row, a filename beyond what the step
  records in its own artifact.
- Prompts and model output. They are in the transcripts.
- Unbounded fields. `why` and `text` are one sentence.

## 2. Duration and cost — `scripts/usage_report.py`

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/usage_report.py <run_dir> [--json]
```

Reads the session ids from `run.json`, then the transcripts under `~/.claude/projects/`,
one per subagent included. Writes nothing into the run directory.

Tokens are counted once per API response, keyed by `message.id`; the transcript writes one
record per content block. Dollars are derived from [`rates.json`](rates.json) and printed
with that file's capture date. A model absent from the table has its tokens reported and
its cost withheld.

Three time measures:

- **elapsed**: first activity to last.
- **active**: the union of dispatch intervals. At most elapsed.
- **dispatch time**: the sum of dispatch intervals. Exceeds active where dispatches
  overlapped.

To verify a cost, compare against the provider's usage console. It shares no inputs with
this report.

## 3. Debug mode — the run's own execution trace

Off by default. The user turns it on:

```
setup_run.py <run_dir> ... --debug          # at registration
run_state.py debug <run_dir> [--off]        # any time after
```

`run.json.inputs.debug` carries the mode; `debug_enabled` records it. While on:

- `scripts/preview.py` names every artifact, the working-papers bundle and the review
  findings included. Off, it names only the engagement preview, the plan, the workbook
  and the report deck ([RUN_CONTRACT.md](RUN_CONTRACT.md) § Every wave). The synced run
  directory carries everything in either mode.
- `run_state.py record` ends every wave with a `GATHER:` line. The relay runs it before
  `sync_run.py`:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/gather_debug.py <run_dir> [--cli-debug-log <path>]
```

Gather every wave, not at the close of the run. Transcripts live under
`~/.claude/projects/` on the machine that ran the session; a cloud container discards them
when it exits, and the CLI prunes old ones.

### What lands in `<run_dir>/debug/`

| file | holds |
|---|---|
| `timeline.jsonl` | the ordered stream, per dispatch: `prompt`, the `context` injected around it, `thinking`, `text`, `tool_use` with its full input, `tool_result` with its full output, `api_error`. Every model row carries model, effort, request id and CLI version. This is the reading surface. |
| `tool_calls.jsonl` | one line per call, excerpt-truncated: the index over the same calls. A `result` of null is a call that never returned. |
| `errors.jsonl` | every error-flagged tool result and every API-error record |
| `client_reads.jsonl` | every call that named a registered source path: the tool, the bound the call states (`limit` / `pages` on a Read, a `peek.py` line), the result's size (the offloaded body's where one was offloaded) and `whole` where that size crosses the whole-read mark. The gather's `GATHERED:` line counts them and prints a `WHOLE_READ:` line per hit. Measures `reference/CONDUCT.md` § Reading client files. |
| `transcripts/` | the copied transcripts, and under `<sid>/tool-results/` the result bodies Claude Code offloaded out of them |
| `instructions/` | every agent charter, `SKILL.md`, reference doc, playbook and script of the plugin that ran, one sha256 each, with the plugin version and the git sha in `instructions/manifest.json` |
| `traces/` | the `PreToolUse`/`PostToolUse` hook trace, where the machine writes one: local tool durations the transcript does not carry |
| `file_history/` | the pre-edit backup of every run file an agent overwrote, indexed by run-relative path |
| `cli/` | the CLI's own `--debug-file` log, when one is handed to `--cli-debug-log` |
| `manifest.json` | what was gathered, which sessions had no transcript, and what cannot be captured at all |

A run of a dozen dispatches produces a `debug/` of about 30 MB, nearly all transcripts
and offloaded results. Re-running refreshes the copies and rewrites the views. On a synced
run whose live transcripts are gone it re-extracts from the copies under `debug/`;
`usage_report.py` reads those same copies when `~/.claude/projects/` has nothing.

### Two rules the extracts follow

**A file the run already holds is referenced, not copied.** A read whose path resolves
under `run_dir` (the dispatch brief above all) is recorded as `{"elided": "in-run",
"path": ...}`. The copied transcript stays verbatim.

**A result over the inline limit is copied whole.** Claude Code writes it to
`<session>/tool-results/<id>.txt` and leaves a 2KB preview in the transcript; the gather
copies the file and the timeline row points at it.

### What cannot be captured

- **The system prompt.** Claude Code writes it to no file, and `claude --debug-file` logs
  the request line without its body (CLI 2.1.251). `instructions/` is the substitute: the
  charter and `SKILL.md` a dispatch ran under, by sha, plus the plugin version and git sha.
- **Reasoning the API returned without text.** A thinking block often carries a signature
  and an empty string. A `thinking` row is written only where there is text.
- **Raw API request and response bodies, retries, rate-limit events.** Start the session
  as `claude --debug-file <path>` to record API timing and errors; pass that path to
  `--cli-debug-log` and the log travels with the run.

## 4. Where a run's content may go

The plugin runs on the user's machine under the user's Claude account. Every run record
(the run directory, the session transcripts, a gathered `debug/`) stays there and reaches
the user through `sync_run.py` and the paths it prints.

Nothing from a run is sent to the Countz connector, with one bounded exception. The
connector (`countz` in `.mcp.json`) serves recipes; it never receives a run artifact —
not `debug/`, transcripts, workpapers, checks, the workbook, the source files, a path, a
figure or a file name. A skill, agent or script that would upload any of them is
refused; what goes to the user is the local path that holds it.

The exception is the **scrubbed pre-run description**: when `countz-analysis` finds no
catalog entry for what the user asked, it sends the ask — rewritten by the local model
and passed through `scripts/scrub_ask.py`'s gate (no digits outside a period vocabulary,
no currency symbols, no `@`, no path separators, no token matching a registered source
name or the company) — as the `ask` argument of `get_recipe_for_countz_analysis`, and
prints the exact bytes first. Countz retains it (the connector's design, in the
monorepo's `docs/arch/`, states the basis): the
unmatched asks are how Countz decides which recipes to write next. The full, unscrubbed
ask stays local in `run.json.inputs.params.instructions`. A named shim and a matched
generic run send nothing. The user is told this once, at collection, before the ask is
sent.

The § 1 exclusions hold for `events.jsonl` whether or not it was gathered.
