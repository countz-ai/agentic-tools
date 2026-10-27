---
name: explain
description: >-
  Explain a result of a finished run: re-perform the statements behind it from the
  data-room tables, query the run's tables for the evidence the statements do not hold,
  and walk from the source data through each step of logic to the result. Invoke when
  the user asks to explain, trace or question a figure, finding or open item of a run,
  for example "explain the 1,406 customers first billed in August 2025".
argument-hint: "[run directory] what to explain"
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz-accounting $(ls -td "$HOME"/.claude/plugins/cache/*/countz-accounting/*/ 2>/dev/null); do grep -qs '^def emptying' "$d/scripts/sql.py" && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz-accounting/scripts/sql.py" -exec grep -l '^def emptying' {} + 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/sql.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz-accounting/scripts/sql.py" -exec grep -l '^def emptying' {} + 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/sql.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" DOCTRINE.md "Voice" "Number conventions"; fi
```

`$R` below is the `CLAUDE_PLUGIN_ROOT` the block printed. You explain one result from the
run's own tables, in this conversation.

## Inputs

- **What to explain**: the arguments, or the message that invoked you.
- **The run directory**: a path in the arguments; else the run this session ran or last
  named; else ask the user for it. It holds `run.json` and `catalog.sql`.

## Querying

Run SQL with `$R/scripts/countz-sql -agent -init <run_dir>/catalog.sql -c "<sql>"`. Each
call starts an empty in-memory database: a `CREATE TEMP VIEW` lasts for that call, so put
the queries that use it in the same `-c`. The catalog describes the run:

- `countz.tables`: every table, with a parsed table's file, sheet and rows, and a derived
  table's statement in `definition`;
- `countz.columns`: each column's type, description and unit;
- `countz.figures`: every figure, with its `statement`; `fig('F.x')` reads one;
- `countz.reads`: what each statement reads (`reader`, `read`);
- `countz.ties`, and `room.constants` with each constant's `kind` (`stated`, `declared`,
  `chosen`) and its `quote` or `basis`.

Compute in SQL. Use Python only for what SQL cannot do. Write nothing into the run:
create no table in a run schema, and call no `run_sql` or `Ledger`.

## 1. Find the result

Search `countz.figures` for the figures the description names, by label, id, and value
within 0.5% of each number the description states (example: `abs(value - 20820000) <=
0.005 * 20820000`). A description quoted from the run's output: grep `out/RUN_SUMMARY.md` and
`checks/*.md` for its numbers to find the check and the ids. Where a table or a tie holds
the result and no figure does, explain that table or tie.

## 2. Re-perform it

Run `uv run --quiet --project $R python3 $R/scripts/sql.py emptying <run_dir> <figure id>`.
It rebuilds each derived table in the figure's lineage from its statement and recomputes
the figure (first line: re-performed and recorded value). Then it empties each input in
turn, nearest first:

- `affects`: the value changes without it;
- `no effect`: the value does not change in this run (example: a filter every row
  passes);
- `not tested`: read only through a node with no effect.

If it refuses because the re-performed value differs from the ledger, report both values
and stop. For a figure with no statement (a tie's difference), re-perform each side.

Read the statements of the nodes that affect the value: `definition` in `countz.tables`,
`statement` in `countz.figures`, and each constant's row in `room.constants`. Where a
statement builds several results (UNION branches, CTEs), follow the branch that yields
the figure's row. A `chosen` constant is the run's judgment; step 3 tests it.

## 3. Fill the gaps

The lineage shows how the run computed the value. Query for what the reader also needs
to understand it. Examples of gaps:

- the evidence for each `chosen` constant (example: a month chosen as unusual, and the
  monthly series that shows whether it is);
- each condition of a filter applied one at a time, and what each removes;
- the population next to a comparison group;
- each plausible explanation, and whether the data supports or rules it out;
- the figures that read this one (`countz.reads` where `read` is its id), and how far
  they move;
- the run's open questions about it (`checks/<check>.md`).

## 4. Explain

Lead with the answer in one short paragraph: what the result is and what explains it,
or that no record in the run explains it.

Then the chain, from the data-room files to the result and on through the gaps, in
alternating steps:

- **Data**: what a table holds at that point, in the counts, sums and rows that matter,
  and where it comes from: the file and rows for a parsed table, the statement that made
  it otherwise.
- **Logic**: what the next statement or query does, in words (what it filters, joins,
  groups or computes, and on which columns), with its SQL below in a fenced block.

Follow each logic step with the data it yields. Show the nodes that affect the value,
and a node with no effect where its condition carries the explanation (example: earlier
revenue that shows no customer billed before). Name the other nodes in one line.

Mark every figure as the run's, with its id, or as computed for this explanation and
absent from the run's ledger. Close with what no record in the run answers, and who
holds it where the run names an owner.

Example of the cycle:

> **Data.** `Customer Revenue Stream FY2025.csv`, rows 6:121430, parsed as
> `room.revenue_stream_fy2025`: one row per customer, month and stream.
>
> **Logic.** The statement behind `g0_scoping.customers` takes each customer's earliest
> month with revenue.
>
> **Data.** 1,518 customers have August 2025 as their first month; in each month from
> October 2024 to July 2025, 17 or 18 do (computed for this explanation).

Write the explanation per § Voice and § Number conventions, which the block printed.
