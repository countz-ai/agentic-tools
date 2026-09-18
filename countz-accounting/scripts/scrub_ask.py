#!/usr/bin/env python3
"""The gate on the one text that crosses to the Countz connector: the scrubbed
pre-run ask (`OBSERVABILITY.md` § 4; `AUTH_MCP_OAUTH.md` § 6.1 in the monorepo).

    scrub_ask.py <run_dir> --ask "<the scrubbed ask>"
    scrub_ask.py <run_dir> --ask-file <path>

The relay rewrites the user's ask into a form that names the analysis and nothing of
the company's; this script refuses what the rewrite left in. It reads `run.json` for
the registered sources and the company and applies a mechanical gate — no model:

- **digits** only inside a period token: `FY2024`, `FY24`, `Q3`, `Q3 2024`, `H1 2025`,
  `2024-12-31`, `2024-12`, a bare four-digit year, `March 2026`; any other digit is
  refused (an amount, an account number, an invoice id)
- no currency symbol (`$ € £ ¥ ₹`), no `@`, no path separator (`/`, `\\`)
- no token matching the company the user named, or a registered source's file name -
  whole, or any word of four letters or more
- at most 8,192 bytes UTF-8 - the server's cap; over it the server refuses the call
  whole, so the client refuses first

Exit 0 and print the exact bytes that will be sent after `SEND:\\t` - the relay shows
that line to the user before the call. Exit 1 with one `REFUSED:\\t<rule>\\t<token>`
line per hit; the relay rewrites and runs the gate again. Exit 2 on a usage error.
The full, unscrubbed ask never passes through here: it stays in
`run.json.inputs.params.instructions`.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

MAX_BYTES = 8 * 1024
CURRENCY = "$€£¥₹"
MIN_WORD = 4

MONTHS = ("january|february|march|april|may|june|july|august|september|october|"
          "november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
# Every shape a digit may sit in. Matched case-insensitively, longest first.
PERIOD = re.compile(
    r"(?<![\w-])(?:"
    r"fy\s?\d{2,4}"                         # FY2024, FY 24
    r"|[qh][1-4](?:\s?(?:fy)?\s?\d{2,4})?"  # Q3, Q3 2024, H1 FY25
    r"|\d{4}-\d{2}(?:-\d{2})?"              # 2024-12, 2024-12-31
    r"|(?:19|20)\d{2}"                      # a bare year
    r"|(?:" + MONTHS + r")\.?\s?(?:19|20)?\d{2,4}"   # March 2026, Mar 26
    r")(?![\w-])", re.I)


def load_run(run_dir: pathlib.Path) -> dict:
    p = run_dir / "run.json"
    if not p.is_file():
        raise SystemExit(f"scrub_ask: {run_dir} carries no run.json")
    return json.loads(p.read_text())


def protected_tokens(run: dict) -> set[str]:
    """Lower-cased strings the ask may not contain: the company, each source's file
    name (extension dropped), and every word of MIN_WORD+ letters in either."""
    out: set[str] = set()
    names = [str(run.get("inputs", {}).get("company") or "")]
    for s in run.get("sources", []):
        names.append(pathlib.Path(str(s.get("path", ""))).stem)
        names.append(str(s.get("name") or ""))
    for n in names:
        n = n.strip().lower()
        if not n:
            continue
        out.add(n)
        for w in re.findall(r"[a-z]+", n):
            if len(w) >= MIN_WORD:
                out.add(w)
    return out


def gate(ask: str, protected: set[str]) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    if len(ask.encode("utf-8")) > MAX_BYTES:
        hits.append(("size", f"{len(ask.encode('utf-8'))} bytes > {MAX_BYTES}"))
    stripped = PERIOD.sub(" ", ask)
    for m in re.finditer(r"\S*\d\S*", stripped):
        hits.append(("digit", m.group(0)))
    for ch in ask:
        if ch in CURRENCY:
            hits.append(("currency", ch))
    if "@" in ask:
        hits.append(("at_sign", "@"))
    for sep in ("/", "\\"):
        if sep in ask:
            hits.append(("path_separator", sep))
    low = ask.lower()
    words = set(re.findall(r"[a-z]+", low))
    for tok in sorted(protected):
        if " " in tok or not tok.isalpha():
            if tok in low:
                hits.append(("named", tok))
        elif tok in words:
            hits.append(("named", tok))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=pathlib.Path)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ask", help="the scrubbed ask, as one argument")
    g.add_argument("--ask-file", type=pathlib.Path, help="a file holding the scrubbed ask")
    a = ap.parse_args()
    ask = a.ask if a.ask is not None else a.ask_file.read_text()
    ask = ask.strip()
    if not ask:
        print("scrub_ask: the ask is empty", file=sys.stderr)
        return 2
    run = load_run(a.run_dir.resolve())
    hits = gate(ask, protected_tokens(run))
    seen = set()
    for rule, tok in hits:
        if (rule, tok) in seen:
            continue
        seen.add((rule, tok))
        print(f"REFUSED:\t{rule}\t{tok}")
    if hits:
        print("scrub_ask: rewrite the ask without the tokens above and run the gate "
              "again; nothing was sent", file=sys.stderr)
        return 1
    print(f"SEND:\t{ask}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
