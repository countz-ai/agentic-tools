#!/usr/bin/env python3
"""Self-test for scripts/step_record.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_step_record.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import run_state  # noqa: E402
import step_record  # noqa: E402
from step_record import (GateRefused, brief, consumed_from_citations, finish,  # noqa: E402
                         main as cli, own_files, place_tab, start)

BRIEF = ("# dispatch\n\nYour arguments:\n\n    run_dir=/x\n    seq={seq}\n{check}"
         "    sources=gl\n    goal=(none)\n    params={{\"tolerance\": 1}}\n    mode=fresh\n")


def _run(d: pathlib.Path, name: str, *, seq: int = 7, step: str = "tie", check: str | None = "k1",
         sources: list | None = None, text: str | None = None) -> pathlib.Path:
    """A run directory with one brief, a data room and run.json."""
    run, room = d / name / "run", d / name / "room"
    for sub in ("dispatch", "steps", "checks", "workpapers", "out/.staging", "plan"):
        (run / sub).mkdir(parents=True)
    room.mkdir()
    (room / "gl.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (run / "run.json").write_text(json.dumps(
        {"sources": sources if sources is not None else [{"id": "gl", "path": str(room)}]}),
        encoding="utf-8")
    if text is None:
        text = BRIEF.format(seq=seq, check=f"    check={check}\n" if check else "")
    (run / "dispatch" / f"{seq:04d}-{step}.md").write_text(text, encoding="utf-8")
    return run


def _refuses(bad: list, what: str, fn, *args, errors=(ValueError,), want: str = "", **kw):
    try:
        fn(*args, **kw)
        bad.append(f"accepted {what}")
    except errors as exc:
        if want and want not in str(exc):
            bad.append(f"{what}: refusal lacks {want!r}: {exc}")


def test_lifecycle(d: pathlib.Path, bad: list) -> None:
    run = d / "life" / "run"
    room = d / "life" / "room"
    for sub in ("dispatch", "steps", "checks", "workpapers", "out/.staging", "plan"):
        (run / sub).mkdir(parents=True)
    room.mkdir()
    (room / "gl.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (run / "plan" / "p.json").write_text("{}", encoding="utf-8")
    (run / "run.json").write_text(json.dumps({
        "sources": [{"id": "gl", "path": str(room)}],
        "playbook": {"path": "/elsewhere/plan/p.json"}}), encoding="utf-8")
    (run / "dispatch" / "0007-tie.md").write_text(BRIEF.format(seq=7, check="    check=k1\n"),
                                                  encoding="utf-8")
    (run / "workpapers" / "evidence-k1.yaml").write_text(
        "- id: E.k1.gl\n  kind: span\n  file: gl.csv\n  source: gl\n"
        "  file_role: system_export\n- id: E.k1.a0\n  kind: span\n"
        "  file: checks/k0.md\n  source: null\n  file_role: run_artifact\n", encoding="utf-8")
    (run / "checks" / "k0.md").write_text("k0", encoding="utf-8")
    (run / "checks" / "k1-old.csv").write_text("x", encoding="utf-8")
    old = time.time() - 3600
    for f in ("checks/k1-old.csv", "workpapers/evidence-k1.yaml"):
        os.utime(run / f, (old, old))

    b = brief(run, 7)
    if (b["step"], b["check"], b["args"]["params"], b["args"]["goal"]) != \
            ("tie", "k1", {"tolerance": 1}, None):
        bad.append(f"brief: {b}")
    _refuses(bad, "a finish with no step_start", finish, run, 7, conclusion="x")
    start(run, 7)
    (run / "checks" / "k1.md").write_text("record", encoding="utf-8")
    (run / "checks" / "k1-ties.csv").write_text("t", encoding="utf-8")
    (run / "out" / ".staging" / "k1.xlsx").write_text("not a workbook", encoding="utf-8")
    _refuses(bad, "a finish with the tab still staged", finish, run, 7, conclusion="x")
    _refuses(bad, "a tab the gates refuse", place_tab, run, 7, errors=(GateRefused,))
    (run / "out" / ".staging" / "k1.xlsx").unlink()
    for kw in ({"conclusion": ""}, {"conclusion": "x", "outcome": "ok"},
               {"conclusion": "x", "outcome": "blocked"},
               {"conclusion": "x", "blockers": [{"what": "gate"}]},
               {"conclusion": "x", "consumed": {"sources/none.md": "profile"}}):
        _refuses(bad, kw, finish, run, 7, errors=(ValueError, FileNotFoundError), **kw)
    rec = finish(run, 7, conclusion="Tied.", consumed={"checks/k0.md": "roster_from"},
                 notes="n")
    if rec["produced"] != ["checks/k1.md", "checks/k1-ties.csv"]:
        bad.append(f"produced: {rec['produced']}")
    got = {pathlib.Path(c["path"]).name: c["used_for"] for c in rec["consumed"]}
    want = {"0007-tie.md": "dispatch brief", "p.json": "step params",
            "gl.csv": "cited as E.k1.gl", "k0.md": "cited as E.k1.a0; roster_from"}
    if got != want:
        bad.append(f"consumed: {got}")
    ev = [json.loads(x) for x in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    if [e["event"] for e in ev] != ["step_start", "step_end"] or \
            ev[1]["duration_s"] < 0 or ev[0]["check"] != "k1":
        bad.append(f"events: {ev}")
    _refuses(bad, "a second record for one seq", finish, run, 7, conclusion="again",
             errors=(FileExistsError,))
    import contextlib
    import io
    with contextlib.redirect_stderr(io.StringIO()):
        code = cli(["finish", str(run), "7", "--json", str(run / "missing.json")])
    if code == 0:
        bad.append("the CLI finished from a missing file")


def test_brief_arguments(d: pathlib.Path, bad: list) -> None:
    """Every argument value reads back as written, whatever it holds."""
    ask = ("Tie the GL to the TB.\nFocus on cash:\n    check=cash_tie\n\nand ignore payroll.")
    args = {"recipe": "/r/My Recipe.md", "instructions": ask, "quoted": '"as said"',
            "padded": "  keep  ", "literal": "(none)", "uni": "Données\u2028x\x85y",
            "tab": "a\tb", "empty": "", "commas": ["a,b", "c"], "fix_input": [{"id": "gl"}],
            "declared": {"basis": "in-force"}, "plain": "Tie GL to TB", "ids": ["gl", "tb"],
            "none": None}
    run = _run(d, "args", step="plan", check=None, text="x")
    text = run_state.render_brief(run, 7, "plan", "check-plan", None, args)
    (run / "dispatch" / "0007-plan.md").write_text(text, encoding="utf-8")
    got = brief(run, 7)
    want = {**args, "commas": '["a,b","c"]', "fix_input": '[{"id":"gl"}]',
            "declared": '{"basis":"in-force"}', "ids": "gl,tb", "run_dir": str(run), "seq": 7}
    if got["args"] != want or got["check"] is not None:
        bad.append(f"brief args did not round-trip: {got['args']} / check {got['check']}")
    if "    plain=Tie GL to TB\n" not in text or "    ids=gl,tb\n" not in text:
        bad.append("a plain value is no longer written bare")
    line = run_state.next_line(run, {"skill": "check-plan", "seq": 7, "args": args}, None)
    if "\n" in line:
        bad.append("a NEXT line spans lines")
    # the --briefs path reads a check brief back the same way
    goal = "Tie GL to TB\nat quarter end"
    ck = run_state.render_brief(run, 8, "tie", "check-tie", "k1",
                                run_state.check_args(["gl", "tb"], goal, {"t": 1}, "fresh"))
    (run / "dispatch" / "0008-tie.md").write_text(ck, encoding="utf-8")
    pb = run_state.parse_brief(run / "dispatch" / "0008-tie.md")
    if (pb["check"], pb["args"]) != ("k1", {"sources": ["gl", "tb"], "goal": goal,
                                           "params": {"t": 1}, "mode": "fresh"}):
        bad.append(f"parse_brief: {pb}")
    # a hand-written block with a value spanning lines, or a key twice, is refused
    for name, extra in (("span", "    goal=one\ntwo\n"), ("twice", "    mode=fix\n"),
                        ("seq", None)):
        r = _run(d, f"args-{name}", text=(
            BRIEF.format(seq=7, check="    check=k1\n") + (extra or "")) if extra else
            BRIEF.format(seq=9, check="    check=k1\n"))
        _refuses(bad, f"a brief with {name}", brief, r, 7)
        _refuses(bad, f"a start on a brief with {name}", start, r, 7)
    for key in ("fix-input", "seq", "check"):
        _refuses(bad, f"argument key {key!r}", run_state.render_brief, run, 7, "tie",
                 "check-tie", "k1", {key: "x"}, errors=(run_state.Refuse,))


def test_check_ids(d: pathlib.Path, bad: list) -> None:
    """A check id is CHECK_ID; a check's files are named, never globbed by suffix."""
    run = _run(d, "ids", check="a5-bridge")
    _refuses(bad, "a brief naming check a5-bridge", brief, run, 7, want="check id")
    _refuses(bad, "a start on check a5-bridge", start, run, 7)
    _refuses(bad, "place_tab('a5-bridge')", place_tab, run, "a5-bridge")
    _refuses(bad, "consumed_from_citations('a5-bridge')", consumed_from_citations, run,
             "a5-bridge")
    _refuses(bad, "own_files('a5-bridge')", own_files, run, "a5-bridge")
    run = _run(d, "ids-ok", check="k1_b")
    for f in ("checks/k1_b.md", "checks/k1_b-items.csv", "workpapers/figures-k1_b.yaml",
              "workpapers/evidence-k1_b.yaml", "workpapers/notes-k1_b.yaml",
              "workpapers/figures-x_k1_b.yaml", "checks/k1_b_2-items.csv"):
        (run / f).write_text("[]\n" if f.endswith(".yaml") else "x", encoding="utf-8")
    got = [str(p.relative_to(run)) for p in own_files(run, "k1_b")]
    if got != ["checks/k1_b.md", "checks/k1_b-items.csv", "workpapers/figures-k1_b.yaml",
               "workpapers/evidence-k1_b.yaml"]:
        bad.append(f"own_files: {got}")
    start(run, 7)
    if finish(run, 7, conclusion="x")["check_id"] != "k1_b":
        bad.append("an underscore check id did not record")
    run = _run(d, "notab", step="review", check=None)
    _refuses(bad, "place_tab on a step with no check", place_tab, run, 7, want="no check")
    _refuses(bad, "place_tab(True)", place_tab, run, True)


