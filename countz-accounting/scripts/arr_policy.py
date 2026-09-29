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
- defaults each convention that is still unset and marks it `set_by: default`, and each
  field a partly stated convention leaves open (`default_fields`);
- derives every decision no statement or override settles, and each field a partly
  stated decision leaves open (`derived_fields`).

It prints one line per finding and exits 0 when every decision is settled, 2 when the
policy still needs answers (each `ASK` line is one question, in the order to ask them),
and 1 on a malformed or contradictory input, each `ERROR` line naming what to fix.
`approve` refuses a file that resolving again would change; `check` passes only an
approved file unchanged since approval. Lines:

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

# A convention is a choice no position decides. `fields`: a composite value's fields.
# `needed(values)`: whether any figure uses it, from the policy and rule decisions' values
# (None: always); where none does, it takes `not_needed`. `field`: the field it supplies
# in a decision that is not itself a convention (L4's threshold).
CONVENTIONS = {
    "window": {
        "decision": "S2", "label": "Measurement window for flow-based ARR",
        "options": ["month_x12", "trailing_3_months", "trailing_12_months"],
        "default": "trailing_3_months",
        "needed": lambda v: v["S1"] in ("recognized_run_rate", "billed_spread",
                                        "contract_else_billed")
        or v["S3"] == "ratable_revenue" or v["S4"] == "recognized_revenue"
        or v["S5"]["timing"] == "at_issuance"
        or v["R1"] == "commit_plus_usage" or v["R2"] == "include",
        "not_needed": "point_in_time",
        "why_not_needed": "a contract snapshot at the date needs no window",
        "needed_text": "when a decision measures an amount from a flow: S1 "
                       "recognized_run_rate, billed_spread or contract_else_billed, S3 "
                       "ratable_revenue, S4 recognized_revenue, S5 timing at_issuance, R1 "
                       "commit_plus_usage, R2 include",
    },
    "fx": {
        "decision": "V4", "label": "Currency translation rate",
        "options": ["prior_year_end_rate", "start_of_year_rate", "contract_signing_rate",
                    "period_average_rate", "closing_spot_rate"],
        "default": "closing_spot_rate", "needed": None,
    },
    "modification_classes": {
        "decision": "A1", "label": "Bridge classes for mid-term modifications",
        "options": ["expansion_contraction", "register_type", "price_vs_quantity"],
        "default": "expansion_contraction", "needed": None,
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
    "entry_event": {
        "decision": "L1", "label": "The event whose month a new stream enters ARR from",
        "options": ["signed", "booked"], "default": "signed", "needed": None,
    },
    "signing_lag_months": {
        "decision": "L1", "label": "Months after the entry month a new stream enters ARR",
        "options": "int", "default": 0, "needed": None,
    },
    "outlier_threshold_pct": {
        "decision": "L4", "label": "Contract size, % of ARR, that needs document support "
                                   "(none: no such test)",
        "options": "number", "default": 5, "needed": None,
        "field": "document_threshold_pct",
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
     "options": list(POLICIES["source"]["positions"]) + ["contract_else_billed"],
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
     "by": ["lifecycle", "source"],
     "fields": {"churn_at": ["at_notice", "effective_date"],
                "conflicting_records": ["earliest_end", "contract_as_amended"]},
     "field_by": {"churn_at": "lifecycle", "conflicting_records": "source"},
     "derive": lambda p, c: {
         "churn_at": "at_notice" if p["lifecycle"] == "live_paying" else "effective_date",
         "conflicting_records": "earliest_end" if p["source"] == "all_agree"
         else "contract_as_amended"}},
    {"id": "L3", "name": "Renewal gaps, holdover and grace periods", "type": "policy",
     "by": ["lifecycle"],
     "fields": {"treatment": ["grace_window", "continuation", "until_renewal",
                              "while_paying"],
                "grace_months": "int"},
     "derive": lambda p, c: {
         "treatment": "continuation" if p["lifecycle"] == "signed_assumed" else "grace_window",
         "grace_months": 3 if p["lifecycle"] == "grace" else 0}},
    {"id": "L4", "name": "Outlier and short-lived contracts", "type": "rule", "by": [],
     "constrained_by": ["source"],
     "fields": {"short_terminated": ["service_months_only", "annualize", "exclude"],
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
    {"id": "V1", "name": "Ramps and escalators", "type": "policy", "by": ["value", "source"],
     "fields": {"step": ["current_step", "term_average"],
                "billing_only_step_ups": ["require_contract_evidence", "as_billed"]},
     "field_by": {"step": "value", "billing_only_step_ups": "source"},
     "derive": lambda p, c: {
         "step": ["current_step", "current_step", "term_average",
                  "term_average"][_ix("value", p["value"])],
         "billing_only_step_ups": "require_contract_evidence"
         if p["source"] in ("all_agree", "contract") else "as_billed"}},
    {"id": "V2", "name": "Discounts and free months", "type": "policy", "by": ["value"],
     "options": ["net_current", "net_current_free_months_at_rate", "net_term_average",
                 "list_price"],
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
    Unset positions take the first position so the derivation runs. Only the field `pol`
    decides is compared, and each field depends on its one deciding policy alone
    (test_arr_policy asserts it), so the filler never decides the result."""
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
    if opts == "int":  # months: a count, never negative
        return None if isinstance(value, int) and not isinstance(value, bool) and value >= 0 \
            else "expects a whole number, 0 or more"
    if opts == "number":  # a percentage; `none` switches its test off
        return None if value == "none" or (isinstance(value, (int, float))
                                           and not isinstance(value, bool)
                                           and 0 <= value <= 100) \
            else "expects a percentage from 0 to 100, or none"
    if value not in opts:
        return f"`{value}` is not one of: {', '.join(map(str, opts))}"
    return None


def _empty(value) -> str | None:
    return "states none of its fields" if isinstance(value, dict) and not value else None


def _stated_part(value, filled) -> object:
    """What a statement said of a composite: its value less the fields `resolve` filled
    (`derived_fields`, `default_fields`). Those are refilled on every resolve and never
    count as stated."""
    if isinstance(value, dict) and filled:
        return {f: x for f, x in value.items() if f not in filled}
    return value


def _merge_part(have, part):
    """A convention stated in two places: the value both carry, or None where they
    disagree. A composite may be stated in parts; each field must agree wherever stated."""
    if isinstance(have, dict) and isinstance(part, dict):
        if any(k in have and have[k] != v for k, v in part.items()):
            return None
        return {**have, **part}
    return have if have == part else None


def _conv_value(k: str, value):
    """A convention's value for the derivations: its default where unset, and its
    default's fields where a composite is partly stated."""
    spec = CONVENTIONS[k]
    if value is None:
        return spec["default"]
    if "fields" in spec and isinstance(value, dict):
        return {f: value.get(f, spec["default"][f]) for f in spec["fields"]}
    return value


# ---------------------------------------------------------------------------- resolve

INSTRUCTION_SOURCES = ("user", "stated", "inferred")
# An instruction's id: `I<n>` given here, `I.<check_id>.<n>` a step inferred, or
# `IQ.<check_id>.<n>` the answer to a step's question Q.<check_id>.<n> (ARR_POLICY.md
# § Applying the policy). A check id is check_playbook.CHECK_ID: no `-`.
CHECK_ID = r"[a-z0-9][a-z0-9_]*"
INSTRUCTION_ID = re.compile(rf"I[1-9]\d*|IQ?\.{CHECK_ID}\.[1-9]\d*")
GAP_ID = {"inferred": re.compile(rf"I\.{CHECK_ID}\.[1-9]\d*"),
          "questions": re.compile(rf"Q\.{CHECK_ID}\.[1-9]\d*")}


def instructions(doc: dict, errors: list[str]) -> list[dict]:
    """Validate the free-text instructions and give each without an id a stable one (I1,
    I2, ...). One id never names two texts, since figures cite instructions by id: an
    instruction repeated (under its own id or without one) is skipped; another text under
    a taken id is refused."""
    raw = doc.get("instructions") or []
    if not isinstance(raw, list):
        errors.append("instructions: a list of {text, applies_to, source, ...}")
        return []
    out, by_id, seen_text = [], {}, set()
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
        key = " ".join(str(e["text"]).split()).lower()
        if e.get("id"):
            e["id"] = str(e["id"])
            if not INSTRUCTION_ID.fullmatch(e["id"]):
                errors.append(f"instructions[{k}]: id `{e['id']}` is not I<n>, I.<check_id>.<n> "
                              f"or IQ.<check_id>.<n> (a check id is lowercase letters, digits "
                              f"and `_`)")
                continue
            if e["id"] in by_id:
                if by_id[e["id"]] != key:
                    errors.append(f"instructions[{k}]: id `{e['id']}` already names another "
                                  f"instruction; a step numbers its additions after the highest "
                                  f"`n` the policy carries for its check id")
                continue
        else:
            if key in seen_text:
                continue
            while True:
                n += 1
                if f"I{n}" not in taken:
                    break
            e["id"] = f"I{n}"
        by_id[e["id"]] = key
        seen_text.add(key)
        out.append({"id": e["id"], **{k2: v for k2, v in e.items() if k2 != "id"}})
    return out


def resolve(doc: dict) -> tuple[dict, list[str], list[str], list[str]]:
    """Settle what can be settled. Returns (policy, report lines, asks, errors).
    Idempotent: only what a document stated or the user answered is carried; everything
    else is recomputed from it."""
    errors: list[str] = []
    lines: list[str] = []
    asks: list[str] = []
    for k in ("policies", "conventions", "decisions"):
        if doc.get(k) is not None and not isinstance(doc[k], dict):
            errors.append(f"{k}: expects a mapping")
            doc = {**doc, k: {}}

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
        spec = CONVENTIONS[k]
        if s.get("value") is None:
            continue
        s["value"] = _stated_part(s["value"], s.pop("default_fields", None))
        err = None if s["value"] == spec.get("not_needed") else (
            _valid_value(spec if "fields" in spec else {"options": spec["options"]}, s["value"])
            or _empty(s["value"]))
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
        e = dict(e) if isinstance(e, dict) and "value" in e else {"value": e}
        e["value"] = _stated_part(e["value"], e.get("derived_fields"))
        err = _valid_value(DEC[i], e["value"]) or _empty(e["value"])
        if err:
            errors.append(f"decisions.{i} {err}")
            continue
        if e.get("basis") in (None, "stated", "override", "answer"):
            stated[i] = {k: v for k, v in e.items()
                         if k not in ("derived", "derived_fields", "rule_breach")}

    # 1. A convention has one value. A convention decision (S2, V4, A1, A2, A3, A6) and a
    #    rule field a convention supplies (L4's threshold) hold it; stated in both places,
    #    the two must agree.
    for k, spec in CONVENTIONS.items():
        i = spec["decision"]
        e = stated.get(i)
        if e is None:
            continue
        if DEC[i]["type"] == "convention":
            part = e["value"]
            del stated[i]
        elif isinstance(e["value"], dict) and spec.get("field") in e["value"]:
            rest = dict(e["value"])
            part = rest.pop(spec["field"])
            if rest:
                stated[i] = {**e, "value": rest}
            else:
                del stated[i]
        else:
            continue
        have = convs[k].get("value")
        if have is None:
            convs[k] = {"value": part, "set_by": "answer" if e.get("basis") == "answer"
                        else "stated", **{x: e[x] for x in ("cite", "reason") if e.get(x)}}
            continue
        merged = _merge_part(have, part)
        if merged is None:
            errors.append(f"decisions.{i} states {json.dumps(part)} and conventions.{k} is "
                          f"{json.dumps(have)}: state the `{k}` convention once")
        else:
            convs[k]["value"] = merged
    conv_now = {k: _conv_value(k, s.get("value")) for k, s in convs.items()}
    positions = {k: s.get("position") for k, s in pols.items()}

    # 2. Infer each unset position from the stated decisions it decides.
    ties: dict[str, list[str]] = {}
    for pol in POLICIES:
        if positions[pol]:
            pols[pol].setdefault("set_by", "stated")
            continue
        voters = [d for d in DECISIONS if d["id"] in stated and pol in d["by"]]
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

    # 4. Conventions: an unset one, and each field a partly stated one leaves open, takes
    #    its default. One no figure needs takes `not_needed`; any other value there, or
    #    `not_needed` where a figure needs it, is an error.
    complete = all(positions.values())
    values = {}
    if complete:
        for d in DECISIONS:
            if d["type"] != "convention":
                v, s = d["derive"](positions, conv_now), (stated.get(d["id"]) or {}).get("value")
                values[d["id"]] = v if s is None else ({**v, **s} if isinstance(v, dict) else s)
    for k, spec in CONVENTIONS.items():
        s, v = convs[k], convs[k].get("value")
        if spec["needed"] is not None and complete:
            if not spec["needed"](values):
                if v is None:
                    convs[k] = {"value": spec["not_needed"], "set_by": "not_needed",
                                "why": spec["why_not_needed"]}
                    conv_now[k] = spec["not_needed"]
                elif v != spec["not_needed"]:
                    errors.append(f"conventions.{k} is `{v}`, but no figure uses it "
                                  f"({spec['why_not_needed']}); it is needed "
                                  f"{spec['needed_text']}: remove it, or settle the decision "
                                  f"it serves")
                continue
            if v == spec["not_needed"]:
                errors.append(f"conventions.{k} is `{v}`, but a figure needs it: it is needed "
                              f"{spec['needed_text']}")
                continue
        if v is None:
            convs[k] = {"value": spec["default"], "set_by": "default"}
            conv_now[k] = spec["default"]
            asks.append(f"ASK convention {k} default={json.dumps(spec['default'])} "
                        f"({spec['label']}; the default stands unless changed)")
            continue
        s.setdefault("set_by", "stated")
        open_ = [f for f in spec.get("fields") or {} if isinstance(v, dict) and f not in v]
        if open_:
            s["value"] = conv_now[k]
            s["default_fields"] = open_
            asks.append(f"ASK convention {k} default="
                        f"{json.dumps({f: spec['default'][f] for f in open_})} ({spec['label']}: "
                        f"{', '.join(open_)} not stated; the default stands unless changed)")

    # 5. Derive every decision; a statement that departs from its derivation is an override,
    #    and one that departs from a rule, or from a field the catalog fixes, a rule breach.
    decisions: dict[str, dict] = {}
    filled = {k: positions.get(k) or next(iter(POLICIES[k]["positions"])) for k in POLICIES}
    for d in DECISIONS:
        i = d["id"]
        # A rule or a convention needs no position; a policy decision needs them all.
        derived = d["derive"](positions, conv_now) if complete else \
            (d["derive"](filled, conv_now) if d["type"] != "policy" else None)
        if i not in stated:
            if derived is not None:
                decisions[i] = {"value": derived,
                                "basis": {"policy": "derived", "rule": "rule",
                                          "convention": "convention"}[d["type"]]}
            continue
        e = stated[i]
        val, open_ = e["value"], []
        if isinstance(derived, dict) and isinstance(val, dict):
            open_ = [f for f in derived if f not in val]
            val = {f: val.get(f, derived[f]) for f in derived}
        row = {"value": val}
        if derived is None or val == derived:
            row["basis"] = "stated"
        else:
            row["basis"] = "override"
            fixed = d.get("fixed_fields") or {}
            breach = {f: val[f] for f, x in fixed.items() if val.get(f) != x}
            departs = [f for f in derived if f not in fixed and val[f] != derived[f]] \
                if isinstance(derived, dict) else [i]
            if d["type"] == "rule" or breach:
                row["rule_breach"] = True
                lines.append(f"RULE-BREACH {i} {json.dumps(breach or val)} (the rule fixes "
                             f"{json.dumps({f: fixed[f] for f in breach} or derived)})")
            if d["type"] == "policy" and departs:
                row["derived"] = derived
                lines.append(f"OVERRIDE {i} {json.dumps(val)} "
                             f"({'+'.join(d['by'])} derives {json.dumps(derived)})")
        if open_:
            row["derived_fields"] = open_
        for k in ("reason", "cite", "quote"):
            if e.get(k):
                row[k] = e[k]
        if row["basis"] == "override" and not row.get("reason") and not row.get("cite"):
            errors.append(f"decisions.{i}: an override needs a `reason` or a `cite`")
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
    """Every position set, and every decision settled with every field of a composite."""
    decs, pols = policy.get("decisions") or {}, policy.get("policies") or {}
    return all(isinstance(pols.get(k), dict) and pols[k].get("position") for k in POLICIES) \
        and all(isinstance(decs.get(i), dict) and "value" in decs[i]
                and ("fields" not in d or (isinstance(decs[i]["value"], dict)
                                           and set(decs[i]["value"]) == set(d["fields"])))
                for i, d in DEC.items())


# What a policy settles: what `approve` digests and `check` compares. A file whose CORE
# differs from its own resolution was edited after `resolve`, or the catalog changed.
CORE = ("company", "purpose", "policies", "conventions", "decisions", "instructions")


def _core(policy: dict) -> dict:
    return {k: policy.get(k) or None for k in CORE}


def _drift(doc: dict, policy: dict) -> list[str]:
    a, b = _core(doc), _core(policy)
    return [k for k in CORE if a[k] != b[k]]


def _digest(policy: dict) -> str:
    return hashlib.sha256(json.dumps(_core(policy), sort_keys=True, default=str)
                          .encode()).hexdigest()[:16]


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


def _row(*cells) -> str:
    """A table row: a `|` or a line break in free text would split it."""
    return "| " + " | ".join(str(c).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
                             for c in cells) + " |"


def _entry(v, key: str) -> dict:
    """A policy, convention or decision entry, which a file `resolve` has not yet written
    may carry as a bare value."""
    return v if isinstance(v, dict) else ({key: v} if v is not None else {})


def render(policy: dict) -> str:
    L = []
    L.append(f"# ARR policy: {policy.get('company') or '(company not named)'}")
    L.append("")
    L.append(f"**Apply per** {APPLY_PER}: read it before you use any value below.")
    L.append("")
    st = policy.get("status", "draft")
    ap = policy.get("approved") or {}
    L.append(f"**Status:** {st}" + (f", approved by {ap.get('by')} on {ap.get('at')}"
                                    if isinstance(ap, dict) and ap else ""))
    if policy.get("purpose"):
        L.append(f"**Purpose:** {_fmt(policy['purpose'])}: "
                 f"{PURPOSES.get(policy['purpose'], 'not a purpose')}")
    if policy.get("documents"):
        L.append("**Read from:** " + "; ".join(
            str(d.get("title") or d.get("path")) if isinstance(d, dict) else str(d)
            for d in policy["documents"]))
    L += ["", "## Policies", "", "| Policy | Question | Position | Set by |", "|---|---|---|---|"]
    for k, spec in POLICIES.items():
        s = _entry((policy.get("policies") or {}).get(k), "position")
        pos = s.get("position")
        L.append(_row(k.title(), spec["question"],
                      spec["positions"].get(pos, f"`{pos}`, not a position") if pos
                      else "**not set**",
                      f"{SET_BY.get(s.get('set_by'), s.get('set_by') or '')}"
                      f"{(' (' + str(s['evidence']) + ')') if s.get('evidence') else ''}"))
    L += ["", "## Conventions", "", "| Convention | Decision | Value | Set by |", "|---|---|---|---|"]
    for k, spec in CONVENTIONS.items():
        s = _entry((policy.get("conventions") or {}).get(k), "value")
        why = [str(s[x]) for x in ("why", "reason", "cite") if s.get(x)]
        if s.get("default_fields"):
            why.append(f"{', '.join(map(_fmt, s['default_fields']))}: proposed default")
        L.append(_row(spec["label"], spec["decision"], _fmt(s.get("value", "not set")),
                      f"{SET_BY.get(s.get('set_by'), s.get('set_by') or '')}"
                      f"{(' (' + '; '.join(why) + ')') if why else ''}"))
    L += ["", f"## The {len(DECISIONS)} decisions", "",
          "| ID | Decision | Type | Value | Basis | Note |", "|---|---|---|---|---|---|"]
    decs = {i: _entry(e, "value") for i, e in (policy.get("decisions") or {}).items()}
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
        if e.get("derived_fields"):
            note.append(f"{', '.join(map(_fmt, e['derived_fields']))} derived")
        for k in ("reason", "cite"):
            if e.get(k):
                note.append(str(e[k]))
        refs = [str(x.get("id")) for x in ins
                if isinstance(x, dict) and d["id"] in (x.get("applies_to") or [])]
        if refs:
            note.append("see " + ", ".join(refs))
        L.append(_row(d["id"], d["name"], d["type"], _fmt(e.get("value")),
                      BASIS.get(e.get("basis"), e.get("basis")), "; ".join(note)))
    L += ["", "## Instructions", ""]
    if ins:
        L += ["How the decisions apply to this business, in words no option can carry.", "",
              "| ID | Instruction | Applies to | Source | Basis |", "|---|---|---|---|---|"]
        src = {"user": "the user", "stated": "stated in the company's documents",
               "inferred": "inferred from the policy"}
        for x in (_entry(x, "text") for x in ins):
            at = x.get("applies_to") or []
            L.append(_row(x.get("id", ""), x.get("text", ""),
                          (at if isinstance(at, str) else ", ".join(map(str, at))) or "all",
                          src.get(x.get("source"), x.get("source") or ""),
                          x.get("basis") or x.get("cite") or ""))
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


def amend(doc: dict, args) -> int:
    """Add a run's pending additions to a policy as instructions (ARR_POLICY.md § Applying
    the policy): each `inferred` entry under its id `I.<check_id>.<n>`, and each answered
    question `Q.<check_id>.<n>` as a `user` instruction `IQ.<check_id>.<n>`. An id the
    policy already gives to another text is refused. An unanswered question is an ASK
    line. The draft is written either way and needs approval before it is pinned again."""
    gaps, errors = {"inferred": [], "questions": []}, []
    try:
        for g in args.gaps:
            one = _load(g) or {}
            if not isinstance(one, dict):
                errors.append(f"{g}: a mapping of `inferred` and `questions`")
                continue
            for k in gaps:
                part = one.get(k) or []
                if not isinstance(part, list) or not all(isinstance(x, dict) for x in part):
                    errors.append(f"{g}: `{k}` is a list of mappings")
                    continue
                for x in part:
                    if not GAP_ID[k].fullmatch(str(x.get("id") or "")):
                        errors.append(f"{g}: {k} id `{x.get('id')}` is not "
                                      f"{'I' if k == 'inferred' else 'Q'}.<check_id>.<n> (a "
                                      f"check id is lowercase letters, digits and `_`)")
                gaps[k] += part
        answers = (_load(args.answers) or {}) if args.answers else {}
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR the gaps or answers file is not YAML or JSON ({exc})")
        return 1
    if not isinstance(answers, dict):
        errors.append(f"{args.answers}: a mapping of question id to the user's answer")
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        return 1
    stamp = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z"), **({"in": args.run} if args.run else {})}
    new = list(doc.get("instructions") or [])
    before = {str(x.get("id")) for x in new if isinstance(x, dict) and x.get("id")}
    asks = []
    for e in gaps["inferred"]:
        new.append({"id": e["id"], "text": e.get("text"), "applies_to": e.get("applies_to") or [],
                    "source": "inferred", "basis": e.get("basis"), "added": stamp})
    for q in gaps["questions"]:
        a = answers.get(q["id"])
        if a is None:
            asks.append(f"ASK {q['id']} {q.get('question')}")
            continue
        a = a if isinstance(a, dict) else {"text": str(a)}
        new.append({"id": "I" + str(q["id"]), "text": a.get("text"),
                    "applies_to": a.get("applies_to") or q.get("applies_to") or [],
                    "source": "user", "basis": f"answer to: {q.get('question')}", "added": stamp})
    doc = {**doc, "instructions": new}
    policy, lines, _asks, errors = resolve(doc)
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_dump(policy))
    for x in policy["instructions"]:
        if str(x["id"]) not in before:
            print(f"ADDED {x['id']} {x['source']}: {x['text']}")
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
    args = ap.parse_args()

    if args.cmd == "catalog":
        print(json.dumps(catalog_json(), indent=2, default=str) if args.json else catalog_md(), end="")
        return 0
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
    if not isinstance(doc, dict):
        print(f"ERROR {args.file}: a policy is a mapping (ARR_POLICY.md § The file)")
        return 1

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

    if args.cmd == "render":
        print(render(doc), end="")
        return 0

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
        # Stamp only what the user saw rendered: a file `resolve` would change is refused.
        drift = _drift(doc, policy)
        if drift:
            print(f"REFUSED: {args.file} is not what resolve writes from it (differs in "
                  f"{', '.join(drift)}) - resolve it with --out, show its render, and approve "
                  f"that file")
            return 2
        policy["status"] = "approved"
        policy["approved"] = {"by": args.by, "at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "digest": _digest(policy)}
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
        drift = _drift(doc, policy)
        if drift:
            print(f"NOT-CONSISTENT: the file is not what resolve writes from it (differs in "
                  f"{', '.join(drift)}): it was edited by hand, or the catalog changed since - "
                  f"resolve and approve it again")
            return 2
        stamp = doc.get("approved")
        if doc.get("status") != "approved" or not isinstance(stamp, dict) or not stamp.get("at"):
            print("NOT-APPROVED: the policy was never approved - run create-arr-policy")
            return 2
        if stamp.get("digest") != _digest(doc):
            print("NOT-APPROVED: the policy changed after it was approved - resolve and "
                  "approve it again")
            return 2
        print(f"OK {policy.get('company')}: {len(DECISIONS)} decisions settled, approved "
              f"{stamp.get('at')}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
