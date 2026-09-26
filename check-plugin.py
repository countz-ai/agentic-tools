#!/usr/bin/env python3
"""Structural checks a Cowork plugin must pass before it is packaged.

Run by `make -C models/plugins check` and as a prerequisite of `zip`. Each check exists
because the property it tests is invisible until a run misbehaves, and none of them is
something `claude plugin validate` looks at.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import zipfile

# A frontmatter key not on this list is dropped silently by the loader, so a typo here is
# a skill that quietly loses a setting. Source: the CLI's own skill frontmatter schema.
SKILL_KEYS = {
    "name", "description", "model", "allowed-tools", "disallowed-tools", "disallowedTools",
    "argument-hint", "arguments", "disable-model-invocation", "user-invocable", "effort",
    "shell", "version", "when_to_use", "paths", "hooks", "context", "agent", "background",
    "fallback", "metadata",
}
AGENT_KEYS = {
    "name", "description", "model", "tools", "disallowedTools", "color", "effort",
    "permissionMode", "mcpServers", "hooks", "maxTurns", "skills", "initialPrompt",
    "memory", "background", "isolation", "observer", "observerMessage", "observeSubagents",
}

# The aliases the CLI resolves for a frontmatter `model:`, plus full ids (`claude-*`).
# An unrecognized value is not a run-time error: the CLI logs a warning and keeps the
# session model, so a typo silently re-prices the step at the big-model rate.
MODEL_VALUES = {"inherit", "haiku", "sonnet", "opus", "fable"}

# Three shapes a cap default takes when it escapes goal.json: a named cap key assigned a
# literal, a cap-ish key assigned one, and prose asserting a cap equals a number.
CAP_LITERAL = [
    # `(?!\.?used)` keeps the counter out of it: incrementing `budget.used` is the
    # mechanism, not a duplicated default.
    re.compile(r"\b(?:critique_cap|coordinator_budget|hook_budget|reindex_limit|retry_limit)\b(?!\.?used)[^\n]{0,24}?\b\d+", re.I),
    re.compile(r"\b\w*(?:_cap|_limit|_budget)\b\s*[:=]\s*\d", re.I),
    re.compile(r"\b(?:cap|limit|budget|ceiling)\b\s+(?:is|of|at|to|=)\s+\d", re.I),
    re.compile(r"\bcapped\s+(?:at|to)\s+\d", re.I),
]


# The index skill: lists every user-invocable skill for the user, one row each. Check 8r
# gates the list, and check 8m exempts it from the one-launcher rule for that reason.
INDEX_SKILL = "countz"

# The hosted upload refuses a skill or agent description carrying anything shaped
# like an XML tag (measured 2026-09-17: `<description>` in a quoted example phrase).
_XML_TAG = re.compile(r"<[A-Za-z/][^<>]*>")

# The hosted upload refuses a manifest description over this many characters.
DESCRIPTION_CAP = 500


def frontmatter(path: pathlib.Path) -> dict[str, str]:
    lines = path.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out, key = {}, None
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


def check(root: pathlib.Path) -> list[str]:
    bad: list[str] = []
    rel = lambda p: str(p.relative_to(root.parent))

    manifest = root / ".claude-plugin" / "plugin.json"
    mf: dict = {}
    try:
        mf = json.loads(manifest.read_text())
    except Exception as exc:
        bad.append(f"{rel(manifest)}: not valid JSON ({exc})")
    # Measured 2026-09-10: a 544-character description was refused at upload, and the
    # refusal reported the archive as carrying no manifest at all.
    if len(str(mf.get("description", ""))) > DESCRIPTION_CAP:
        bad.append(f"{rel(manifest)}: description is "
                   f"{len(str(mf.get('description', '')))} characters; the hosted "
                   f"validator caps it at {DESCRIPTION_CAP}")

    goals = sorted(d.name for d in (root / "goals").glob("*") if d.is_dir())

    # 1. Frontmatter is well formed, and a fork names the agent it forks into.
    for f in sorted(root.glob("skills/*/SKILL.md")):
        fm = frontmatter(f)
        for req in ("name", "description"):
            if not fm.get(req):
                bad.append(f"{rel(f)}: frontmatter has no `{req}`")
        for k in set(fm) - SKILL_KEYS:
            bad.append(f"{rel(f)}: unknown frontmatter key `{k}` - the loader drops it silently")
        mv = fm.get("model", "")
        if mv and mv not in MODEL_VALUES and not mv.startswith("claude-"):
            bad.append(f"{rel(f)}: model `{mv}` is neither a CLI alias "
                       f"({', '.join(sorted(MODEL_VALUES))}) nor a claude-* id - at run "
                       f"time it is dropped and the step runs on the session model")
        if fm.get("context") == "fork" and not fm.get("agent"):
            bad.append(f"{rel(f)}: `context: fork` with no `agent`")
        if fm.get("name") != f.parent.name:
            bad.append(f"{rel(f)}: frontmatter name `{fm.get('name')}` != directory `{f.parent.name}`")
        if _XML_TAG.search(str(fm.get("description", ""))):
            bad.append(f"{rel(f)}: description contains an XML-like tag (`<...>`) - the "
                       f"hosted upload refuses it (measured 2026-09-17); write the "
                       f"placeholder as `...` or in words")

    for f in sorted(root.glob("agents/*.md")):
        fm = frontmatter(f)
        for req in ("name", "description"):
            if not fm.get(req):
                bad.append(f"{rel(f)}: frontmatter has no `{req}`")
        for k in set(fm) - AGENT_KEYS:
            bad.append(f"{rel(f)}: unknown frontmatter key `{k}`")
        if _XML_TAG.search(str(fm.get("description", ""))):
            bad.append(f"{rel(f)}: description contains an XML-like tag (`<...>`) - the "
                       f"hosted upload refuses it (measured 2026-09-17)")
        mv = fm.get("model", "")
        if mv and mv not in MODEL_VALUES and not mv.startswith("claude-"):
            bad.append(f"{rel(f)}: model `{mv}` is neither a CLI alias "
                       f"({', '.join(sorted(MODEL_VALUES))}) nor a claude-* id - at run "
                       f"time it is dropped and the agent runs on the session model")

    # 2. Every agent a skill forks into exists.
    have = {frontmatter(a).get("name") for a in root.glob("agents/*.md")}
    for f in sorted(root.glob("skills/*/SKILL.md")):
        ref = frontmatter(f).get("agent", "")
        if ref and ref.split(":")[-1] not in have:
            bad.append(f"{rel(f)}: forks into `{ref}`, which no file in agents/ declares")

    # 3. The pluggable seam. A goal's name may appear in that goal's own directory and in
    #    its launcher. Anywhere else in skills/ means the orchestration has learned about a
    #    specific goal, and a second goal will not be a drop-in.
    for goal in goals:
        pat = re.compile(rf"\b{re.escape(goal)}\b", re.I)
        for f in sorted(root.glob("skills/*/*.md")):
            if f.parent.name == goal:
                continue
            for n, line in enumerate(f.read_text().splitlines(), 1):
                if pat.search(line):
                    bad.append(f"{rel(f)}:{n}: names the goal `{goal}` - the seam leaks")

    # 4. One cap, one home. A default written into prose is a second copy, and the copy
    #    that gets missed is the one being enforced.
    for f in sorted(list(root.glob("skills/**/*.md")) + list(root.glob("agents/*.md"))
                    + list(root.glob("reference/*.md"))):
        for n, line in enumerate(f.read_text().splitlines(), 1):
            if any(rx.search(line) for rx in CAP_LITERAL):
                bad.append(f"{rel(f)}:{n}: a cap value outside goal.json - {line.strip()[:60]}")

    # 5. Each goal declares what the engine reads, and the bodies it points at exist.
    for goal in goals:
        gf = root / "goals" / goal / "goal.json"
        try:
            g = json.loads(gf.read_text())
        except Exception as exc:
            bad.append(f"{rel(gf)}: not valid JSON ({exc})")
            continue
        for key in ("pipeline", "caps", "needs", "tasks", "analysis_body", "critique_rubric"):
            if key not in g:
                bad.append(f"{rel(gf)}: declares no `{key}`")
        for key in ("analysis_body", "critique_rubric"):
            if key in g and not (root / g[key]).is_file():
                bad.append(f"{rel(gf)}: `{key}` points at {g[key]}, which does not exist")
        steps = {s["step"] for s in g.get("pipeline", [])}
        for s in g.get("pipeline", []):
            if not (root / "skills" / s["skill"] / "SKILL.md").is_file():
                bad.append(f"{rel(gf)}: pipeline step `{s['step']}` names skill `{s['skill']}`, which has no SKILL.md")
            for r in s.get("requires", []):
                if r["step"] not in steps:
                    bad.append(f"{rel(gf)}: step `{s['step']}` requires `{r['step']}`, which the pipeline does not declare")
                if r.get("edge") not in ("hard", "soft"):
                    bad.append(f"{rel(gf)}: step `{s['step']}` -> `{r['step']}` has edge `{r.get('edge')}`; must be hard or soft")
        if g.get("abort_authority_step") and g["abort_authority_step"] not in steps:
            bad.append(f"{rel(gf)}: abort_authority_step `{g['abort_authority_step']}` is not a pipeline step")
        need_ids = {n["id"] for n in g.get("needs", [])}
        waves: list[int] = []
        for t in g.get("tasks", []):
            for nd in t.get("needs", []) + t.get("optional_needs", []):
                if nd not in need_ids:
                    bad.append(f"{rel(gf)}: task `{t['id']}` needs `{nd}`, which is not a declared need")
            w = t.get("wave")
            if not isinstance(w, int) or isinstance(w, bool) or w < 1:
                bad.append(f"{rel(gf)}: task `{t.get('id')}` has wave `{w}`; every task "
                           f"declares an integer wave >= 1 - P9 dispatches by it")
            else:
                waves.append(w)
            # Object-form produces entries are the task's output contract; unitlib
            # reconciles minted figures against them, so a malformed entry must fail
            # here, not mid-run. Legacy string entries (bare id or glob) stay valid.
            seen_out = set()
            for p in t.get("produces", []):
                if isinstance(p, str):
                    continue
                if ("id" in p) == ("pattern" in p):
                    bad.append(f"{rel(gf)}: task `{t.get('id')}` has a produces entry "
                               f"with {'both' if 'id' in p else 'neither'} of "
                               f"`id`/`pattern`; declare exactly one")
                    continue
                key = p.get("id") or p.get("pattern")
                if key in seen_out:
                    bad.append(f"{rel(gf)}: task `{t.get('id')}` declares output "
                               f"`{key}` twice")
                seen_out.add(key)
                if not p.get("claim"):
                    bad.append(f"{rel(gf)}: task `{t.get('id')}` output `{key}` has no "
                               f"claim - the declaration states what the figure asserts")
                kind = p.get("kind", "figure")
                if kind not in ("figure", "record"):
                    bad.append(f"{rel(gf)}: task `{t.get('id')}` output `{key}` has "
                               f"kind `{kind}`; must be figure or record")
                if kind == "figure" and p.get("unit") not in ("usd", "days", "pct",
                                                             "count", "ratio"):
                    bad.append(f"{rel(gf)}: task `{t.get('id')}` figure `{key}` needs "
                               f"a unit from usd|days|pct|count|ratio, got "
                               f"`{p.get('unit')}`")
        if waves and sorted(set(waves)) != list(range(1, max(waves) + 1)):
            bad.append(f"{rel(gf)}: task waves {sorted(set(waves))} are not contiguous "
                       f"from 1 - renumber")
        for f_ in g.get("floor", []):
            if f_ not in need_ids:
                bad.append(f"{rel(gf)}: floor names `{f_}`, which is not a declared need")
        for t in g.get("tie_outs", []):
            for side in t.get("sides", []):
                if side not in need_ids:
                    bad.append(f"{rel(gf)}: tie `{t['id']}` has side `{side}`, which is not a declared need")

        # The deliverable's tab order is one declaration, not two lists that can drift.
        # A tab named at run level must not also be a task label: a task writes its own
        # tab, so naming it again produces the tab twice, and a NEAR-duplicate ("Walk" vs
        # a task labelled "Walk from Current to Target") is worse because no string
        # comparison catches it.
        d = g.get("deliverable") or {}
        if "standing_tabs" in d:
            bad.append(f"{rel(gf)}: deliverable uses the retired `standing_tabs`; "
                       f"split it into `tabs_before_tasks` and `tabs_after_tasks`")
        labels = {t.get("label", "") for t in g.get("tasks", [])}
        run_tabs = list(d.get("tabs_before_tasks", [])) + list(d.get("tabs_after_tasks", []))
        for tab in run_tabs:
            if tab in labels:
                bad.append(f"{rel(gf)}: `{tab}` is both a run-level tab and a task label")
            for lab in labels:
                if lab and tab != lab and (tab in lab or lab in tab):
                    bad.append(f"{rel(gf)}: run-level tab `{tab}` and task label `{lab}` "
                               f"name the same tab two ways")
        if len(run_tabs) != len(set(run_tabs)):
            bad.append(f"{rel(gf)}: a run-level tab is listed twice")

    # 5b. The event vocabulary is closed in prose; make it closed in fact. A live run
    #     invented `gate_answered` because the doc's table lacked it - the agent was right,
    #     but nothing would have caught it being wrong. Every event a skill or agent tells
    #     something to write must appear in OBSERVABILITY.md's table.
    obs = root / "reference" / "OBSERVABILITY.md"
    if obs.is_file():
        text = obs.read_text()
        declared = set(re.findall(r"^\| `(\w+)` \|", text, re.M))
        emitted: set[str] = set()
        for f in list(root.glob("skills/**/*.md")) + list(root.glob("agents/*.md")) \
                + list(root.glob("hooks/*")):
            if f.is_file():
                emitted |= set(re.findall(r'"event"\s*:\s*"(\w+)"', f.read_text()))
        for ev in sorted(emitted - declared):
            bad.append(f"{rel(obs)}: event `{ev}` is written somewhere but not declared "
                       f"in the event table")

    # 5c. Every id prefix used must be declared. These ids reach the reader - they are
    #     what the Sources tab cites - so an undeclared one is a token nobody can look up.
    #     Measured: 10 of 12 prefixes were in use with no definition anywhere, found only
    #     because a reader asked what `E` meant, and `E` was one of the two documented.
    ev = root / "reference" / "EVIDENCE.md"
    if ev.is_file():
        text = ev.read_text()
        declared = set(re.findall(r"^\| `([A-Z]{1,2})\.` \|", text, re.M))
        if declared:
            used: dict[str, str] = {}
            for f in sorted(list(root.glob("**/*.md")) + list(root.glob("**/*.json"))):
                if not f.is_file():
                    continue
                for m in re.finditer(r"\b([A-Z]{1,2})\.[a-z_][a-z0-9_.*-]*", f.read_text()):
                    used.setdefault(m.group(1), f"{rel(f)}: {m.group(0)}")
            for pfx in sorted(set(used) - declared):
                bad.append(f"{rel(ev)}: id prefix `{pfx}.` is used but not declared in the "
                           f"namespace table - e.g. {used[pfx]}")

    # 5d. Epigram tics. The real test is semantic - a negation that states something about
    #     its subject is fine; one whose point is the phrasing is cut - and a regex cannot
    #     apply it. This list only holds phrases already cut once (2026-08-20 sweep: 28
    #     instances across 12 files), so a goal copy-adapted from an old checkout cannot
    #     paste them back. When a new tic is cut, add its most distinctive fragment here.
    TICS = ["is not a number", "not garnish", "numeric costume", "not the motor",
            "gets its paperwork", "wearing different words", "roadmap is an order",
            "it is a wish", "protects exactly the runs", "the order is the design",
            "pretended lineage", "band is never a cap", "is not a citation",
            "read as generated", "split is not bookkeeping", "not a style choice",
            "is not an open item", "it is a worry", "is meaningless",
            "the whole point of"]
    for f in sorted(list(root.glob("**/*.md")) + list(root.glob("**/*.json"))
                    + list(root.glob("**/*.sh"))):
        if not f.is_file():
            continue
        low = f.read_text().lower()
        for tic in TICS:
            if tic in low:
                bad.append(f"{rel(f)}: carries the removed phrase '{tic}' - state the "
                           f"checkable fact instead, or delete the sentence")

    # 5f. A dispatched instruction file (an agent charter, a skill) is read by a worker whose
    #     working directory is the RUN, not the plugin. So every reference file it names as a
    #     read target carries ${CLAUDE_PLUGIN_ROOT}; a bare `reference/X.md` resolves to
    #     nothing there. Measured 2026-09-22: check-report/SKILL.md named REPORT.md and
    #     WORKBOOK_STYLE.md bare in the one sentence listing what the report worker must
    #     read, while naming DOCTRINE.md and WORKBOOK.md with the prefix in the same
    #     sentence. Reference docs cite each other by bare name and are exempt: they are
    #     siblings, already resolved by whoever opened one.
    BARE_REF = re.compile(r"`reference/[A-Z][A-Z_]*\.md")
    for f in sorted(list(root.glob("agents/*.md")) + list(root.glob("skills/*/SKILL.md"))):
        if not f.is_file():
            continue
        for m in BARE_REF.finditer(f.read_text()):
            bad.append(f"{rel(f)}: names `{m.group(0)[1:]}` with no ${{CLAUDE_PLUGIN_ROOT}} "
                       f"prefix - a dispatched worker runs in the run directory, where that "
                       f"path resolves to nothing")

    # 5g. Where scripts/section.py ships, every context a reader enters the plugin
    #     through reaches the rule for using it in one hop. The rule has two homes, one
    #     per reader class: reference/CONDUCT.md (the agents that touch client data read
    #     it first) and reference/RUN_CONTRACT.md (every relay and the engine read it
    #     whole, first). An agent file or an inline skill that cites a section names one
    #     of the two, or states the rule itself. Reference docs and recipes are never an
    #     entry point.
    if (root / "scripts" / "section.py").is_file():
        homes = []
        for h in ("reference/CONDUCT.md", "reference/RUN_CONTRACT.md"):
            hf = root / h
            if hf.is_file() and "section.py" in hf.read_text():
                homes.append(h)
            else:
                bad.append(f"{rel(hf)}: does not state how to read a section citation "
                           f"(scripts/section.py)")

        def reaches(txt: str) -> bool:
            return "section.py" in txt or any(h in txt for h in homes)

        for af in sorted((root / "agents").glob("*.md")):
            txt = af.read_text()
            if "\u00a7" in txt and not reaches(txt):
                bad.append(f"{rel(af)}: names neither scripts/section.py nor a document "
                           f"stating the rule ({', '.join(homes) or 'none ships'}) - a "
                           f"reader entering here has no rule for section citations")
        for sf in sorted((root / "skills").glob("*/SKILL.md")):
            txt = sf.read_text()
            if frontmatter(sf).get("context") == "inline" and "\u00a7" in txt \
                    and not reaches(txt):
                bad.append(f"{rel(sf)}: inline skill cites a section and reaches no rule "
                           f"for reading one ({', '.join(homes) or 'scripts/section.py'})")

    # 5f. A `<FILE>.md § <Section>` citation resolves to a heading in that file. Nothing
    #     dereferences the section mark at run time - an agent reads the named file and
    #     looks for the heading - so a section that is renamed, or demoted to a bold
    #     run-in, orphans its citations in silence. Measured 2026-09-13: five citations
    #     named PLAYBOOK_RECIPES.md lead-ins that had never been headings, and one named
    #     `RUN_CONTRACT.md § Classification` for `## Classification and retries`.
    #     The key set is scripts/section.py's own `keys()` where the plugin ships that
    #     script, so the gate and the dereferencing tool cannot drift apart.
    def _local_keys(h: str) -> set[str]:
        keys = {h, h.split(" \u2014 ")[0]}
        num = re.match(r"^(\d+)[.)]\s", h)
        if num:
            keys.add(num.group(1))
        return {k.strip().rstrip(".") for k in keys if k.strip()}

    _heading_keys = _local_keys
    sec = root / "scripts" / "section.py"
    if sec.is_file():
        import importlib.util
        try:
            spec = importlib.util.spec_from_file_location("_section_check", sec)
            smod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(smod)
            _heading_keys = smod.keys
        except Exception as exc:
            bad.append(f"{rel(sec)}: will not import, so its keys() cannot back the "
                       f"section-citation gate ({exc})")

    heads: dict[str, set[str]] = {}
    for f in root.rglob("*.md"):
        if not f.is_file():
            continue
        ks = heads.setdefault(f.name, set())
        for line in f.read_text(errors="replace").splitlines():
            h = re.match(r"^#{1,6}\s+(.*?)\s*$", line)
            if h:
                ks |= _heading_keys(h.group(1))
    # The section name may wrap across a line; join it before matching.
    SECREF = re.compile(r"([A-Za-z0-9_-]+\.md)`?[^\S\n]*\n?[^\S\n]*(\u00a7(?:[^\n`,;)]|\n)*)")
    for f in sorted(root.rglob("*.md")):
        if not f.is_file():
            continue
        for m in SECREF.finditer(f.read_text(errors="replace")):
            fn, tail = m.group(1), " ".join(m.group(2).split())
            ks = heads.get(fn)
            if ks is None:
                bad.append(f"{rel(f)}: cites `{fn}` \u00a7 ..., and no such file ships "
                           f"in this plugin")
                continue
            for piece in (p for p in tail.split("\u00a7") if p.strip()):
                cand = piece.strip()
                if not any(cand.lower().startswith(k.lower())
                           and (len(cand) == len(k) or not cand[len(k)].isalnum())
                           for k in ks):
                    bad.append(f"{rel(f)}: cites `{fn}` \u00a7 {cand[:48]} - that file "
                               f"has no such heading")

    # 5e. Every goal.json top-level key has a consumer. At run time nothing executes the
    #     declaration - it is followed because skills are told to read named keys - so a key
    #     nothing references is dead bytes that LOOK load-bearing. `recommendation_guard`
    #     sat exactly there: the rule lived in analyze.md prose and the key was an unread
    #     second copy, found only because a reader asked what the file did.
    META = {"schema", "goal", "title", "version", "//"}
    for goal in goals:
        gf = root / "goals" / goal / "goal.json"
        try:
            g = json.loads(gf.read_text())
        except Exception:
            continue                          # already reported by check 5
        consumers = ""
        for f in sorted(list(root.glob("skills/**/*.md")) + list(root.glob("agents/*.md"))
                        + list(root.glob("reference/*.md"))
                        + list((root / "goals" / goal).glob("*.md"))):
            consumers += f.read_text()
        consumers += pathlib.Path(__file__).read_text()
        for k in g:
            if k in META:
                continue
            if k not in consumers:
                bad.append(f"{rel(gf)}: top-level key `{k}` is referenced by nothing - "
                           f"either point a consumer at it or delete it")

    # 6. The rate table: every model must point at a tier that exists, and the table must
    #    say when it was captured. A dollar figure with no provenance is a bill-shaped guess.
    rf = root / "reference" / "rates.json"
    if rf.is_file():
        try:
            r = json.loads(rf.read_text())
            for key in ("captured_at", "source", "tiers", "models"):
                if not r.get(key):
                    bad.append(f"{rel(rf)}: has no `{key}`")
            for model, tier in (r.get("models") or {}).items():
                if tier not in (r.get("tiers") or {}):
                    bad.append(f"{rel(rf)}: model `{model}` points at tier `{tier}`, which is not declared")
            for tier, cols in (r.get("tiers") or {}).items():
                for col in ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read", "web_search"):
                    if col not in cols:
                        bad.append(f"{rel(rf)}: tier `{tier}` has no `{col}` rate")
        except Exception as exc:
            bad.append(f"{rel(rf)}: not valid JSON ({exc})")

    # 7. A top-level bin/ is REFUSED by the claude.ai-hosted validator: its contents are
    #    added to PATH on the CLI but are not shown on the admin approval surface, so an
    #    approver cannot see what they are approving. That rule lives server-side - neither
    #    `claude plugin validate` nor this file's other checks catch it, and it surfaces
    #    only at upload. Ship helper executables under scripts/ (the convention the
    #    official claude-security plugin uses) and invoke them by full path.
    if (root / "bin").is_dir():
        for f in sorted((root / "bin").rglob("*")):
            if f.is_file():
                bad.append(f"{rel(f)}: top-level bin/ is refused by the hosted plugin "
                           f"validator; move it to scripts/ and invoke it by full path")

    # 8. Anything shipped in scripts/ must parse and be executable.
    for b in sorted(root.glob("scripts/*.py")):
        try:
            compile(b.read_text(), str(b), "exec")
        except SyntaxError as exc:
            bad.append(f"{rel(b)}: syntax error at line {exc.lineno}")
        if not b.stat().st_mode & 0o111:
            bad.append(f"{rel(b)}: not executable")

    # 7b. usage_report must count usage once per API RESPONSE. The transcript writes one
    #     record per CONTENT BLOCK, each carrying the response's usage; summing records
    #     inflated a real report 1.83x, and the error was invisible from outside (totals
    #     self-consistent, decomposition "confirmed" from the script's own outputs). The
    #     fixture below is the ninety-second raw-source check, made permanent: 3 records
    #     sharing one message id + 1 alone, progressive usage on the shared id so last-wins
    #     is also exercised. Want 2 responses / 30 output tokens; per-record summing sees 4
    #     and 55.
    ur = root / "scripts" / "usage_report.py"
    if ur.is_file():
        import importlib.util
        import tempfile
        try:
            spec = importlib.util.spec_from_file_location("_ur_check", ur)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            with tempfile.TemporaryDirectory() as td:
                fx = pathlib.Path(td) / "t.jsonl"
                def rec(mid, out):
                    return json.dumps({"type": "assistant",
                        "timestamp": "2026-01-01T00:00:00.000Z",
                        "message": {"id": mid, "model": "m",
                                    "usage": {"input_tokens": 1, "output_tokens": out,
                                              "cache_creation_input_tokens": 0,
                                              "cache_read_input_tokens": 100}}})
                fx.write_text("\n".join([rec("msg_a", 5), rec("msg_a", 15), rec("msg_a", 20),
                                         rec("msg_b", 10)]) + "\n")
                by_model, _f, _l, records = mod.read_transcript(fx)
                got = by_model.get("m", {})
                if (records, got.get("messages"), got.get("output_tokens"),
                        got.get("cache_read_input_tokens")) != (4, 2, 30, 200):
                    bad.append(f"{rel(ur)}: read_transcript returned "
                               f"{got.get('messages')} responses / {got.get('output_tokens')} "
                               f"output / {got.get('cache_read_input_tokens')} cache-read from "
                               f"the 3+1 fixture (want 2 / 30 / 200) - per-content-block "
                               f"duplication or wrong-record-wins is back")
        except Exception as exc:
            bad.append(f"{rel(ur)}: dedup self-test failed to run ({exc})")

    # 8c. coordinate.py decides the mechanical predicates; three fixture calls keep the
    #     dispatch chain and the escalate contract honest: a fresh bootstrap must dispatch
    #     the first pipeline step, a finished step must advance to the next, and an orphan
    #     step record (the class of state damage the agent coordinator twice had to repair
    #     by hand) must exit 3 without writing.
    co = root / "scripts" / "coordinate.py"
    if co.is_file() and goals:
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            room = tdp / "room"
            room.mkdir()
            (room / "a.xlsx").write_text("x")
            rd = tdp / "out" / "sess-check"

            def run_co(*extra):
                return subprocess.run([sys.executable, str(co), str(rd), *extra],
                                      capture_output=True, text=True)

            r = run_co("--goal", goals[0], "--data-room", str(room),
                       "--output-root", str(tdp / "out"), "--session-id", "sess-check")
            first = json.loads((root / "goals" / goals[0] / "goal.json").read_text()
                               )["pipeline"][0]
            if r.returncode != 0 or f"NEXT: Skill {first['skill']}" not in r.stdout:
                bad.append(f"{rel(co)}: fresh bootstrap did not dispatch {first['step']} "
                           f"(exit {r.returncode}): {(r.stdout or r.stderr).strip()[:100]}")
            else:
                fp = subprocess.run([sys.executable, str(co), "--fingerprint", str(room)],
                                    capture_output=True, text=True).stdout.strip()
                (rd / "file_index.json").write_text(json.dumps({"room_fingerprint": fp}))
                (rd / "steps" / f"0001-{first['step']}.json").write_text(json.dumps(
                    {"seq": 1, "step": first["step"], "outcome": "complete", "error": None,
                     "conclusion": "ok", "produced": ["file_index.json"], "consumed": []}))
                r2 = run_co()
                if r2.returncode != 0 or "NEXT: Skill" not in r2.stdout:
                    bad.append(f"{rel(co)}: a finished {first['step']} did not advance the "
                               f"pipeline (exit {r2.returncode}): "
                               f"{(r2.stdout or r2.stderr).strip()[:100]}")
                # Every run.json write must land run-view.json beside it at the same
                # revision, holding none of the fields the view exists to omit.
                view_p = rd / "run-view.json"
                if not view_p.is_file():
                    bad.append(f"{rel(co)}: save_run wrote no run-view.json - dispatched "
                               f"steps have nothing slim to read")
                else:
                    rj = json.loads((rd / "run.json").read_text())
                    rv = json.loads(view_p.read_text())
                    if rv.get("for_revision") != rj.get("revision"):
                        bad.append(f"{rel(co)}: run-view.json for_revision "
                                   f"{rv.get('for_revision')} != run.json revision "
                                   f"{rj.get('revision')} - the view lags its source")
                    for k in ("dispatches", "deliverable", "control"):
                        if k in rv:
                            bad.append(f"{rel(co)}: run-view.json carries `{k}`, a field "
                                       f"the view exists to omit")
                before = (rd / "run.json").read_text()
                before_view = view_p.read_text() if view_p.is_file() else ""
                (rd / "steps" / "0055-analyze.json").write_text("{}")
                r3 = run_co()
                if r3.returncode != 3:
                    bad.append(f"{rel(co)}: an orphan step record must escalate with "
                               f"exit 3, got {r3.returncode}")
                elif (rd / "run.json").read_text() != before:
                    bad.append(f"{rel(co)}: an escalate wrote run.json - escalation must "
                               f"leave the state untouched for the agent")
                elif view_p.is_file() and view_p.read_text() != before_view:
                    bad.append(f"{rel(co)}: an escalate rewrote run-view.json - escalation "
                               f"must leave the state untouched for the agent")

    # 8c2. P10 scopes a later round's critique by the deliverable hash snapshot: with a
    #      snapshot, one moved tab and a round still budgeted it must dispatch
    #      scope=incremental naming exactly the moved file, the prior critique's record
    #      and the fix record, and re-snapshot; with no snapshot it must fall back to
    #      scope=full; with no round budgeted it must fall through to finalize — a fix
    #      verifies its own change by diff and never buys a re-critique.
    if co.is_file() and goals:
        import hashlib
        import subprocess
        import tempfile
        g = json.loads((root / "goals" / goals[0] / "goal.json").read_text())
        pipe = g.get("pipeline", [])
        pre, per_task = [], None
        for s in pipe:
            if s.get("per_task"):
                per_task = s["step"]
                break
            pre.append(s["step"])
        if per_task and {"critique", "finalize"} <= {s["step"] for s in pipe}:
            fin_skill = next(s["skill"] for s in pipe if s["step"] == "finalize")
            dh = lambda b: "dh_" + hashlib.sha256(b).hexdigest()[:16]
            ts = lambda m: f"2026-01-01T00:0{m}:00.000+00:00"

            def p10_fixture(tdp, with_snapshot, crit_fresh=False, fin=None, cap=None):
                rd = tdp / "run"
                (rd / "steps").mkdir(parents=True)
                (rd / "out" / "tabs").mkdir(parents=True)
                (rd / "workpapers").mkdir()
                (rd / "out" / "tabs" / "t1.xlsx").write_bytes(b"new tab bytes")
                (rd / "workpapers" / "figures-t1.yaml").write_bytes(b"unchanged")
                rows = []

                def row(seq, step, **kw):
                    rows.append({"seq": seq, "step": step,
                                 "task_id": kw.get("task_id"), "skill": "x",
                                 "args": kw.get("args", {}), "attempt_of": None,
                                 "round": kw.get("round"), "state": "done_ok",
                                 "dispatched_at": ts(0),
                                 "recorded_at": kw.get("recorded_at"),
                                 "record": f"steps/{seq:04d}-{step}.json",
                                 "conclusion": "ok", "verdict": None, "produced": [],
                                 "consumed_paths": [], "blockers": [], "error": None,
                                 "folded_at": ts(0), "notes": None})

                for i, stepname in enumerate(pre, 1):
                    row(i, stepname)
                a1 = len(pre) + 1
                row(a1, per_task, task_id="t1", recorded_at=ts(1),
                    args={"mode": "fresh"})
                cs = a1 + 1
                # crit_fresh puts the critique AFTER the fix round, with an advisory
                # rerun finding and a material one whose id the fix already carried -
                # neither may buy a fix round (P11's actionable filter).
                row(cs, "critique", recorded_at=ts(4) if crit_fresh else ts(2))
                (rd / "steps" / f"{cs:04d}-critique.json").write_text(json.dumps(
                    {"seq": cs, "step": "critique", "outcome": "complete",
                     "error": None, "conclusion": "ok", "produced": [],
                     "consumed": [], "findings": [
                         {"id": "C1", "severity": "advisory",
                          "fix_kind": "rerun_task", "fix_task": "t1",
                          "disposition": "open"},
                         {"id": "C2", "severity": "material",
                          "fix_kind": "rerun_task", "fix_task": "t1",
                          "disposition": "open"}]}))
                fs = cs + 1
                row(fs, per_task, task_id="t1", recorded_at=ts(3),
                    args={"mode": "fix", "finding": "C2"}, round=1)
                if fin == "stale":
                    row(fs + 1, "finalize", recorded_at=ts(2))
                caps = g["caps"]
                run = {"schema": "advisory-report/run@1", "revision": 1,
                       "run_id": "fx", "goal": goals[0], "goal_version": "1",
                       "created_at": ts(0), "updated_at": ts(0),
                       "updated_by": "fixture", "degraded": False,
                       "inputs": {"data_room": str(tdp / "room"),
                                  "output_root": str(tdp), "run_dir": str(rd),
                                  "sessions": []},
                       "control": {"halt": False, "halt_reason": None,
                                   "halt_requested_by": None,
                                   "critique_cap": caps["critique_cap"]
                                   if cap is None else cap,
                                   "coordinator_budget": {
                                       "limit": caps["coordinator_budget"], "used": 0},
                                   "hook_budget": {"limit": caps["hook_budget"],
                                                   "used": 0},
                                   "reindex_limit": caps["reindex_limit"],
                                   "abort_authority_step": None},
                       "plan": {"recorded_by_seq": None, "approved_by_user": True,
                                "analysis_window": None, "wanted": [],
                                "tasks": [{"id": "t1", "wave": 1,
                                           "state": "runnable"}]},
                       "room": {"fingerprint": None, "scanned_at": None,
                                "changes": []},
                       "deliverable": ({"hashes": {
                                            "out/tabs/t1.xlsx": dh(b"old tab bytes"),
                                            "workpapers/figures-t1.yaml":
                                                dh(b"unchanged")},
                                        "for_seq": cs, "snapped_at": ts(2)}
                                       if with_snapshot else None),
                       "dispatches": rows, "steps": {}, "next": {},
                       "termination": None}
                (rd / "run.json").write_text(json.dumps(run))
                return rd, cs, fs

            with tempfile.TemporaryDirectory() as td:
                rd, cs, fs = p10_fixture(pathlib.Path(td), with_snapshot=True, cap=2)
                r = subprocess.run([sys.executable, str(co), str(rd)],
                                   capture_output=True, text=True)
                want = ["scope=incremental", "changed=out/tabs/t1.xlsx",
                        f"carry_from=steps/{cs:04d}-critique.json",
                        f"fix_records=steps/{fs:04d}-{per_task}.json"]
                missing = [w for w in want if w not in r.stdout]
                if r.returncode != 0 or missing:
                    bad.append(f"{rel(co)}: P10 with a snapshot and one moved tab must "
                               f"dispatch an incremental critique (exit {r.returncode}, "
                               f"missing {missing or 'nothing'}): "
                               f"{(r.stdout or r.stderr).strip()[:120]}")
                else:
                    after = json.loads((rd / "run.json").read_text())["deliverable"]
                    if after["hashes"].get("out/tabs/t1.xlsx") != dh(b"new tab bytes") \
                            or after["for_seq"] != fs + 1:
                        bad.append(f"{rel(co)}: P10 did not re-snapshot the deliverable "
                                   f"hashes for the dispatch it made")
            with tempfile.TemporaryDirectory() as td:
                rd, cs, fs = p10_fixture(pathlib.Path(td), with_snapshot=False, cap=2)
                r = subprocess.run([sys.executable, str(co), str(rd)],
                                   capture_output=True, text=True)
                if r.returncode != 0 or "scope=full" not in r.stdout:
                    bad.append(f"{rel(co)}: P10 with no deliverable snapshot must fall "
                               f"back to a full critique (exit {r.returncode}): "
                               f"{(r.stdout or r.stderr).strip()[:120]}")
            # A fix never buys a re-critique: with the round budget spent (one critique
            # dispatched, cap 1) the landed fix must fall through to finalize, not
            # dispatch another critique.
            with tempfile.TemporaryDirectory() as td:
                rd, cs, fs = p10_fixture(pathlib.Path(td), with_snapshot=True, cap=1)
                r = subprocess.run([sys.executable, str(co), str(rd)],
                                   capture_output=True, text=True)
                if r.returncode != 0 or f"NEXT: Skill {fin_skill}" not in r.stdout \
                        or "scope=" in r.stdout:
                    bad.append(f"{rel(co)}: a fix with no round budgeted must fall "
                               f"through to finalize, not buy a re-critique "
                               f"(exit {r.returncode}): "
                               f"{(r.stdout or r.stderr).strip()[:120]}")
            # P11's actionable filter: an advisory rerun finding, and a material one whose
            # id a fix dispatch already carried, must buy no second fix round - the loop
            # falls through to finalize and the findings reach the quality memo.
            with tempfile.TemporaryDirectory() as td:
                rd, cs, fs = p10_fixture(pathlib.Path(td), with_snapshot=True,
                                         crit_fresh=True)
                r = subprocess.run([sys.executable, str(co), str(rd)],
                                   capture_output=True, text=True)
                if r.returncode != 0 or f"NEXT: Skill {fin_skill}" not in r.stdout:
                    bad.append(f"{rel(co)}: an advisory rerun finding plus one already "
                               f"fix-attempted must fall through to finalize, not buy a "
                               f"fix round (exit {r.returncode}): "
                               f"{(r.stdout or r.stderr).strip()[:120]}")
            # P11 groups a round's actionable findings by task and dispatches the fix
            # with their ids comma-joined, so one re-run answers every finding naming
            # the task and the one-attempt rule can key on each id.
            with tempfile.TemporaryDirectory() as td:
                rd, cs, fs = p10_fixture(pathlib.Path(td), with_snapshot=True,
                                         crit_fresh=True, cap=2)
                (rd / "steps" / f"{cs:04d}-critique.json").write_text(json.dumps(
                    {"seq": cs, "step": "critique", "outcome": "complete",
                     "error": None, "conclusion": "ok", "produced": [],
                     "consumed": [], "findings": [
                         {"id": "C3", "severity": "blocking",
                          "fix_kind": "rerun_task", "fix_task": "t1",
                          "disposition": "open"},
                         {"id": "C4", "severity": "material",
                          "fix_kind": "rerun_task", "fix_task": "t1",
                          "disposition": "open"}]}))
                r = subprocess.run([sys.executable, str(co), str(rd)],
                                   capture_output=True, text=True)
                if r.returncode != 0 or "finding=C3,C4" not in r.stdout:
                    bad.append(f"{rel(co)}: P11 must dispatch one fix per task with the "
                               f"actionable finding ids comma-joined "
                               f"(exit {r.returncode}): "
                               f"{(r.stdout or r.stderr).strip()[:120]}")
            # P13's staleness arm: a seal older than the latest critique is re-run, which
            # is what lets a user-directed fix after completion reseal the workbook.
            with tempfile.TemporaryDirectory() as td:
                rd, cs, fs = p10_fixture(pathlib.Path(td), with_snapshot=True,
                                         crit_fresh=True, fin="stale")
                r = subprocess.run([sys.executable, str(co), str(rd)],
                                   capture_output=True, text=True)
                if r.returncode != 0 or f"NEXT: Skill {fin_skill}" not in r.stdout \
                        or "reseal" not in r.stdout:
                    bad.append(f"{rel(co)}: a finalize older than the latest critique "
                               f"must be re-dispatched to reseal (exit {r.returncode}): "
                               f"{(r.stdout or r.stderr).strip()[:120]}")

    # 8g. A wave must not serialize as repeat invocations of one forked skill, so a
    #     multi-dispatch decision runs as clean-context sub-agents: with two runnable
    #     wave-1 tasks the coordinator must print the WAVE marker and one NEXT line per
    #     task, each carrying brief=, and write each brief as a self-contained instruction
    #     file - agent file, skill file, plugin root and the dispatch args, all absolute,
    #     because a sub-agent prompt gets no ${CLAUDE_PLUGIN_ROOT} substitution and no
    #     conversation. The single dispatch that follows the wave must carry none of that:
    #     a single runs as its skill's fork.
    if co.is_file() and goals:
        import subprocess
        import tempfile
        g = json.loads((root / "goals" / goals[0] / "goal.json").read_text())
        pipe = g.get("pipeline", [])
        pre, pt = [], None
        for s in pipe:
            if s.get("per_task"):
                pt = s
                break
            pre.append(s["step"])
        if pt:
            ts = lambda m: f"2026-01-01T00:0{m}:00.000+00:00"
            with tempfile.TemporaryDirectory() as td:
                tdp = pathlib.Path(td)
                rd = tdp / "run"
                (rd / "steps").mkdir(parents=True)
                rows = [{"seq": i, "step": stepname, "task_id": None, "skill": "x",
                         "args": {}, "attempt_of": None, "round": None,
                         "state": "done_ok", "dispatched_at": ts(0), "recorded_at": ts(1),
                         "record": f"steps/{i:04d}-{stepname}.json", "conclusion": "ok",
                         "verdict": None, "produced": [], "consumed_paths": [],
                         "blockers": [], "error": None, "folded_at": ts(1), "notes": None}
                        for i, stepname in enumerate(pre, 1)]
                caps = g["caps"]
                run = {"schema": "advisory-report/run@1", "revision": 1, "run_id": "fx",
                       "goal": goals[0], "goal_version": "1", "created_at": ts(0),
                       "updated_at": ts(0), "updated_by": "fixture", "degraded": False,
                       "inputs": {"data_room": str(tdp / "room"), "output_root": str(tdp),
                                  "run_dir": str(rd), "sessions": []},
                       "control": {"halt": False, "halt_reason": None,
                                   "halt_requested_by": None,
                                   "critique_cap": caps["critique_cap"],
                                   "coordinator_budget": {
                                       "limit": caps["coordinator_budget"], "used": 0},
                                   "hook_budget": {"limit": caps["hook_budget"],
                                                   "used": 0},
                                   "reindex_limit": caps["reindex_limit"],
                                   "abort_authority_step": None},
                       "plan": {"recorded_by_seq": None, "approved_by_user": True,
                                "analysis_window": None, "wanted": [],
                                "tasks": [{"id": "t1", "wave": 1, "state": "runnable"},
                                          {"id": "t2", "wave": 1, "state": "runnable"}]},
                       "room": {"fingerprint": None, "scanned_at": None, "changes": []},
                       "deliverable": None, "dispatches": rows, "steps": {}, "next": {},
                       "termination": None}
                (rd / "run.json").write_text(json.dumps(run))
                r = subprocess.run([sys.executable, str(co), str(rd)],
                                   capture_output=True, text=True)
                nexts = [l for l in r.stdout.splitlines() if l.startswith("NEXT:")]
                seq0 = len(pre) + 1
                if r.returncode != 0 or "WAVE: 2 dispatches" not in r.stdout \
                        or len(nexts) != 2 or any("brief=" not in l for l in nexts):
                    bad.append(f"{rel(co)}: two runnable wave-1 tasks must dispatch as a "
                               f"WAVE of 2 NEXT lines each carrying brief= (exit "
                               f"{r.returncode}, {len(nexts)} NEXT line(s)): "
                               f"{(r.stdout or r.stderr).strip()[:120]}")
                else:
                    ok = True
                    for i, task in enumerate(("t1", "t2")):
                        bp = rd / "dispatch" / f"{seq0 + i:04d}-{pt['step']}.md"
                        if not bp.is_file():
                            bad.append(f"{rel(co)}: wave dispatch {seq0 + i} has no "
                                       f"brief at dispatch/{bp.name}")
                            ok = False
                            continue
                        text = bp.read_text()
                        need = [str((root / "agents" / "worker.md").resolve()),
                                str((root / "skills" / pt["skill"] / "SKILL.md").resolve()),
                                f"task={task}", f"seq={seq0 + i}", "mode=fresh"]
                        missing = [w for w in need if w not in text]
                        if missing:
                            bad.append(f"{rel(co)}: brief dispatch/{bp.name} is not "
                                       f"self-contained - missing {missing}")
                            ok = False
                    if ok:
                        for i in range(2):
                            (rd / "steps" / f"{seq0 + i:04d}-{pt['step']}.json").write_text(
                                json.dumps({"seq": seq0 + i, "step": pt["step"],
                                            "outcome": "complete", "error": None,
                                            "conclusion": "ok", "produced": ["x"],
                                            "consumed": []}))
                        r2 = subprocess.run([sys.executable, str(co), str(rd)],
                                            capture_output=True, text=True)
                        if r2.returncode != 0 or "NEXT: Skill" not in r2.stdout \
                                or "brief=" in r2.stdout or "WAVE:" in r2.stdout:
                            bad.append(f"{rel(co)}: the single dispatch after a wave must "
                                       f"be a plain Skill line - no WAVE, no brief= (exit "
                                       f"{r2.returncode}): "
                                       f"{(r2.stdout or r2.stderr).strip()[:120]}")

    # 8h. The plan gate defaults to auto: a terminal, unapproved plan under plan_gate
    #     "auto" must not stop the run - the coordinator approves it mechanically
    #     (approved_by "auto"), records a gate_auto_approved event, and dispatches on in
    #     the same decision. Under a declared "confirm" it must escalate with exit 3 and
    #     write nothing. Guards the no-permission default and the opt-in gate both.
    if co.is_file() and goals:
        import subprocess
        import tempfile
        g = json.loads((root / "goals" / goals[0] / "goal.json").read_text())
        pre = []
        for s in g.get("pipeline", []):
            if s.get("per_task"):
                break
            pre.append(s["step"])
        if "plan" in pre:
            upto = pre[:pre.index("plan") + 1]
            ts = lambda m: f"2026-01-01T00:0{m}:00.000+00:00"

            def gate_fixture(tdp, gate):
                rd = tdp / "run"
                (rd / "steps").mkdir(parents=True)
                rows = [{"seq": i, "step": stepname, "task_id": None, "skill": "x",
                         "args": {}, "attempt_of": None, "round": None,
                         "state": "done_ok", "dispatched_at": ts(0), "recorded_at": ts(1),
                         "record": f"steps/{i:04d}-{stepname}.json", "conclusion": "ok",
                         "verdict": None, "produced": [], "consumed_paths": [],
                         "blockers": [], "error": None, "folded_at": ts(1), "notes": None}
                        for i, stepname in enumerate(upto, 1)]
                caps = g["caps"]
                run = {"schema": "advisory-report/run@1", "revision": 1, "run_id": "fx",
                       "goal": goals[0], "goal_version": "1", "created_at": ts(0),
                       "updated_at": ts(0), "updated_by": "fixture", "degraded": False,
                       "inputs": {"data_room": str(tdp / "room"), "output_root": str(tdp),
                                  "run_dir": str(rd), "sessions": []},
                       "control": {"halt": False, "halt_reason": None,
                                   "halt_requested_by": None,
                                   "critique_cap": caps["critique_cap"],
                                   "coordinator_budget": {
                                       "limit": caps["coordinator_budget"], "used": 0},
                                   "hook_budget": {"limit": caps["hook_budget"],
                                                   "used": 0},
                                   "reindex_limit": caps["reindex_limit"],
                                   "abort_authority_step": None,
                                   "plan_gate": gate},
                       "plan": {"recorded_by_seq": len(upto),
                                "approved_by_user": False, "analysis_window": None,
                                "wanted": [],
                                "tasks": [{"id": "t1", "wave": 1, "state": "runnable"}]},
                       "room": {"fingerprint": None, "scanned_at": None, "changes": []},
                       "deliverable": None, "dispatches": rows, "steps": {}, "next": {},
                       "termination": None}
                (rd / "run.json").write_text(json.dumps(run))
                return rd

            with tempfile.TemporaryDirectory() as td:
                rd = gate_fixture(pathlib.Path(td), "auto")
                r = subprocess.run([sys.executable, str(co), str(rd)],
                                   capture_output=True, text=True)
                after = {}
                if (rd / "run.json").is_file():
                    after = json.loads((rd / "run.json").read_text())
                ev_text = ""
                if (rd / "events.jsonl").is_file():
                    ev_text = (rd / "events.jsonl").read_text()
                if r.returncode != 0 or "NEXT: Skill" not in r.stdout \
                        or after.get("plan", {}).get("approved_by_user") is not True \
                        or after.get("plan", {}).get("approved_by") != "auto" \
                        or '"gate_auto_approved"' not in ev_text:
                    bad.append(f"{rel(co)}: a terminal unapproved plan under the default "
                               f"gate must auto-approve (approved_by auto, "
                               f"gate_auto_approved event) and dispatch on (exit "
                               f"{r.returncode}): "
                               f"{(r.stdout or r.stderr).strip()[:120]}")
            with tempfile.TemporaryDirectory() as td:
                rd = gate_fixture(pathlib.Path(td), "confirm")
                before = (rd / "run.json").read_text()
                r = subprocess.run([sys.executable, str(co), str(rd)],
                                   capture_output=True, text=True)
                if r.returncode != 3 or (rd / "run.json").read_text() != before:
                    bad.append(f"{rel(co)}: plan_gate confirm must escalate with exit 3 "
                               f"and write nothing (exit {r.returncode}): "
                               f"{(r.stdout or r.stderr).strip()[:120]}")

    # 8d. check_prose must refuse a drifted prose number and pass a bound one. The class it
    #     guards was found live: four critique rounds whose second through fourth existed to
    #     chase dollar amounts typed into sentences. Fixture: a ledger carrying 44.6 and
    #     6312400.55, prose stating $6.3M (bound, within rounding tolerance) and $7.1M
    #     (drifted). A gate that stops refusing the drifted line re-opens that loop.
    cp = root / "scripts" / "check_prose.py"
    if cp.is_file():
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = pathlib.Path(td)
            (rd / "workpapers").mkdir()
            (rd / "workpapers" / "figures-t.yaml").write_text(
                "- id: F.a\n  value: 44.6\n- id: F.b\n  value: 6312400.55\n")
            good = rd / "good.md"
            good.write_text("The metric is 44.6 days; $6.3M is unapplied.\n")
            drift = rd / "drift.md"
            drift.write_text("The metric is 44.6 days; $7.1M is unapplied.\n")
            for f, want in ((good, 0), (drift, 1)):
                r = subprocess.run([sys.executable, str(cp), str(f), "--run-dir", str(rd)],
                                   capture_output=True, text=True)
                if r.returncode != want:
                    bad.append(f"{rel(cp)}: {f.name} fixture exited {r.returncode}, want "
                               f"{want} - {(r.stdout or r.stderr).strip()[:80]}")

    # 8e. Shipped workpaper units must parse, and when the plugin ships a units
    #     self-test it must pass. The units are the computation the deliverable rests
    #     on; a syntax error or a broken formula in shipped code is otherwise invisible
    #     until a paid run executes it.
    for b in sorted(root.glob("goals/*/units/*.py")):
        try:
            compile(b.read_text(), str(b), "exec")
        except SyntaxError as exc:
            bad.append(f"{rel(b)}: syntax error at line {exc.lineno}")
    st = root / "scripts" / "units-selftest.py"
    if st.is_file():
        import subprocess
        r = subprocess.run([sys.executable, str(st)], capture_output=True, text=True)
        if r.returncode != 0:
            tail = " | ".join((r.stdout + r.stderr).strip().splitlines()[-3:])
            bad.append(f"{rel(st)}: units self-test failed (exit {r.returncode}): {tail}")

    # 8f. preview.py names each surfaceable artifact exactly once per content version:
    #     a fresh run dir must SHOW the plan, the room inventory, the rendered datasets
    #     workbook (only where the plugin ships unitlib and a catalog step - the other
    #     plugins get no catalog fixture) and a tab; an unchanged second call must print nothing (or the
    #     relay re-sends the same files at every decision); a changed source must be
    #     named again (or a fix round's rewritten tab never reaches the user's preview).
    #     countz-accounting tiers the send (its RUN_CONTRACT.md § Every wave): every
    #     SHOW line carries a fourth column, deliverable|working; the plan, the
    #     workbook and the report deck are deliverable (one rendered card each) and
    #     everything else - of the final documents, the deck's source report.yaml and the
    #     run summary - is working, bundled into one attach card per wave whose caption
    #     is the single BUNDLE: line, so a run of many checks costs the conversation one
    #     card per wave rather than one per file. Its roster follows the run's debug mode
    #     (run.json.inputs.debug): on, every kind prints; off, only the engagement
    #     preview, the plan, the workbook and the deck - the rest is still rendered into
    #     the run directory (the sync carries it) and left unrecorded, so turning debug
    #     on mid-run surfaces what was withheld. The fixture runs with debug on, then
    #     asserts the off roster.
    pv = root / "scripts" / "preview.py"
    if pv.is_file():
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = pathlib.Path(td) / "run"
            (rd / "out" / "tabs").mkdir(parents=True)
            (rd / "steps").mkdir()
            (rd / "run.json").write_text(json.dumps({"inputs": {"debug": True}}))
            (rd / "run-view.json").write_text(json.dumps(
                {"goal": goals[0] if goals else "g"}))
            (rd / "engagement-preview.md").write_text("# engagement\n")
            (rd / "plan.md").write_text("# plan\n")
            (rd / "file_index.json").write_text(json.dumps(
                {"totals": {"files": 1, "bytes": 9, "by_type": {"csv": 1}},
                 "files": [{"name": "a.csv", "folder": "", "ext": "csv",
                            "size_bytes": 9}]}))
            has_units = (root / "scripts" / "unitlib.py").is_file()
            if has_units:                 # only the canonical-data plugin builds a catalog
                (rd / "catalog").mkdir()
                (rd / "catalog" / "ds1.csv").write_text("a,b\n1,x\n")
                (rd / "catalog" / "index.json").write_text(json.dumps(
                    {"datasets": {"ds1": {"path": "catalog/ds1.csv", "status": "built",
                                          "row_count": 1, "dtypes": {"a": "number"}}}}))
            (rd / "out" / "tabs" / "t1.xlsx").write_bytes(b"tab bytes")
            (rd / "out" / "workbook.xlsx").write_bytes(b"workbook bytes")
            (rd / "out" / "report.pptx").write_bytes(b"deck bytes")
            (rd / "out" / "report.yaml").write_text("schema: countz-accounting/report@1\n")

            def run_pv():
                r = subprocess.run([sys.executable, str(pv), str(rd)],
                                   capture_output=True, text=True)
                return r, [l for l in r.stdout.splitlines() if l.startswith("SHOW:")]

            def bundles(r):
                return [l for l in r.stdout.splitlines() if l.startswith("BUNDLE:")]

            r1, shows = run_pv()
            named = "\n".join(shows)
            want = ["plan.md", "room-inventory.md", "t1.xlsx"] \
                + (["datasets.xlsx"] if has_units else [])
            missing = [w for w in want if w not in named]
            if r1.returncode != 0 or missing:
                bad.append(f"{rel(pv)}: first pass over a populated run dir must SHOW "
                           f"{', '.join(want)} "
                           f"(exit {r1.returncode}, missing {missing or 'nothing'}): "
                           f"{(r1.stdout or r1.stderr).strip()[:120]}")
            else:
                if root.name == "countz-accounting":
                    tiers = {}
                    for s in shows:
                        cols = s.split("\t")
                        if len(cols) != 4 or cols[3] not in ("deliverable", "working"):
                            bad.append(f"{rel(pv)}: every SHOW line carries path, "
                                       f"caption and a tier of deliverable|working: "
                                       f"{s[:100]}")
                            continue
                        tiers[pathlib.Path(cols[1]).name] = cols[3]
                    want_tier = {"plan.md": "deliverable", "workbook.xlsx": "deliverable",
                                 "report.pptx": "deliverable",
                                 "room-inventory.md": "working", "t1.xlsx": "working",
                                 "report.yaml": "working"}
                    wrong = [f"{n}={tiers.get(n)}" for n, tier in want_tier.items()
                             if tiers.get(n) != tier]
                    if wrong:
                        bad.append(f"{rel(pv)}: tier mismatch ({', '.join(wrong)}) - "
                                   f"only the plan, the findings, the workbook and the "
                                   f"report deck are deliverable; the deck's source is working")
                    b1 = bundles(r1)
                    if len(b1) != 1:
                        bad.append(f"{rel(pv)}: a pass that names working files must "
                                   f"print exactly one BUNDLE: line, got {len(b1)}")
                    elif "1 check schedule" not in b1[0] or "deck's source" not in b1[0] \
                            or "out/tabs/" not in b1[0]:
                        bad.append(f"{rel(pv)}: the BUNDLE caption must count each kind "
                                   f"it carries and name where it lives: {b1[0][:140]}")
                r2, shows2 = run_pv()
                if r2.returncode != 0 or shows2 or bundles(r2):
                    bad.append(f"{rel(pv)}: second pass with nothing changed must "
                               f"print no SHOW or BUNDLE line, got "
                               f"{len(shows2) + len(bundles(r2))}")
                if has_units:
                    with open(rd / "catalog" / "ds1.csv", "a") as fh:
                        fh.write("2,y\n")
                    r3, shows3 = run_pv()
                    if r3.returncode != 0 or len(shows3) != 1 \
                            or "datasets.xlsx" not in shows3[0]:
                        bad.append(f"{rel(pv)}: a changed dataset must re-SHOW exactly "
                                   f"the datasets workbook, got "
                                   f"{[s.split(chr(9))[1] for s in shows3] or 'nothing'}")
                if root.name == "countz-accounting":
                    def names(shows):
                        return sorted(pathlib.Path(s.split("\t")[1]).name for s in shows)
                    (rd / "run.json").write_text("{}")          # debug off
                    (rd / "out" / "preview" / ".shown.json").unlink()
                    (rd / "out" / "preview" / "room-inventory.md").unlink()
                    r4, shows4 = run_pv()
                    want4 = sorted(["engagement-preview.md", "plan.md", "workbook.xlsx",
                                    "report.pptx"])
                    if r4.returncode != 0 or names(shows4) != want4:
                        bad.append(f"{rel(pv)}: with debug off a fresh pass must SHOW "
                                   f"exactly {', '.join(want4)}, got "
                                   f"{', '.join(names(shows4)) or 'nothing'}")
                    if not (rd / "out" / "preview" / "room-inventory.md").is_file():
                        bad.append(f"{rel(pv)}: with debug off the withheld artifacts "
                                   f"are still rendered into out/preview/ (the sync "
                                   f"carries them); room-inventory.md was not")
                    (rd / "run.json").write_text(json.dumps({"inputs": {"debug": True}}))
                    r5, shows5 = run_pv()
                    got5 = names(shows5)
                    if r5.returncode != 0 or "room-inventory.md" not in got5 \
                            or "t1.xlsx" not in got5 or "plan.md" in got5:
                        bad.append(f"{rel(pv)}: turning debug on mid-run must SHOW the "
                                   f"working papers withheld so far and nothing already "
                                   f"shown, got {', '.join(got5) or 'nothing'}")

    # 8i. Playbook declarations are executed by an agent reading them, so a broken one
    #     fails at its next run, in front of the user. Where a plugin ships the validator
    #     (scripts/check_playbook.py), it must refuse an unknown check kind and a
    #     dependency cycle, accept a well-formed file, and every playbook the plugin
    #     ships must pass it.
    cw = root / "scripts" / "check_playbook.py"
    if cw.is_file():
        import subprocess
        import tempfile

        def run_cw(*paths):
            return subprocess.run([sys.executable, str(cw), *map(str, paths)],
                                  capture_output=True, text=True)

        def wf(name, steps):
            return {"schema": "countz-accounting/playbook@1", "name": name,
                    "title": "t", "sources": [{"slot": "a", "name": "A"},
                                              {"slot": "b", "name": "B"}],
                    "steps": steps}

        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            good = tdp / "good.json"
            good.write_text(json.dumps(wf("good", [
                {"id": "s1", "check": "tieout", "sources": ["a", "b"], "after": []}])))
            unknown = tdp / "unknown.json"
            unknown.write_text(json.dumps(wf("unknown", [
                {"id": "s1", "check": "no-such-kind", "sources": ["a", "b"],
                 "after": []}])))
            cyclic = tdp / "cyclic.json"
            cyclic.write_text(json.dumps(wf("cyclic", [
                {"id": "s1", "check": "tieout", "sources": ["a"], "after": ["s2"],
                 "params": {"ties_from": "s2"}},
                {"id": "s2", "check": "tieout", "sources": ["b"], "after": ["s1"],
                 "params": {"ties_from": "s1"}}])))
            # `after` is derived from the `_from` reads: an order no read justifies is
            # refused, and an extract step's cache reads resolve against its file list.
            unread = tdp / "unread.json"
            unread.write_text(json.dumps(wf("unread", [
                {"id": "s1", "check": "tieout", "sources": ["a"], "after": []},
                {"id": "s2", "check": "tieout", "sources": ["b"], "after": ["s1"]}])))
            files = [{"id": "gl_fy2026", "path": "gl.xlsx", "source": "a",
                      "file_role": "system_export", "sheet": "GL", "control": "amount",
                      "what": "the GL detail, header at row 5"},
                     {"id": "gl_summary", "path": "gl.xlsx", "source": "a",
                      "file_role": "system_export", "sheet": "GL",
                      "what": "the account summary, header at row 40"}]
            cached = tdp / "cached.json"
            cached.write_text(json.dumps(wf("cached", [
                {"id": "x0", "check": "extract", "sources": ["a"], "after": [],
                 "params": {"files": files}},
                {"id": "s1", "check": "tieout", "sources": ["a", "b"], "after": ["x0"],
                 "params": {"cache_from": "x0", "reads": ["gl_fy2026"]}}])))
            unparsed = tdp / "unparsed.json"
            unparsed.write_text(json.dumps(wf("unparsed", [
                {"id": "x0", "check": "extract", "sources": ["a"], "after": [],
                 "params": {"files": files}},
                {"id": "s1", "check": "tieout", "sources": ["a", "b"], "after": ["x0"],
                 "params": {"cache_from": "x0", "reads": ["tb_fy2026"]}}])))
            # Two tables on one sheet are two entries, each saying which table it is; a
            # read-spec key is the extract step's to measure, never the plan's.
            unnamed = tdp / "unnamed.json"
            unnamed.write_text(json.dumps(wf("unnamed", [
                {"id": "x0", "check": "extract", "sources": ["a"], "after": [],
                 "params": {"files": [dict(files[0]), {k: v for k, v in files[1].items()
                                                       if k != "what"}]}}])))
            respec = tdp / "respec.json"
            respec.write_text(json.dumps(wf("respec", [
                {"id": "x0", "check": "extract", "sources": ["a"], "after": [],
                 "params": {"files": [{**files[0], "header_row": 5}]}}])))
            # A saved extract step's prior script sits beside the playbook file.
            prior = tdp / "prior.json"
            prior.write_text(json.dumps(wf("prior", [
                {"id": "x0", "check": "extract", "sources": ["a", "b"], "after": [],
                 "params": {"files": files, "prior_script": "prior.extract/x0.py"}}])))
            (tdp / "prior.extract").mkdir()
            (tdp / "prior.extract" / "x0.py").write_text("# last period's script\n")
            noprior = tdp / "noprior.json"
            noprior.write_text(json.dumps(wf("noprior", [
                {"id": "x0", "check": "extract", "sources": ["a", "b"], "after": [],
                 "params": {"files": files, "prior_script": "noprior.extract/x0.py"}}])))
            for f, want, label in ((good, 0, "a well-formed playbook"),
                                   (prior, 0, "an extract step whose prior script is "
                                              "beside the playbook"),
                                   (noprior, 1, "a prior script that is not beside the "
                                                "playbook"),
                                   (unknown, 1, "an unknown check kind"),
                                   (cyclic, 1, "a dependency cycle"),
                                   (unread, 1, "an `after` no `_from` read justifies"),
                                   (cached, 0, "an extract step with a resolved cache read"),
                                   (unparsed, 1, "a cache read of an id the extract step "
                                                 "does not parse"),
                                   (unnamed, 1, "two tables on one sheet, one without "
                                                "`what`"),
                                   (respec, 1, "an extract file entry carrying a read "
                                               "spec (`header_row`)")):
                r = run_cw(f)
                if r.returncode != want:
                    bad.append(f"{rel(cw)}: {label} fixture exited {r.returncode}, want "
                               f"{want} - {(r.stdout or r.stderr).strip()[:80]}")
        for f in sorted(root.glob("playbooks/*.json")):
            r = run_cw(f)
            if r.returncode != 0:
                bad.append(f"{rel(f)}: shipped playbook fails its own validator - "
                           f"{(r.stdout or r.stderr).strip()[:120]}")

    # 8j. playbook_next.py decides the wave mechanically and escalates the rest; four
    #     fixture calls keep the decision chain and the escalate contract honest: a
    #     bound run must dispatch the dependency-free step with a self-contained brief
    #     and a decision event, a finished step must advance to its dependent, a failed
    #     dependency must skip the dependent and reach DONE, and an orphan step record
    #     must exit 3 without writing.
    pn = root / "scripts" / "playbook_next.py"
    if pn.is_file():
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            rd = tdp / "run"
            (rd / "steps").mkdir(parents=True)
            (rd / "steps" / "0001-setup.json").write_text(json.dumps(
                {"seq": 1, "step": "setup", "outcome": "complete", "error": None}))
            pb = tdp / "pb.json"
            pb.write_text(json.dumps(
                {"schema": "countz-accounting/playbook@1", "name": "pb", "title": "t",
                 "sources": [{"slot": "a", "name": "A"}, {"slot": "b", "name": "B"}],
                 "steps": [
                     {"id": "s1", "check": "tieout", "sources": ["a", "b"], "after": [],
                      "params": {"family": "c1"}},
                     {"id": "s2", "check": "recon", "sources": ["a", "b"],
                      "after": ["s1"], "params": {"items_from": "s1"}}]}))
            # s1 carries a recipe family and s2 none, so one run exercises both forms of
            # the SAY line: the family's title, and the bare id with its kind.
            recipe = tdp / "PB.md"
            recipe.write_text("---\nname: pb\nobjective: o\n---\n\n## The families\n\n"
                              "### C1 — the books agree internally (kind `tieout`, "
                              "per account)\n")
            run = {"schema": "countz-accounting/run@1", "run_id": "sess", "goal": "pb",
                   "sources": [{"id": "a", "name": "A", "path": "/x/a", "kind": "file",
                                "setup_seq": 1},
                               {"id": "b", "name": "B", "path": "/x/b", "kind": "file",
                                "setup_seq": 1}],
                   "checks": [], "playbook": {"name": "pb", "path": str(pb),
                                              "bound": {"a": "a", "b": "b"}},
                   "plan": {"record": None, "recipe": str(recipe), "playbook": str(pb),
                            "approved_at": "x"},
                   "dispatches": [{"seq": 1, "step": "setup", "skill": "check-setup",
                                   "args": {}, "state": "ok",
                                   "record": "steps/0001-setup.json"}],
                   "next_seq": 2}
            (rd / "run.json").write_text(json.dumps(run))

            def run_pn():
                return subprocess.run([sys.executable, str(pn), str(rd), str(pb)],
                                      capture_output=True, text=True)

            r = run_pn()
            brief = rd / "dispatch" / "0002-tie.md"
            if r.returncode != 0 or "NEXT: Skill check-tie" not in r.stdout \
                    or "check=s1" not in r.stdout or "THEN:" not in r.stdout:
                bad.append(f"{rel(pn)}: a bound run did not dispatch the dependency-free "
                           f"step (exit {r.returncode}): "
                           f"{(r.stdout or r.stderr).strip()[:100]}")
            elif not brief.is_file() or not all(
                    s in brief.read_text() for s in
                    (str((root / "agents" / "worker.md").resolve()),
                     str((root / "skills" / "check-tie" / "SKILL.md").resolve()),
                     "check=s1", "mode=fresh")):
                bad.append(f"{rel(pn)}: brief {brief.name} is not self-contained - a "
                           f"wave sub-agent starts from it alone")
            elif "decision" not in (rd / "events.jsonl").read_text():
                bad.append(f"{rel(pn)}: a wave decision appended no `decision` event")
            else:
                # Every wave opens with ONE SAY: line ahead of RECORD: - the progress line
                # the relay puts in chat - naming the wave, the count and, where the
                # step carries a recipe family, that family's title.
                out = r.stdout.splitlines()
                say = [l for l in out if l.startswith("SAY:")]
                rec_at = next((i for i, l in enumerate(out) if l.startswith("RECORD:")),
                              len(out))
                if len(say) != 1 or "Wave 1" not in say[0] \
                        or "running 1 check:" not in say[0] \
                        or "C1 the books agree internally" not in say[0] \
                        or out.index(say[0]) > rec_at:
                    bad.append(f"{rel(pn)}: a wave must open with one SAY: line before "
                               f"RECORD:, naming the wave, the count and the recipe "
                               f"family's title: {say or r.stdout.strip()[:120]}")
                run["dispatches"].append({"seq": 2, "step": "tie", "check_id": "s1",
                                          "skill": "check-tie", "args": {},
                                          "state": "ok",
                                          "record": "steps/0002-tie.json"})
                run["next_seq"] = 3
                (rd / "run.json").write_text(json.dumps(run))
                ok_rec = {"seq": 2, "step": "tie", "outcome": "complete", "error": None}
                (rd / "steps" / "0002-tie.json").write_text(json.dumps(ok_rec))
                r2 = run_pn()
                if r2.returncode != 0 or "check=s2" not in r2.stdout \
                        or "NEXT: Skill check-recon" not in r2.stdout:
                    bad.append(f"{rel(pn)}: a finished s1 did not advance to s2 "
                               f"(exit {r2.returncode}): "
                               f"{(r2.stdout or r2.stderr).strip()[:100]}")
                elif "SAY: Wave 2 — running 1 check: s2 (reconciliation)." \
                        not in r2.stdout:
                    bad.append(f"{rel(pn)}: a member with no recipe family must be "
                               f"named by id and kind in the SAY: line: "
                               f"{r2.stdout.strip()[:120]}")
                (rd / "steps" / "0002-tie.json").write_text(json.dumps(
                    {**ok_rec, "error": "died"}))
                r3 = run_pn()
                if r3.returncode != 0 or "DONE: s1 failed" not in r3.stdout \
                        or "DONE: s2 skipped" not in r3.stdout:
                    bad.append(f"{rel(pn)}: a failed dependency must skip its dependent "
                               f"and reach DONE (exit {r3.returncode}): "
                               f"{(r3.stdout or r3.stderr).strip()[:100]}")
                elif "SAY:" in r3.stdout:
                    bad.append(f"{rel(pn)}: DONE launches nothing, so it says nothing - "
                               f"no SAY: line")
                (rd / "steps" / "0002-tie.json").write_text(json.dumps(ok_rec))
                before_ev = (rd / "events.jsonl").read_text()
                before_br = sorted(p.name for p in (rd / "dispatch").iterdir())
                (rd / "steps" / "0099-tie.json").write_text("{}")
                r4 = run_pn()
                if r4.returncode != 3 or "ESCALATE:" not in r4.stdout:
                    bad.append(f"{rel(pn)}: an orphan step record must escalate with "
                               f"exit 3, got {r4.returncode}")
                elif (rd / "events.jsonl").read_text() != before_ev or \
                        sorted(p.name for p in (rd / "dispatch").iterdir()) != before_br:
                    bad.append(f"{rel(pn)}: an escalate wrote briefs or events - "
                               f"escalation must leave the run untouched for the agent")
        # The relay executes the printed vocabulary as its contract describes it, and
        # the engine agent renders the same lines on escalation: both must carry SAY:.
        for doc in (root / "reference" / "RUN_CONTRACT.md",
                    root / "skills" / "playbook-next" / "SKILL.md"):
            if doc.is_file() and "SAY:" not in doc.read_text():
                bad.append(f"{rel(doc)}: does not carry the SAY: line the scripts print "
                           f"- the relay would launch the wave and tell the user nothing")

    # 8k. sync_run must move the run WHOLE through both hops - run dir -> archive ->
    #     result root. The failure it guards was live (2026-08-30): a cloud run's relay
    #     hand-copied the report, summary and workbook into the result root and nothing
    #     else, so the landed copy could not be priced, triaged, or resumed. Fixture: a
    #     run dir with a nested check file and a __pycache__/; archive it, land the
    #     archive, assert the nested file and sync.json arrive whole and the excluded
    #     dir does not, then assert a second landing refuses with exit 2.
    sr = root / "scripts" / "sync_run.py"
    if sr.is_file():
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            rd = tdp / "run"
            (rd / "checks").mkdir(parents=True)
            (rd / "__pycache__").mkdir()
            (rd / "run.json").write_text(json.dumps(
                {"run_id": "fx", "goal": "fixture-goal",
                 "inputs": {"sessions": [{"session_id": "s1"}]}}))
            (rd / "checks" / "c1.md").write_text("evidence\n")
            (rd / "__pycache__" / "junk.pyc").write_text("x")
            r1 = subprocess.run([sys.executable, str(sr), str(rd)],
                                capture_output=True, text=True)
            arch = rd / "out" / "run_sync.tar.gz"
            if r1.returncode != 0 or not arch.is_file():
                bad.append(f"{rel(sr)}: archive mode failed (exit {r1.returncode}): "
                           f"{(r1.stdout or r1.stderr).strip()[:100]}")
            else:
                dest = tdp / "results"
                r2 = subprocess.run([sys.executable, str(sr), str(arch),
                                     "--dest", str(dest)],
                                    capture_output=True, text=True)
                landed = sorted(dest.glob("fixture-goal.*")) if dest.is_dir() else []
                if r2.returncode != 0 or not landed:
                    bad.append(f"{rel(sr)}: landing the archive failed (exit "
                               f"{r2.returncode}): "
                               f"{(r2.stdout or r2.stderr).strip()[:100]}")
                else:
                    top = landed[0]
                    missing = [p for p in ("checks/c1.md", "sync.json", "run.json")
                               if not (top / p).is_file()]
                    if missing:
                        bad.append(f"{rel(sr)}: the landed run is missing {missing} - "
                                   f"the run must land whole")
                    if (top / "__pycache__").exists():
                        bad.append(f"{rel(sr)}: __pycache__ traveled through the "
                                   f"archive - the exclusions are off")
                    r3 = subprocess.run([sys.executable, str(sr), str(arch),
                                         "--dest", str(dest)],
                                        capture_output=True, text=True)
                    if r3.returncode != 2:
                        bad.append(f"{rel(sr)}: landing onto an existing target must "
                                   f"refuse with exit 2, got {r3.returncode}")

    # 8l. peek.py is the bounded first look at a client file, and the bound must hold on
    #     the file that would hurt: a fixture workbook of 20,000 rows with a formula column
    #     and a header below row 1, a 3,000-line csv and a one-line multi-megabyte json go
    #     through it, and the peek must come back with the sheet's extent, the default
    #     handful of rows, a clipped line - and refuse a --rows above its ceiling. The
    #     prose that sends agents to it must name it, in every tier that reads a client
    #     file: a rule with no wiring is followed by nobody.
    pk = root / "scripts" / "peek.py"
    if pk.is_file():
        import importlib.util
        import subprocess
        import tempfile
        try:
            spec = importlib.util.spec_from_file_location("_peek_check", pk)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            # The ceilings are pinned HERE as well as in the tool: a self-test that reads
            # the ceiling from the module moves with it, and a lifted ceiling is the one
            # change that turns a bounded peek into a whole read.
            if mod.ROWS_MAX > 50 or mod.LINES_MAX > 200:
                bad.append(f"{rel(pk)}: ROWS_MAX {mod.ROWS_MAX} / LINES_MAX "
                           f"{mod.LINES_MAX} exceed the pinned 50 / 200 - the peek is "
                           f"no longer bounded; change both homes deliberately or not "
                           f"at all")
            with tempfile.TemporaryDirectory() as td:
                room = pathlib.Path(td) / "room"
                room.mkdir()
                nrows = 20000
                rows = ['<row r="1"><c r="A1" t="s"><v>0</v></c></row>',
                        '<row r="3"><c r="A3" t="s"><v>1</v></c><c r="B3" t="s"><v>2</v></c>'
                        '<c r="C3" t="s"><v>3</v></c></row>']
                rows += [f'<row r="{i}"><c r="A{i}"><v>{i}</v></c><c r="B{i}" t="s"><v>4'
                         f'</v></c><c r="C{i}"><f>A{i}*2</f><v>{i * 2}</v></c></row>'
                         for i in range(4, nrows + 3)]
                ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                rns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                pns = "http://schemas.openxmlformats.org/package/2006/relationships"
                with zipfile.ZipFile(room / "GL.xlsx", "w", zipfile.ZIP_DEFLATED) as z:
                    z.writestr("[Content_Types].xml",
                               '<Types xmlns="http://schemas.openxmlformats.org/package/'
                               '2006/content-types"><Default Extension="xml" ContentType='
                               '"application/xml"/></Types>')
                    z.writestr("_rels/.rels", f'<Relationships xmlns="{pns}"/>')
                    z.writestr("xl/workbook.xml",
                               f'<workbook xmlns="{ns}" xmlns:r="{rns}"><sheets><sheet '
                               f'name="Detail" sheetId="1" r:id="rId1"/></sheets></workbook>')
                    z.writestr("xl/_rels/workbook.xml.rels",
                               f'<Relationships xmlns="{pns}"><Relationship Id="rId1" '
                               f'Type="{rns}/worksheet" Target="worksheets/sheet1.xml"/>'
                               f'</Relationships>')
                    z.writestr("xl/sharedStrings.xml",
                               f'<sst xmlns="{ns}"><si><t>GL export</t></si><si><t>Date'
                               f'</t></si><si><t>Account</t></si><si><t>Amount</t></si>'
                               f'<si><t>1000 - Cash</t></si></sst>')
                    z.writestr("xl/worksheets/sheet1.xml",
                               f'<worksheet xmlns="{ns}"><dimension ref="A1:C{nrows + 2}"/>'
                               f'<sheetData>{"".join(rows)}</sheetData></worksheet>')
                (room / "bank.csv").write_text(
                    "Date,Amount\n" + "".join(f"2026-01-01,{i}.00\n" for i in range(3000)))
                (room / "export.json").write_text(
                    "[" + ",".join(f'{{"id":{i}}}' for i in range(200000)) + "]")
                r = subprocess.run([sys.executable, str(pk), "--json", str(room)],
                                   capture_output=True, text=True, timeout=60)
                got = {}
                for line in r.stdout.splitlines():
                    e = json.loads(line)
                    got[e["name"]] = e
                if r.returncode != 0 or set(got) != {"GL.xlsx", "bank.csv", "export.json"}:
                    bad.append(f"{rel(pk)}: --json over the fixture room returned "
                               f"{r.returncode} with {sorted(got)} (stderr: "
                               f"{r.stderr.strip()[:200]})")
                else:
                    sh = ((got["GL.xlsx"].get("peek") or {}).get("sheets") or [{}])[0]
                    if (sh.get("rows_extent"), len(sh.get("rows") or []),
                            sh.get("formula_columns"), [x["r"] for x in
                                                        (sh.get("rows") or [])][:2]) \
                            != (nrows + 2, mod.ROWS, ["C"], [1, 3]):
                        bad.append(f"{rel(pk)}: the {nrows}-row workbook peeked as extent "
                                   f"{sh.get('rows_extent')}, {len(sh.get('rows') or [])} "
                                   f"rows, formulas {sh.get('formula_columns')}, first "
                                   f"rows {[x['r'] for x in (sh.get('rows') or [])][:2]} "
                                   f"(want {nrows + 2} / {mod.ROWS} / ['C'] / [1, 3])")
                    cs = got["bank.csv"].get("peek") or {}
                    if (cs.get("lines_total"), len(cs.get("lines") or [])) != \
                            (3001, mod.LINES):
                        bad.append(f"{rel(pk)}: the 3,001-line csv peeked as "
                                   f"{cs.get('lines_total')} lines total, "
                                   f"{len(cs.get('lines') or [])} shown (want 3001 / "
                                   f"{mod.LINES})")
                    js = got["export.json"].get("peek") or {}
                    ln = (js.get("lines") or [""])[0]
                    if js.get("lines_total") != 1 or len(ln) > mod.CHARS:
                        bad.append(f"{rel(pk)}: the one-line json peeked as "
                                   f"{js.get('lines_total')} line(s), first line "
                                   f"{len(ln)} chars (want 1 / <= {mod.CHARS})")
                r2 = subprocess.run([sys.executable, str(pk), "--rows",
                                     str(mod.ROWS_MAX + 1), str(room / "bank.csv")],
                                    capture_output=True, text=True, timeout=60)
                if r2.returncode != 2:
                    bad.append(f"{rel(pk)}: --rows {mod.ROWS_MAX + 1} exited "
                               f"{r2.returncode}; a value above the ceiling must exit 2")
        except Exception as exc:
            bad.append(f"{rel(pk)}: bounded-peek self-test failed to run ({exc})")
        # Naming peek.py in the shared standing-rules file counts: every agent below
        # reads it first, so one hop still wires the bounded first look.
        shared = root / "reference/CONDUCT.md"
        hop = shared.is_file() and "scripts/peek.py" in shared.read_text()
        for wired in ("agents/worker.md", "agents/planner.md", "agents/critic.md",
                      "skills/check-plan/SKILL.md"):
            wf = root / wired
            if not wf.is_file():
                continue
            text = wf.read_text()
            if "scripts/peek.py" in text or (hop and "reference/CONDUCT.md" in text):
                continue
            bad.append(f"{rel(wf)}: reads client files and names neither scripts/peek.py "
                       f"nor reference/CONDUCT.md - the bounded first look is unwired here")

    # 8m. Recipes are executed by agents reading them, and every launcher is a shim naming
    #     one. The document's shape (countz-accounting/reference/RECIPE_FORMAT.md § The
    #     document) is ONE module, scripts/recipe_format.py — shared with the run-time
    #     gate scripts/validate_recipe.py a generated recipe passes — so the rules are
    #     stated once. This check runs that module over the corpus and adds the tree
    #     rules the module cannot know: exactly one inline shim asks for each recipe by
    #     its catalog name (`recipe="<name>"`), and no shared doc lists recipes. A README,
    #     reference doc, agent file or non-shim skill names at most one recipe and one
    #     shim, as its exemplar. A second is a list, and a list is a hand edit per recipe
    #     (root CLAUDE.md § Documentation discipline: no hand-maintained file lists).
    #     catalog.yaml is the one mechanical list and is exempt.
    recipes = sorted(root.glob("playbook-recipes/*.md"))
    rfmod = None
    if recipes:
        import importlib.util
        rf = root / "scripts" / "recipe_format.py"
        if not rf.is_file():
            bad.append(f"{rel(root / 'scripts')}: recipes exist but scripts/recipe_format.py does "
                       f"not - the recipe contract lives in one module")
        else:
            spec = importlib.util.spec_from_file_location("_recipe_format", rf)
            rfmod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rfmod)
    if recipes and rfmod is not None:
        kinds = rfmod.kinds_from(root / "scripts" / "check_playbook.py")
        names: dict[str, pathlib.Path] = {}
        for rf_ in recipes:
            text = rf_.read_text()
            for rule, msg in rfmod.validate(text, kinds):
                bad.append(f"{rel(rf_)}: {msg}")
            name = rfmod.frontmatter(text).get("name")
            if name in names:
                bad.append(f"{rel(rf_)}: `name: {name}` is already carried by {rel(names[name])}")
            elif name:
                names[name] = rf_
        shims: dict[str, list[str]] = {}
        for f in sorted(root.glob("skills/*/SKILL.md")):
            if frontmatter(f).get("context") != "inline":
                continue
            for name in set(re.findall(r'recipe="([a-z0-9-]+)"', f.read_text())):
                shims.setdefault(name, []).append(f.parent.name)
        for name, rf_ in sorted(names.items()):
            owners = [o for o in shims.get(name, []) if o != "countz-analysis"]
            if len(owners) != 1:
                bad.append(f"{rel(rf_)}: {len(owners)} inline skills ask for `{name}` "
                           f"({', '.join(owners) or 'none'}); a recipe has exactly one shim")
        for name, owners in sorted(shims.items()):
            if name not in names and name not in ("<name>", "<the entry's name>"):
                bad.append(f"skills/{owners[0]}/SKILL.md: asks for recipe `{name}`, which "
                           f"no recipe in playbook-recipes/ carries as its frontmatter name")
        shim_names = {s for n, owners in shims.items() if n in names for s in owners}
        readmes = [p for p in (root / "README.md", root.parent / "README.md") if p.is_file()]
        shared = readmes + sorted(root.glob("reference/*.md")) + sorted(root.glob("agents/*.md"))
        shared += [f for f in sorted(root.glob("skills/*/SKILL.md"))
                   if f.parent.name not in shim_names and f.parent.name != INDEX_SKILL]
        for f in shared:
            ft = f.read_text()
            named = [n for n in sorted(names) if f"`{n}`" in ft or f'recipe="{n}"' in ft]
            if len(named) > 1:
                bad.append(f"{rel(f)}: names {len(named)} recipes ({', '.join(named)}) - a "
                           f"shared doc names at most one, as its exemplar; the catalog "
                           f"is the list")
            named = [s for s in sorted(shim_names) if f"`{s}`" in ft]
            if len(named) > 1:
                bad.append(f"{rel(f)}: names {len(named)} launchers ({', '.join(named)}) - "
                           f"a shared doc names at most one, as its exemplar")
        for readme in readmes:
            if "playbook-recipes/" not in readme.read_text():
                bad.append(f"{rel(readme)}: does not point at playbook-recipes/ - the "
                           f"reader finds recipes by listing the directory")
        for f in sorted(root.glob("skills/*/SKILL.md")) + sorted(root.glob("agents/*.md")) \
                + sorted(root.glob("reference/*.md")):
            if "${CLAUDE_PLUGIN_ROOT}/playbook-recipes" in f.read_text():
                bad.append(f"{rel(f)}: reads a recipe from the plugin tree - recipes are "
                           f"served by the connector and pinned under <run_dir>/recipes/")

    # 8t. catalog.yaml is what the server serves and the agent matches on
    #     (docs/schemas/API_MCP_TOOLS.yaml::RecipeCatalog): every entry names a recipe by
    #     its frontmatter `name`, every recipe has an entry, a `skill` is the inline shim
    #     that asks for that recipe, aliases are non-empty and lower-case, and the
    #     matching fixture's expected names exist. A drift here is a served catalog that
    #     promises a recipe the server cannot return.
    cat = root / "playbook-recipes" / "catalog.yaml"
    if recipes and rfmod is not None:
        if not cat.is_file():
            bad.append(f"{rel(root / 'playbook-recipes')}: no catalog.yaml beside the recipes")
        else:
            try:
                import yaml
                doc = yaml.safe_load(cat.read_text()) or {}
            except Exception as exc:  # noqa: BLE001 — one message for any unparsable file
                doc, bad = None, bad + [f"{rel(cat)}: not YAML ({exc})"]
            if doc is not None:
                if doc.get("schema") != "countz-accounting/catalog@1":
                    bad.append(f"{rel(cat)}: schema must be countz-accounting/catalog@1")
                entries = doc.get("recipes") or []
                seen: set[str] = set()
                for e in entries:
                    n = str((e or {}).get("name") or "")
                    if not n:
                        bad.append(f"{rel(cat)}: an entry has no name")
                        continue
                    if n in seen:
                        bad.append(f"{rel(cat)}: `{n}` appears twice")
                    seen.add(n)
                    if n not in names:
                        bad.append(f"{rel(cat)}: `{n}` names no recipe (frontmatter `name`) in playbook-recipes/")
                    if not str(e.get("description") or "").strip():
                        bad.append(f"{rel(cat)}: `{n}` has no description - the agent matches on it")
                    al = e.get("aliases") or []
                    if not al:
                        bad.append(f"{rel(cat)}: `{n}` has no aliases - the server matches on them")
                    for a in al:
                        if str(a) != str(a).strip().lower():
                            bad.append(f"{rel(cat)}: `{n}` alias {a!r} is not lower-case and trimmed")
                    sk = e.get("skill")
                    if sk:
                        sf = root / "skills" / str(sk) / "SKILL.md"
                        if not sf.is_file() or frontmatter(sf).get("context") != "inline":
                            bad.append(f"{rel(cat)}: `{n}` names skill `{sk}`, not an inline skill")
                        elif f'recipe="{n}"' not in sf.read_text():
                            bad.append(f"{rel(cat)}: skill `{sk}` does not ask for recipe `{n}`")
                for n in sorted(set(names) - seen):
                    bad.append(f"{rel(cat)}: recipe `{n}` ({rel(names[n])}) has no catalog entry")
                fx = root.parent / "smoke" / "catalog_phrasings.yaml"
                if fx.is_file():
                    try:
                        ph = yaml.safe_load(fx.read_text()) or {}
                        for row in ph.get("phrasings") or []:
                            for acc in row.get("accept") or []:
                                if acc != "none" and acc not in seen:
                                    bad.append(f"{rel(fx)}: {row.get('id')} expects `{acc}`, "
                                               f"not a catalog name")
                    except Exception as exc:  # noqa: BLE001
                        bad.append(f"{rel(fx)}: not YAML ({exc})")

    # 8u. The corpus never ships: the Makefile's zip recipe excludes playbook-recipes/,
    #     the file count it checks against the Cowork limit excludes it too, and a
    #     packaged zip carries no recipe. gather_debug.py snapshots no recipe glob (the
    #     run carries its own pinned copy).
    if recipes:
        mk = root.parent / "Makefile"
        if mk.is_file():
            mt = mk.read_text()
            if "'*/playbook-recipes/*'" not in mt:
                bad.append(f"{rel(mk)}: the zip recipe does not exclude '*/playbook-recipes/*'")
        gd = root / "scripts" / "gather_debug.py"
        if gd.is_file() and "playbook-recipes" in gd.read_text().replace(
                "The recipe a run executed is not here", ""):
            bad.append(f"{rel(gd)}: still snapshots playbook-recipes/ - the run carries its recipe")
        for z in sorted((root.parent / "dist").glob(f"{root.name}-*.zip")):
            try:
                inside = [n for n in zipfile.ZipFile(z).namelist() if "/playbook-recipes/" in n]
            except zipfile.BadZipFile:
                continue
            if inside:
                bad.append(f"{rel(z)}: packages {len(inside)} recipe file(s) - the corpus is served, "
                           f"never shipped; rebuild with `make zip`")

    # 8v. The two run-time gates this plugin adds must refuse what they exist to refuse
    #     (root CLAUDE.md: every incident lands a rule AND a mechanical check). Each is
    #     driven over fixtures here so `make check` proves the gate before a run relies
    #     on it. (a) validate_recipe.py: a missing required section, a malformed family
    #     header, a headline naming no family and a `## Report` block that is not
    #     `{"schedules": [...]}` each fail, with the rule named.
    #     (b) run_state.py record-scrub, the record of the agent scrub (SCRUB.md): a
    #     flagged round with no flags, a last blind read that is not clean, and more rounds than the cap each refuse; a clean record prints SEND:
    #     with the exact bytes and appends `ask_scrubbed`. The scrub itself is an agent's
    #     judgment and is not checked here.
    vr = root / "scripts" / "validate_recipe.py"
    rs = root / "scripts" / "run_state.py"
    if vr.is_file() and recipes:
        import subprocess
        import tempfile

        def run(*args: str) -> tuple[int, str]:
            r = subprocess.run([sys.executable, *args], capture_output=True, text=True, timeout=60)
            return r.returncode, r.stdout + r.stderr

        good = recipes[0].read_text()
        cases = {
            "section.missing": good.replace("## Granularity", "## Grain"),
            "family.header": good.replace("### ", "### X ", 1),
            "headline.family": re.sub(r"^headline: .*$", "headline: z9", good, count=1, flags=re.M),
            "report.block": good.replace('"schedules"', '"schedule"', 1),
        }
        with tempfile.TemporaryDirectory() as td:
            rc, out = run(str(vr), str(recipes[0]))
            if rc != 0:
                bad.append(f"{rel(vr)}: refuses the live recipe {recipes[0].name}: {out.strip()[:200]}")
            for rule, text in cases.items():
                bp = pathlib.Path(td) / f"{rule}.md"
                bp.write_text(text)
                rc, out = run(str(vr), str(bp))
                if rc == 0 or rule not in out:
                    bad.append(f"{rel(vr)}: a recipe breaking `{rule}` must exit non-zero naming "
                               f"the rule (exit {rc}): {out.strip()[:160]}")
            if rs.is_file():
                rd = pathlib.Path(td) / "run"
                rd.mkdir()
                (rd / "run.json").write_text(json.dumps({
                    "schema": "countz-accounting/run@1", "inputs": {"company": "Acme Widgets"},
                    "sources": []}))
                send = "test fixed asset additions against the depreciation schedule for FY2025"
                ok_round = {"verdict": "clean", "removed": [{"category": "company_name",
                                                             "replacement": "the company"}]}
                flag = {"category": "figure", "where": "a threshold"}
                bad_recs = {
                    "flagged with no flags": {"send": send, "rounds": [
                        {"verdict": "flagged"}, ok_round]},
                    "last not clean": {"send": send, "rounds": [
                        ok_round, {"verdict": "flagged", "flags": [flag]}]},
                    "rounds": {"send": send, "rounds": [
                        {"verdict": "flagged", "flags": [flag]}] * 3 + [ok_round]},
                }
                for rule, rec in bad_recs.items():
                    rc, out = run(str(rs), "record-scrub", str(rd), "--json", json.dumps(rec))
                    if rc == 0:
                        bad.append(f"{rel(rs)}: record-scrub must refuse a record breaking "
                                   f"`{rule}` (exit 0): {out.strip()[:160]}")
                rc, out = run(str(rs), "record-scrub", str(rd), "--json",
                              json.dumps({"send": send, "rounds": [ok_round]}))
                ev = rd / "events.jsonl"
                if (rc != 0 or f"SEND:\t{send}" not in out or not ev.is_file()
                        or "ask_scrubbed" not in ev.read_text()):
                    bad.append(f"{rel(rs)}: a clean scrub record must print SEND: with the exact "
                               f"bytes and append ask_scrubbed (exit {rc}): {out.strip()[:160]}")

    # 8n. run_state.py and the ledger tools, on the four defects one live run produced
    #     (2026-09-03). (a) Every dispatch writes its brief: a --step and a fix wave of
    #     one wrote none, so dispatch/ lost the launch instruction it exists to preserve
    #     (0012, 0015, 0016 missing; a worker reconstructed 0015 from run.json). The
    #     wave-of-one NEXT line stays a plain Skill call. (b) A record claiming blocked
    #     with blockers is blocked even when error is set: the report step put its gate
    #     output in `error`, record read error first, and minted a ~$11 retry to reach
    #     the identical answer. (c) resolve_roots.py refuses a mapping-shaped ledger
    #     instead of iterating its keys (749 of 1,802 figures reached Sources with no
    #     root). (d) check_workbook.py --run-dir refuses, at the check's own gate, a
    #     ledger that is not a list and a declared id outside the grammar
    #     (`F.q6.ebit.LTM July 2023` cited as `F.q6.ebit.LTM`: 38 of 72 dead ends).
    rs = root / "scripts" / "run_state.py"
    rr = root / "scripts" / "resolve_roots.py"
    cwb = root / "scripts" / "check_workbook.py"
    if rs.is_file() and rr.is_file() and cwb.is_file():
        import subprocess
        import tempfile

        def xlsx(path: pathlib.Path, cells: dict[str, str] | None = None,
                 design: bool = True,
                 sheets: list[tuple[str, dict[str, str]]] | None = None) -> None:
            """A staged workbook of inline strings, no Sources tab: one tab `q6_bridge`
            holding `cells`, or the `sheets` given as (name, cells) in tab order. With
            `design`, every tab is built to reference/WORKBOOK.md + WORKBOOK_STYLE.md as
            stored: Arial styles, B1 title, B2 subtitle, B3 the summary, the BAND header on
            row 4, freeze panes at B4, gridlines off, the deliverable tab colour - and the
            cells land on rows 5+. Without it, the bare tab an unstyled writer produces."""
            ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
            rns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
            sheets = sheets or [("q6_bridge", cells or {})]

            def c(ref, v, s=0):
                return f'<c r="{ref}" s="{s}" t="inlineStr"><is><t>{v}</t></is></c>'

            def sheet_xml(name: str, body: dict[str, str]) -> str:
                if design:
                    # Every tab's band is rows 1-3, frozen at B4 - the row-4 table header
                    # is never frozen (WORKBOOK_STYLE.md § 4, WORKBOOK.md § 6).
                    split = 3
                    rows = [f'<row r="1">{c("B1", "q6 · the bridge foots", 1)}</row>',
                            f'<row r="2">{c("B2", "Acme Corp · FY2023 · accrual · USD whole dollars", 3)}</row>',
                            f'<row r="3">{c("B3", "Every rung of the bridge foots to the ledger.", 0)}</row>',
                            f'<row r="4">{c("B4", "id", 2)}{c("C4", "line", 2)}</row>']
                    rows += [f'<row r="{i}">{c(ref, v)}</row>'
                             for i, (ref, v) in enumerate(body.items(), 5)]
                    pre = ('<sheetPr><tabColor rgb="FF0F756D"/></sheetPr><sheetViews><sheetView '
                           f'workbookViewId="0" showGridLines="0"><pane xSplit="1" ySplit="{split}" '
                           f'topLeftCell="B{split + 1}" activePane="bottomRight" state="frozen"/></sheetView>'
                           '</sheetViews>')
                else:
                    rows = [f'<row r="{i}"><c r="{ref}" s="0" t="inlineStr"><is><t>{v}</t></is></c></row>'
                            for i, (ref, v) in enumerate(body.items(), 1)]
                    pre = ""
                return (f'<?xml version="1.0"?><worksheet xmlns="{ns}">{pre}<sheetData>'
                        f'{"".join(rows)}</sheetData></worksheet>')

            styles = (f'<?xml version="1.0"?><styleSheet xmlns="{ns}"><numFmts count="1">'
                      '<numFmt numFmtId="164" formatCode="#,##0;(#,##0);&quot;–&quot;"/></numFmts>'
                      '<fonts count="4"><font><sz val="10"/><color rgb="FF1C2A2A"/><name val="Arial"/></font>'
                      '<font><b/><sz val="14"/><color rgb="FF1C2A2A"/><name val="Arial"/></font>'
                      '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>'
                      '<font><sz val="10"/><color rgb="FF566665"/><name val="Arial"/></font></fonts>'
                      '<fills count="3"><fill><patternFill patternType="none"/></fill>'
                      '<fill><patternFill patternType="gray125"/></fill>'
                      '<fill><patternFill patternType="solid"><fgColor rgb="FF005C53"/></patternFill></fill></fills>'
                      '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
                      '<border><left style="thin"><color rgb="FFD3DAD8"/></left><right style="thin">'
                      '<color rgb="FFD3DAD8"/></right><top style="thin"><color rgb="FFD3DAD8"/></top>'
                      '<bottom style="thin"><color rgb="FFD3DAD8"/></bottom><diagonal/></border></borders>'
                      '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                      '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                      '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/>'
                      '<xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>'
                      '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0"/>'
                      '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
                      '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/>'
                      '</cellStyles></styleSheet>')
            n = len(sheets)
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("[Content_Types].xml",
                           '<?xml version="1.0"?><Types xmlns="http://schemas.openxml'
                           'formats.org/package/2006/content-types"><Default Extension'
                           '="rels" ContentType="application/vnd.openxmlformats-package'
                           '.relationships+xml"/><Default Extension="xml" ContentType='
                           '"application/xml"/><Override PartName="/xl/workbook.xml" '
                           'ContentType="application/vnd.openxmlformats-officedocument'
                           '.spreadsheetml.sheet.main+xml"/>'
                           + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                                     f'ContentType="application/vnd.openxmlformats-officedocument'
                                     f'.spreadsheetml.worksheet+xml"/>' for i in range(1, n + 1))
                           + '<Override PartName="/xl/styles.xml" ContentType="application/'
                           'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
                z.writestr("_rels/.rels",
                           f'<?xml version="1.0"?><Relationships xmlns="http://schemas.'
                           f'openxmlformats.org/package/2006/relationships"><Relationship '
                           f'Id="rId1" Type="{rns}/officeDocument" Target="xl/workbook.xml"'
                           f'/></Relationships>')
                z.writestr("xl/workbook.xml",
                           f'<?xml version="1.0"?><workbook xmlns="{ns}" xmlns:r="{rns}"><sheets>'
                           + "".join(f'<sheet name="{name}" sheetId="{i}" r:id="rId{i}"/>'
                                     for i, (name, _) in enumerate(sheets, 1))
                           + '</sheets></workbook>')
                z.writestr("xl/_rels/workbook.xml.rels",
                           f'<?xml version="1.0"?><Relationships xmlns="http://schemas.'
                           f'openxmlformats.org/package/2006/relationships">'
                           + "".join(f'<Relationship Id="rId{i}" Type="{rns}/worksheet" '
                                     f'Target="worksheets/sheet{i}.xml"/>' for i in range(1, n + 1))
                           + f'<Relationship Id="rId{n + 1}" Type="{rns}/styles" Target="styles.xml"'
                           f'/></Relationships>')
                z.writestr("xl/styles.xml", styles)
                for i, (name, body) in enumerate(sheets, 1):
                    z.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml(name, body))

        def rstate(rd, *args):
            return subprocess.run([sys.executable, str(rs), *args[:1], str(rd), *args[1:]],
                                  capture_output=True, text=True)

        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            rd = tdp / "run"
            (rd / "steps").mkdir(parents=True)
            (rd / "run.json").write_text(json.dumps(
                {"schema": "countz-accounting/run@1", "run_id": "s", "goal": "checks",
                 "created_at": "x", "updated_at": "x", "degraded": False,
                 "inputs": {"output_root": str(tdp), "run_dir": str(rd), "debug": False,
                            "params": {}, "sessions": []},
                 "sources": [{"id": "gl", "name": "GL", "path": "/x/gl", "kind": "file"},
                             {"id": "tb", "name": "TB", "path": "/x/tb", "kind": "file"}],
                 "checks": [], "playbook": None, "plan": None, "dispatches": [],
                 "next_seq": 2}))
            r = rstate(rd, "add-checks", "--checks",
                       '[{"id":"tie_gl_tb","kind":"tieout","sources":["gl","tb"]}]')
            r1 = rstate(rd, "dispatch", "--step", "report", "--args", '{"title":"T"}')
            r2 = rstate(rd, "dispatch", "--checks", "tie_gl_tb", "--mode", "fix",
                        "--extra", '{"findings_from":"steps/0001-review.json"}')
            b_rep, b_tie = rd / "dispatch" / "0002-report.md", rd / "dispatch" / "0003-tie.md"
            if r.returncode or r1.returncode or r2.returncode:
                bad.append(f"{rel(rs)}: fixture dispatches failed - "
                           f"{(r.stderr + r1.stderr + r2.stderr).strip()[:120]}")
            else:
                for b, need in ((b_rep, [str((root / "agents" / "worker.md").resolve()),
                                         str((root / "skills" / "check-report" /
                                              "SKILL.md").resolve()),
                                         "seq=2", "title=T"]),
                                (b_tie, [str((root / "agents" / "worker.md").resolve()),
                                         "check=tie_gl_tb", "sources=gl,tb", "mode=fix",
                                         "findings_from=steps/0001-review.json"])):
                    if not b.is_file():
                        bad.append(f"{rel(rs)}: {b.parent.name}/{b.name} not written - "
                                   f"every dispatch writes its brief, a --step and a "
                                   f"wave of one included")
                    else:
                        missing = [w for w in need if w not in b.read_text()]
                        if missing:
                            bad.append(f"{rel(rs)}: brief {b.name} is not self-contained "
                                       f"- missing {missing}")
                for out in (r1.stdout, r2.stdout):
                    if "brief=" in out or "LAUNCH:" in out:
                        bad.append(f"{rel(rs)}: a wave of one must print a plain Skill "
                                   f"line - no LAUNCH, no brief=: {out.strip()[:100]}")
                # Every dispatch opens with its SAY: progress line: a step names what it
                # does, a check wave names its checks by id and kind (no recipe here).
                if "SAY: Assembling the workbook and the report deck" not in r1.stdout \
                        or "SAY: Re-running 1 check on the review's findings: " \
                           "tie_gl_tb (tie-out)." not in r2.stdout:
                    bad.append(f"{rel(rs)}: a dispatch must print its SAY: line - the "
                               f"report step naming the deliverables, a fix wave naming "
                               f"its checks: {(r1.stdout + r2.stdout).strip()[:160]}")
                rows = json.loads((rd / "run.json").read_text())["dispatches"]
                if [d.get("brief") for d in rows] != ["dispatch/0002-report.md",
                                                       "dispatch/0003-tie.md"]:
                    bad.append(f"{rel(rs)}: dispatch rows do not carry their brief path")
                # (b) a plan dispatch's brief names the planner, per the skill's agent:
                r3 = rstate(rd, "dispatch", "--step", "plan", "--args",
                            '{"recipe":"/r/QOE.md","name":"qoe","objective":"o"}')
                b_plan = rd / "dispatch" / "0004-plan.md"
                if r3.returncode or not b_plan.is_file() or \
                        str((root / "agents" / "planner.md").resolve()) \
                        not in b_plan.read_text():
                    bad.append(f"{rel(rs)}: the plan brief must name agents/planner.md - "
                               f"the agent the skill's frontmatter declares")
                elif "SAY: Drafting the check plan from the data room." not in r3.stdout:
                    bad.append(f"{rel(rs)}: the plan dispatch must print its SAY: line: "
                               f"{r3.stdout.strip()[:120]}")
                # (b) blocked + blockers + error -> BLOCKED, no retry; error alone ->
                # FAILED with one RETRY that carries its own brief.
                (rd / "steps" / "0002-report.json").write_text(json.dumps(
                    {"seq": 2, "step": "report", "outcome": "blocked",
                     "error": "check_workbook.py: 38 link failures",
                     "conclusion": "gate held", "blockers": [{"what": "x", "effect": "y"}]}))
                (rd / "steps" / "0003-tie.json").write_text(json.dumps(
                    {"seq": 3, "step": "tie", "outcome": "complete", "error": "boom",
                     "conclusion": "c"}))
                (rd / "steps" / "0004-plan.json").write_text(json.dumps(
                    {"seq": 4, "step": "plan", "outcome": "complete", "error": None,
                     "conclusion": "drafted"}))
                r4 = rstate(rd, "record")
                run = json.loads((rd / "run.json").read_text())
                states = {d["seq"]: d["state"] for d in run["dispatches"]}
                retry_rows = [d for d in run["dispatches"] if d.get("attempt_of")]
                if r4.returncode or states.get(2) != "blocked" or \
                        "BLOCKED: seq=2" not in r4.stdout or \
                        any(d["attempt_of"] == 2 for d in retry_rows):
                    bad.append(f"{rel(rs)}: a record claiming blocked with blockers must "
                               f"classify BLOCKED with no retry even when error is set "
                               f"(exit {r4.returncode}): {(r4.stdout or r4.stderr).strip()[:120]}")
                if states.get(3) != "failed" or len(retry_rows) != 1 or \
                        retry_rows[0]["attempt_of"] != 3 or \
                        not (rd / retry_rows[0]["brief"]).is_file() or \
                        "RETRY: Skill check-tie" not in r4.stdout or "brief=" in r4.stdout:
                    bad.append(f"{rel(rs)}: an error-only record must FAIL, mint one "
                               f"retry with its own brief, and print it as a plain Skill "
                               f"RETRY line: {(r4.stdout or r4.stderr).strip()[:120]}")
                elif "SAY: Retrying 1 check that failed: tie_gl_tb (tie-out)." \
                        not in r4.stdout:
                    bad.append(f"{rel(rs)}: a minted retry wave must open with its SAY: "
                               f"line: {r4.stdout.strip()[:120]}")
                if not run["degraded"]:
                    bad.append(f"{rel(rs)}: a blocked step must set degraded")

            # (c) + (d): the ledgers. One list-shaped figures ledger with a spaced id,
            # one mapping-shaped ledger, one clean evidence ledger.
            wp = rd / "workpapers"
            wp.mkdir()
            (wp / "evidence-q4.yaml").write_text(
                "- id: E.q4.pl\n  kind: cell\n  file: pl.xlsx\n")
            (wp / "figures-q1.yaml").write_text(
                "- id: F.q1.rev.fy2023\n  value: 5\n  expression: as stated at E.q4.pl "
                "(passthrough)\n  inputs:\n    - {role: pl, source_type: room_file, "
                "citation_id: E.q4.pl}\n")
            (wp / "figures-q6.yaml").write_text(
                "figures:\n  - id: F.q6.ebit.fy2023\n    value: 10\n    inputs:\n"
                "      - {role: pl, source_type: room_file, citation_id: E.q4.pl}\n")
            # GATE 5: the map. A run whose recipe declares `lead: [q6, q5]` wants
            # Exec Summary · q6 · q5 · Basis of Preparation · q1 · Coverage - Basis of
            # Preparation second is refused with the wanted strip named, the wanted strip
            # passes, and without a run to ask Exec Summary not first is refused on the
            # shape alone.
            rd2 = tdp / "run2"
            (rd2 / "workpapers").mkdir(parents=True)
            recipe = tdp / "QOE.md"
            recipe.write_text("---\nname: quality-of-earnings\nobjective: o\nheadline: q6\n"
                              "lead: [q6, q5]\n---\n# r\n")
            (rd2 / "run.json").write_text(json.dumps(
                {"schema": "countz-accounting/run@1", "run_id": "s2",
                 "goal": "quality-of-earnings",
                 "checks": [{"id": "q1_fy2023", "kind": "tieout", "params": {"family": "q1"}},
                            {"id": "q5_addbacks", "kind": "analysis", "params": {"family": "q5"}},
                            {"id": "q6_bridge", "kind": "analysis", "params": {"family": "q6"}}],
                 "plan": {"record": "steps/0001-plan.json", "recipe": str(recipe),
                          "playbook": "plan/qoe.json", "approved_at": "x"}}))
            body = {"B5": "x"}
            wrong = tdp / "map_wrong.xlsx"
            xlsx(wrong, sheets=[("Exec Summary", body), ("Basis of Preparation", body),
                                ("q1 FY2023 statements", body), ("q5 Addback walk", body),
                                ("q6 EBITDA bridge", body), ("Coverage", body)])
            r11 = subprocess.run([sys.executable, str(cwb), str(wrong), "--run-dir", str(rd2)],
                                 capture_output=True, text=True)
            want = ("Exec Summary · q6 EBITDA bridge · q5 Addback walk · Basis of Preparation · "
                    "q1 FY2023 statements · Coverage")
            if r11.returncode != 1 or "map failure" not in r11.stdout or want not in r11.stdout:
                bad.append(f"{rel(cwb)}: Basis of Preparation ahead of the lead tabs must be refused by GATE 5 "
                           f"with the wanted strip named (exit {r11.returncode}): "
                           f"{(r11.stdout or r11.stderr).strip()[:200]}")
            right = tdp / "map_right.xlsx"
            xlsx(right, sheets=[("Exec Summary", body), ("q6 EBITDA bridge", body),
                                ("q5 Addback walk", body), ("Basis of Preparation", body),
                                ("q1 FY2023 statements", body), ("Coverage", body)])
            r12 = subprocess.run([sys.executable, str(cwb), str(right), "--run-dir", str(rd2)],
                                 capture_output=True, text=True)
            if r12.returncode != 0:
                bad.append(f"{rel(cwb)}: the reader's order must pass GATE 5 (exit "
                           f"{r12.returncode}): {(r12.stdout or r12.stderr).strip()[:200]}")
            shape = tdp / "map_shape.xlsx"
            xlsx(shape, sheets=[("Basis of Preparation", body), ("Exec Summary", body), ("q6 EBITDA bridge", body)])
            r13 = subprocess.run([sys.executable, str(cwb), str(shape)],
                                 capture_output=True, text=True)
            if r13.returncode != 1 or "is the first tab" not in r13.stdout:
                bad.append(f"{rel(cwb)}: Exec Summary not first must be refused on the shape alone "
                           f"(exit {r13.returncode}): {(r13.stdout or r13.stderr).strip()[:200]}")
            (wp / "figures-q5.yaml").write_text(
                "- id: \"F.q5.sbc.LTM July 2023\"\n  value: 1\n  inputs:\n"
                "    - {role: pl, source_type: room_file, citation_id: E.q4.pl}\n")
            r5 = subprocess.run(["uv", "run", "--with", "pyyaml", "python3", str(rr),
                                 str(rd)], capture_output=True, text=True)
            if r5.returncode != 2 or "figures-q6.yaml" not in r5.stderr or \
                    "figures-q5.yaml" not in r5.stderr or r5.stdout.strip():
                bad.append(f"{rel(rr)}: a mapping-shaped ledger and a spaced id must be "
                           f"refused with exit 2, both named on stderr, nothing on stdout "
                           f"(exit {r5.returncode}): {(r5.stderr or r5.stdout).strip()[:160]}")
            (wp / "figures-q6.yaml").write_text(
                "- id: F.q6.ebit.fy2023\n  value: 10\n  inputs:\n"
                "    - {role: pl, source_type: room_file, citation_id: E.q4.pl}\n")
            (wp / "figures-q5.yaml").write_text(
                "- id: F.q5.sbc.ltm_2023-07\n  value: 1\n  inputs:\n"
                "    - {role: pl, source_type: room_file, citation_id: E.q4.pl}\n")
            r6 = subprocess.run(["uv", "run", "--with", "pyyaml", "python3", str(rr),
                                 str(rd)], capture_output=True, text=True)
            try:
                out6 = json.loads(r6.stdout)
            except ValueError:
                out6 = {}
            if r6.returncode != 0 or set(out6.get("figures", {})) != \
                    {"F.q1.rev.fy2023", "F.q6.ebit.fy2023", "F.q5.sbc.ltm_2023-07"} or \
                    out6.get("ledgers", {}).get("figures-q6.yaml") != 1:
                bad.append(f"{rel(rr)}: clean list ledgers must resolve every figure and "
                           f"report per-ledger counts (exit {r6.returncode}): "
                           f"{(r6.stderr or r6.stdout).strip()[:120]}")
            # (d) the check-time gate, on a staged tab citing the ids as written.
            tab = tdp / "q6.xlsx"
            xlsx(tab, {"B5": "F.q6.ebit.fy2023", "B6": "E.q4.pl"})
            r7 = subprocess.run([sys.executable, str(cwb), str(tab), "--run-dir", str(rd)],
                                capture_output=True, text=True)
            if r7.returncode != 0:
                bad.append(f"{rel(cwb)}: a staged tab over clean ledgers, built to the "
                           f"design, must pass (exit {r7.returncode}): "
                           f"{(r7.stdout or r7.stderr).strip()[:120]}")
            # GATE 4: the same ids on a bare, unstyled tab — column A, default font, no
            # band, nothing frozen — are refused as a design failure, named by rule.
            bare = tdp / "q6_bare.xlsx"
            xlsx(bare, {"A1": "F.q6.ebit.fy2023", "A2": "E.q4.pl", "A4": "unruled header"}, design=False)
            r7b = subprocess.run([sys.executable, str(cwb), str(bare), "--run-dir", str(rd)],
                                 capture_output=True, text=True)
            if r7b.returncode != 1 or "design failure" not in r7b.stdout or \
                    "column A is the empty margin" not in r7b.stdout or \
                    "BAND header row" not in r7b.stdout or \
                    "no border" not in r7b.stdout:
                bad.append(f"{rel(cwb)}: an unstyled tab must be refused by GATE 4 with the "
                           f"failed rules named (exit {r7b.returncode}): "
                           f"{(r7b.stdout or r7b.stderr).strip()[:160]}")
            # GATE 4: a long cell cut mid-sentence to fit the cap is refused; the same
            # text ending in a full stop passes.
            body = "a real recurring cost settled other than in cash and borderline by nature " * 4
            cut = tdp / "q6_cut.xlsx"
            xlsx(cut, {"B5": body[:236]})
            r7c = subprocess.run([sys.executable, str(cwb), str(cut), "--run-dir", str(rd)],
                                 capture_output=True, text=True)
            whole = tdp / "q6_whole.xlsx"
            xlsx(whole, {"B5": body[:224].strip() + "."})
            r7d = subprocess.run([sys.executable, str(cwb), str(whole), "--run-dir", str(rd)],
                                 capture_output=True, text=True)
            # GATE 4: the same whole text with a neighbour to its right, in an unwrapped
            # default-width column, is prose that cannot overflow — refused.
            narrow = tdp / "q6_narrow.xlsx"
            xlsx(narrow, {"B5": body[:224].strip() + ".", "C5": "x"})
            r7e = subprocess.run([sys.executable, str(cwb), str(narrow), "--run-dir", str(rd)],
                                 capture_output=True, text=True)
            if r7e.returncode != 1 or "narrow or unwrapped" not in r7e.stdout:
                bad.append(f"{rel(cwb)}: prose in an unwrapped column with a neighbour must be "
                           f"refused by GATE 4 (exit {r7e.returncode}): "
                           f"{(r7e.stdout or r7e.stderr).strip()[:160]}")
            if r7c.returncode != 1 or "cut mid-sentence" not in r7c.stdout or r7d.returncode != 0:
                bad.append(f"{rel(cwb)}: a long cell cut mid-sentence must be refused by GATE 4 "
                           f"and the same text with its full stop must pass (exit "
                           f"{r7c.returncode}/{r7d.returncode}): "
                           f"{(r7c.stdout or r7c.stderr).strip()[:160]}")
            (wp / "figures-q5.yaml").write_text(
                "- id: F.q5.sbc.LTM July 2023\n  value: 1\n")
            (wp / "figures-q6.yaml").write_text(
                "figures:\n  - id: F.q6.ebit.fy2023\n    value: 10\n")
            r8 = subprocess.run([sys.executable, str(cwb), str(tab), "--run-dir", str(rd)],
                                capture_output=True, text=True)
            if r8.returncode != 1 or "LTM July 2023" not in r8.stdout or \
                    "figures-q6.yaml: top level is a mapping" not in r8.stdout:
                bad.append(f"{rel(cwb)}: --run-dir must refuse a spaced ledger id and a "
                           f"mapping-shaped ledger at the check's own gate (exit "
                           f"{r8.returncode}): {(r8.stdout or r8.stderr).strip()[:160]}")
            # The ledgers alone, no workbook - the plan step's gate, which writes
            # evidence ledgers and no tab.
            r9 = subprocess.run([sys.executable, str(cwb), "--run-dir", str(rd)],
                                capture_output=True, text=True)
            if r9.returncode != 1 or "LTM July 2023" not in r9.stdout:
                bad.append(f"{rel(cwb)}: --run-dir alone must gate the ledgers and refuse "
                           f"the spaced id (exit {r9.returncode}): "
                           f"{(r9.stdout or r9.stderr).strip()[:120]}")
            (wp / "figures-q5.yaml").write_text("- id: F.q5.sbc.ltm_2023-07\n  value: 1\n")
            (wp / "figures-q6.yaml").write_text("- id: F.q6.ebit.fy2023\n  value: 10\n")
            r10 = subprocess.run([sys.executable, str(cwb), "--run-dir", str(rd)],
                                 capture_output=True, text=True)
            if r10.returncode != 0:
                bad.append(f"{rel(cwb)}: --run-dir alone over clean ledgers must pass "
                           f"(exit {r10.returncode}): {(r10.stdout or r10.stderr).strip()[:120]}")
            for skill in ("check-plan",):
                txt = (root / "skills" / skill / "SKILL.md").read_text()
                if "check_workbook.py --run-dir" not in txt:
                    bad.append(f"skills/{skill}/SKILL.md: writes ledgers and no tab, so "
                               f"it must run `check_workbook.py --run-dir <run_dir>` "
                               f"before its record - or its ledger defects surface at "
                               f"the next check's gate, blamed on that check")

    # 8o. setup_run.py mints the run directory - `<skill>-<company>.<YYYYMMDD-HHMMSS>`
    #     under the output root - and nothing else creates one: a relay-composed path
    #     without run.json is refused, and so is a --skill that names a goal rather than
    #     one of the plugin's launchers. Four fixture calls hold the contract: a mint lands
    #     at the minted name and prints it as RUN_DIR:, a fold by that path joins a second
    #     session, an unminted path is refused, a foreign --skill is refused.
    su = root / "scripts" / "setup_run.py"
    if su.is_file():
        import subprocess
        import tempfile
        launchers = sorted(frontmatter(f)["name"] for f in root.glob("skills/*/SKILL.md")
                           if frontmatter(f).get("context") == "inline"
                           and frontmatter(f).get("name"))
        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            src = tdp / "gl.csv"
            src.write_text("a,b\n")
            srcs = json.dumps([{"id": "gl", "path": str(src), "name": "GL"}])
            results = tdp / "results"

            def run_su(*args):
                return subprocess.run([sys.executable, str(su), *args],
                                      capture_output=True, text=True)

            if not launchers:
                bad.append(f"{rel(su)}: no inline skill to mint a run for")
            else:
                r = run_su("--output-root", str(results), "--skill", launchers[0],
                           "--company", "Demo ZS Co.", "--goal", "checks",
                           "--session", "s1", "--sources", srcs)
                first = (r.stdout.splitlines() or [""])[0]
                m = re.fullmatch(r"RUN_DIR:\t(.+)", first)
                minted = pathlib.Path(m.group(1)) if m else None
                shape = re.compile(rf"{re.escape(launchers[0])}-demo-zs-co\.\d{{8}}-\d{{6}}")
                if r.returncode != 0 or minted is None or not shape.fullmatch(minted.name) \
                        or minted.parent != results.resolve() \
                        or not (minted / "run.json").is_file():
                    bad.append(f"{rel(su)}: a mint did not land at <output_root>/"
                               f"{launchers[0]}-demo-zs-co.<stamp> with its run.json and "
                               f"print it as RUN_DIR: (exit {r.returncode}): "
                               f"{(r.stdout or r.stderr).strip()[:120]}")
                else:
                    state = json.loads((minted / "run.json").read_text())
                    inputs = state.get("inputs", {})
                    if state.get("run_id") != minted.name \
                            or inputs.get("skill") != launchers[0] \
                            or inputs.get("company") != "Demo ZS Co." \
                            or [s.get("session_id") for s in inputs.get("sessions", [])] \
                            != ["s1"]:
                        bad.append(f"{rel(su)}: run.json does not carry run_id = the "
                                   f"directory name, inputs.skill, inputs.company and the "
                                   f"minting session")
                    r2 = run_su(str(minted), "--session", "s2", "--sources", "[]")
                    state2 = json.loads((minted / "run.json").read_text())
                    if r2.returncode != 0 or [s.get("session_id") for s in
                                               state2["inputs"]["sessions"]] != ["s1", "s2"]:
                        bad.append(f"{rel(su)}: a fold by run path did not join the second "
                                   f"session (exit {r2.returncode}): "
                                   f"{(r2.stdout or r2.stderr).strip()[:120]}")
                hand = results / "hand-named"
                r3 = run_su(str(hand), "--output-root", str(results), "--goal", "checks",
                            "--session", "s1", "--sources", srcs)
                if r3.returncode == 0 or hand.exists():
                    bad.append(f"{rel(su)}: a relay-composed run path without run.json was "
                               f"adopted; only a mint creates a run directory")
                r4 = run_su("--output-root", str(results), "--skill", "quality-of-earnings",
                            "--company", "Demo", "--goal", "checks", "--session", "s1",
                            "--sources", srcs)
                if r4.returncode == 0:
                    bad.append(f"{rel(su)}: --skill accepted a name that is not one of the "
                               f"plugin's inline skills")

    # 8q. The report deck mints nothing: build_report.py renders it from report.yaml and
    #     the sealed workbook, check_report.py refuses a deck that says what the workbook
    #     does not. tests/<plugin>/report-selftest.py (outside the plugin, so it never
    #     ships) holds the cases - a spec-conformant
    #     workbook builds a deck that passes; a figure typed into a sentence, an
    #     unresolved reference and a figure edited after the build are refused, each
    #     named. The gate holds mechanics only - what the deck says is the author's. Run through the plugin's own environment: the builder needs
    #     python-pptx and openpyxl, pinned in pyproject.toml / uv.lock (TOOLING.md).
    st = root.parent / "tests" / root.name / "report-selftest.py"
    if st.is_file():
        import subprocess
        r = subprocess.run(["uv", "run", "--project", str(root), "python3", str(st)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            tail = " | ".join((r.stdout + r.stderr).strip().splitlines()[-4:])
            bad.append(f"{rel(st)}: report self-test failed (exit {r.returncode}): {tail}")
        for skill in ("check-report",):
            txt = (root / "skills" / skill / "SKILL.md").read_text()
            for need in ("build_report.py", "check_report.py", "reference/REPORT.md"):
                if need not in txt:
                    bad.append(f"skills/{skill}/SKILL.md: does not name {need} - the deck is "
                               f"built and gated by script, never written by hand")

    # 8w. The workbook kit is ONE module, scripts/wbkit.py: WORKBOOK_STYLE.md § 9's
    #     constants and WORKBOOK.md § 7's helpers, imported by every tab script. Measured
    #     2026-09-22 on one revenue run: WORKBOOK.md told every tab script to start from
    #     the kit "verbatim", and eighteen worker scripts carried a typed copy each - the
    #     largest class of generated code in the run. The module must self-check in the
    #     plugin's own environment, no other shipped script may carry the palette with a
    #     NamedStyle (a second copy drifts from the gate), and the two documents must send
    #     the reader to the module rather than to a code block.
    wk = root / "scripts" / "wbkit.py"
    if wk.is_file():
        import subprocess
        r = subprocess.run(["uv", "run", "--project", str(root), "python3", str(wk)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            tail = " | ".join((r.stdout + r.stderr).strip().splitlines()[-3:])
            bad.append(f"{rel(wk)}: self-check failed (exit {r.returncode}): {tail}")
        for b in sorted(root.glob("scripts/*.py")):
            if b == wk:
                continue
            t = b.read_text()
            if "005C53" in t and "NamedStyle(" in t:
                bad.append(f"{rel(b)}: carries its own copy of the workbook kit - import "
                           f"scripts/wbkit.py instead")
        for doc in ("reference/WORKBOOK.md", "reference/WORKBOOK_STYLE.md"):
            df = root / doc
            if df.is_file() and "scripts/wbkit.py" not in df.read_text():
                bad.append(f"{rel(df)}: does not name scripts/wbkit.py - a tab script "
                           f"reading it would type the kit again")

    # 8z. The shared modules a step imports carry their own self-checks, and each must
    #     pass in the plugin's own environment: style.py (currencies, US number and date
    #     forms, the token grammar the gates read with), figures.py (units per currency,
    #     cross-currency ties refused), periods.py (fiscal calendars, windows, time zones),
    #     step_record.py, check_prose.py's gate cases, cache.py (the cache's bookkeeping:
    #     refusals, stated totals, the exact re-check), and the shared helpers a worker
    #     computes with instead of retyping them (agents/worker.md § Shared modules).
    for name, extra in (("style.py", ()), ("figures.py", ()), ("periods.py", ()),
                        ("step_record.py", ()), ("check_prose.py", ("--self-check",)),
                        ("rework.py", ()), ("items.py", ()),
                        ("matching.py", ()), ("resolve.py", ()), ("cache.py", ())):
        mod = root / "scripts" / name
        if mod.is_file():
            import subprocess
            r = subprocess.run(["uv", "run", "--project", str(root), "python3", str(mod), *extra],
                               capture_output=True, text=True)
            if r.returncode != 0:
                tail = " | ".join((r.stdout + r.stderr).strip().splitlines()[-3:])
                bad.append(f"{rel(mod)}: self-check failed (exit {r.returncode}): {tail}")

    # 8x. The read and the citation are one query: a table the extract step's own
    #     script landed through scripts/cache.py, read back by evidence.py select,
    #     returns the rows and a span whose file, anchors, letters and parses come from
    #     the manifest, whose filter is the WHERE clause, and whose row count and control
    #     total are measured over those rows; a JOIN is refused; and a source changed
    #     under the cache fails `cache.py --verify` (exit 3).
    ev, cp = root / "scripts" / "evidence.py", root / "scripts" / "cache.py"
    if ev.is_file() and cp.is_file():
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tdp = pathlib.Path(td)
            room, rd = tdp / "room", tdp / "run"
            room.mkdir()
            rd.mkdir()
            (room / "ar.csv").write_text(
                "Demo Corp\nAR by customer\n\ncustomer,region,amount\n"
                "Acme,East,100.00\nBeta,West,200.00\nGamma,East,300.00\n"
                "Total,,600.00\nDelta,West,50.00\n")
            (rd / "run.json").write_text(json.dumps({
                "schema": "countz-accounting/run@1", "run_id": "fx.20260923-000000",
                "sources": [{"id": "dataroom", "name": "room", "path": str(room),
                             "kind": "folder"}], "checks": [], "dispatches": [],
                "next_seq": 2}))
            land = (
                "import sys, polars as pl\n"
                f"sys.path.insert(0, {str(root / 'scripts')!r})\n"
                "import cache\n"
                "df = pl.DataFrame({'customer': ['Acme', 'Beta', 'Gamma', 'Delta'],\n"
                "                   'region': ['East', 'West', 'East', 'West'],\n"
                "                   'amount': [100.0, 200.0, 300.0, 50.0]})\n"
                f"cache.write({str(rd)!r}, 'ar', df, file='ar.csv', source='dataroom',\n"
                "            file_role='management_prepared', header_at='A4', rows='5:7,9:9',\n"
                "            columns={'customer': {'at': 'A', 'parse': 'as written'},\n"
                "                     'region': {'at': 'B', 'parse': 'as written'},\n"
                "                     'amount': {'at': 'C', 'parse': 'as written'}},\n"
                "            control='amount', stated={'value': 600.0, 'where': 'C8 (Total)'})\n")
            r = subprocess.run(["uv", "run", "--project", str(root), "python3", "-c", land],
                               capture_output=True, text=True)
            if r.returncode != 0:
                bad.append(f"{rel(cp)}: cache.write did not land a parsed table (exit "
                           f"{r.returncode}): {(r.stdout + r.stderr).strip()[:200]}")
            else:
                r = subprocess.run(["uv", "run", "--project", str(root), "python3", str(ev),
                                    "select", "SELECT customer FROM ar WHERE region = 'West'",
                                    "--run-dir", str(rd), "--id", "E.ar.west"],
                                   capture_output=True, text=True)
                want = ("file: ar.csv", "header_at: A4", "rows: 5:7,9:9",
                        "filter: region = 'West'", "row_count: 2", "value: 250.0",
                        "at: A", "parse: as written")
                if r.returncode != 0 or not all(w in r.stdout for w in want):
                    bad.append(f"{rel(ev)}: `select` must return the span of the rows the "
                               f"statement selects - file, anchors, letters and parses from "
                               f"the manifest, the WHERE as filter, count and control "
                               f"measured (exit {r.returncode}): "
                               f"{(r.stdout + r.stderr).strip()[:200]}")
                r = subprocess.run(["uv", "run", "--project", str(root), "python3", str(ev),
                                    "select", "SELECT a.customer FROM ar a JOIN ar b ON a.customer = b.customer",
                                    "--run-dir", str(rd)], capture_output=True, text=True)
                if r.returncode == 0 or "one table" not in (r.stdout + r.stderr):
                    bad.append(f"{rel(ev)}: a JOIN in a span select must be refused naming "
                               f"the one-table rule (exit {r.returncode})")
                r = subprocess.run(["uv", "run", "--project", str(root), "python3", str(cp),
                                    str(rd), "--verify", "ar"], capture_output=True, text=True)
                if r.returncode != 0:
                    bad.append(f"{rel(cp)}: --verify on an unchanged source must agree "
                               f"(exit {r.returncode}): {(r.stdout + r.stderr).strip()[:160]}")
                with (room / "ar.csv").open("a") as fh:
                    fh.write("Zeta,East,1.00\n")
                r = subprocess.run(["uv", "run", "--project", str(root), "python3", str(cp),
                                    str(rd), "--verify", "ar"], capture_output=True, text=True)
                if r.returncode != 3 or "changed" not in (r.stdout + r.stderr):
                    bad.append(f"{rel(cp)}: --verify must fail when the source changed under "
                               f"the cache (exit {r.returncode}): "
                               f"{(r.stdout + r.stderr).strip()[:160]}")
                r = subprocess.run(["uv", "run", "--project", str(root), "python3", str(ev),
                                    "select", "SELECT customer FROM ar", "--run-dir", str(rd),
                                    "--reperform"], capture_output=True, text=True)
                if r.returncode != 3:
                    bad.append(f"{rel(ev)}: `select --reperform` over a changed source must "
                               f"exit 3, a cache defect (exit {r.returncode})")

    # 8p. One document names the preferred libraries and pyproject.toml pins them; the
    #     worker charter, the one place every computing step reads, must point at it.
    #     countz-accounting states them in reference/CONDUCT.md; a plugin that keeps them
    #     in reference/TOOLING.md must name that file instead.
    for libs in ("reference/CONDUCT.md", "reference/TOOLING.md"):
        lf = root / libs
        if not lf.is_file() or "polars" not in lf.read_text():
            continue
        wf = root / "agents" / "worker.md"
        if wf.is_file() and libs not in wf.read_text():
            bad.append(f"{rel(wf)}: does not name {libs}, where the preferred libraries "
                       f"are named")
        if not (root / "uv.lock").is_file():
            bad.append(f"{rel(root / 'uv.lock')}: missing - run `uv lock` in the plugin root")
        break

    # 8r. The index skill lists every user-facing skill as a static row — the list the
    #     user sees when the server is not reachable — and calls `get_countz_config` once, so a
    #     recipe added server-side (an entry whose `skill` is not a row) reaches every
    #     installed plugin with no release. Re-keyed 2026-09-17 (operator: the index
    #     must be fast and work unsigned-in): a row per local skill is required, a
    #     catalogued skill included; the catalog contributes only what has no local
    #     skill. Mechanical: every user-facing skill has a row, no row names a
    #     non-facing skill, the catalog call is present.
    idx = root / "skills" / INDEX_SKILL / "SKILL.md"
    if idx.is_file():
        itext = idx.read_text()
        listed = set(re.findall(r"^\| `([a-z-]+)` \|", itext, re.M))
        facing = {f.parent.name for f in root.glob("skills/*/SKILL.md")
                  if f.parent.name != INDEX_SKILL
                  and frontmatter(f).get("user-invocable", "true").lower() != "false"}
        catalogued: set[str] = set()
        cat = root / "playbook-recipes" / "catalog.yaml"
        if cat.is_file():
            try:
                import yaml
                for e in (yaml.safe_load(cat.read_text()) or {}).get("recipes") or []:
                    if (e or {}).get("skill"):
                        catalogued.add(str(e["skill"]))
            except Exception:  # noqa: BLE001 — 8t reports the parse failure
                pass
            if "get_countz_config" not in itext:
                bad.append(f"{rel(idx)}: does not call `get_countz_config` - the catalogued "
                           f"analyses are fetched, never listed by hand")
        for name in sorted(facing - listed):
            bad.append(f"{rel(idx)}: does not list user-facing skill `{name}` - one table row "
                       f"per local skill, the list the user sees when the server is unreachable")
        for name in sorted(catalogued - facing):
            bad.append(f"{rel(idx)}: catalog.yaml names skill `{name}`, which is not a "
                       f"user-facing skill in this plugin")
        for name in sorted(listed - facing):
            bad.append(f"{rel(idx)}: lists `{name}`, which is not a user-facing skill")

    # 8s. The Countz connector declaration (docs/arch/AUTH_MCP_OAUTH.md in the monorepo):
    #     `.mcp.json` declares exactly the `countz` server, the manifest lists the
    #     connector, and no skill hardcodes a host's wire name (`mcp__...`) — the short
    #     name is the contract. The sign-in procedure lives once, in
    #     `reference/RUN_CONTRACT.md § Sign in first`, which every launcher skill reads
    #     before it collects; no per-skill section is required.
    mcp_json = root / ".mcp.json"
    if mcp_json.is_file():
        try:
            servers = json.loads(mcp_json.read_text()).get("mcpServers", {})
        except Exception as exc:  # noqa: BLE001 — one message for any unparsable file
            servers = None
            bad.append(f"{rel(mcp_json)}: not JSON ({exc})")
        if servers is not None:
            if list(servers) != ["countz"]:
                bad.append(f"{rel(mcp_json)}: declares {sorted(servers)} - exactly one server, `countz`")
            srv = servers.get("countz") or {}
            if srv.get("type") != "http" or not str(srv.get("url", "")).startswith("https://"):
                bad.append(f"{rel(mcp_json)}: `countz` must be an http server at an https URL")
            if mf.get("connectors") != ["countz"]:
                bad.append(f"{rel(manifest)}: connectors must be [\"countz\"] when .mcp.json declares the server")
        for f in sorted(root.glob("skills/*/SKILL.md")):
            if "mcp__" in f.read_text():
                bad.append(f"{rel(f)}: names a tool by wire name (`mcp__...`) - use the short name on the `countz` server")
        rc_txt = (root / "reference" / "RUN_CONTRACT.md").read_text() if (root / "reference" / "RUN_CONTRACT.md").is_file() else ""
        if "## Sign in first" not in rc_txt:
            bad.append(f"{rel(root / 'reference' / 'RUN_CONTRACT.md')}: missing § Sign in first")

    # 8y. The ARR policy catalog (reference/ARR_POLICY.md) has one home,
    #     scripts/arr_policy.py: 31 decisions, every derivation defined at every position
    #     under every purpose, and every derived value one of the decision's own options.
    #     A catalog edit that breaks a derivation fails here, not in a user's run.
    ap_script = root / "scripts" / "arr_policy.py"
    if ap_script.is_file():
        import subprocess
        r = subprocess.run([sys.executable, str(ap_script), "selftest"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            bad.append(f"{rel(ap_script)}: selftest failed - "
                       f"{(r.stdout or r.stderr).strip().splitlines()[-1]}")
        for skill in ("create-arr-policy", "extract-arr-policy"):
            if not (root / "skills" / skill / "SKILL.md").is_file():
                bad.append(f"{rel(ap_script)}: the ARR policy ships without skills/{skill}")

    # 8. A shipped hook must be executable, or it fails silently at run time.
    for h in sorted(root.glob("hooks/*.sh")):
        if not h.stat().st_mode & 0o111:
            bad.append(f"{rel(h)}: not executable")
    hj = root / "hooks" / "hooks.json"
    if hj.is_file():
        try:
            for ev, matchers in json.loads(hj.read_text()).get("hooks", {}).items():
                for m in matchers:
                    for hook in m.get("hooks", []):
                        cmd = hook.get("command", "")
                        target = cmd.replace("${CLAUDE_PLUGIN_ROOT}/", "")
                        if cmd.startswith("${CLAUDE_PLUGIN_ROOT}") and not (root / target).is_file():
                            bad.append(f"{rel(hj)}: {ev} hook points at {target}, which does not exist")
        except Exception as exc:
            bad.append(f"{rel(hj)}: not valid JSON ({exc})")

    return bad


def check_marketplace(parent: pathlib.Path) -> list[str]:
    """The marketplace manifest is how a plugin is installed without a shell command.

    A plugin missing from it is invisible to `/plugin` and to `claude plugin install`,
    which is not a packaging error `claude plugin validate` can see: it validates the
    manifest's own shape, never that the manifest covers the plugins beside it.
    """
    bad: list[str] = []
    mp = parent / ".claude-plugin" / "marketplace.json"
    if not mp.is_file():
        return [f"{mp}: no marketplace manifest, so no plugin here is installable "
                f"without a shell command"]
    try:
        doc = json.loads(mp.read_text())
    except Exception as exc:
        return [f"{mp}: not valid JSON ({exc})"]

    listed: dict[str, str] = {}
    for entry in doc.get("plugins", []):
        name, src = entry.get("name"), entry.get("source")
        if not name or not isinstance(src, str):
            bad.append(f"marketplace.json: entry {entry!r} has no name or no path source")
            continue
        listed[name] = src
        target = (parent / src).resolve()
        pj = target / ".claude-plugin" / "plugin.json"
        if not pj.is_file():
            bad.append(f"marketplace.json: {name} points at {src}, which holds no plugin")
            continue
        declared = json.loads(pj.read_text()).get("name")
        if declared != name:
            bad.append(f"marketplace.json: {name} points at {src}, whose manifest "
                       f"names it {declared!r}")

    for p in sorted(parent.glob("*/.claude-plugin/plugin.json")):
        declared = json.loads(p.read_text()).get("name")
        if declared not in listed:
            bad.append(f"marketplace.json: no entry for {declared} "
                       f"({p.parent.parent.name}/), so it cannot be installed")
    return bad


def main() -> int:
    args = [pathlib.Path(a) for a in sys.argv[1:]]
    roots = args or [p.parent for p in pathlib.Path(".").glob("*/.claude-plugin")]
    failed = False

    # Repo-level, so it runs once on the full sweep rather than per plugin.
    if not args:
        problems = check_marketplace(pathlib.Path("."))
        if problems:
            failed = True
            print(f"\nmarketplace: {len(problems)} problem(s)", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
        else:
            print("marketplace: ok")

    for root in roots:
        problems = check(root)
        if problems:
            failed = True
            print(f"\n{root.name}: {len(problems)} problem(s)", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
        else:
            print(f"{root.name}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