def test_events(d: pathlib.Path, bad: list) -> None:
    """A line that is not an object, bytes that are not UTF-8, a start with no readable
    ts - each skipped, never fatal."""
    run = _run(d, "events")
    start(run, 7)
    with (run / "events.jsonl").open("ab") as f:
        f.write(b'1\n["x"]\n{"ts": "x", "event": "note", "text": "\xe2\x82"}\n'
                b'{"event": "step_start", "seq": 7, "step": "tie", "ts": "garbage"}\n'
                b'{"event": "step_start", "seq": 7, "step": "tie"}\n')
    try:
        rec = finish(run, 7, conclusion="x")
        ev = [json.loads(x) for x in (run / "events.jsonl").read_text(
            encoding="utf-8", errors="replace").splitlines()[:1]]
        if rec["started_at"] != ev[0]["ts"]:
            bad.append(f"started_at {rec['started_at']} is not the readable step_start")
    except Exception as exc:  # noqa: BLE001
        bad.append(f"a malformed events.jsonl line broke finish: {type(exc).__name__} {exc}")


def test_finish_inputs(d: pathlib.Path, bad: list) -> None:
    """finish refuses inputs it would misread, list and mapping shapes included."""
    run = _run(d, "inputs")
    start(run, 7)
    (run / "out" / ".staging" / "k1.xlsx").write_text("staged", encoding="utf-8")
    for err in ("", "  ", 5):
        _refuses(bad, f"error={err!r}", finish, run, 7, conclusion="x", error=err, want="error")
    for kw in ({"step": "recon"}, {"check_id": "other"}, {"args": {}}, {"started_at": "x"},
               {"schema": "s"}, {"completed_at": "x"}):
        _refuses(bad, f"extra {kw}", finish, run, 7, conclusion="x", error="e", **kw,
                 want=next(iter(kw)))
    for kw in ({"produced": "plan.md"}, {"findings": "text"}, {"blockers": {"what": "w",
               "effect": "e"}}, {"blockers": ["gate"]}, {"cache_defects": [("id", "x")]},
               {"notes": None}, {"consumed": ["checks/k0.md"]},
               {"consumed": {"run.json": ""}}):
        _refuses(bad, f"shape {kw}", finish, run, 7, conclusion="x", error="e", **kw)
    if (run / "steps" / "0007-tie.json").exists():
        bad.append("a refused finish wrote a record")
    defects = ({"id": f"c{i}", "what": "w", "fix": "f"} for i in range(2))
    rec = finish(run, 7, conclusion="x", error="could not open the ledger", fix={"n": 1},
                 cache_defects=defects, findings=(f for f in [{"id": "C.1"}]))
    if [x["id"] for x in rec["cache_defects"]] != ["c0", "c1"] or rec["fix"] != {"n": 1} \
            or rec["findings"] != [{"id": "C.1"}] or rec["step"] != "tie":
        bad.append(f"a generator or an extra field was lost: {rec}")


