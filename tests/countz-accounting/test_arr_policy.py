#!/usr/bin/env python3
"""Self-test for scripts/arr_policy.py.

Run by check-plugin.py (8z) as `uv run --project <plugin> python3 tests/countz-accounting/test_arr_policy.py`
from the repository root; it lives outside the plugin so it never ships.
"""
from __future__ import annotations

import contextlib
import copy
import io
import itertools
import pathlib
import random
import re
import subprocess
import sys
import tempfile
import types

import yaml

# The plugin under test: <repo>/countz-accounting/scripts, from <repo>/tests/countz-accounting.
SCRIPTS = pathlib.Path(__file__).resolve().parents[2] / "countz-accounting" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from arr_policy import (CONVENTIONS, DEC, DECISIONS, POLICIES, PURPOSE_POSITIONS,  # noqa: E402
                        _derived_at, _drift, _dump, _valid_value, amend, instructions,
                        is_complete, render, resolve)


def selftest() -> list[str]:
    """The catalog's own invariants: 31 decisions, ids unique, every derivation runs at
    every position under every purpose, and yields a valid value."""
    bad = []
    if len(DECISIONS) != 31 or len(DEC) != 31:
        bad.append(f"the catalog carries {len(DEC)} decisions, not 31")
    conv = {k: s["default"] for k, s in CONVENTIONS.items()}
    conv["window"] = "trailing_3_months"
    for d in DECISIONS:
        if d["type"] == "policy" and not d["by"]:
            bad.append(f"{d['id']}: a policy decision names no policy that decides it")
        if d["type"] != "policy" and d["by"]:
            bad.append(f"{d['id']}: a {d['type']} is decided by no policy position")
        for purpose, base in PURPOSE_POSITIONS.items():
            for pol in POLICIES:
                for pos in POLICIES[pol]["positions"]:
                    try:
                        v = _derived_at(d, pol, pos, base, conv)
                    except Exception as exc:  # noqa: BLE001
                        bad.append(f"{d['id']}: derivation fails at {pol}={pos} ({exc})")
                        continue
                    if d["id"] == "S2":
                        continue
                    err = _valid_value(d, v)
                    if err:
                        bad.append(f"{d['id']}: derives an invalid value at {pol}={pos}: {err}")
    for k, s in CONVENTIONS.items():
        if s["decision"] not in DEC:
            bad.append(f"convention {k} names decision {s['decision']}, which is not in the catalog")
    return (bad + _computing_gaps() + _field_ownership() + _fixed_point() + _decisions()
            + _conventions() + _instructions() + _cli())


def _field_ownership() -> list[str]:
    """Every field of a policy decision moves only with the policy that decides it (its
    `field_by` owner, or its one `by`), at every combination of positions."""
    bad = []
    conv = {k: s["default"] for k, s in CONVENTIONS.items()}
    for d in (d for d in DECISIONS if d["type"] == "policy"):
        fb = d.get("field_by")
        if not fb and len(d["by"]) != 1:
            bad.append(f"{d['id']}: decided by {d['by']} without `field_by`")
            continue
        if fb and set(fb.values()) != set(d["by"]):
            bad.append(f"{d['id']}: `field_by` owners {sorted(set(fb.values()))} are not `by` {d['by']}")
        owner = (lambda f: fb[f]) if fb else (lambda f: d["by"][0])
        for combo in itertools.product(*(list(POLICIES[p]["positions"]) for p in POLICIES)):
            base = dict(zip(POLICIES, combo))
            v0 = d["derive"](base, conv)
            for pol in POLICIES:
                for pos in POLICIES[pol]["positions"]:
                    v1 = d["derive"]({**base, pol: pos}, conv)
                    moved = [f for f in v0 if v0[f] != v1[f]] if isinstance(v0, dict) \
                        else ([None] if v0 != v1 else [])
                    for f in moved:
                        if owner(f) != pol:
                            bad.append(f"{d['id']}{'.' + f if f else ''} moves with {pol}, "
                                       f"which does not decide it")
    return sorted(set(bad))


# ---------------------------------------------------------------------------- resolve


def _rt(policy: dict) -> dict:
    """A policy as the CLI reads it back: through the YAML file `_dump` writes."""
    return yaml.safe_load(_dump(policy))


def _res(doc: dict):
    return resolve(copy.deepcopy(doc))


