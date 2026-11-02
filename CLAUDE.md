# ReturnGuard — project rules

## What this is
A take-home prototype for MiraFlores AI (AI Engineer, Tax). Problem: a corrected
tax form (corrected 1099-DIV or W-2c) arrives after a CPA approved work based on
the original. ReturnGuard decides what changed, whether the correction can be
trusted, which approved items are now stale, and what the reviewer should do.
AI suggests; code verifies; a CPA decides. It never computes tax liability,
never files anything, never clears a hold automatically.

## Source of truth
- docs/brief.md (plain-text copy of docs/brief.docx): the MiraFlores brief. Requirements come from here.
- docs/memo_v1.pdf: original design memo.
- HANDOFF.md: current state. Read it at the start of every session; update it at the end.

## Take-home rules (from the brief and the recruiter email; never break these)
- Total time 2–4 hours; stop at 4 hours. Keep work small enough to finish.
- Must complete ONE useful core workflow end to end: realistic input -> meaningful output/action.
  The core logic must actually run. Static screens, pseudocode or slides alone do NOT count.
- Must demonstrate a representative case (T1) AND a difficult/invalid-input case (T5, T12).
- Synthetic data and mocked integrations are allowed ONLY if clearly labelled
  (SYNTHETIC in data files, MOCKED in cached LLM output and in the UI).
- No paid service or production account may be required: everything, including tests,
  must run with no API key and no network.
- Deliverables: written submission (<= 4 pages, kept separately), working prototype,
  source code, README.
- README must include: setup and run instructions, dependencies, sample data,
  example inputs with expected outputs, time spent, what I'd investigate next.
- Must state what is implemented, mocked, or deferred.
- Must state how AI was used, how its output was checked, and what prior work was reused (none).
- Reviewers will watch it run for 15 minutes and then run a 30-minute live case where
  requirements change: keep rules in config so new forms/fields can be added without code changes.

## How the work is split (one fresh session each; never do another session's work)
- Session 1: skeleton, schemas, cited config, synthetic fixtures T1–T15
- Session 2: validate.py + impact.py (checks, dependency walk) + tests
- Session 3: decide.py + audit.py + cli.py (statuses, fingerprints, log) + tests
- Session 4: extract.py + explain.py (LLM extraction cached/live, source checks, grounded note) + tests
- Session 5: app.py (Streamlit) + README.md
- Session 6: fresh-eyes review from a clean clone -> REVIEW.md (report only, no code fixes)
Each session starts by restating its goal in 3 lines and waiting for my OK.

## Stack (do not add others without asking)
Python 3.11+, pydantic v2, decimal.Decimal for all money, PyYAML, pytest,
streamlit. Optional LLM SDK in Session 4 only (anthropic or google-genai),
behind a flag; default mode replays cached outputs from data/llm_cache/.

## Layout
config/forms.yaml        field definitions + validation rules per form
config/dependencies.yaml field -> return line -> workpaper/approval map
data/synthetic/          synthetic inputs (labelled SYNTHETIC in every file)
data/llm_cache/          hand-written stand-ins for LLM outputs (labelled MOCKED); real ones are *.live.json
returnguard/models.py    pydantic schemas
returnguard/validate.py  identity + prior-value + field checks
returnguard/impact.py    dependency walk -> stale approvals
returnguard/decide.py    status decision
returnguard/audit.py     evidence fingerprints + append-only log
returnguard/extract.py   LLM extraction (live or cached) + verification
returnguard/explain.py   reviewer note + number-grounding check
app.py, cli.py           interfaces
tests/                   pytest

## Statuses (exactly these)
APPLY_AND_REREVIEW, POSSIBLE_AMENDMENT, CONFLICT, SPECIALIST_REVIEW,
DUPLICATE_NO_CHANGE, REJECTED_INVALID_INPUT

## Rules
- Only touch files listed in the session prompt.
- Never change a test's expected value to make it pass without explaining why in HANDOFF.md.
- Never claim a result you did not run. Paste real pytest output.
- No real SSNs, EINs, names or taxpayer data. Synthetic only.
- Tax facts (box meanings, 1040 line numbers) must cite the IRS source in
  config comments. If unsure, mark `# UNVERIFIED` and list it in HANDOFF.md.
- Keep it small. No frameworks, agents, databases or auth.
- End every session: pytest -q, update HANDOFF.md, commit, push.