def test_paths(d: pathlib.Path, bad: list) -> None:
    """Paths: sources, aliases, stale run.json paths, surrogates."""
    # a registered file source with no extension; a folder source with a dot in its name
    run = _run(d, "src")
    room = run.parent / "room"
    (room / "GLEXPORT").write_text("x", encoding="utf-8")
    (room / "Q4.2025").mkdir()
    (room / "Q4.2025" / "tb.csv").write_text("x", encoding="utf-8")
    (run / "run.json").write_text(json.dumps({"sources": [
        {"id": "gl", "path": str(room / "GLEXPORT"), "kind": "file"},
        {"id": "tb", "path": str(room / "Q4.2025"), "kind": "folder"},
        {"id": "bank", "path": str(room / "gl.csv")}]}), encoding="utf-8")
    (run / "workpapers" / "evidence-k1.yaml").write_text(
        "- id: E.k1.gl\n  file: GLEXPORT\n  source: gl\n  file_role: system_export\n"
        "- id: E.k1.tb\n  file: tb.csv\n  source: tb\n  file_role: system_export\n"
        "- id: E.k1.bk\n  file: gl.csv\n  source: bank\n  file_role: bank_statement\n"
        f"- id: E.k1.abs\n  file: {room / 'gl.csv'}\n  source: null\n"
        "  file_role: system_export\n", encoding="utf-8")
    got = {str(p.relative_to(room)): ids for p, ids in consumed_from_citations(run, "k1").items()}
    if got != {"GLEXPORT": ["E.k1.gl"], "Q4.2025/tb.csv": ["E.k1.tb"],
               "gl.csv": ["E.k1.bk", "E.k1.abs"]}:
        bad.append(f"sources resolved to {got}")
    for name, entry in (("unregistered", "  file: gl.csv\n  source: nope\n"),
                        ("relative, no source", "  file: gl.csv\n  source: null\n"),
                        ("YAML number", "  file: 010\n  source: gl\n")):
        (run / "workpapers" / "evidence-k1.yaml").write_text(
            f"- id: E.k1.x\n{entry}  file_role: system_export\n", encoding="utf-8")
        _refuses(bad, f"a citation with {name}", consumed_from_citations, run, "k1")
    (run / "workpapers" / "evidence-k1.yaml").write_text("E.k1.x: {file: gl.csv}\n",
                                                         encoding="utf-8")
    _refuses(bad, "a mapping-shaped evidence ledger", consumed_from_citations, run, "k1")

    # a run directory reached through a symlink; produced outside the run refused
    run = _run(d, "alias")
    link = run.parent / "link"
    os.symlink(run, link)
    (link / "workpapers" / "evidence-k1.yaml").write_text(
        "- id: E.k1.a0\n  file: checks/k0.md\n  source: null\n  file_role: run_artifact\n",
        encoding="utf-8")
    (link / "checks" / "k0.md").write_text("k0", encoding="utf-8")
    time.sleep(0.2)
    start(link, 7)
    (link / "plan.md").write_text("p", encoding="utf-8")
    _refuses(bad, "a produced path outside the run", finish, link, 7, conclusion="x",
             produced=[run.parent / "room" / "gl.csv"], want="outside")
    rec = finish(link, 7, conclusion="x", produced=[link / "plan.md", "checks/../plan.md"],
                 consumed={link / "checks" / "k0.md": "roster"})
    k0 = [c for c in rec["consumed"] if c["path"].endswith("k0.md")]
    if rec["produced"] != ["plan.md"] or len(k0) != 1 or \
            k0[0]["used_for"] != "cited as E.k1.a0; roster":
        bad.append(f"alias: produced {rec['produced']}, k0 rows {k0}")

    # a stale plan path is named as run.json's; the recipe at plan.recipe is consumed
    run = _run(d, "stale")
    (run / "recipes").mkdir()
    (run / "recipes" / "r.md").write_text("r", encoding="utf-8")
    rj = json.loads((run / "run.json").read_text(encoding="utf-8"))
    rj.update({"playbook": {"path": "/gone/pb.json"},
               "plan": {"recipe": str(run / "recipes" / "r.md")}})
    (run / "run.json").write_text(json.dumps(rj), encoding="utf-8")
    start(run, 7)
    _refuses(bad, "a stale playbook path", finish, run, 7, conclusion="x",
             errors=(FileNotFoundError,), want="run.json playbook.path")
    (run / "plan" / "pb.json").write_text("{}", encoding="utf-8")
    rec = finish(run, 7, conclusion="x", notes="file \udcff.csv")
    names = {pathlib.Path(c["path"]).name: c["used_for"] for c in rec["consumed"]}
    if names.get("r.md") != "the family's procedure" or names.get("pb.json") != "step params":
        bad.append(f"plan/recipe not consumed: {names}")
    back = json.loads((run / "steps" / "0007-tie.json").read_text(encoding="utf-8"))
    if back["notes"] != "file \udcff.csv" or list((run / "steps").glob("*.tmp")):
        bad.append("a lone surrogate did not round-trip, or a .tmp was left")