def _pick(rnd, opts):
    if isinstance(opts, list):
        return rnd.choice(opts)
    return rnd.choice([0, 1, 3, 12]) if opts == "int" else rnd.choice([5, 10, "none"])


def _some(rnd, spec):
    """A random valid value, a composite stated in part as a document states it."""
    if isinstance(spec, dict):
        keys = [f for f in spec if rnd.random() < 0.6] or [next(iter(spec))]
        return {f: _pick(rnd, spec[f]) for f in keys}
    return _pick(rnd, spec)


def _random_input(rnd) -> dict:
    doc = {"company": "X"}
    if rnd.random() < 0.7:
        doc["purpose"] = rnd.choice(list(PURPOSE_POSITIONS))
    if rnd.random() < 0.4:
        doc["policies"] = {k: {"position": rnd.choice(list(POLICIES[k]["positions"])),
                               "set_by": "answer"}
                           for k in rnd.sample(list(POLICIES), rnd.randint(1, 3))}
    if rnd.random() < 0.4:
        doc["conventions"] = {k: {"value": _some(rnd, s.get("fields") or s["options"]),
                                  "set_by": rnd.choice(["stated", "answer"])}
                              for k, s in rnd.sample(list(CONVENTIONS.items()), rnd.randint(1, 3))}
    ids = rnd.sample(list(DEC), rnd.randint(0, 6))
    doc["decisions"] = {i: {"value": _some(rnd, DEC[i].get("fields") or DEC[i]["options"]),
                            "basis": rnd.choice(["stated", "stated", "answer"]), "cite": "c"}
                        for i in ids}
    if rnd.random() < 0.3:
        doc["instructions"] = [{"text": f"rule {rnd.randint(1, 3)}", "source": "user",
                                "applies_to": [rnd.choice(ids or ["S1"])]}]
    return doc


def _fixed_point(n: int = 300, seed: int = 7) -> list[str]:
    """Resolving what `resolve` wrote changes nothing, from any valid input: no error, no
    drift, the same completeness, and every value valid and whole."""
    bad, rnd, ok = [], random.Random(seed), 0
    for _ in range(n):
        doc = _random_input(rnd)
        try:
            p1, _l, _a, e1 = _res(doc)
            if e1:
                continue
            ok += 1
            d2 = _rt(p1)
            p2, _l, _a, e2 = _res(d2)
        except Exception as exc:  # noqa: BLE001
            bad.append(f"resolve raises {exc!r} on {doc}")
            continue
        if e2 or _drift(d2, p2) or is_complete(p2) != is_complete(p1):
            bad.append(f"resolve is not a fixed point on {doc}: errors {e2}, drift "
                       f"{_drift(d2, p2)}, complete {is_complete(p1)}->{is_complete(p2)}")
        for i, e in p1["decisions"].items() if is_complete(p1) else ():
            err = _valid_value(DEC[i], e["value"])
            if err or ("fields" in DEC[i] and set(e["value"]) != set(DEC[i]["fields"])):
                bad.append(f"{i} resolves to {e['value']} ({err or 'fields missing'}) on {doc}")
    if ok < n // 2:
        bad.append(f"fixed point: only {ok} of {n} random inputs resolve without error")
    return bad[:5]


def _dec(doc: dict, i: str):
    return _res(doc)[0]["decisions"].get(i, {})


def _check(bad: list, cond: bool, what: str) -> None:
    if not cond:
        bad.append(what)


def _at(obj, *keys):
    """A nested value, or None where the path is missing: a regression reports, never raises."""
    for k in keys:
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


def _st(value, **kw) -> dict:
    return {"value": value, "basis": "stated", "cite": "memo", **kw}


