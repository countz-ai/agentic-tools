---
name: reperform
description: >-
  Re-perform a result of a finished run step by step: from the data-room file, through
  each statement and query, to the result, with the data, the logic and the SQL to copy
  at each step. Invoke when the user says "reperform", or asks to walk through, trace or
  reproduce a figure, finding or open item of a run, and when the user says "run query"
  after a re-performance.
argument-hint: "[run directory] what to re-perform"
context: inline
---

```
R=; for d in "${CLAUDE_PLUGIN_ROOT}" "${CLAUDE_SKILL_DIR}/../.." "$HOME"/.claude/plugins/synced/*/countz $(ls -td "$HOME"/.claude/plugins/cache/*/countz/*/ 2>/dev/null); do grep -qs '^def emptying' "$d/scripts/sql.py" && R=$(cd "$d" && pwd) && break; done; [ -n "$R" ] || { f=$(find "$HOME/.claude/plugins" -maxdepth 7 -path "*/countz/scripts/sql.py" -exec grep -l '^def emptying' {} + 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/sql.py}; }; [ -n "$R" ] || { f=$(find / \( -path /proc -o -path /sys -o -path /dev \) -prune -o -path "*/countz/scripts/sql.py" -exec grep -l '^def emptying' {} + 2>/dev/null | head -1); [ -n "$f" ] && R=${f%/scripts/sql.py}; }; if [ -z "$R" ]; then echo "NOT INSTALLED: this plugin's files are not in the session. Tell the user so in one line, and stop."; else echo "CLAUDE_PLUGIN_ROOT=$R"; python3 "$R/scripts/section.py" DOCTRINE.md "Voice" "Number conventions" && python3 "$R/scripts/section.py" skills/drilldown/SKILL.md Inputs Querying "Find the result" "Re-perform it" "Fill the gaps"; fi
```

`$R` below is the `CLAUDE_PLUGIN_ROOT` the block printed. The block also printed the
drilldown skill's Inputs, Querying and steps 1 to 3. You re-perform one result from the run's
own tables, in this conversation.

## 1. Research

If this conversation drilled into the result, start from that work: its lineage, the
statements it read and its query outputs. Run a query only for an output the
conversation does not hold. Otherwise do drilldown's steps 1 to 3: find the result,
re-perform it, and fill the gaps.

## 2. Walk it through

Tell it as one chain, from the data-room file to the result and on through the gaps.
Alternate two kinds of step, starting and ending with data:

- **Data**: what a table holds at that point, and where it comes from: the file and rows
  for a parsed table, the statement that made it otherwise. Show the counts, sums and
  rows that matter as a table.
- **Logic**: in words, what the next statement or query does: what it filters, joins,
  groups or computes, and on which columns, and what that means for the result. Under it,
  the SQL exactly as it ran, in a fenced block the user can copy. Give a statement that
  builds a table as its `SELECT`, followed by the query for the counts or sums the next
  data step shows. A statement that reads an earlier step's table reads the run's copy.
  Write each query against the run's tables, with no temp view: one the user can paste
  back as it stands.

The data step after each logic step is that SQL's output: show at most ten rows of a
longer result, and state its row count.

Show the nodes the value rests on, and a node that leaves it unchanged where its
condition carries the explanation (example: earlier revenue that shows no customer billed
before). Name the other nodes in one line. Where a statement builds several results (UNION
branches, CTEs), show the branch that yields the result's row.

Example of one cycle:

> **Data.** `Customer Revenue Stream FY2025.csv`, rows 6:121430, parsed as
> `room.revenue_stream_fy2025`: one row per customer, month and stream.
>
> **Logic.** The statement behind `g0_scoping.customers` takes each customer's earliest
> month with revenue, over the FY2023 to FY2025 files. This query counts the customers by
> that month:
>
> ```sql
> SELECT first_revenue_month, count(*) AS customers FROM g0_scoping.customers
> WHERE first_revenue_month BETWEEN '2025-07' AND '2025-09' GROUP BY 1 ORDER BY 1
> ```
>
> **Data.** 1,518 customers have August 2025 as their first month; 18 have July 2025
> and 28 September 2025 (computed for this re-performance).

Mark every figure as the run's, with its id, or as computed for this re-performance and
absent from the run's ledger. Close with what the run's records do not show, and who
holds the answer where the run names an owner. End with this line:

> To run any of these queries, or a changed one, say: run query <sql>.

Write the walkthrough per § Voice and § Number conventions, which the block printed.

## 3. Run the user's queries

The user runs SQL through you in this conversation, never in a shell; give no shell
command. When the user says *run query* followed by SQL, run that SQL with `countz-sql`
as drilldown's § Querying says, and show the output as a table: at most ten rows, with
the row count.