def test_produced_mtime(d: pathlib.Path, bad: list) -> None:
    """A file changed before step_start is not produced; one changed after it is."""
    run = _run(d, "mtime")
    ts = step_record._parse(start(run, 7)).timestamp()
    for name, t in (("before", ts - 0.5), ("after", ts + 0.2), ("second", float(int(ts))),
                    ("old_second", float(int(ts) - 3))):
        p = run / "checks" / f"k1-{name}.csv"
        p.write_text("x", encoding="utf-8")
        os.utime(p, (t, t))
    rec = finish(run, 7, conclusion="x")
    if rec["produced"] != ["checks/k1-after.csv", "checks/k1-second.csv"]:
        bad.append(f"produced by mtime: {rec['produced']}")


def test_fallback_ledger(d: pathlib.Path, bad: list) -> None:
    """Without PyYAML the ledger reads as PyYAML reads it, or is refused."""
    import yaml
    names = ["gl/GL Detail FY2026.xlsx", "Données/Grand livre 2026.xlsx", "it's here.csv",
             "tab\t" + "x y " * 40 + ".csv", "a " * 70, "it's " * 30, "x: y.csv", "# h.csv",
             "multi\nline\n\nx.csv", "back\\slash \"q\".csv", "bell\x07.csv", "yes", "2024-01-01",
             "010", "null", " lead" + " w" * 50]
    entries = [{"id": f"E.k1.f{i}", "kind": "span", "file": n, "source": "gl",
                "file_role": "system_export", "columns": [{"name": "a", "at": "C"}]}
               for i, n in enumerate(names)]
    entries.append({"id": "E.k1.none", "file": "gl.csv", "source": None,
                    "file_role": "run_artifact"})
    p = d / "evidence-fallback.yaml"
    p.write_text(yaml.safe_dump(entries, sort_keys=False, allow_unicode=True, width=100),
                 encoding="utf-8")
    want = [{k: e.get(k) for k in ("id", "file", "source", "file_role")}
            for e in yaml.safe_load(p.read_text(encoding="utf-8"))]
    saved = sys.modules.get("yaml")
    sys.modules["yaml"] = None
    try:
        got = [{k: e.get(k) for k in ("id", "file", "source", "file_role")}
               for e in step_record._ledger_entries(p)]
        if got != want:
            bad.append("fallback: " + "; ".join(f"{w['file']!r} read as {g['file']!r}"
                                                for g, w in zip(got, want) if g != w))
        for text, why in (("- id: E.a\n  file: 010\n", "a YAML number"),
                          ('- id: E.a\n  file: "open\n', "an unclosed quote"),
                          ("- {id: E.a, file: x}\n", "a flow entry"),
                          ("E.a: {file: x}\n", "a mapping")):
            q = d / "evidence-bad.yaml"
            q.write_text(text, encoding="utf-8")
            _refuses(bad, f"a fallback ledger with {why}", step_record._ledger_entries, q)
    finally:
        sys.modules["yaml"] = saved


def main() -> int:
    bad: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td).resolve()
        for t in (test_lifecycle, test_brief_arguments, test_check_ids, test_events,
                  test_finish_inputs, test_paths, test_produced_mtime, test_fallback_ledger):
            try:
                t(d, bad)
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{t.__name__} raised {type(exc).__name__}: {exc}")
    for x in bad:
        print(f"step_record: {x}")
    print("step_record: ok" if not bad else "step_record: self-check FAILED")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
