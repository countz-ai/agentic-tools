#!/usr/bin/env python3
"""The recipe shape contract (reference/RECIPE_FORMAT.md § The document), as code.

One module, two callers: `check-plugin.py` check 8m runs it over the corpus in git, and
`validate_recipe.py` runs it over a recipe `create-recipe` generated at run time. A
second implementation would drift, so neither caller restates a rule.

`validate(text, kinds)` returns one `(rule, message)` per defect — `rule` is the
mechanical name a caller can test against, `message` the sentence a reader acts on —
and an empty list for a recipe that conforms. Stdlib only.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from style import CURRENCIES, SCALES  # noqa: E402

REQUIRED = ["Population", "Source classes", "Granularity", "The families",
            "Exec summary", "Report", "What the plan notes rather than checks"]
INHERITED = {"Reperformance", "Exceptions", "The bar", "Rulings", "Coverage",
             "The source-class ladder", "The verdict ladder", "The headline walk"}
FRONTMATTER_KEYS = {"name", "objective", "declares", "headline", "lead"}
FAMILY = re.compile(r"^### ([A-Z])(\d) — .+ \(kind `([a-z]+)`, (.+)\)\s*$")
# `(kind `x`, one check, after A0)`: an order in the header. The plan derives `after`
# from the reads a family declares; a recipe never schedules.
AFTER = re.compile(r"(?:^|,)\s*after\b", re.I)
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# `## Report` (RECIPE_FORMAT.md § Report): the deck's opening and the schedules it
# carries before its narrative, as one fenced ```json block —
# `{"metrics": {"title": ...}, "schedules": [...]}`. Stdlib-parseable, so the deck gate
# (check_report.py, plain python3) reads the same block this module validates.
REPORT = "Report"
REPORT_KEYS = {"metrics", "schedules"}
METRICS_KEYS = {"title"}
SCHEDULE_KEYS = {"title", "from", "columns", "block", "where", "through", "periods", "scale",
                 "currency", "dense", "ids"}
SCHEDULE_REQUIRED = ("title", "from", "columns")
PERIODS = {"all", "latest", "none"}
FENCE = re.compile(r"^```json\s*\n(.*?)^```\s*$", re.S | re.M)


def frontmatter(text: str) -> dict[str, str]:
    """The YAML frontmatter as flat `key -> value` strings: a block scalar or a nested
    mapping is folded onto its key, which is all the shape rules need."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    key = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            out[key] = m.group(2).strip()
        elif key and line.startswith((" ", "\t")):
            out[key] += " " + line.strip()
    return out


def kinds_from(check_playbook: pathlib.Path) -> set[str]:
    """The check kinds `KINDS` in scripts/check_playbook.py declares; empty when the
    file is absent, in which case the kind rule is not applied."""
    if not check_playbook.is_file():
        return set()
    m = re.search(r"^KINDS\s*=\s*\{(.*?)^\}", check_playbook.read_text(encoding="utf-8"), re.S | re.M)
    return set(re.findall(r'"([a-z]+)":', m.group(1))) if m else set()


def section_body(text: str, heading: str) -> str | None:
    """The text under `## <heading>` up to the next `## `, or None when absent."""
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def report_block(text: str) -> dict | None:
    """The parsed `## Report` json block; None when the recipe has no such section, or
    the section carries no single parseable block (`validate` names why)."""
    body = section_body(text, REPORT)
    if body is None:
        return None
    blocks = FENCE.findall(body)
    if len(blocks) != 1:
        return None
    try:
        data = json.loads(blocks[0])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def report_schedules(text: str) -> list[dict] | None:
    """The schedules `## Report` declares, in order; None when the block is absent."""
    data = report_block(text)
    sched = data.get("schedules") if data else None
    return sched if isinstance(sched, list) else None


def report_metrics(text: str) -> dict | None:
    """The `metrics` mapping `## Report` declares — the headline of the deck's
    key-metrics page (`title`); None when the block is absent."""
    data = report_block(text)
    m = data.get("metrics") if data else None
    return m if isinstance(m, dict) else None


