#!/usr/bin/env python3
"""The DuckDB CLI's agent mode (`duckdb -agent`, DuckDB 2.0) on the Python package, until the
2.0 CLI ships on PyPI. `countz-sql` runs it. The options and the output follow the CLI, so
switching to `duckdb -agent` changes nothing for the caller:

    countz-sql [-agent] [-init FILE] [-readonly] [-c SQL] [FILENAME]

FILENAME is a database file (default in memory). `-init` runs a file of statements first,
printing nothing. The SQL comes from `-c`, else from stdin. A line that starts with `.` is a
dot command: `.maxrows N`, `.maxbytes N`, `.maxcellwidth N` (-1 or 0 for all) and `.tables`.

Output, per statement that returns rows: a markdown table whose header names each column
with its type; a result of up to 1000 rows and 10000 bytes whole, a larger one as its first
and last 20 rows; cells cut at 500 characters; a footer with the row count and an
order-independent hash of the result when it has none or ten or more rows, or was cut.
The hash is this module's own, not the CLI's. An error is one JSON line on stderr, exit 1;
the statements after it do not run.

Run with `uv run --project ${CLAUDE_PLUGIN_ROOT} python3`.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import re
import sys

SILENT = {"CREATE", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "SET", "VARIABLE_SET",
          "ATTACH", "DETACH", "TRANSACTION", "LOAD", "COPY", "PREPARE", "EXECUTE"}
EDGE = 20                        # rows shown at each end of a cut result
ERROR = re.compile(r"(?P<type>[A-Za-z ]+?) Error: (?P<msg>.*?)(?:\n\nLINE \d+:.*)?\Z", re.S)


class Shell:
    def __init__(self, database: str = ":memory:", read_only: bool = False):
        import duckdb
        self.duckdb = duckdb
        self.con = duckdb.connect(database, read_only=read_only)
        self.maxrows, self.maxbytes, self.maxcell = 1000, 10000, 500

    # -- running ---------------------------------------------------------------------------
    def script(self, text: str, out=sys.stdout, quiet: bool = False) -> None:
        """Run a script: SQL statements and dot-command lines, in order."""
        sql: list[str] = []
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith(".") and not "".join(sql).strip():
                self.dot(line.strip(), out)
                sql = []
            else:
                sql.append(line)
        if "".join(sql).strip():
            self.statements("".join(sql), out, quiet)

    def statements(self, text: str, out, quiet: bool) -> None:
        for st in self.con.extract_statements(text):
            cur = self.con.execute(st)
            if quiet or st.type.name in SILENT or cur.description is None:
                continue
            out.write(self.render(cur.description, cur.fetchall()))

    def dot(self, line: str, out) -> None:
        word, *arg = line.split()
        if word in (".maxrows", ".maxbytes", ".maxcellwidth") and len(arg) == 1:
            n = int(arg[0])
            n = None if n in (-1, 0) else n
            setattr(self, {".maxrows": "maxrows", ".maxbytes": "maxbytes",
                           ".maxcellwidth": "maxcell"}[word], n)
        elif word == ".tables" and not arg:
            cur = self.con.execute("SELECT CASE WHEN schema_name = 'main' THEN table_name ELSE "
                                   "schema_name || '.' || table_name END AS name FROM "
                                   "duckdb_tables() UNION ALL SELECT CASE WHEN schema_name = "
                                   "'main' THEN view_name ELSE schema_name || '.' || view_name "
                                   "END FROM duckdb_views() WHERE NOT internal ORDER BY 1")
            out.write(self.render(cur.description, cur.fetchall()))
        else:
            raise ValueError(f"unknown dot command {line!r}; this shell takes .maxrows N, "
                             f".maxbytes N, .maxcellwidth N and .tables")

    # -- rendering -------------------------------------------------------------------------
    def cell(self, v) -> str:
        if v is None:
            s = "NULL"
        elif isinstance(v, bool):
            s = "true" if v else "false"
        elif isinstance(v, datetime.datetime):
            s = v.isoformat(sep=" ")
        else:
            s = str(v)
        s = s.replace("|", "\\|")
        if self.maxcell and len(s) > self.maxcell:
            s = f"{s[:self.maxcell]}…(+{len(s) - self.maxcell} chars)"
        return s

    def render(self, description, rows: list[tuple]) -> str:
        head = "| " + " | ".join(f"{d[0]}:{d[1]}" for d in description) + " |\n"
        head += "|" + "---|" * len(description) + "\n"
        lines = ["| " + " | ".join(self.cell(v) for v in r) + " |\n" for r in rows]
        n = len(rows)
        h = 0
        for line in lines:                       # order-independent: a sum of row hashes
            h = (h + int.from_bytes(hashlib.blake2b(line.encode(), digest_size=8).digest(),
                                    "big")) % 2 ** 64
        digest = f"{h:016x}"
        how, size = None, 0
        for i, line in enumerate(lines):         # the limit the rows cross first, read in order
            size += len(line)
            if self.maxrows is not None and i + 1 > self.maxrows:
                how = ".maxrows -1"
            elif self.maxbytes is not None and size > self.maxbytes:
                how = ".maxbytes 0"
            if how:
                break
        if how and n > 2 * EDGE:
            gap = f"| … {n - 2 * EDGE} rows omitted … |\n"
            return (head + "".join(lines[:EDGE]) + gap + "".join(lines[-EDGE:])
                    + f"first {EDGE} and last {EDGE} of {n} rows ({how} for all), "
                      f"hash {digest}\n")
        foot = f"{n} rows, hash {digest}\n" if n == 0 or n >= 10 else ""
        return head + "".join(lines) + foot


def error_json(exc: Exception) -> str:
    text = str(exc).strip()
    m = ERROR.match(text)
    kind, msg = (m.group("type"), m.group("msg").strip()) if m else (type(exc).__name__, text)
    return json.dumps({"exception_type": kind, "exception_message": msg}, ensure_ascii=False,
                      separators=(",", ":"))


def main(argv: list[str]) -> int:
    init = sql = None
    database, read_only = ":memory:", False
    it = iter(argv)
    for a in it:
        if a in ("-agent", "-no-agent", "-batch"):
            continue                                 # agent output is the only mode
        if a == "-init":
            init = next(it, None)
        elif a == "-c":
            sql = next(it, None)
        elif a == "-readonly":
            read_only = True
        elif a.startswith("-"):
            print(json.dumps({"exception_type": "Usage",
                              "exception_message": f"unknown option {a}; countz-sql takes "
                                                   f"-agent, -init FILE, -readonly, -c SQL "
                                                   f"and a database FILENAME"},
                             separators=(",", ":")), file=sys.stderr)
            return 1
        else:
            database = a
    try:
        sh = Shell(database, read_only)
        if init:
            sh.script(pathlib.Path(init).read_text(encoding="utf-8"), quiet=True)
        sh.script(sql if sql is not None else sys.stdin.read())
    except Exception as exc:
        sys.stdout.flush()
        print(error_json(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
