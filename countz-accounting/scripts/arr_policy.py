#!/usr/bin/env python3
"""The ARR policy: the one home of its catalog, and the tool that settles, renders,
approves and checks a company's `arr_policy.yaml` (reference/ARR_POLICY.md).

    arr_policy.py catalog [--json]                    # the purposes, policies, conventions, 31 decisions
    arr_policy.py new --company "<name>" [--purpose <p>] --out <file>
    arr_policy.py resolve <in.yaml|json> [--out <file>]  # infer, derive, report what is missing
    arr_policy.py render <file>                       # the one presentation the user approves
    arr_policy.py approve <file> --by "<name>" --out <dest>
    arr_policy.py check <file>                        # exit 0 only for a complete, approved policy
    arr_policy.py amend <file> --gaps <gaps-*.yaml>... [--answers <answers.yaml>] --out <draft>
                                                      # add the instructions a run's steps found
    arr_policy.py same-core <a> <b>                   # exit 0 when b only adds instructions to a

An ARR policy settles every one of the 31 decisions (ARR_POLICY.md § The decisions) from
four top-level policy positions, a set of conventions, seven fixed rules, and the
overrides the company records where it departs from them. A decision is never asked on
its own while a position or a convention can settle it.

`resolve` reads a partial policy — a purpose, positions, conventions, and any decisions
the company's own documents state (`basis: stated`, with `cite`) — and:

- takes each unset position from the stated decisions that position decides, choosing the
  position most of them agree with; a stated decision that disagrees becomes an override;
- takes each position still unset from `purpose`, when one is set;
- defaults each convention that is still unset and marks it `set_by: default`;
- derives every decision no statement or override settles.

It prints one line per finding and exits 0 when every decision is settled, 2 when the
policy still needs answers (each `ASK` line is one question, in the order to ask them),
and 1 on a malformed input. Lines:

    POSITION <policy>=<position> <how it was set>
    INCOHERENT <policy> <why> -- candidates: <positions>
    OVERRIDE <id> <value> (<policy> derives <value>)
    RULE-BREACH <id> <value> (the rule fixes <value>)
    ASK purpose | ASK policy <name> [candidates] | ASK convention <name> default=<value>
    STATUS complete | incomplete (<n> questions)

**Instructions** are the policy's free-text part (ARR_POLICY.md § Instructions): how a
decision applies to this business's own products and records, where no option can say
it. Each is `{id, text, applies_to: [decision ids], source: user | stated | inferred,
basis?, cite?, added?}`. `resolve` validates them and carries them unchanged; `amend`
adds the ones a run's steps inferred and the user's answers to the questions they raised
(ARR_POLICY.md § Applying the policy).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import re
import sys

SCHEMA = "countz-accounting/arr-policy@1"

# Where every policy file points its reader before any value in it is used. A worker that
# opens the policy to read a decision meets this first (ARR_POLICY.md § Applying the policy).
APPLY_PER = "${CLAUDE_PLUGIN_ROOT}/reference/ARR_POLICY.md § Applying the policy"
HEADER = (
    "# ARR policy. Before you use any value in this file, read how it is applied:\n"
    "#   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py reference/ARR_POLICY.md "
    "\"Applying the policy\"\n"
    "# It says how decisions and instructions are applied and cited, and what to do with a\n"
    "# question this policy does not answer. Edit this file only through arr_policy.py.\n")

# ---------------------------------------------------------------------------- catalog

PURPOSES = {
    "operator": "Operator forecasting: contract value, forward-looking; signed-not-started "
                "counted and renewal assumed",
    "public_reporting": "Public reporting: a disclosed definition over active contracts",
    "sell_side": "Sell-side diligence: contract value corroborated by billing; a "
                 "defensible upper bound",
    "buy_side": "Buy-side diligence or lender: only what contract, invoice and cash agree "
                "on; live, paying customers",
}

POLICIES = {
    "source": {
        "question": "Which record do we trust for the amount?",
        "positions": {
            "all_agree": "Only where contract, invoice and cash all agree",
            "contract": "Signed contract value, as modified",
            "recognized_run_rate": "Recognized revenue, annualized",
            "billed_spread": "Billed amounts spread over their service periods, annualized",
        },
    },
    "recurrence": {
        "question": "Would this revenue come back next year without a new sale?",
        "positions": {
            "subscription_only": "Fixed-fee subscriptions and term licences only",
            "plus_services_warranty": "+ recurring services, maintenance and warranty, "
                                      "bundled equipment",
            "plus_usage_commit": "+ committed consumption minimums",
            "plus_usage_actual": "+ actual usage above the commitment and uncommitted usage",
        },
    },
    "lifecycle": {
        "question": "When does a customer's ARR start, and when does it stop?",
        "positions": {
            "live_paying": "Live (end customer activated), paying, no notice received",
            "effective_termination": "Go-live to the effective termination date",
            "grace": "+ a grace window for late renewals and holdover service",
            "signed_assumed": "+ signed-not-started contracts, renewal assumed",
        },
    },
    "value": {
        "question": "At what annual price?",
        "positions": {
            "net_all": "Net of discounts, all credits and channel margin; current ramp step",
            "net_current_step": "Net contract price at the current ramp step",
            "contract_average": "Contract price before credits; ramps at the term average",
            "list_gross": "List or renewal price; gross of channel",
        },
    },
}

PURPOSE_POSITIONS = {
    "operator": {"source": "contract", "recurrence": "plus_usage_commit",
                 "lifecycle": "signed_assumed", "value": "contract_average"},
    "public_reporting": {"source": "contract", "recurrence": "plus_usage_commit",
                         "lifecycle": "grace", "value": "net_current_step"},
    "sell_side": {"source": "contract", "recurrence": "plus_services_warranty",
                  "lifecycle": "grace", "value": "net_current_step"},
    "buy_side": {"source": "all_agree", "recurrence": "subscription_only",
                 "lifecycle": "live_paying", "value": "net_all"},
}

# A convention is a choice no position decides. `fields` for a composite value; `needed`
# names when it bears on any figure (None: always); where it does not, its value is `none`.
CONVENTIONS = {
    "window": {
        "decision": "S2", "label": "Measurement window for flow-based ARR",
        "options": ["month_x12", "trailing_3_months", "trailing_12_months"],
        "default": "trailing_3_months",
        "needed": lambda p: p.get("source") in ("recognized_run_rate", "billed_spread")
        or p.get("recurrence") == "plus_usage_actual",
        "not_needed": "point_in_time",
        "why_not_needed": "a contract snapshot at the date needs no window",
        "needed_text": "when source is recognized_run_rate or billed_spread, or recurrence "
                       "is plus_usage_actual",
    },
    "fx": {
        "decision": "V4", "label": "Currency translation rate",
        "options": ["prior_year_end_rate", "start_of_year_rate", "contract_signing_rate",
                    "period_average_rate", "closing_spot_rate"],
        "default": "prior_year_end_rate", "needed": None,
    },
    "modification_classes": {
        "decision": "A1", "label": "Bridge classes for mid-term modifications",
        "options": ["register_type", "price_vs_quantity"],
        "default": "register_type", "needed": None,
    },
    "acquired": {
        "decision": "A2", "label": "Acquired ARR: entry and organic window",
        "fields": {"entry": ["close_date", "first_full_month"],
                   "window_months": "int"},
        "default": {"entry": "close_date", "window_months": 12}, "needed": None,
    },
    "customer_unit": {
        "decision": "A3", "label": "The customer unit for logos and retention",
        "options": ["root_parent", "bill_to", "payer"],
        "default": "root_parent", "needed": None,
    },
    "retention": {
        "decision": "A6", "label": "Retention formula",
        "fields": {"basis": ["point_to_point_arr", "trailing_12m_revenue"],
                   "grain": ["customer", "customer_product"],
                   "grr_cap": ["per_customer", "none"]},
        "default": {"basis": "point_to_point_arr", "grain": "customer",
                    "grr_cap": "per_customer"}, "needed": None,
    },
    "signing_lag_months": {
        "decision": "L1", "label": "Months after the signing month a new stream enters ARR",
        "options": "int", "default": 0, "needed": None,
    },
    "outlier_threshold_pct": {
        "decision": "L4", "label": "Contract size, % of ARR, that needs document support",
        "options": "number", "default": 5, "needed": None,
    },
}


def _ix(pol: str, pos: str | None) -> int:
    return list(POLICIES[pol]["positions"]).index(pos) if pos else -1


def _by(pol, table):
    """A derivation by position: `table` lists the value for each position, in order."""
    return lambda p, c: table[_ix(pol, p[pol])]


def _conv(name):
    return lambda p, c: c[name]


# Every decision: id, name, type (policy | rule | convention), the policies whose
# position decides it (`by`), those that constrain it (`constrained_by`), its options (a
# list, or `fields` for a composite value), and `derive(positions, conventions)`. A
# composite decided by two policies names which field each decides (`field_by`).
DECISIONS = [
    # Source
    {"id": "S1", "name": "ARR basis", "type": "policy", "by": ["source"],
     "options": list(POLICIES["source"]["positions"]),
     "derive": lambda p, c: p["source"]},
    {"id": "S2", "name": "Measurement window", "type": "convention", "by": [],
     "constrained_by": ["source", "recurrence"],
     "options": ["point_in_time", "month_x12", "trailing_3_months", "trailing_12_months"],
     "derive": _conv("window")},
    {"id": "S3", "name": "Multi-year and prepaid contracts", "type": "policy",
     "by": ["source"], "constrained_by": ["value"],
     "options": ["annualized_contract", "ratable_revenue"],
     "derive": _by("source", ["annualized_contract", "annualized_contract",
                              "ratable_revenue", "annualized_contract"])},
    {"id": "S4", "name": "Term or perpetual licences recognized upfront", "type": "policy",
     "by": ["source"], "options": ["annualized_contract", "recognized_revenue"],
     "derive": _by("source", ["annualized_contract", "annualized_contract",
                              "recognized_revenue", "annualized_contract"])},
    {"id": "S5", "name": "Point-in-time products bought repeatedly (e.g. certificates)",
     "type": "policy", "by": ["source", "recurrence"],
     "fields": {"timing": ["coverage_per_year", "at_issuance"],
                "one_off": ["exclude", "after_first_renewal", "include"]},
     "field_by": {"timing": "source", "one_off": "recurrence"},
     "derive": lambda p, c: {
         "timing": "at_issuance" if p["source"] == "recognized_run_rate" else "coverage_per_year",
         "one_off": ["exclude", "after_first_renewal", "after_first_renewal",
                     "include"][_ix("recurrence", p["recurrence"])]}},
    {"id": "S6", "name": "Prepaid funds and drawdown balances", "type": "rule", "by": [],
     "constrained_by": ["recurrence"], "options": ["not_arr", "annualize_balance"],
     "derive": lambda p, c: "not_arr"},
    {"id": "S7", "name": "Revenue run-rate labeled as ARR", "type": "rule", "by": [],
     "options": ["not_arr", "report_as_arr"], "derive": lambda p, c: "not_arr"},
    # Recurrence
    {"id": "R1", "name": "Consumption with a committed minimum", "type": "policy",
     "by": ["recurrence"], "constrained_by": ["source"],
     "options": ["exclude", "commit_only", "commit_plus_usage"],
     "derive": _by("recurrence", ["exclude", "exclude", "commit_only", "commit_plus_usage"])},
    {"id": "R2", "name": "Overage and true-ups billed in arrears", "type": "policy",
     "by": ["recurrence"], "options": ["exclude", "include"],
     "derive": _by("recurrence", ["exclude", "exclude", "exclude", "include"])},
    {"id": "R3", "name": "Professional services and setup bundled in the deal", "type": "rule",
     "by": [], "constrained_by": ["source", "value"],
     "fields": {"treatment": ["exclude", "include"],
                "carve_out": ["contract_line_then_ssp", "contract_line", "ssp_allocation"]},
     "derive": lambda p, c: {"treatment": "exclude", "carve_out": "contract_line_then_ssp"}},
    {"id": "R4", "name": "Recurring services: premium support, managed services, data plans",
     "type": "policy", "by": ["recurrence"], "constrained_by": ["value"],
     "options": ["exclude", "include"],
     "derive": _by("recurrence", ["exclude", "include", "include", "include"])},
    {"id": "R5", "name": "Hardware: outright sale vs hardware-as-a-service", "type": "policy",
     "by": ["recurrence"],
     "fields": {"outright_sales": ["exclude", "include"], "bundled": ["exclude", "include"]},
     "fixed_fields": {"outright_sales": "exclude"},
     "derive": lambda p, c: {"outright_sales": "exclude",
                             "bundled": "exclude" if p["recurrence"] == "subscription_only"
                             else "include"}},
    {"id": "R6", "name": "Maintenance or warranty attached to hardware", "type": "policy",
     "by": ["recurrence"], "options": ["exclude", "include_term_contracted", "include"],
     "derive": _by("recurrence", ["exclude", "include_term_contracted",
                                  "include_term_contracted", "include"])},
    {"id": "R7", "name": "Pilots, trials, break clauses and refund windows", "type": "rule",
     "by": [], "constrained_by": ["lifecycle"],
     "fields": {"pilots": ["exclude", "include"],
                "refund_window": ["count_after_window", "count_at_booking"]},
     "derive": lambda p, c: {"pilots": "exclude", "refund_window": "count_after_window"}},
    # Lifecycle
    {"id": "L1", "name": "Signed but not started (CARR vs ARR), and entry after signing",
     "type": "policy",
     "by": ["lifecycle"], "options": ["exclude_report_separately", "include"],
     "derive": _by("lifecycle", ["exclude_report_separately", "exclude_report_separately",
                                 "exclude_report_separately", "include"])},
    {"id": "L2", "name": "Churn timing, and which termination record wins", "type": "policy",
     "by": ["lifecycle"], "constrained_by": ["source"],
     "fields": {"churn_at": ["at_notice", "effective_date"],
                "conflicting_records": ["earliest_end", "modification_register",
                                        "last_recognized_month", "last_billed_service_period"]},
     "derive": lambda p, c: {
         "churn_at": "at_notice" if p["lifecycle"] == "live_paying" else "effective_date",
         "conflicting_records": ["earliest_end", "modification_register",
                                 "last_recognized_month",
                                 "last_billed_service_period"][_ix("source", p["source"])]}},
    {"id": "L3", "name": "Renewal gaps, holdover and grace periods", "type": "policy",
     "by": ["lifecycle"],
     "fields": {"treatment": ["grace_window", "continuation"], "grace_months": "int"},
     "derive": lambda p, c: {
         "treatment": "continuation" if p["lifecycle"] == "signed_assumed" else "grace_window",
         "grace_months": 3 if p["lifecycle"] == "grace" else 0}},
    {"id": "L4", "name": "Outlier and short-lived contracts", "type": "rule", "by": [],
     "constrained_by": ["source"],
     "fields": {"short_terminated": ["service_months_only", "annualize"],
                "document_threshold_pct": "number"},
     "derive": lambda p, c: {"short_terminated": "service_months_only",
                             "document_threshold_pct": c["outlier_threshold_pct"]}},
    {"id": "L5", "name": "Stub, co-term and month-to-month contracts", "type": "policy",
     "by": ["lifecycle"], "options": ["exclude", "annualize_coterm_only", "annualize_all"],
     "derive": _by("lifecycle", ["exclude", "annualize_coterm_only",
                                 "annualize_coterm_only", "annualize_all"])},
    {"id": "L6", "name": "Collectability and bad debt", "type": "policy",
     "by": ["lifecycle"], "constrained_by": ["value"],
     "options": ["exclude_written_off_and_90_days", "exclude_written_off",
                 "include_until_terminated"],
     "derive": _by("lifecycle", ["exclude_written_off_and_90_days", "exclude_written_off",
                                 "exclude_written_off", "include_until_terminated"])},
    # Value
    {"id": "V1", "name": "Ramps and escalators", "type": "policy", "by": ["value"],
     "constrained_by": ["source"],
     "fields": {"step": ["current_step", "term_average"],
                "billing_only_step_ups": ["require_contract_evidence", "as_billed"]},
     "derive": lambda p, c: {
         "step": ["current_step", "current_step", "term_average",
                  "term_average"][_ix("value", p["value"])],
         "billing_only_step_ups": "require_contract_evidence"
         if p["source"] in ("all_agree", "contract") else "as_billed"}},
    {"id": "V2", "name": "Discounts and free months", "type": "policy", "by": ["value"],
     "options": ["net_current", "net_term_average", "list_price"],
     "derive": _by("value", ["net_current", "net_current", "net_term_average", "list_price"])},
    {"id": "V3", "name": "Credits, refunds and SLA credits", "type": "policy", "by": ["value"],
     "options": ["net_all_credits", "net_recurring_credits", "before_credits"],
     "derive": _by("value", ["net_all_credits", "net_recurring_credits", "before_credits",
                             "before_credits"])},
    {"id": "V4", "name": "Currency translation", "type": "convention", "by": [],
     "constrained_by": ["value"], "options": CONVENTIONS["fx"]["options"],
     "derive": _conv("fx")},
    {"id": "V5", "name": "Channel: sell-in vs sell-through, gross vs net", "type": "policy",
     "by": ["value", "lifecycle"], "constrained_by": ["attribution"],
     "fields": {"price": ["net_of_channel", "gross"],
                "start": ["end_customer_activation", "sell_in"]},
     "field_by": {"price": "value", "start": "lifecycle"},
     "derive": lambda p, c: {
         "price": "gross" if p["value"] == "list_gross" else "net_of_channel",
         "start": "end_customer_activation" if p["lifecycle"] == "live_paying" else "sell_in"}},
    # Attribution
    {"id": "A1", "name": "Mid-term modifications: bridge classes", "type": "convention",
     "by": [], "options": CONVENTIONS["modification_classes"]["options"],
     "derive": _conv("modification_classes")},
    {"id": "A2", "name": "Acquired ARR and organic growth", "type": "convention", "by": [],
     "constrained_by": ["lifecycle"], "fields": CONVENTIONS["acquired"]["fields"],
     "derive": _conv("acquired")},
    {"id": "A3", "name": "Customer unit: bill-to, parent or payer", "type": "convention",
     "by": [], "options": CONVENTIONS["customer_unit"]["options"],
     "derive": _conv("customer_unit")},
    {"id": "A4", "name": "Reallocations between customers", "type": "rule", "by": [],
     "constrained_by": ["source"], "options": ["not_churn_with_evidence", "as_recorded"],
     "derive": lambda p, c: "not_churn_with_evidence"},
    {"id": "A5", "name": "Opening base and reactivation", "type": "rule", "by": [],
     "constrained_by": ["lifecycle"], "options": ["opening", "new"],
     "derive": lambda p, c: "opening"},
    {"id": "A6", "name": "Net and gross revenue retention definitions", "type": "convention",
     "by": [], "fields": CONVENTIONS["retention"]["fields"], "derive": _conv("retention")},
]
DEC = {d["id"]: d for d in DECISIONS}
GROUP = {"S": "source", "R": "recurrence", "L": "lifecycle", "V": "value", "A": "attribution"}


def _derived_at(d: dict, pol: str, pos: str, positions: dict, conv: dict):
    """The value `d` derives when `pol` sits at `pos` and the others where they are.
    Unset positions are filled with the first position so a derivation can run; only
    the field `pol` decides is compared, so the filler never decides anything."""
    p = {k: positions.get(k) or next(iter(POLICIES[k]["positions"])) for k in POLICIES}
    p[pol] = pos
    return d["derive"](p, conv)


def _field_of(d: dict, pol: str) -> str | None:
    """For a composite decided by two policies, the field `pol` decides."""
    for f, owner in (d.get("field_by") or {}).items():
        if owner == pol:
            return f
    return None


def _agrees(d: dict, pol: str, stated, derived) -> bool | None:
    """Whether a stated value agrees with the derived one on what `pol` decides; None
    when the statement says nothing about that part."""
    if "fields" in d:
        keys = [_field_of(d, pol)] if d.get("field_by") else \
            [k for k in d["fields"] if k not in (d.get("fixed_fields") or {})]
        keys = [k for k in keys if k and isinstance(stated, dict) and k in stated]
        if not keys:
            return None
        return all(stated[k] == derived[k] for k in keys)
    return stated == derived


# ---------------------------------------------------------------------------- io

def _load(path: pathlib.Path) -> dict:
    text = path.read_text()
    try:
        import yaml
    except ImportError:
        try:
            return json.loads(text)
        except ValueError:
            raise SystemExit("arr_policy: PyYAML is not importable - run this script as "
                             "`uv run --project <plugin root> python3 scripts/arr_policy.py ...`")
    return yaml.safe_load(text) or {}


def _dump(obj: dict) -> str:
    """Every policy file is written here, so every one carries the header and `apply_per`,
    however many times it is resolved, amended or approved."""
    obj = {"schema": obj.get("schema", SCHEMA), "apply_per": APPLY_PER,
           **{k: v for k, v in obj.items() if k not in ("schema", "apply_per")}}
    try:
        import yaml
    except ImportError:
        return json.dumps(obj, indent=2) + "\n"
    return HEADER + yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, width=100)


# What a resolve recomputes rather than carries forward: a position the purpose or the
# stated decisions set, a defaulted convention, a derived decision. Only what a document
# stated or the user answered survives a re-resolve, so changing the purpose never
# leaves a stale position behind.
RECOMPUTED = {"purpose", "inferred", "default", "not_needed"}


def _slot(v, key="position"):
    """A policy or convention entry may be written as a bare value or as a mapping."""
    if isinstance(v, dict):
        if key not in v or v.get("set_by") in RECOMPUTED:
            return {}
        return dict(v)
    return {key: v} if v is not None else {}


def _valid_value(d_or_opts, value) -> str | None:
    spec = d_or_opts
    if isinstance(spec, dict) and "fields" in spec:
        if not isinstance(value, dict):
            return f"expects a mapping of {', '.join(spec['fields'])}"
        for k, v in value.items():
            if k not in spec["fields"]:
                return f"has no field `{k}` (fields: {', '.join(spec['fields'])})"
            err = _valid_value({"options": spec["fields"][k]}, v)
            if err:
                return f"`{k}` {err}"
        return None
    opts = spec["options"] if isinstance(spec, dict) else spec
    if opts == "int":
        return None if isinstance(value, int) and not isinstance(value, bool) else "expects a whole number"
    if opts == "number":
        return None if isinstance(value, (int, float)) and not isinstance(value, bool) else "expects a number"
    if value not in opts:
        return f"`{value}` is not one of: {', '.join(map(str, opts))}"
    return None


# ---------------------------------------------------------------------------- resolve

INSTRUCTION_SOURCES = ("user", "stated", "inferred")


def instructions(doc: dict, errors: list[str]) -> list[dict]:
    """Validate the free-text instructions and give each a stable id (I1, I2, ...)."""
    raw = doc.get("instructions") or []
    if not isinstance(raw, list):
        errors.append("instructions: a list of {text, applies_to, source, ...}")
        return []
    out, seen_ids, seen_text = [], set(), set()
    taken = {str(e.get("id")) for e in raw if isinstance(e, dict) and e.get("id")}
    n = 0
    for k, e in enumerate(raw, 1):
        if isinstance(e, str):
            e = {"text": e, "source": "user"}
        if not isinstance(e, dict) or not str(e.get("text") or "").strip():
            errors.append(f"instructions[{k}]: needs `text`")
            continue
        e = dict(e)
        if e.get("source") not in INSTRUCTION_SOURCES:
            errors.append(f"instructions[{k}]: `source` is one of {', '.join(INSTRUCTION_SOURCES)}")
            continue
        if e["source"] == "inferred" and not e.get("basis"):
            errors.append(f"instructions[{k}]: an inferred instruction states its `basis` - "
                          f"the positions, conventions or decisions it follows from")
        if e["source"] == "stated" and not e.get("cite"):
            errors.append(f"instructions[{k}]: a stated instruction carries its `cite`")
        at = e.get("applies_to") or []
        at = [at] if isinstance(at, str) else list(at)
        bad = [i for i in at if i not in DEC]
        if bad:
            errors.append(f"instructions[{k}]: applies_to names no such decision: {', '.join(bad)}")
        e["applies_to"] = [i for i in at if i in DEC]
        key = " ".join(e["text"].split()).lower()
        if key in seen_text:
            continue
        seen_text.add(key)
        if not e.get("id") or str(e["id"]) in seen_ids:
            while True:
                n += 1
                if f"I{n}" not in taken and f"I{n}" not in seen_ids:
                    break
            e["id"] = f"I{n}"
        seen_ids.add(str(e["id"]))
        out.append({"id": e["id"], **{k2: v for k2, v in e.items() if k2 != "id"}})
    return out


def resolve(doc: dict) -> tuple[dict, list[str], list[str], list[str]]:
    """Settle what can be settled. Returns (policy, report lines, asks, errors)."""
    errors: list[str] = []
    lines: list[str] = []
    asks: list[str] = []

    purpose = doc.get("purpose")
    if purpose is not None and purpose not in PURPOSES:
        errors.append(f"purpose `{purpose}` is not one of: {', '.join(PURPOSES)}")
        purpose = None

    pols = {k: _slot((doc.get("policies") or {}).get(k)) for k in POLICIES}
    for k, s in pols.items():
        if s.get("position") is not None and s["position"] not in POLICIES[k]["positions"]:
            errors.append(f"policies.{k}: `{s['position']}` is not one of: "
                          f"{', '.join(POLICIES[k]['positions'])}")
            s.clear()
    for k in (doc.get("policies") or {}):
        if k not in POLICIES:
            errors.append(f"policies.{k}: no such policy ({', '.join(POLICIES)})")

    convs = {k: _slot((doc.get("conventions") or {}).get(k), "value") for k in CONVENTIONS}
    for k, s in convs.items():
        if "value" in s and s["value"] not in (None, "none"):
            err = _valid_value(CONVENTIONS[k] if "fields" in CONVENTIONS[k]
                               else {"options": CONVENTIONS[k]["options"]}, s["value"])
            if err:
                errors.append(f"conventions.{k} {err}")
                s.clear()
    for k in (doc.get("conventions") or {}):
        if k not in CONVENTIONS:
            errors.append(f"conventions.{k}: no such convention ({', '.join(CONVENTIONS)})")

    decs_in = doc.get("decisions") or {}
    stated: dict[str, dict] = {}
    for i, e in decs_in.items():
        if i not in DEC:
            errors.append(f"decisions.{i}: no such decision")
            continue
        e = e if isinstance(e, dict) and "value" in e else {"value": e}
        err = _valid_value(DEC[i], e["value"])
        if err:
            errors.append(f"decisions.{i} {err}")
            continue
        if e.get("basis") == "override" and "derived" in e:
            e = {k: v for k, v in e.items() if k != "derived"}
        if e.get("basis") in (None, "stated", "override", "answer"):
            stated[i] = e

    positions = {k: s.get("position") for k, s in pols.items()}
    conv_now = {k: (s.get("value") if s.get("value") is not None
                    else CONVENTIONS[k]["default"]) for k, s in convs.items()}

    # 1. A convention a stated decision carries is that convention's value.
    for k, spec in CONVENTIONS.items():
        i = spec["decision"]
        if i in stated and convs[k].get("value") is None and DEC[i]["type"] == "convention":
            convs[k] = {"value": stated[i]["value"], "set_by": "stated",
                        **({"cite": stated[i]["cite"]} if stated[i].get("cite") else {})}
            conv_now[k] = stated[i]["value"]

    # 2. Infer each unset position from the stated decisions it decides.
    ties: dict[str, list[str]] = {}
    for pol in POLICIES:
        if positions[pol]:
            pols[pol].setdefault("set_by", "stated")
            continue
        voters = [DEC[i] for i in stated if pol in DEC[i]["by"]]
        if not voters:
            continue
        score = {}
        for pos in POLICIES[pol]["positions"]:
            agree = disagree = 0
            for d in voters:
                a = _agrees(d, pol, stated[d["id"]]["value"],
                            _derived_at(d, pol, pos, positions, conv_now))
                if a is True:
                    agree += 1
                elif a is False:
                    disagree += 1
            score[pos] = (agree, disagree)
        best = max(v[0] for v in score.values())
        if best == 0:
            continue
        top = [pos for pos, v in score.items() if v[0] == best]
        ids = ", ".join(d["id"] for d in voters)
        if len(top) > 1 and purpose and PURPOSE_POSITIONS[purpose][pol] in top:
            top = [PURPOSE_POSITIONS[purpose][pol]]
        if len(top) > 1:
            ties[pol] = top
            asks.append(f"ASK policy {pol} candidates={','.join(top)} "
                        f"(stated {ids} fit each equally)")
            continue
        pos = top[0]
        agree, disagree = score[pos]
        if disagree >= agree:
            lines.append(f"INCOHERENT {pol} stated {ids}: {agree} fit {pos}, {disagree} "
                         f"do not -- candidates: {','.join(POLICIES[pol]['positions'])}")
            asks.append(f"ASK policy {pol} (the stated rules do not follow one position)")
            ties[pol] = []  # asked directly; the purpose never papers over it
            continue
        positions[pol] = pos
        pols[pol] = {"position": pos, "set_by": "inferred",
                     "evidence": f"{agree} of {agree + disagree} stated decisions ({ids})"}
        lines.append(f"POSITION {pol}={pos} inferred from stated {ids} "
                     f"({agree} agree, {disagree} become overrides)")

    # 3. The purpose fills what is still unset.
    unset = [p for p in POLICIES if not positions[p]]
    if unset and purpose:
        for p in [p for p in unset if p not in ties]:
            positions[p] = PURPOSE_POSITIONS[purpose][p]
            pols[p] = {"position": positions[p], "set_by": "purpose"}
            lines.append(f"POSITION {p}={positions[p]} from purpose {purpose}")
        unset = [p for p in unset if not positions[p]]
    if unset and not purpose:
        # One question settles every unset position, and every tie whose candidates
        # include the purpose's position; the per-policy questions stand only for the rest.
        rest = [p for p in unset if p not in ties]
        tied = [p for p in unset if ties.get(p)]
        what = []
        if rest:
            what.append(f"sets {', '.join(rest)}")
        if tied:
            what.append(f"settles {', '.join(tied)} where its position is a candidate")
        asks.insert(0, f"ASK purpose ({'; '.join(what)}; or answer each policy position "
                       f"directly)")

    # 4. Conventions: unset ones take their default; ones no figure needs are `none`.
    for k, spec in CONVENTIONS.items():
        needed = spec["needed"] is None or (all(positions.values()) and spec["needed"](positions))
        if spec["needed"] is not None and all(positions.values()) and not needed:
            convs[k] = {"value": spec["not_needed"], "set_by": "not_needed",
                        "why": spec["why_not_needed"]}
            conv_now[k] = spec["not_needed"]
            continue
        if convs[k].get("value") is None:
            convs[k] = {"value": spec["default"], "set_by": "default"}
            conv_now[k] = spec["default"]
            asks.append(f"ASK convention {k} default={json.dumps(spec['default'])} "
                        f"({spec['label']}; the default stands unless changed)")
        else:
            convs[k].setdefault("set_by", "stated")

    # 5. Derive every decision; a statement that departs from its derivation is an override.
    decisions: dict[str, dict] = {}
    complete = all(positions.values())
    filled = {k: positions.get(k) or next(iter(POLICIES[k]["positions"])) for k in POLICIES}
    for d in DECISIONS:
        i = d["id"]
        # A rule or a convention needs no position; a policy decision needs them all.
        derived = d["derive"](positions, conv_now) if complete else \
            (d["derive"](filled, conv_now) if d["type"] != "policy" else None)
        if i in stated:
            e = stated[i]
            val = e["value"]
            if isinstance(derived, dict) and isinstance(val, dict):
                val = {**derived, **val}
            row = {"value": val}
            same = derived is not None and val == derived
            if d["type"] == "convention":
                row["basis"] = "convention"
            elif same:
                row["basis"] = "stated"
            elif d["type"] == "rule":
                row["basis"] = "override"
                row["rule_breach"] = True
                lines.append(f"RULE-BREACH {i} {json.dumps(val)} (the rule fixes "
                             f"{json.dumps(derived)})")
            elif derived is not None:
                row["basis"] = "override"
                row["derived"] = derived
                lines.append(f"OVERRIDE {i} {json.dumps(val)} ({'+'.join(d['by'])} derives "
                             f"{json.dumps(derived)})")
            else:
                row["basis"] = "stated"
            for k in ("reason", "cite", "quote"):
                if e.get(k):
                    row[k] = e[k]
            if row["basis"] == "override" and not row.get("reason") and not row.get("cite"):
                errors.append(f"decisions.{i}: an override needs a `reason` or a `cite`")
        elif derived is not None:
            row = {"value": derived,
                   "basis": {"policy": "derived", "rule": "rule",
                             "convention": "convention"}[d["type"]]}
        else:
            continue
        decisions[i] = row

    out = {
        "schema": SCHEMA,
        "company": doc.get("company"),
        "status": "draft",  # only `approve` writes `approved`; any re-resolve needs it again
        "purpose": purpose,
        "policies": pols,
        "conventions": convs,
        "decisions": decisions,
    }
    out["instructions"] = instructions(doc, errors)
    for k in ("documents", "notes"):
        if doc.get(k):
            out[k] = doc[k]
    return out, lines, asks, errors


def is_complete(policy: dict) -> bool:
    return len(policy.get("decisions") or {}) == len(DECISIONS) and \
        all((policy.get("policies") or {}).get(k, {}).get("position") for k in POLICIES)


# ---------------------------------------------------------------------------- render

_ACRONYMS = re.compile(r"\b(arr|ssp|carr|grr|nrr|pct|fx|12m)\b")


def _fmt(v) -> str:
    if isinstance(v, dict):
        return "; ".join(f"{_fmt(k)}: {_fmt(x)}" for k, x in v.items())
    return _ACRONYMS.sub(lambda m: m.group(1).upper(), str(v).replace("_", " "))


SET_BY = {"stated": "stated in the company's documents", "inferred": "inferred from stated rules",
          "purpose": "from the purpose", "answer": "the user's answer",
          "default": "proposed default", "not_needed": "not needed"}
BASIS = {"derived": "derived", "rule": "rule", "convention": "convention",
         "stated": "stated", "override": "OVERRIDE", "answer": "answer"}


def render(policy: dict) -> str:
    L = []
    L.append(f"# ARR policy: {policy.get('company') or '(company not named)'}")
    L.append("")
    L.append(f"**Apply per** {APPLY_PER}: read it before you use any value below.")
    L.append("")
    st = policy.get("status", "draft")
    ap = policy.get("approved") or {}
    L.append(f"**Status:** {st}" + (f", approved by {ap.get('by')} on {ap.get('at')}" if ap else ""))
    if policy.get("purpose"):
        L.append(f"**Purpose:** {_fmt(policy['purpose'])}: {PURPOSES[policy['purpose']]}")
    if policy.get("documents"):
        L.append("**Read from:** " + "; ".join(
            str(d.get("title") or d.get("path")) if isinstance(d, dict) else str(d)
            for d in policy["documents"]))
    L += ["", "## Policies", "", "| Policy | Question | Position | Set by |", "|---|---|---|---|"]
    for k, spec in POLICIES.items():
        s = (policy.get("policies") or {}).get(k) or {}
        pos = s.get("position")
        L.append(f"| {k.title()} | {spec['question']} | "
                 f"{spec['positions'][pos] if pos else '**not set**'} | "
                 f"{SET_BY.get(s.get('set_by'), s.get('set_by') or '')}"
                 f"{(' (' + s['evidence'] + ')') if s.get('evidence') else ''} |")
    L += ["", "## Conventions", "", "| Convention | Decision | Value | Set by |", "|---|---|---|---|"]
    for k, spec in CONVENTIONS.items():
        s = (policy.get("conventions") or {}).get(k) or {}
        L.append(f"| {spec['label']} | {spec['decision']} | {_fmt(s.get('value', 'not set'))} | "
                 f"{SET_BY.get(s.get('set_by'), s.get('set_by') or '')}"
                 f"{(' (' + s['why'] + ')') if s.get('why') else ''} |")
    L += ["", f"## The {len(DECISIONS)} decisions", "",
          "| ID | Decision | Type | Value | Basis | Note |", "|---|---|---|---|---|---|"]
    decs = policy.get("decisions") or {}
    ins = policy.get("instructions") or []
    for d in DECISIONS:
        e = decs.get(d["id"])
        if not e:
            L.append(f"| {d['id']} | {d['name']} | {d['type']} | **not settled** | | |")
            continue
        note = []
        if e.get("derived") is not None:
            note.append(f"policy derives {_fmt(e['derived'])}")
        if e.get("rule_breach"):
            note.append("departs from a rule")
        for k in ("reason", "cite"):
            if e.get(k):
                note.append(str(e[k]))
        refs = [x["id"] for x in ins if d["id"] in (x.get("applies_to") or [])]
        if refs:
            note.append("see " + ", ".join(refs))
        L.append(f"| {d['id']} | {d['name']} | {d['type']} | {_fmt(e['value'])} | "
                 f"{BASIS.get(e.get('basis'), e.get('basis'))} | {'; '.join(note)} |")
    L += ["", "## Instructions", ""]
    if ins:
        L += ["How the decisions apply to this business, in words no option can carry.", "",
              "| ID | Instruction | Applies to | Source | Basis |", "|---|---|---|---|---|"]
        src = {"user": "the user", "stated": "stated in the company's documents",
               "inferred": "inferred from the policy"}
        for x in ins:
            L.append(f"| {x['id']} | {x['text']} | {', '.join(x.get('applies_to') or []) or 'all'} | "
                     f"{src.get(x.get('source'), x.get('source'))} | "
                     f"{x.get('basis') or x.get('cite') or ''} |")
    else:
        L.append("None.")
    ov = [i for i, e in decs.items() if e.get("basis") == "override"]
    L += ["", f"**Overrides:** {', '.join(ov) if ov else 'none'}. "
              f"**Instructions:** {len(ins)}. **Settled:** {len(decs)} of {len(DECISIONS)}."]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------- catalog

def catalog_md() -> str:
    L = ["# ARR policy catalog", "", "## Purposes (the dial)", "",
         "| purpose | " + " | ".join(POLICIES) + " | meaning |",
         "|---|" + "---|" * (len(POLICIES) + 1)]
    for k, v in PURPOSES.items():
        L.append(f"| `{k}` | " + " | ".join(f"`{PURPOSE_POSITIONS[k][p]}`" for p in POLICIES)
                 + f" | {v} |")
    L += ["", "## Policies (conservative to expansive)", ""]
    for k, spec in POLICIES.items():
        L.append(f"- **{k}**: {spec['question']} " + " → ".join(
            f"`{p}` ({t})" for p, t in spec["positions"].items()))
    L += ["", "## Conventions", "", "| convention | decision | options | default | needed |",
          "|---|---|---|---|---|"]
    for k, spec in CONVENTIONS.items():
        opts = spec.get("fields") or spec.get("options")
        opts = "; ".join(f"{f}: {'|'.join(o) if isinstance(o, list) else o}"
                         for f, o in opts.items()) if isinstance(opts, dict) else \
            ("|".join(opts) if isinstance(opts, list) else opts)
        L.append(f"| `{k}` | {spec['decision']} | {opts} | `{json.dumps(spec['default'])}` | "
                 f"{'always' if spec['needed'] is None else spec['needed_text']} |")
    L += ["", "## Decisions", "",
          "| id | decision | type | decided by | options | value at each position |",
          "|---|---|---|---|---|---|"]
    for d in DECISIONS:
        opts = d.get("fields") or d.get("options")
        opts = "; ".join(f"{f}: {'|'.join(o) if isinstance(o, list) else o}"
                         for f, o in opts.items()) if isinstance(opts, dict) else "|".join(opts)
        if d["type"] == "policy":
            conv = {k: s["default"] for k, s in CONVENTIONS.items()}
            base = PURPOSE_POSITIONS["sell_side"]
            per = []
            for pol in d["by"]:
                vals = []
                for pos in POLICIES[pol]["positions"]:
                    v = _derived_at(d, pol, pos, base, conv)
                    f = _field_of(d, pol)
                    v = v[f] if f else v
                    vals.append(f"`{pos}`→{_fmt(v)}")
                per.append(f"{pol}: " + ", ".join(vals))
            how = "; ".join(per)
        elif d["type"] == "rule":
            how = f"fixed: {_fmt(d['derive'](PURPOSE_POSITIONS['sell_side'], {k: s['default'] for k, s in CONVENTIONS.items()}))}"
        else:
            how = "the convention's value"
        L.append(f"| {d['id']} | {d['name']} | {d['type']} | {', '.join(d['by']) or '-'} | "
                 f"{opts} | {how} |")
    return "\n".join(L) + "\n"


def catalog_json() -> dict:
    return {
        "purposes": {k: {"meaning": v, "positions": PURPOSE_POSITIONS[k]} for k, v in PURPOSES.items()},
        "policies": POLICIES,
        "conventions": {k: {x: y for x, y in s.items() if not callable(y)}
                        for k, s in CONVENTIONS.items()},
        "decisions": [{k: v for k, v in d.items() if k != "derive"} for d in DECISIONS],
    }


# ---------------------------------------------------------------------------- cli

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
    return bad + _computing_gaps()


def _computing_gaps() -> list[str]:
    """Every decision has a paragraph in ARR_POLICY.md § Computing ARR, opened by its
    bold id, and that paragraph names every option and field in backticks: an option
    added here without its computing rule fails the selftest."""
    doc = pathlib.Path(__file__).resolve().parent.parent / "reference" / "ARR_POLICY.md"
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


def amend(doc: dict, args) -> int:
    """Add a run's pending additions to a policy as instructions (ARR_POLICY.md § Applying
    the policy): every `inferred` entry as it stands, with the id the step cited it by,
    and every question the user answered as a `user` instruction. An unanswered question
    is an ASK line; the draft is written either way, and needs approval before it is
    pinned again."""
    try:
        gaps = {"inferred": [], "questions": []}
        for g in args.gaps:
            one = _load(g) or {}
            for k in gaps:
                gaps[k] += one.get(k) or []
        answers = (_load(args.answers) or {}) if args.answers else {}
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR the gaps or answers file is not YAML or JSON ({exc})")
        return 1
    stamp = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z"), **({"in": args.run} if args.run else {})}
    new = list(doc.get("instructions") or [])
    added, asks = [], []
    for e in gaps.get("inferred") or []:
        new.append({**({"id": e["id"]} if e.get("id") else {}),
                    "text": e.get("text"), "applies_to": e.get("applies_to") or [],
                    "source": "inferred", "basis": e.get("basis"), "added": stamp})
        added.append(("inferred", e.get("text")))
    for q in gaps.get("questions") or []:
        a = answers.get(q.get("id"))
        if a is None:
            asks.append(f"ASK {q.get('id')} {q.get('question')}")
            continue
        a = a if isinstance(a, dict) else {"text": str(a)}
        new.append({**({"id": "I" + str(q["id"])} if q.get("id") else {}),
                    "text": a.get("text"), "applies_to": a.get("applies_to") or q.get("applies_to") or [],
                    "source": "user", "basis": f"answer to: {q.get('question')}", "added": stamp})
        added.append(("user", a.get("text")))
    doc = {**doc, "instructions": new}
    policy, lines, _asks, errors = resolve(doc)
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_dump(policy))
    for src, text in added:
        print(f"ADDED {src}: {text}")
    for x in asks:
        print(x)
    print("STATUS " + ("complete" if not asks and is_complete(policy) else
                       f"incomplete ({len(asks)} questions)"))
    print(f"WROTE {args.out} (draft: approve it before it is pinned again)")
    return 0 if not asks else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("catalog")
    c.add_argument("--json", action="store_true")
    n = sub.add_parser("new")
    n.add_argument("--company", required=True)
    n.add_argument("--purpose", choices=list(PURPOSES))
    n.add_argument("--out", type=pathlib.Path, required=True)
    r = sub.add_parser("resolve")
    r.add_argument("file", type=pathlib.Path)
    r.add_argument("--out", type=pathlib.Path)
    rd = sub.add_parser("render")
    rd.add_argument("file", type=pathlib.Path)
    a = sub.add_parser("approve")
    a.add_argument("file", type=pathlib.Path)
    a.add_argument("--by", required=True)
    a.add_argument("--out", type=pathlib.Path, required=True)
    k = sub.add_parser("check")
    k.add_argument("file", type=pathlib.Path)
    am = sub.add_parser("amend")
    am.add_argument("file", type=pathlib.Path)
    am.add_argument("--gaps", type=pathlib.Path, nargs="+", required=True,
                    help="the steps' gaps files: `inferred` instructions and `questions`")
    am.add_argument("--answers", type=pathlib.Path,
                    help="{<question id>: <the user's words> | {text, applies_to}}")
    am.add_argument("--run", default=None, help="the run the gaps were found in")
    am.add_argument("--out", type=pathlib.Path, required=True)
    sc = sub.add_parser("same-core")
    sc.add_argument("a", type=pathlib.Path)
    sc.add_argument("file", type=pathlib.Path)
    sub.add_parser("selftest")
    args = ap.parse_args()

    if args.cmd == "catalog":
        print(json.dumps(catalog_json(), indent=2, default=str) if args.json else catalog_md(), end="")
        return 0
    if args.cmd == "selftest":
        bad = selftest()
        for b in bad:
            print(b)
        print("arr_policy selftest: " + ("ok" if not bad else f"{len(bad)} defect(s)"))
        return 1 if bad else 0
    if args.cmd == "new":
        doc = {"schema": SCHEMA, "company": args.company, "status": "draft",
               "purpose": args.purpose, "policies": {}, "conventions": {}, "decisions": {}}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_dump(doc))
        print(f"WROTE {args.out}")
        return 0

    if not args.file.is_file():
        print(f"arr_policy: no such file: {args.file}", file=sys.stderr)
        return 1
    try:
        doc = _load(args.file)
    except Exception as exc:  # noqa: BLE001
        print(f"arr_policy: {args.file} is not YAML or JSON ({exc})", file=sys.stderr)
        return 1

    if args.cmd == "render":
        print(render(doc), end="")
        return 0

    if args.cmd == "amend":
        return amend(doc, args)

    if args.cmd == "same-core":
        try:
            a_doc = _load(args.a)
        except Exception as exc:  # noqa: BLE001
            print(f"arr_policy: {args.a} is not YAML or JSON ({exc})", file=sys.stderr)
            return 1
        core = ("purpose", "policies", "conventions", "decisions")
        diff = [k for k in core if a_doc.get(k) != doc.get(k)]
        old = {x.get("id"): x for x in a_doc.get("instructions") or []}
        new = {x.get("id"): x for x in doc.get("instructions") or []}
        changed = [i for i in old if new.get(i) != old[i]]
        if diff or changed:
            print("DIFFERS " + ", ".join(diff + [f"instruction {i}" for i in changed]))
            return 2
        print(f"SAME-CORE {len(new) - len(old)} instruction(s) added")
        return 0

    policy, lines, asks, errors = resolve(doc)
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        return 1

    if args.cmd == "resolve":
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(_dump(policy))
        for ln in lines:
            print(ln)
        blocking = [x for x in asks if not x.startswith("ASK convention")]
        for x in asks:
            print(x)
        done = is_complete(policy)
        print("STATUS complete" if done else f"STATUS incomplete ({len(blocking)} questions)")
        if args.out:
            print(f"WROTE {args.out}")
        return 0 if done else 2

    if args.cmd == "approve":
        if not is_complete(policy):
            print(f"REFUSED: the policy does not settle all {len(DECISIONS)} decisions - resolve it first")
            return 2
        policy["status"] = "approved"
        policy["approved"] = {"by": args.by, "at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        data = _dump(policy)
        args.out.write_text(data)
        print(f"SAVED {args.out} sha256={hashlib.sha256(data.encode()).hexdigest()[:12]}")
        return 0

    if args.cmd == "check":
        # The approved file itself must settle every decision: resolving fills a decision
        # added to the catalog since approval with its default, which nobody approved.
        missing = [d["id"] for d in DECISIONS if d["id"] not in (doc.get("decisions") or {})]
        if missing or not is_complete(policy):
            print(f"NOT-COMPLETE: the policy does not settle all {len(DECISIONS)} decisions"
                  + (f" (missing {', '.join(missing)}: resolve and approve it again)"
                     if missing else ""))
            return 2
        if doc.get("status") != "approved" or not doc.get("approved"):
            print("NOT-APPROVED: the policy was never approved - run create-arr-policy")
            return 2
        print(f"OK {policy.get('company')}: {len(DECISIONS)} decisions settled, approved "
              f"{doc['approved'].get('at')}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