def _decisions() -> list[str]:
    """Stated decisions: a part stated stays the only part stated, a field is compared
    only by the policy that decides it, and a breach is named as one."""
    bad = []
    # A partial statement whose other field another policy decides: resolving the draft
    # again changes nothing, and it never turns INCOHERENT.
    doc = {"company": "X", "purpose": "public_reporting",
           "decisions": {"L2": _st({"churn_at": "at_notice"})}}
    p1 = _res(doc)[0]
    p2, _l, _a, e2 = _res(_rt(p1))
    _check(bad, _at(p1, "policies", "lifecycle", "position") == "live_paying" and not e2
           and not _drift(_rt(p1), p2), f"L2 churn_at alone: approve changes the draft {p2['policies']}")
    _check(bad, _at(p1, "decisions", "L2", "derived_fields") == ["conflicting_records"],
           "L2 churn_at alone: the derived field is not marked `derived_fields`")
    doc = {"company": "X", "purpose": "sell_side",
           "decisions": {"L2": _st({"churn_at": "effective_date"}),
                         "L3": _st({"treatment": "grace_window", "grace_months": 3})}}
    p1 = _res(doc)[0]
    p2, lines, _a, _e = _res(_rt(p1))
    _check(bad, is_complete(p1) and is_complete(p2) and not any("INCOHERENT" in x for x in lines),
           "L2 + L3: a complete draft resolves incomplete")
    # The valid neighbour: L2 stated whole, both fields, infers source and lifecycle.
    doc = {"company": "X", "purpose": "sell_side", "decisions": {
        "L2": _st({"churn_at": "effective_date", "conflicting_records": "contract_as_amended"}),
        "L5": _st("annualize_coterm_only")}}
    p, lines, _a, _e = _res(doc)
    _check(bad, _at(p, "policies", "lifecycle", "position") == "grace"
           and not any("INCOHERENT" in x for x in lines), f"L2 whole + L5: {lines}")
    # A changed purpose: a field the old purpose derived never votes as stated.
    d = _rt(_res({"company": "X", "purpose": "sell_side",
                  "decisions": {"V5": _st({"price": "net_of_channel"})}})[0])
    d["purpose"] = "buy_side"
    p = _res(d)[0]
    _check(bad, _at(p, "policies", "lifecycle", "position") == "live_paying"
           and _at(p, "decisions", "V5", "value", "start") == "end_customer_activation",
           f"V5 after a purpose change: {p['policies']['lifecycle']}")
    # Changed answers: a field derived before is derived afresh, never an override.
    d = _rt(_res({"company": "X", "purpose": "sell_side",
                  "policies": {"source": {"position": "contract", "set_by": "answer"}},
                  "decisions": {"V1": _st({"step": "current_step"}),
                                "L4": _st({"short_terminated": "service_months_only"})}})[0])
    d["policies"]["source"] = {"position": "recognized_run_rate", "set_by": "answer"}
    d["conventions"]["outlier_threshold_pct"] = {"value": 10, "set_by": "answer"}
    p, lines, _a, _e = _res(d)
    _check(bad, not lines or not any(x.startswith(("OVERRIDE", "RULE-BREACH")) for x in lines),
           f"V1/L4 after changed answers: fabricated {lines}")
    _check(bad, _at(p, "decisions", "V1", "value", "billing_only_step_ups") == "as_billed"
           and _at(p, "decisions", "L4", "value", "document_threshold_pct") == 10,
           "V1/L4 after changed answers: derived fields not derived afresh")
    # The valid neighbour: a field stated against its answered derivation is an override.
    answered = {"company": "X", "purpose": "sell_side", "policies": {
        "source": {"position": "contract", "set_by": "answer"},
        "recurrence": {"position": "plus_services_warranty", "set_by": "answer"}}}
    lines = _res({**answered, "decisions": {
        "V1": _st({"step": "current_step", "billing_only_step_ups": "as_billed"})}})[1]
    _check(bad, any(x.startswith("OVERRIDE V1") for x in lines), "V1 stated as_billed: no OVERRIDE")
    # A field the catalog fixes is a rule breach, not an override.
    doc = {"company": "X", "purpose": "sell_side", "decisions": {"R5": _st({"outright_sales": "include"})}}
    p, lines, _a, _e = _res(doc)
    _check(bad, _at(p, "decisions", "R5", "rule_breach") and any(x.startswith("RULE-BREACH R5") for x in lines)
           and not any(x.startswith("OVERRIDE R5") for x in lines), f"R5 outright include: {lines}")
    lines = _res({**answered, "decisions": {"R5": _st({"bundled": "exclude"})}})[1]
    _check(bad, any(x.startswith("OVERRIDE R5") for x in lines)
           and not any(x.startswith("RULE-BREACH") for x in lines), f"R5 bundled exclude: {lines}")
    # L4's threshold is the outlier_threshold_pct convention, not a breach of the rule.
    doc = {"company": "X", "purpose": "sell_side", "decisions": {"L4": _st({"document_threshold_pct": 10})}}
    p, lines, _a, e = _res(doc)
    _check(bad, not e and not any("RULE-BREACH" in x for x in lines)
           and _at(p, "conventions", "outlier_threshold_pct", "value") == 10
           and _at(p, "decisions", "L4", "value", "document_threshold_pct") == 10,
           f"L4 threshold 10: {lines} {e}")
    e = _res({**doc, "conventions": {"outlier_threshold_pct": {"value": 5, "set_by": "answer"}}})[3]
    _check(bad, any("outlier_threshold_pct" in x for x in e), "L4 10 against convention 5: no ERROR")
    lines = _res({"company": "X", "purpose": "sell_side",
                  "decisions": {"L4": _st({"short_terminated": "annualize"})}})[1]
    _check(bad, any(x.startswith("RULE-BREACH L4") for x in lines), "L4 annualize: no RULE-BREACH")
    return bad


