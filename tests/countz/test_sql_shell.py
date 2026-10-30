#!/usr/bin/env python3
"""Self-test for scripts/sql_shell.py and scripts/countz-sql: the output of DuckDB's
agent-mode CLI, as DuckDB 2.0 prints it (hashes aside).

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz/test_sql_shell.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import io
import pathlib
import re
import subprocess
import sys
import tempfile

SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from sql_shell import Shell, error_json  # noqa: E402

HASH = re.compile(r"hash [0-9a-f]{16}")


def out(sh: Shell, sql: str) -> str:
    buf = io.StringIO()
    sh.script(sql, buf)
    return HASH.sub("hash H", buf.getvalue())


def main() -> int:
    bad: list[str] = []

    def want(label, got, expected):
        if got != expected:
            bad.append(f"{label}:\n--- got\n{got}--- want\n{expected}")

    sh = Shell()
    want("typed header, no footer under ten rows",
         out(sh, "SELECT range AS i FROM range(2)"), "| i:BIGINT |\n|---|\n| 0 |\n| 1 |\n")
    want("footer at ten rows", out(sh, "SELECT range FROM range(10)").splitlines()[-1],
         "10 rows, hash H")
    want("footer on no rows", out(sh, "SELECT 1 AS a WHERE false"),
         "| a:INTEGER |\n|---|\n0 rows, hash H\n")
    want("cells", out(sh, "SELECT 'p|q' AS s, NULL::INT AS n, true AS b, "
                          "TIMESTAMP '2025-01-01 10:00' AS ts, 12.50::DECIMAL(18,2) AS m, "
                          "[1, 2] AS l"),
         "| s:VARCHAR | n:INTEGER | b:BOOLEAN | ts:TIMESTAMP | m:DECIMAL(18,2) | l:INTEGER[] |\n"
         "|---|---|---|---|---|---|\n| p\\|q | NULL | true | 2025-01-01 10:00:00 | 12.50 | [1, 2] |\n")
    want("long cell", out(sh, "SELECT repeat('a', 501) AS s").splitlines()[-1],
         f"| {'a' * 500}…(+1 chars) |")
    narrow = out(sh, "SELECT range FROM range(2000)").splitlines()
    want("narrow rows cut on the row limit", (narrow[22], narrow[-1]),
         ("| … 1960 rows omitted … |", "first 20 and last 20 of 2000 rows (.maxrows -1 for all), hash H"))
    wide = out(sh, "SELECT range, repeat('x', 100) AS s FROM range(200)").splitlines()
    want("wide rows cut on the byte limit", wide[-1],
         "first 20 and last 20 of 200 rows (.maxbytes 0 for all), hash H")
    want("dot command lifts the limits",
         len(out(sh, ".maxrows -1\n.maxbytes 0\nSELECT range FROM range(2000)").splitlines()), 2003)
    want("a CREATE prints nothing; each SELECT prints",
         out(sh, "CREATE TABLE t AS SELECT 1 AS a; SELECT * FROM t; SELECT 42 AS b"),
         "| a:INTEGER |\n|---|\n| 1 |\n| b:INTEGER |\n|---|\n| 42 |\n")
    a = out(Shell(), "SELECT * FROM (VALUES (1), (2), (3), (4), (5), (6), (7), (8), (9), (10)) v(x)")
    b = out(Shell(), "SELECT * FROM (VALUES (10), (9), (8), (7), (6), (5), (4), (3), (2), (1)) v(x)")
    if HASH.search(a.replace("hash H", "")) or a.splitlines()[-1] != b.splitlines()[-1]:
        bad.append("the hash is not order-independent")
    try:
        sh.script("SELECT nosuch FROM t", io.StringIO())
        bad.append("an unknown column ran")
    except Exception as exc:
        want("error JSON", error_json(exc),
             '{"exception_type":"Binder","exception_message":"Referenced column \\"nosuch\\" '
             'not found in FROM clause!\\nCandidate bindings: \\"a\\""}')

    with tempfile.TemporaryDirectory() as td:
        init = pathlib.Path(td) / "init.sql"
        init.write_text("CREATE VIEW v AS SELECT 7 AS x;\n", encoding="utf-8")
        cli = str(SCRIPTS / "countz-sql")
        r = subprocess.run([cli, "-agent", "-init", str(init), "-c", "SELECT * FROM v"],
                           capture_output=True, text=True)
        want("countz-sql -init -c", (r.returncode, r.stdout), (0, "| x:INTEGER |\n|---|\n| 7 |\n"))
        r = subprocess.run([cli, "-c", ".maxcellwidth 3", "-c", "SELECT 'abcdef' AS s",
                            "-c", "SELECT 2 AS y"], capture_output=True, text=True)
        want("countz-sql runs each -c in order",
             (r.returncode, r.stdout), (0, "| s:VARCHAR |\n|---|\n| abc…(+3 chars) |\n"
                                           "| y:INTEGER |\n|---|\n| 2 |\n"))
        r = subprocess.run([cli], input="SELECT 3 AS z;", capture_output=True, text=True)
        want("countz-sql from stdin", r.stdout, "| z:INTEGER |\n|---|\n| 3 |\n")
        r = subprocess.run([cli, "-c", "SELECT 1; SELECT * FROM nosuch; SELECT 2"],
                           capture_output=True, text=True)
        want("countz-sql stops at an error", (r.returncode, r.stdout, r.stderr.startswith(
            '{"exception_type":"Catalog"')), (1, "| 1:INTEGER |\n|---|\n| 1 |\n", True))

    for b_ in bad:
        print(f"FAIL: {b_}")
    print("sql_shell.py self-check: " + ("ok" if not bad else f"{len(bad)} failure(s)"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