def _report_defects(text: str, fams: dict[str, str]) -> list[tuple[str, str]]:
    body = section_body(text, REPORT)
    if body is None:
        return []
    bad: list[tuple[str, str]] = []
    blocks = FENCE.findall(body)
    if len(blocks) != 1:
        return [("report.block", f"`## {REPORT}` carries {len(blocks)} fenced ```json blocks; "
                                 f"exactly one, `{{\"schedules\": [...]}}`")]
    try:
        data = json.loads(blocks[0])
    except ValueError as exc:
        return [("report.block", f"`## {REPORT}` json block does not parse: {exc}")]
    if not isinstance(data, dict):
        return [("report.block", f"`## {REPORT}` json block is a mapping")]
    for k in sorted(set(data) - REPORT_KEYS):
        bad.append(("report.block", f"`## {REPORT}` json block: unknown key `{k}` "
                                    f"(keys: {', '.join(sorted(REPORT_KEYS))})"))
    metrics = data.get("metrics")
    if not isinstance(metrics, dict) or not str(metrics.get("title") or "").strip():
        bad.append(("report.metrics", f"`## {REPORT}` json block carries `\"metrics\": "
                                      f"{{\"title\": ...}}` — the headline of the deck's key-metrics "
                                      f"page, naming what it shows"))
    elif set(metrics) - METRICS_KEYS:
        bad.append(("report.metrics", f"`metrics`: unknown key(s) "
                                      f"{', '.join(sorted(set(metrics) - METRICS_KEYS))}"))
    sched = data.get("schedules")
    if not isinstance(sched, list) or not sched:
        return bad + [("report.block", f"`## {REPORT}` json block carries `\"schedules\": [...]`, "
                                       f"a non-empty list")]
    for i, sc in enumerate(sched):
        at = f"schedules[{i}]"
        if not isinstance(sc, dict):
            bad.append(("report.schedule", f"{at} is not a mapping"))
            continue
        for k in SCHEDULE_REQUIRED:
            if not sc.get(k):
                bad.append(("report.schedule", f"{at} has no `{k}`"))
        for k in sorted(set(sc) - SCHEDULE_KEYS):
            bad.append(("report.schedule", f"{at}: unknown key `{k}` "
                                           f"(keys: {', '.join(sorted(SCHEDULE_KEYS))})"))
        fam = str(sc.get("from", "")).lower()
        if fam and fams and fam not in fams:
            bad.append(("report.schedule", f"{at}: `from: {fam}` names no family in the recipe"))
        cols = sc.get("columns")
        if cols is not None and (not isinstance(cols, list) or not cols
                                 or not all(isinstance(c, str) and c.strip() for c in cols)):
            bad.append(("report.schedule", f"{at}: `columns` is a non-empty list of header words"))
        where = sc.get("where")
        if where is not None and (not isinstance(where, dict) or not where or not all(
                isinstance(k, str) and (isinstance(v, str) or (isinstance(v, list) and v
                                                               and all(isinstance(x, str) for x in v)))
                for k, v in where.items())):
            bad.append(("report.schedule", f"{at}: `where` maps a header word to a value or a "
                                           f"list of values"))
        if sc.get("periods") is not None and sc["periods"] not in PERIODS:
            bad.append(("report.schedule", f"{at}: `periods` is {' | '.join(sorted(PERIODS))}"))
        if sc.get("scale") is not None and sc["scale"] not in SCALES:
            bad.append(("report.schedule", f"{at}: `scale` is {' | '.join(SCALES)}"))
        if sc.get("currency") is not None and str(sc["currency"]).lower() not in CURRENCIES:
            bad.append(("report.schedule", f"{at}: `currency` is a lower-case ISO 4217 code "
                                           f"scripts/style.py defines (`usd`, `eur`, ...)"))
        for k in ("dense", "ids"):
            if sc.get(k) is not None and not isinstance(sc[k], bool):
                bad.append(("report.schedule", f"{at}: `{k}` is true or false"))
        for k in ("title", "block", "through"):
            if sc.get(k) is not None and not isinstance(sc[k], str):
                bad.append(("report.schedule", f"{at}: `{k}` is a string"))
    return bad