def _conventions() -> list[str]:
    """A convention is valid, whole, stated once, and set exactly when a figure needs it."""
    bad = []
    base = {"company": "X", "purpose": "sell_side"}
    # A composite stated in part takes its default for the rest, and asks about it.
    p, _l, asks, e = _res({**base, "conventions": {"retention": {
        "value": {"basis": "trailing_12m_revenue"}, "set_by": "stated", "cite": "10-K"}},
        "decisions": {"A2": _st({"entry": "first_full_month"})}})
    _check(bad, not e and is_complete(p)
           and _at(p, "decisions", "A6", "value") == {"basis": "trailing_12m_revenue",
                                                      "grain": "customer", "grr_cap": "per_customer"}
           and _at(p, "conventions", "retention", "default_fields") == ["grain", "grr_cap"]
           and _at(p, "decisions", "A2", "value") == {"entry": "first_full_month", "window_months": 12}
           and any(x.startswith("ASK convention retention") for x in asks),
           f"partial retention/acquired: {p['decisions']['A6']} {p['decisions']['A2']}")
    p = _res({**base, "conventions": {"retention": {"value": {
        "basis": "trailing_12m_revenue", "grain": "customer", "grr_cap": "none"}, "set_by": "answer"}}})[0]
    _check(bad, "default_fields" not in p["conventions"]["retention"], "whole retention: default_fields")
    # `none` only where the catalog offers it; numbers in range.
    for k, v in (("fx", "none"), ("entry_event", "none"), ("signing_lag_months", "none"),
                 ("signing_lag_months", -1), ("outlier_threshold_pct", 150),
                 ("outlier_threshold_pct", float("nan")),
                 ("acquired", {"entry": "close_date", "window_months": -12})):
        e = _res({**base, "conventions": {k: {"value": v, "set_by": "answer"}}})[3]
        _check(bad, any(x.startswith(f"conventions.{k}") for x in e), f"conventions.{k}={v}: no ERROR")
    e = _res({**base, "decisions": {"L3": _st({"treatment": "grace_window", "grace_months": -3})}})[3]
    _check(bad, any(x.startswith("decisions.L3") for x in e), "L3 grace_months -3: no ERROR")
    for k, v in (("outlier_threshold_pct", "none"), ("signing_lag_months", 0), ("outlier_threshold_pct", 0)):
        e = _res({**base, "conventions": {k: {"value": v, "set_by": "answer"}}})[3]
        _check(bad, not e, f"conventions.{k}={v}: {e}")
    # The window: stated once, set only where a figure needs one, and then not point_in_time.
    rr = {**base, "policies": {"source": "recognized_run_rate"}}
    for doc, want in (
            ({**rr, "conventions": {"window": {"value": "month_x12", "set_by": "answer"}},
              "decisions": {"S2": _st("trailing_12_months")}}, "state the `window` convention once"),
            ({**rr, "decisions": {"S2": _st("point_in_time")}}, "a figure needs it"),
            ({**base, "decisions": {"S2": _st("trailing_12_months")}}, "no figure uses it"),
            ({**base, "conventions": {"window": {"value": "trailing_12_months", "set_by": "answer"}}},
             "no figure uses it")):
        e = _res(doc)[3]
        _check(bad, any(want in x for x in e), f"window {doc.get('conventions')} {doc['decisions'] if 'decisions' in doc else ''}: {e}")
    for doc, s2 in (({**rr, "conventions": {"window": {"value": "month_x12", "set_by": "answer"}}}, "month_x12"),
                    ({**rr, "conventions": {"window": {"value": "month_x12", "set_by": "answer"}},
                      "decisions": {"S2": _st("month_x12")}}, "month_x12"),
                    ({**base, "decisions": {"S2": _st("point_in_time")}}, "point_in_time"),
                    (base, "point_in_time")):
        p, _l, _a, e = _res(doc)
        _check(bad, not e and p["decisions"]["S2"]["value"] == s2, f"window neighbour {doc}: {e}")
    # A flow a stated decision measures needs a window, whatever the source.
    contract = {**base, "policies": {"source": {"position": "contract", "set_by": "answer"}}}
    for i, v in (("S3", "ratable_revenue"), ("S4", "recognized_revenue"), ("S5", {"timing": "at_issuance"})):
        p, _l, _a, e = _res({**contract, "decisions": {i: _st(v)}})
        _check(bad, not e and p["decisions"]["S2"]["value"] == "trailing_3_months",
               f"{i} {v} under a contract source: S2 {p['decisions']['S2']}")
    return bad


