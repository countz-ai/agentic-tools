---
name: create-arr-policy
description: >-
  Settle the company's ARR policy: the four positions, the conventions and all 31
  decisions that fix how annual recurring revenue is computed. Reads the company's
  existing ARR rules from its documents or a policy file, asks only the questions they
  leave open, shows the whole policy for approval and saves it. Invoke when the user asks
  to set up, write, review or change an ARR policy or ARR definition, and whenever a run
  that computes ARR has no approved policy.
context: inline
---

# Settle the ARR policy

Read `${CLAUDE_PLUGIN_ROOT}/reference/ARR_POLICY.md` whole. A § citation below is read
with `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/section.py <document> "<heading>"`. Every
command below is `uv run --project ${CLAUDE_PLUGIN_ROOT} python3 ${CLAUDE_PLUGIN_ROOT}/scripts/arr_policy.py`
(it needs the plugin's pinned libraries), called `arr_policy.py` here.

**Aim for the fewest questions.** One purpose settles four positions, and the positions
settle 18 decisions. The rules need no answer. Every convention has a default the user
approves with the whole policy. Never ask a decision on its own while a position or a
convention can settle it. Put every open question in one message. A second round is only
for an answer that left a policy incoherent.

**Arguments** when a relay invokes you: `run_dir` (the run's registered sources are the
data room), `company`. Invoked by the user, you have neither.

## 1. What the company already has

The library path is `$HOME/.countz-accounting/arr-policies/<company-slug>.yaml`, the
slug lowercase with hyphens.

1. **An approved policy in the library.** If the file exists and `arr_policy.py check`
   exits 0, show `arr_policy.py render <file>` and ask one question: use it as it
   stands, or change it. Use it: go to § 5. Change it: resolve it as a stated input
   (step 3) with the user's changes.
2. **Otherwise, ask in one message** for:
   - the company, when you were not given it;
   - what they have: an ARR policy file, a document that states their ARR rules (a
     policy memo, KPI definitions, a filing, a board or lender pack), rules to paste
     in, or nothing.

   With a `run_dir`, the data room is already in hand. Say that you are reading it for
   the company's ARR rules, and ask only whether they have documents beyond it.

## 2. Read what they have

- **A policy file.** It is stated input as it stands: go to step 3 with it.
- **Documents, or rules they pasted.** They are read by the `extract-arr-policy` fork,
  never by you: you open no client file. Paste text into
  `<workspace>/arr_policy/pasted.md` with the Write tool, and register it with the
  documents.
  - The workspace is `run_dir` when you have one. New documents join it through
    `setup_run.py <run_dir> --session ${CLAUDE_SESSION_ID} --sources '[...]'`.
  - Without one, register a workspace:

    ```
    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup_run.py \
        --output-root $HOME/.countz-accounting/arr-policies/work --skill create-arr-policy \
        --company "<the user's words>" --goal arr-policy --session ${CLAUDE_SESSION_ID} \
        --sources '[{"id": "...", "path": "<abs>", "name": "<the user's words>"}, ...]'
    ```

  Then dispatch the fork as a wave of one:
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py dispatch <workspace> --step arr_policy --args '{"out": "<workspace>/arr_policy/stated.yaml", "company": "<company>"}'`,
  execute the `NEXT:` line it prints, then `run_state.py record <workspace>`. Its return
  names the documents that state rules and how many decisions they settle. Say that to
  the user in one line.
- **Nothing.** Write `<workspace or scratch>/stated.yaml` holding only `company`.

## 3. Resolve, and ask what is left

```
arr_policy.py resolve <stated.yaml> --out <draft.yaml>
```

Exit 0 means every decision is settled: go to step 4. Exit 1 is a malformed input: fix
the file (a policy file the user gave you is theirs, so say what is wrong and ask them).
Exit 2 prints what is left, as `ASK` lines in the order to ask them. Put all of them to
the user in **one message**:

- **`ASK purpose`**: the four purposes, each with its meaning and the four positions it
  sets, from `arr_policy.py catalog`. Offer "set the positions myself" as the fifth
  answer.
- **`ASK policy <name>`**: the policy's question, and its candidate positions with their
  meanings. Where it follows an `INCOHERENT` line, quote the stated rules that split,
  with their citations.
- **`ASK convention` lines**: one table of every convention with its proposed default,
  answered all at once ("keep the defaults, or name the ones to change").
- **The document's `notes`**: each is a rule that contradicts a decision or another
  document. Quote it with its citation and ask which reading holds. Rules the documents
  state that no option expresses are already `instructions`, and need no question.

Where the host offers a multiple-choice question tool, use it for the purpose and the
positions. Record each answer in the draft:

- the purpose as `purpose`;
- a position as `policies.<name>: {position, set_by: answer}`;
- a convention as `conventions.<name>: {value, set_by: answer}`;
- a decision the user settles directly as `decisions.<id>: {value, basis: stated,
  reason: "<their words>"}`.

Then resolve again. `OVERRIDE` and `RULE-BREACH` lines are findings to show the user,
not questions.

## 4. Show the whole policy, and approve it

Show the output of `arr_policy.py render <draft.yaml>` verbatim. It is the one
presentation of a policy: the purpose, the four positions and how each was set, the
conventions, the 31 decisions with the basis of each, every override, and the
instructions. Then say, in at most three lines:

- which positions were inferred from their documents and which came from answers;
- each override and rule breach, and what it departs from;
- that the conventions marked "proposed default" stand unless they change them.

Ask for approval, and invite any rule of theirs the policy does not yet carry: how
their own products, plans or channels are counted, in their words. Record each under
`instructions` as `{text, applies_to, source: user}`, where `applies_to` names the
decisions it refines (`ARR_POLICY.md` § Instructions). An instruction that contradicts a
decision's value is a change to that decision instead: record it as an override with
their reason. A change is recorded in the draft as in step 3 and resolved again, then
shown again. Nothing is saved before the user approves.

## 5. Save it

```
arr_policy.py approve <draft.yaml> --by "<the user's name>" --out <path>
```

`<path>` is the library path unless the user names another. It prints `SAVED`. With a
`run_dir`, pin it into the run:

```
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup_run.py <run_dir> --session ${CLAUDE_SESSION_ID} \
    --sources '[]' --arr-policy <path>
```

## Return

To a relay, two lines: the saved path and the pinned path. To the user: where the policy
is saved, and that a revenue analysis will now use it.