def _lead(fm: dict[str, str]) -> list[str]:
    return [v.strip().strip("'\"") for v in fm.get("lead", "").strip().strip("[]").split(",")
            if v.strip()]


def validate(text: str, kinds: set[str] | None = None) -> list[tuple[str, str]]:
    """Every defect in `text` against RECIPE_FORMAT.md § The document, in reading order.
    `kinds` empty or None skips the family-kind rule (the caller has no KINDS)."""
    bad: list[tuple[str, str]] = []
    fm = frontmatter(text)
    if not fm:
        bad.append(("frontmatter.missing", "has no YAML frontmatter"))
    for req in ("name", "objective"):
        if not fm.get(req):
            bad.append(("frontmatter.required", f"frontmatter has no `{req}`"))
    if fm.get("name") and not NAME.match(fm["name"]):
        bad.append(("frontmatter.name", f"`name: {fm['name']}` is not kebab-case "
                                        f"(lower-case letters, digits, single hyphens)"))
    for k in sorted(set(fm) - FRONTMATTER_KEYS):
        bad.append(("frontmatter.unknown_key", f"unknown frontmatter key `{k}`"))
    heads = re.findall(r"^## (.+?)\s*$", text, re.M)
    pos = [heads.index(h) if h in heads else None for h in REQUIRED]
    for h, at in zip(REQUIRED, pos):
        if at is None:
            bad.append(("section.missing", f"has no `## {h}` section"))
    present = [at for at in pos if at is not None]
    if present != sorted(present):
        bad.append(("section.order", "required sections out of order - want "
                                     f"{' > '.join(REQUIRED)}"))
    for h in heads:
        if h in INHERITED:
            bad.append(("section.inherited", f"`## {h}` restates an inherited rule - "
                                             f"PLAYBOOK_RECIPES.md § What every recipe inherits owns it"))
    fams: dict[str, str] = {}
    for line in re.findall(r"^### .+$", text, re.M):
        m = FAMILY.match(line)
        if not m:
            bad.append(("family.header", "family header is not "
                                         f"`### <ID> — <what> (kind `<kind>`, <scope>)`: {line[:70]}"))
            continue
        fid = (m.group(1) + m.group(2)).lower()
        fams[fid] = m.group(4)
        if AFTER.search(m.group(4)):
            bad.append(("family.after", f"family {fid.upper()} states an order (`after ...`) "
                                        f"in its header; a family states what it reads from "
                                        f"other families, and the plan derives the order "
                                        f"from those reads (RECIPE_FORMAT.md § The families)"))
        if kinds and m.group(3) not in kinds:
            bad.append(("family.kind", f"family {fid.upper()} names kind `{m.group(3)}`, "
                                       f"which KINDS does not declare"))
    if not fams:
        bad.append(("family.none", "declares no family under `## The families`"))
    bad.extend(_report_defects(text, fams))
    hl = fm.get("headline")
    if hl:
        if hl not in fams:
            bad.append(("headline.family", f"`headline: {hl}` names no family in the recipe"))
        elif "one check" not in fams[hl]:
            bad.append(("headline.one_check", f"`headline: {hl}` must name a one-check family"))
    lead = _lead(fm)
    for fam in lead:
        if fam not in fams:
            bad.append(("lead.family", f"`lead` names `{fam}`, no family in the recipe"))
    if len(lead) != len(set(lead)):
        bad.append(("lead.repeat", "`lead` repeats a family"))
    if lead and hl and lead[0] != hl:
        bad.append(("lead.headline_first", f"`lead` opens with `{lead[0]}`, not the headline family "
                                           f"`{hl}` - the Exec Summary stands on the headline's tab, "
                                           f"so that tab sits first (WORKBOOK.md § 2)"))
    return bad