def _instructions() -> list[str]:
    """One id names one instruction: well formed, never reused for another text, and a
    repeat under its own id is skipped."""
    bad = []
    import arr_policy
    import check_playbook
    _check(bad, arr_policy.CHECK_ID == check_playbook.CHECK_ID.pattern,
           f"arr_policy.CHECK_ID {arr_policy.CHECK_ID} is not check_playbook.CHECK_ID "
           f"{check_playbook.CHECK_ID.pattern}")
    one = {"text": "Certificate reissues count once.", "source": "inferred", "basis": "S5",
           "applies_to": ["S5"]}
    for ins, want_err, want_n in (
            ([{**one, "id": "I.tie-01.1"}], True, 0),
            ([{**one, "id": "I.tie_01.1"}, {**one, "id": "I.tie_01.1", "text": "Other."}], True, 1),
            ([{**one, "id": "I.tie_01.1"}, {**one, "id": "I.tie_01.1"}], False, 1),
            ([{**one, "source": "user"}, {**one, "source": "user"}], False, 1),
            ([{**one, "id": "I.tie_01.1"}, {**one, "id": "I.tie_01.2"}], False, 2)):
        errors: list[str] = []
        out = instructions({"instructions": ins}, errors)
        _check(bad, bool(errors) == want_err and len(out) == want_n,
               f"instructions {[x.get('id') for x in ins]}: {errors}, {len(out)} kept")
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        policy = _res({"company": "X", "purpose": "sell_side"})[0]

        def run(gaps: dict) -> tuple[int, str]:
            (t / "gaps.yaml").write_text(yaml.safe_dump(gaps))
            args = types.SimpleNamespace(gaps=[t / "gaps.yaml"], answers=None, run="r1",
                                         out=t / "out.yaml")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = amend(copy.deepcopy(policy), args)
            return rc, buf.getvalue()
        g = {"inferred": [{"id": "I.tie_01.1", "text": one["text"], "applies_to": ["S5"], "basis": "S5"}]}
        rc, out = run(g)
        _check(bad, rc == 0 and "ADDED I.tie_01.1" in out, f"amend a new instruction: {rc} {out}")
        policy = yaml.safe_load((t / "out.yaml").read_text())
        rc, out = run(g)
        _check(bad, rc == 0 and "ADDED" not in out, f"amend the same gaps again: {out}")
        rc, out = run({"inferred": [{**g["inferred"][0], "text": "A prepaid balance is not ARR."}]})
        _check(bad, rc == 1 and "already names another instruction" in out, f"amend a reused id: {out}")
        rc, out = run({"inferred": [{**g["inferred"][0], "id": "I.tie-01.2"}]})
        _check(bad, rc == 1 and "I.<check_id>.<n>" in out, f"amend a malformed id: {out}")
    return bad


def _cli() -> list[str]:
    """approve stamps only its own resolution; check passes only that file, unchanged."""
    bad = []
    script = SCRIPTS / "arr_policy.py"

    def cli(*args) -> tuple[int, str]:
        r = subprocess.run([sys.executable, str(script), *map(str, args)],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr
    with tempfile.TemporaryDirectory() as tmp:
        t = pathlib.Path(tmp)
        (t / "in.yaml").write_text(yaml.safe_dump({"company": "X", "purpose": "public_reporting",
                                                   "decisions": {"L2": _st({"churn_at": "at_notice"})}}))
        rc, out = cli("resolve", t / "in.yaml", "--out", t / "draft.yaml")
        _check(bad, rc == 0, f"resolve: {out}")
        rc, out = cli("approve", t / "draft.yaml", "--by", "J", "--out", t / "ok.yaml")
        _check(bad, rc == 0 and "SAVED" in out, f"approve its own draft: {out}")
        if rc:
            return bad
        rc, out = cli("check", t / "ok.yaml")
        _check(bad, rc == 0 and out.startswith("OK"), f"check the approved file: {out}")
        _check(bad, (t / "draft.yaml").read_text().split("status:")[0]
               == (t / "ok.yaml").read_text().split("status:")[0], "approve rewrote the draft's head")

        def edited(src: str, dest: str, edit) -> pathlib.Path:
            d = yaml.safe_load((t / src).read_text())
            edit(d)
            (t / dest).write_text(yaml.safe_dump(d, sort_keys=False))
            return t / dest
        f = edited("draft.yaml", "hand.yaml", lambda d: d["policies"].__setitem__(
            "value", {"position": "net_all", "set_by": "stated"}))
        rc, out = cli("approve", f, "--by", "J", "--out", t / "x.yaml")
        _check(bad, rc == 2 and "REFUSED" in out, f"approve a hand-edited draft: {out}")
        f = edited("ok.yaml", "tampered.yaml", lambda d: d["decisions"]["S1"].__setitem__("value", "billed_spread"))
        rc, out = cli("check", f)
        _check(bad, rc == 2 and "NOT-CONSISTENT" in out, f"check a tampered decision: {out}")

        def fx(d):
            d["conventions"]["fx"] = {"value": "period_average_rate", "set_by": "answer"}
            d["decisions"]["V4"]["value"] = "period_average_rate"
        rc, out = cli("check", edited("ok.yaml", "fx.yaml", fx))
        _check(bad, rc == 2 and "changed after it was approved" in out, f"check a consistent edit: {out}")
        f = edited("draft.yaml", "forged.yaml", lambda d: d.update(
            status="approved", approved={"by": "nobody", "at": "2026-01-01T00:00:00Z"}))
        rc, out = cli("check", f)
        _check(bad, rc == 2 and "NOT-APPROVED" in out, f"check a forged approval: {out}")
        # render: a bare value renders, and free text never splits a table row.
        (t / "bare.yaml").write_text("company: X\npurpose: sell_side\npolicies: {source: contract}\n"
                                     "instructions:\n  - {text: \"A | B\\nper plan\", source: user}\n")
        rc, out = cli("render", t / "bare.yaml")
        _check(bad, rc == 0 and "| Signed contract value, as modified |" in out
               and "A \\| B per plan" in out,
               f"render a bare value and a piped text: {rc} {out[-300:]}")
        text = render(_res({"company": "X", "purpose": "sell_side"})[0])
        _check(bad, "**Settled:** 31 of 31" in text, "render of a resolved policy")
    return bad


def _computing_gaps() -> list[str]:
    """Every decision has a paragraph in ARR_POLICY.md § Computing ARR, opened by its
    bold id, and that paragraph names every option and field in backticks: an option
    added here without its computing rule fails the selftest."""
    doc = SCRIPTS.parent / "reference" / "ARR_POLICY.md"
    m = re.search(r"^## Computing ARR\n(.*?)(?=^## |\Z)", doc.read_text(), re.S | re.M)
    if not m:
        return ["ARR_POLICY.md carries no § Computing ARR"]
    marks = list(re.finditer(r"^\*\*([SRLVA]\d) ", m.group(1), re.M))
    block = {x.group(1): m.group(1)[x.start():marks[i + 1].start() if i + 1 < len(marks)
                                   else len(m.group(1))] for i, x in enumerate(marks)}
    bad = []
    for d in DECISIONS:
        text = block.get(d["id"])
        if text is None:
            bad.append(f"{d['id']}: no paragraph in ARR_POLICY.md § Computing ARR")
            continue
        names = list(d["options"]) if isinstance(d.get("options"), list) else []
        for f, opts in (d.get("fields") or {}).items():
            names += [f] + (list(opts) if isinstance(opts, list) else [])
        names += [k for k, s in CONVENTIONS.items()
                  if s["decision"] == d["id"] and not isinstance(s.get("options"), list)
                  and "fields" not in s]
        for n in names:
            if f"`{n}`" not in text:
                bad.append(f"{d['id']}: `{n}` has no rule in ARR_POLICY.md § Computing ARR")
    return bad


def main() -> int:
    bad = selftest()
    for b in bad:
        print(b)
    print("arr_policy selftest: " + ("ok" if not bad else f"{len(bad)} defect(s)"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
