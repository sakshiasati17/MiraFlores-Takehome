# HANDOFF — ReturnGuard

> **Every session: read `docs/project_plan.md` first. It is the CURRENT design.**
> `CLAUDE.md` holds the rules. The MiraFlores brief (MiraFlores's own material) and the outdated v1 design memo
> were removed from the repo in the final cleanup; `docs/project_plan.md` is the source of truth for the design.

## Final status (submission). Date: 2026-11-02
All earlier "Open" items below are resolved: README time log filled (about 3 h 20 min), GitHub default branch is `main`, requirements-llm.txt comment updated. The written submission is sent separately, not stored in the repo. Still open by design: F4, F8, F11 and the unverified IRS mappings (see README Known limitations).

## Status after final polish. Date: 2026-11-02
Branch `returnguard/final-polish` (from origin/main 11dfebf), merged into `main`. Commits as `sakshiasati17`.
Done (REVIEW.md F5, F6, F9, F10, F12, F13 fixed): form types come from `config/forms.yaml` (models accept any name; a form not
in config -> `UNKNOWN_FORM_TYPE` / SPECIALIST_REVIEW in `decide.py` before `validate()`; the live prompt lists the forms from config,
prompt `extract-v2`); the API is called ONLY with CLI `--live` + `ANTHROPIC_API_KEY` (`RETURNGUARD_LLM` does nothing, `--all`
always replays); a failed live call prints one line and exits 1; money tokens in AI notes must be real amounts/deltas; blocked
statuses say "Nothing has been applied". README: "How to add a form", live commands, time log; T5/T12 screenshots retaken.
Tests: new `test_new_form_via_config.py` (1099-INT on a temp copy, byte-identical Python), `test_cli_live_safety.py`, 6 grounding
tests. Existing tests changed only for the new wording and the `--live` switch (no expected status, amount or fixture changed).
`python3 -m pytest -q`: `364 passed in 7.05s`. `python3 cli.py --all`: 15 of 15 match, exit 0.
Open: README `[RESEARCH AND MEMO TIME]` / `[TOTAL]` (Sakshi); `docs/writeup.md` not in repo; GitHub default branch is still
`returnguard-setup`; `requirements-llm.txt` comment still says "needs RETURNGUARD_LLM=live" (file not in this session's scope).
Still open from REVIEW.md: F4 (stale list not cross-checked with return state), F8 (abbreviated labels), F11 (wording only).

## Status after Session 6 (fresh-eyes review). Date: 2026-11-02
Review done from a clean clone of `main` @ 0dc82ed; full report in **`REVIEW.md`**. Branch `returnguard/session-6-review`, merged into `main`.
Verdict: prototype PASS (341 passed, 15 of 15 match, safety PASS, UI makes 0 API calls in live mode). Only README change: quick start runs pytest/CLI before `streamlit run`.
Open items: `docs/writeup.md` not in repo; GitHub default branch `returnguard-setup` lacks Session 5b (set default to `main`); README `[RESEARCH AND MEMO TIME]`/`[TOTAL]` unfilled;
live-case config edits turn 10 tests red until fixtures/tests are updated and committed (REVIEW.md F3); a new FORM (e.g. 1099-INT) also needs
2 lines in `returnguard/models.py` (F10); note number check is loose (F9). Findings F4–F13 are report-only.

## Status after Session 5b (polish fixes). Date: 2026-11-02
Branch: `returnguard/session-5b-polish` (from origin/main 30973e4), merged into `main`. Commits as `sakshiasati17`.

### Done (each approved by Sakshi before coding)
1. **Next-action wording**: `decide.NEXT_ACTION[APPLY_AND_REREVIEW]` now reads "Re-review the approvals listed in this
   report against the corrected document. ..." (string only). `tests/test_cli.py` assertion updated to the new
   wording (only the quoted string changed, no expected status/value). README limitation line removed.
2. **T12/T13 fixtures** (labels and paths only, no values or expected results changed):
   T12 description "AI misread: extraction says 1b 1060.00, form text says 1600.00", `llm_cache.extraction` ->
   `data/llm_cache/T12.json`; T13 description "Ungrounded AI reviewer note containing a number not in the checked
   facts" (`llm_cache.note` was already `data/llm_cache/T13_note.json`); both `llm_cache.status` ->
   "MOCKED: hand-written stand-in". `models.py`: the one stale comment above `CaseFixture.llm_cache` reworded
   (comment only, approved). The sidebar's PLACEHOLDER-hiding workaround in app.py is removed.
3. **UI never calls the API**: `cli.run_text_case(..., mode=None)` and `cli.run_all(config, log, mode=None)` gained an
   optional `mode` passed through to `extract()`. Default `None` = unchanged CLI behaviour. `app.py` always passes
   `mode="cached"` (with `use_live_cache` from the toggle, so LIVE recordings still replay). The UI live-mode warning
   is removed. **Note:** `run_all` needed the argument too. The new test first FAILED with only `run_text_case`
   changed, because the All cases tab runs T12 through `run_all` -> `run_text_case` with the default mode, which would
   have called the API in live mode. Fixed by the same passthrough.
   New test `test_app_never_calls_the_api_even_in_live_mode`: sets `RETURNGUARD_LLM=live` + a dummy key, asserts
   `live_enabled()` is True (final polish: `live_enabled()` removed; the test now asserts `has_api_key()`), patches `extract._call_live` to raise, then renders T1 (toggle ON -> LIVE replay, OFF ->
   MOCKED) and T12; all render with the expected status. Plus `test_fixture_descriptions_have_no_placeholder`.
4. **Form-text panel wraps** (`white-space: pre-wrap; overflow-wrap: anywhere`, no `overflow-x`). Checked in Chromium at
   1100px width: panel scrollWidth == clientWidth (344 == 344), no sideways scroll.
5. **README time log in Pacific time**, as git prints it (`PST`; DST ended 2026-11-01), from
   `TZ=America/Los_Angeles git log ... --date=format-local:'%H:%M %Z'`. First commit 10:41 PST (git's time: 18:41:40 UTC).
   Research/total placeholders kept. README test counts updated to 341 and the live-safety statement added.
6. Screenshots retaken: `T1.png`, `T1_above_fold.png`, `T12.png` (page text changed). `T5.png` and `all_cases.png`
   unchanged (nothing visible changed on them).

### pytest -q (real output, Session 5b, after committing the code + fixture changes)
```
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 63%]
........................................................................ [ 84%]
.....................................................                    [100%]
341 passed in 7.74s
```
Before committing, `test_fixture_files_untouched_after_run` failed only because the approved T12/T13 edits were still
uncommitted (it checks `git status` of `data/`); it passes on the committed tree. `python3 cli.py --all`: all 15 rows
`match`, exit 0. Headless app served HTTP 200; T1 next action shows the new wording, T12 sidebar shows the new description.

### Known issues (still open)
1. Abbreviated box labels won't verify (fails safe); note check checks numbers, not direction; IRS mappings listed in
   README still UNVERIFIED; filing status entered by hand. (Unchanged.)
2. Streamlit prints "missing ScriptRunContext" warnings when helpers run outside `streamlit run` (harmless).
3. GitHub default branch: `returnguard-setup` was brought up to date with `main` via PR #5 (merged), but `main` is
   still not the default. Sakshi: Settings -> General -> Default branch -> `main`.
Session 5 known issues 1-4 (wording, PLACEHOLDER text, UI live calls, sideways scroll) are resolved above.

### Next: Session 6
Fresh-eyes review from a clean clone -> `REVIEW.md` (report only, no code fixes).

---

## Status after Session 5 (app.py Streamlit UI + README). Date: 2026-11-02
Branch: `returnguard/session-5-ui-readme` (from origin/main 1c4aebd), merged into `main`. Commits as `sakshiasati17`.
The cloud session's auto-assigned `claude/sweet-carson-qi1ewb` branch was NOT used. **No file under `returnguard/`,
`config/`, `data/` or `cli.py` was changed.**

### Done
- **`app.py`** (display only). Calls only existing functions: `cli.run_text_case` (T1, T4, T5, T12 from
  `data/synthetic/raw/*.txt`), `cli.run_case` (all other cases), `cli.run_all` (All cases tab: its text table is
  split into rows, so the tab shows exactly what `python3 cli.py --all` prints), `explain.grounded_note` +
  `load_cached_note`, `decide.naive_total_changed`, `explain.unverified_boxes`. `log=None` everywhere: the UI never
  writes the audit log.
  - Sidebar: case picker (T1, T12, T5, T3, T4 with headline labels, then T2, T6-T11, T13-T15 by fixture angle),
    toggle "Use saved live AI outputs where available" (default ON -> `use_live_cache=True`; T1/T4/T5 replay
    `.live.json` = LIVE, T12 falls back to MOCKED), About box, and a warning if `RETURNGUARD_LLM=live` + key are set (superseded: Session 5b removed the warning; since final polish the env variable does nothing)
    (text cases would then call the API; `run_text_case` has no mode argument).
  - Main ("Case review" tab), top to bottom: header + "Synthetic data · prototype" tag; status banner (coloured left
    border, next action, "Nothing is ever approved automatically."); naive check vs ReturnGuard cards (1099-DIV only);
    "What the AI read" (LIVE/MOCKED pill, monospace form text with each checked line highlighted ✓ verified / ✗ AI read
    X — form says Y, checks table, raw text expander; JSON cases: "Structured input (no AI step)"); "What changed"
    (before/after/delta, applied pill, "(unverified extracted value)" tag); "Approvals that need re-review" as chips
    (dashed + "unverified mapping" when the config flags it); "Reviewer note" with source and rejected numbers (T13);
    "Reasons and evidence" expander; footer.
  - T7 (two submissions): banner shows the last decision plus the sequence APPLY_AND_REREVIEW -> DUPLICATE_NO_CHANGE.
  - All helpers that build HTML are pure functions (`status_banner`, `naive_cards`, `evidence_panel`, `checks_table`,
    `changes_table`, `approvals_html`, `note_html`, `all_cases_html`); `main()` only runs under `__main__`.
- **`.streamlit/config.toml`**: light theme, primary #0F6E6E, bg #FAFAF7, secondary #F1F0EB, text #1F2328, sans serif,
  usage stats off. Inline CSS uses translucent tints, no hard-coded white, max width 1100px, 8px rhythm.
- **`tests/test_app_smoke.py`** (8 tests, AppTest drives the real page): T1 (APPLY_AND_REREVIEW, -800.00, both
  approvals, naive "→ No", LIVE pill), T1 with toggle OFF (MOCKED, same status), T12 (SPECIALIST_REVIEW, UNVERIFIED,
  1060.00, "AI read 1,060.00 — form says 1,600.00", unverified tag, MOCKED), T5 (CONFLICT, "None. Nothing changed."),
  T3 (POSSIBLE_AMENDMENT, no AI step), T13 (LLM note REJECTED, 900.00), All cases tab (15 of 15, 15 "✓ match"),
  and every fixture's banner status == its expected status. AppTest could drive all widgets; no fallback needed.
- **`README.md`** (new; there was none): every result pasted from real runs this session.
- **`docs/screenshots/`**: T1.png, T1_above_fold.png, T12.png, T5.png, all_cases.png (Playwright + Chromium against
  `streamlit run app.py --server.headless true`; the script reported T1 APPLY_AND_REREVIEW, T12 SPECIALIST_REVIEW,
  T5 CONFLICT, "15 of 15 match expected").

### pytest -q (real output, Session 5)
```
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 63%]
........................................................................ [ 84%]
...................................................                      [100%]
339 passed in 6.35s
```
(331 before this session + 8 new.) `python3 cli.py --all`: all 15 rows `match`, exit 0. Headless server check:
`curl http://localhost:8501/` -> HTTP 200, `/_stcore/health` -> `ok`; server stopped afterwards.

### Decisions made (Session 5, all approved by Sakshi before coding)
1. T1/T4/T5 run from form text in the UI (so "What the AI read" is real); `cli.py --all` still runs them from JSON.
   Same statuses either way (tested).
2. UI passes `log=None`: Streamlit re-runs on every click, so it would spam the append-only log. CLI logs as before.
3. venv + `pip install -r requirements.txt` (streamlit/pytest were not installed in the container). Python 3.13 here.
4. README time log uses `TZ=UTC ... --date=format-local:'%H:%M'`: with plain `--date=format` the GitHub web merge of
   PR #1 shows 11:03 (-0800) instead of 19:03 UTC.

### Known issues (found this session; NOT fixed, outside scope)
1. `decide.NEXT_ACTION[APPLY_AND_REREVIEW]` says "approvals listed above"; in the UI (and CLI) they are listed below.
   Wording only; left alone because `returnguard/` was out of scope. Listed in README limitations.
2. T12/T13 fixture `description` and `llm_cache.status` still start "PLACEHOLDER: ... built in Session 4".
   The UI strips the "PLACEHOLDER: " prefix in the sidebar caption (display only); the CLI still prints it.
   Fixture text should be cleaned in a data-scoped session.
3. (Resolved in 5b; since final polish `RETURNGUARD_LLM=live` does nothing.) If `RETURNGUARD_LLM=live` and a key are set when the UI runs, text cases call the API and overwrite `.live.json`
   (the UI shows a warning). A `mode` argument on `cli.run_text_case` would let the UI force cached mode.
4. Long W-2c lines scroll horizontally in the evidence panel at laptop width.
5. **GitHub default branch is `returnguard-setup`** (at 478898f, Session 4 code, no app.py), not `main`. A plain
   `git clone` gets old code. README now clones with `-b main`. Sakshi: set the default branch to `main` in GitHub
   Settings -> General -> Default branch (or delete `returnguard-setup`).
6. Streamlit prints "missing ScriptRunContext" warnings when helpers run outside `streamlit run` (harmless).

### Next: Session 6
Fresh-eyes review from a clean clone -> `REVIEW.md` (report only, no code fixes). Suggested checks: follow the README
quick start exactly in a new venv, run the demo path T1 -> T12 -> T5 -> T3, confirm labels (SYNTHETIC / MOCKED /
LIVE), and look at known issues 1-3 above.

---

## Status after Session 4 (extract.py + explain.py: the AI step). Date: 2026-11-02
Branch: `returnguard/session-4-extract-explain`, merged into `main`. Commits as `sakshiasati17`.
(The cloud session's auto-assigned `claude/loving-ptolemy-lndqda` branch was NOT used, as agreed.)

### Done
- **Raw form text** `data/synthetic/raw/T1.txt, T4.txt, T5.txt, T12.txt`: each starts with
  "SYNTHETIC - NOT A REAL TAX DOCUMENT". 1099-DIV: `[X] CORRECTED`, payer + TIN, recipient C-001, tax year 2025,
  boxes 1a/1b/2a/4 with `$` and commas. W-2c: employer TIN, tax year, `Box 1 ... | Previously reported $... |
  Correct information $...`. T12.txt = T1's text (1b is $1,600.00). Values match the fixtures (tested).
- **Hand-written MOCKED stand-ins** `data/llm_cache/T1, T4, T5, T12.json, T13_note.json`: `"mocked": true`,
  `"_label": "MOCKED: hand-written stand-in for an LLM output, not a real model call"`, `"source": "hand-written"`,
  `"model": null`, `prompt_version`, `written_at`, extraction in the fixed schema. T12 = T1 except 1b `"1060.00"` and
  `"note": "deliberate misread injected for testing"`. T13_note says "fell by $900.00" (true delta -800.00).
  No model produced any of these files. Only real live outputs (`*.live.json`) may say "recorded"/"live".
- **`returnguard/extract.py`**: `EXTRACTION_SCHEMA`, `EXTRACTION_PROMPT`, `check_schema`, `extract`, `verify_extraction`,
  `findings_from_checks`, `build_correction`, `run_from_text`.
- **`returnguard/explain.py`**: `template_note`, `grounded_note`, `allowed_numbers`, `numbers_in`, `load_cached_note`.
- **`returnguard/decide.py`**: ONLY the optional `extra_findings=None` parameter (2 lines + docstring). Extra findings
  are put first and go through the unchanged category -> status rules. `extra_findings=[]` gives the identical Decision (tested).
- **`cli.py`**: `--from-text PATH --case ID` (full pipeline report); `--all` runs T12 from text and T13 with note
  grounding (no case skipped); `cli.py data/synthetic/cases/T12.json` routes through the text pipeline; single-case reports
  now end with a REVIEWER NOTE section showing its source. `LLM_CASES` is kept (test_decide.py imports it).
- **`requirements-llm.txt`**: optional `anthropic` SDK only. `requirements.txt` unchanged.
- **Tests**: `tests/test_extract.py` (41), `tests/test_explain.py` (23), `tests/test_cli.py` +6 (now 13). Total 321.

### pytest -q (real output, Session 4, after commit)
```
........................................................................ [ 22%]
........................................................................ [ 44%]
........................................................................ [ 67%]
........................................................................ [ 89%]
.................................                                        [100%]
321 passed in 3.72s
```
`python3 cli.py --all`: all 15 rows `match` (T12 "SPECIALIST_REVIEW (from text, MOCKED extraction, 1 UNVERIFIED)",
T13 "APPLY_AND_REREVIEW (LLM note rejected: 900.00; TEMPLATE note)"), exit 0.

### Extraction flow
`text -> extract() -> verify_extraction() -> findings_from_checks() -> build_correction() -> decide(extra_findings=...)
-> grounded_note()`. The LLM only fills `EXTRACTION_SCHEMA` (form_type, corrected, payer_or_employer_tin, tax_year,
fields{box: {value, previously_reported}}); the schema and `check_schema` reject any other key, so it cannot carry a
status, decision or advice. **Strict rule:** form type, corrected flag, TIN, tax year and every amount come ONLY from the
extraction. The optional `envelope` (doc_id, client_id, payer_name, corrects_doc_id, received_at = intake details the text
can't give) comes from the case fixture when there is one, else defaults (`SYN-TEXT-<case>`, client/payer name from the
accepted doc, no prior doc ID). Any other envelope key raises ValueError (tested).

### Labels
- Cache record `"mocked": true` -> `MOCKED`; `"live": true` -> `LIVE`. Anything else is an error.
- CLI prints `EXTRACTION: MOCKED (MOCKED: hand-written stand-in for an LLM output, not a real model call)` and
  `source: hand-written stand-in, no model was called`. For a live output: `EXTRACTION: LIVE`, the model, and either
  "live model call" or "replayed from a recorded live output, no API call this run". Notes: `REVIEWER NOTE [source:
  TEMPLATE | LLM (MOCKED) | LLM (LIVE)]`.
- A proposed value whose extraction failed the source check is shown as `1060.00 (unverified extracted value)` in
  "What changed", in the reasons line and in the template note (`explain.unverified_boxes`, `UNVERIFIED_TAG`).

### How verification works (code, not the LLM)
- Each extracted box: find lines that START with the box id (optionally "Box ") AND contain the box label (labels from
  forms.yaml `fields` / `unsupported_fields`, else `_FALLBACK_LABELS` in extract.py). Exactly one line must match.
- 1099-DIV: the part of that line after the box id must hold exactly ONE amount, equal (as Decimal, `$`/commas stripped)
  to the extracted value. So an amount that exists elsewhere in the text (1b = 3,200.00, which is 1a's amount) does
  NOT verify (tested).
- W-2c: "Previously reported" and "Correct information" segments are checked separately (swapped values fail, tested).
- Header: form name in text; corrected flag must equal whether `[X] CORRECTED` or `Form W-2c` appears; TIN must be on a
  TIN/EIN line; every "TAX YEAR nnnn" in the text must equal the extracted year.
- Any failure -> `Finding(code="EXTRACTION_UNVERIFIED", category="SPECIALIST", field="1099-DIV:1b", evidence={extracted,
  found_in_text, line})` -> SPECIALIST_REVIEW via the existing priority. The extracted value is never replaced (tested:
  T12's CorrectionDocument still says 1060.00).

### How notes are grounded
Allowed numbers = old/new/delta (delta with and without sign) of each proposed change, accepted and raw correction values,
numbers inside box ids, form names, stale-approval ids/items/paths (e.g. 1040, 3 from "line 3a"), finding fields and
evidence values, both doc IDs (2025, 1099, 13 ...), and the new version's tax year. Numbers in the LLM note are pulled with
a regex that handles `$`, commas, signs and decimals; a sign is only read when not glued to a word (so "C-001" is 1, not -1).
Comparison is Decimal (1,600 == 1600.00). Any number not allowed -> note rejected, `rejected_numbers` recorded, template
used; the rejected draft is kept in `NoteResult.llm_text` for the audit trail. The template only uses Decision fields and
passes its own check (tested on 9 cases).

### Live mode (optional, never used by tests)
**Superseded by final polish:** live now needs the CLI `--live` flag plus `ANTHROPIC_API_KEY`; `RETURNGUARD_LLM=live`
alone does nothing and `--all` never calls the API. Current commands:
```
pip install -r requirements.txt -r requirements-llm.txt
export ANTHROPIC_API_KEY=...        # optional: RETURNGUARD_LLM_MODEL (default claude-haiku-5-5)
python3 cli.py --from-text data/synthetic/raw/T1.txt --case T1 --live
# later, replay that real output with no API call:
python3 cli.py --from-text data/synthetic/raw/T1.txt --case T1 --use-live-cache
```
One `messages.create` call with `EXTRACTION_PROMPT` (schema embedded): `model`, `max_tokens=16000`, `messages`,
`output_config={"effort": "low"}`. **Left out because Claude Haiku 5.5 returns HTTP 400 for them:** `temperature` /
`top_p` / `top_k` (non-default sampling values), `thinking` with `budget_tokens`, and an assistant prefill. Haiku 5.5
thinks by default and thinking counts toward `max_tokens`, so the cap is generous, only `text` blocks are read, and a
`max_tokens` or `refusal` stop is an error (no partial extraction). Output parsed as JSON and passed through `check_schema`.
The real output is recorded to `data/llm_cache/<case>.live.json` (`"live": true`, `"source": "live"`, model, `recorded_at`);
the hand-written MOCKED files are never overwritten. `--use-live-cache` (or `use_live_cache=True`) replays the `.live.json`
when it exists, labelled LIVE, else falls back to the MOCKED file. (Session 4 behaviour, superseded by final polish: `RETURNGUARD_LLM=live` without a key -> still cached;
`mode="live"` without both -> clear error.) Tests delete both env vars and monkeypatch `_call_live` to raise; one test stubs
it to check the LIVE save path; one runs the real `_call_live` body against a FAKE `anthropic` module to check the request
leaves out the rejected parameters. `test_recorded_live_outputs_verify_against_raw_text` checks any `*.live.json` against
the raw text and is SKIPPED while none exist (currently skipped).

### Decisions made (Session 4)
1. **No `temperature=0` in the live call (deviation from the session prompt).** The default live model is now
   `claude-haiku-5-5` (follow-up), which returns HTTP 400 for non-default `temperature`/`top_p`/`top_k` (checked against
   the Claude API reference). Determinism comes instead from the fixed prompt + schema, `check_schema`, and code
   verification. Live mode was NOT run (no key; tests must stay free), so `_call_live` is untested against the real API
   (its request shape is tested against a fake SDK).
2. **T12 cache file is `data/llm_cache/T12.json`**, not `T12_extraction.json` as the T12 fixture's `llm_cache` placeholder
   says. Fixture not edited (no code reads that path). T12/T13 fixture descriptions still start "PLACEHOLDER:" for the
   same reason.
3. **`test_all_every_row_matches` updated** (approved): it used to expect "LLM case: Session 4" for T12/T13; it now expects
   `match` for all 15 rows. No expected status changed. T12's row only matches if an UNVERIFIED field was found; T13's
   only if the LLM note was rejected.
4. Cached amounts are stored "as printed" with commas (`"3,200.00"`); validate.py already accepts that, and the
   correction fingerprint normalises it, so T1-from-text has the same fingerprint as T1-from-JSON (tested).
5. `run_from_text` takes `accepted` as one document or `{form_type: doc}` (then picks the doc the extracted form
   corrects), plus `envelope=None` (approved) and `mode=None`.

### Known issues
1. `_call_live` never exercised against the real API (see decision 1).
2. Amounts in text must have 2 decimals to be found (`$3,200` without cents does not verify -> UNVERIFIED, safe side).
3. A box line must contain the config label text; a form that abbreviates labels (Session 1 fixtures' `source_text` uses
   "Total capital gain distr.") would not verify. Raw files use full labels. Could add aliases in forms.yaml later.
4. If the extraction omits a box that IS in the text, the reissue MISSING_FIELD check (validate.py) catches it; there is
   no separate "box in text but not extracted" check.
5. T12's proposed change shows 2400.00 -> 1060.00 (the unverified value), marked "proposed, not applied", so the reviewer
   sees exactly what the AI claimed.
6. Grounding checks numbers, not wording: a note could cite only allowed numbers but describe them wrongly
   (e.g. "rose by 800.00"). The template is the safe default.

### Session 4 follow-up (same day, same branch, merged again)
1. MOCKED file labels/keys changed as above (`source`, `model: null`, `written_at` instead of `recorded_at`, T12 `note`);
   CLI header, docstrings, HANDOFF and CLAUDE.md's layout line no longer call them "recorded".
2. Default live model `claude-haiku-5-5`, overridable with `RETURNGUARD_LLM_MODEL`; rejected parameters left out (above).
3. `--use-live-cache` flag + conditional live-output verification test (skips when no `.live.json`).
4. T12's proposed 1b value labelled "(unverified extracted value)" everywhere it is shown.
5. Error text for a missing cache: "no cached extraction for case ..." (was "no recorded extraction").
Tests: `test_extract.py` 48 (1 skipped: no live file), `test_explain.py` 23, `test_cli.py` 14.
pytest -q (real output, follow-up): `328 passed, 1 skipped in 3.52s` (the skip is the live-output check: no
`*.live.json` exists). `python3 cli.py --all`: all 15 rows `match`, exit 0.

### Live run (2026-11-02, T1 / T4 / T5)
- `RETURNGUARD_LLM=live python3 cli.py --from-text data/synthetic/raw/<case>.txt --case <case>` with `claude-haiku-5-5`
  (the Session 4 switch, prompt `extract-v1`; today the same run is `python3 cli.py --from-text ... --case <case> --live`).
  Each first call succeeded. Saved `data/llm_cache/T1.live.json`, `T4.live.json`, `T5.live.json` (`"live": true`,
  `"source": "live"`, model, `recorded_at`). Every value VERIFIED against the source text (T1 8/8, T4 6/6, T5 6/6).
  Statuses: T1 APPLY_AND_REREVIEW (-800.00), T4 APPLY_AND_REREVIEW (+4500.00), T5 CONFLICT, matching expected.
  So `_call_live` has now worked against the real API for these three cases.
- `test_recorded_live_outputs_verify_against_raw_text` now RUNS (3 cases, passing) instead of skipping. It and every
  other test still run with no key and no network (they replay the `.live.json` files).
- **Test change (no expected value changed):** `test_use_live_cache_without_live_file_falls_back_to_mocked` used T1,
  assuming no `T1.live.json` existed; after the live run the flag correctly replays T1 as LIVE, so the test's premise
  was stale. It now uses T12 (no live file; asserted), still checks the fallback to MOCKED, and expects T12's status
  SPECIALIST_REVIEW.
- Key handling: the API key was never printed or committed (a git grep for the Anthropic key prefix finds nothing); the temporary copy used
  for the run was deleted. The key was pasted in chat, so Sakshi will rotate it.
- T12 live was not run on purpose: T12 exists to test a misread, and the live check test skips it.

### Next: Session 5
`app.py` (Streamlit) + `README.md`. Reuse `cli.run_text_case`, `extraction_section` data (`ExtractionReport.checks`),
`grounded_note`. Show the MOCKED label prominently in the UI.

---

## Status after Session 3 (decide.py + audit.py + cli.py). Date: 2026-11-02
Branch: `returnguard/session-3-decide-audit-cli`, merged into `main`. Commits as `sakshiasati17`.

### Done
- **Step 0 (validate.py, small change)**: new `check_completeness()` (style read from forms.yaml), called in
  `validate()` after the prior-value check.
  - `MISSING_PRIOR_VALUE` / SPECIALIST: style `previous_and_correct` (W-2c), a box whose value CHANGES but has
    no `previously_reported`. An unchanged box without it is fine.
  - `MISSING_FIELD` / SPECIALIST: style `reissue` (1099-DIV), a box the accepted doc has but the correction omits.
  - Neither fires on any existing fixture (tested). Tested with in-memory variants of T4 / T1 only.
- **`returnguard/audit.py`**: `fingerprint`, `correction_fingerprint`, `with_baseline_fingerprints`, `new_version`,
  `is_stale`, `AuditLog` (append / read only), `log_record`.
- **`returnguard/decide.py`**: `decide()`, `load_config()`, `ProcessingState`, `Decision` (+ `ProposedChange`,
  `StaleApproval`, `DecisionEvidence`), `NEXT_ACTION`, `naive_total_changed()`, `signed()`.
- **`cli.py`** (repo root): report / `--json` / `--all` / `--log PATH`.
- **Tests**: `test_decide.py` (77), `test_audit.py` (17), `test_cli.py` (7), `test_validate.py` +15 (Step 0). Total 251.

### pytest -q (real output, Session 3)
```
........................................................................ [ 28%]
........................................................................ [ 57%]
........................................................................ [ 86%]
...................................                                      [100%]
251 passed in 1.82s
```

### Status mapping (decide.py, first match wins; written at the top of the file)
1. any INVALID finding -> REJECTED_INVALID_INPUT
2. any SPECIALIST finding -> SPECIALIST_REVIEW
3. any CONFLICT finding -> CONFLICT
4. same correction fingerprint already in `state`, or NO_SUPPORTED_CHANGE -> DUPLICATE_NO_CHANGE
5. return status FILED -> POSSIBLE_AMENDMENT
6. otherwise -> APPLY_AND_REREVIEW

`python3 cli.py --all` (real run): T1–T11, T14, T15 all `match` (T7 = APPLY_AND_REREVIEW, DUPLICATE_NO_CHANGE);
T12 / T13 skipped ("LLM case: Session 4").

### Decision fields (`returnguard.decide.Decision`, frozen pydantic)
| Field | Meaning |
| --- | --- |
| `status` | one of the six statuses |
| `reasons` | plain English: docs compared, each finding message (INFO only when nothing blocking), each change, "nothing changed" (1–4) or new version + each stale path (5–6), FILED note, "No approval has been granted or cleared automatically." |
| `proposed_changes` | every `FieldChange` + label. `applied` = True only for APPLY_AND_REREVIEW; `applied_as_new_version` = True for 5–6. So T3 (FILED) is recorded as a new version but NOT applied. |
| `stale_approvals` | 5–6 only, one per approval: `paths`, `sources` (prefixed `UNVERIFIED: `), `unverified`, `fingerprint_before/after`. Empty for 1–4. |
| `evidence` | both doc IDs, accepted values, raw correction values, all findings, return status + MOCKED source |
| `next_action` | exact wording from the session prompt (`NEXT_ACTION` dict) |
| `correction_fingerprint` | SHA-256 of the correction (duplicate detection, audit log) |
| `new_version` | the new document version record (5–6 only), else null |
| `clears_approvals` | `Literal[False]`: cannot be True (tested) |

### Decisions made (Session 3)
1. **`Decision` lives in decide.py**, not models.py (models.py untouched; `models.Decision` is now unused by the
   pipeline). Same pattern as Session 2's `Finding` in validate.py.
2. **`config` = forms.yaml + dependencies.yaml merged** (`decide.load_config`), so `decide()` keeps the
   5-argument signature: `validate()` reads `config["forms"]`, `find_impact()` reads `config["dependencies"]`.
3. **Fingerprint identity = form type + client_id + tax_year + payer_tin, NOT doc_id / version** (approved default):
   a new version is comparable field by field, and the same content re-sent under a new doc ID is still a duplicate.
   Values are 2-dp strings, sorted keys, compact JSON. A missing box is `null` (differs from `"0.00"`).
4. **Correction fingerprint** covers every box's value and previously_reported (parsed to 2 dp, so `"$3,200"` ==
   `"3200.00"`) plus the CORRECTED flag; unparseable amounts are kept as `"RAW:<text>"` (T10).
5. **Baseline approval fingerprints** are computed at load time (`with_baseline_fingerprints`) from the accepted
   doc of the approval's form; fixture files are never edited. `is_stale` compares against the stored fingerprint
   (or computes it) vs the new-version fingerprint, using only based_on fields on that form.
6. **`is_stale(approval, accepted, correction, config)`** takes `config` as a 4th argument (needed to parse the
   correction and map W-2c -> W-2), like Session 2's checks.
7. **New version record** = an `AcceptedDocument` with the correction's doc_id, version + 1, supported changes
   applied, label "SYNTHETIC: … Proposed for CPA re-review; not approved." Accepted object never modified (tested).
8. **Naive baseline** (`NAIVE_TOTAL_FIELD = {"1099-DIV": "1a"}` in decide.py) is for comparison only, never used to
   decide. It's the only box name in decide.py; W-2c reports show no naive line.
9. Test fix (no expected value changed): fixture deltas are written unsigned when positive (`"4500.00"`) while
   the CLI prints `+4500.00`; the test compares deltas as Decimals.

### How state / duplicates work
- `ProcessingState` (in memory): `seen` = correction fingerprint -> first doc_id; `versions` = new version records.
- `decide()` records every correction's fingerprint (any status) and stores the new version for 5–6.
- A repeat fingerprint -> DUPLICATE_NO_CHANGE (priority 4, so a repeated INVALID/SPECIALIST/CONFLICT keeps its
  higher status). `decide()` always compares against the `accepted` passed in, not the latest version in state.
- **One fresh state per fixture** (CLI `--all` and tests); submissions inside one fixture (T7) share it. So T1 and
  T13 (identical values) never mark each other duplicate (tested).
- Audit log: `AuditLog(path).append()` opens in `"a"` mode only; one JSON line per decision: timestamp, case_id,
  both doc IDs, correction fingerprint, status, stale approval IDs, applied changes, new_version_doc_id,
  clears_approvals. T7 log shows exactly one applied change (tested). Tests use `tmp_path`.

### CLI usage
```
python3 cli.py data/synthetic/cases/T1.json          # readable report (status, changes, stale paths, reasons, next action)
python3 cli.py data/synthetic/cases/T1.json --json   # Decision as JSON (a list for multi-submission cases like T7)
python3 cli.py --all                                 # table: case, expected, actual, match; exit 1 on any mismatch
python3 cli.py --all --log /tmp/x.jsonl              # audit log elsewhere (default out/audit_log.jsonl, gitignored)
```

### Known issues / notes
1. **T12 has empty `fields`**: with Step 0 it now raises MISSING_FIELD for all four boxes (-> SPECIALIST_REVIEW).
   Session 4 must fill fields from extraction before `decide()`; the expected status is SPECIALIST_REVIEW anyway.
2. T5 still lists the box 1 change in `proposed_changes` (marked "proposed, not applied") so the CPA sees what the
   W-2c claims; nothing is applied, no version, no stale approvals.
3. `naive_total_changed` is defined only for 1099-DIV (box 1a); add a form to `NAIVE_TOTAL_FIELD` if needed.
4. Only DIRECT dependencies are walked (unchanged from Session 2).
5. The CLI appends to `out/audit_log.jsonl` on every run (by design; it's append-only and gitignored).
6. `models.Decision` / `ChangedField` / `Evidence` are now unused by the pipeline but kept (models.py not in scope).

### Still UNVERIFIED IRS items (unchanged from Session 2)
1099-DIV 1a -> 1040 line 3b; W-2 box 1 -> line 1a; W-2 box 2 -> line 25a; 1099-DIV box 4 -> line 25b;
which QDCG worksheet lines take 1b / 2a; W-2 / W-2c box labels. The CLI shows `[UNVERIFIED]` on these.

### Next: Session 4
`extract.py` (LLM extraction, cached by default from `data/llm_cache/`, labelled MOCKED; every amount must
appear in `source_text` next to its box label, else UNVERIFIED -> SPECIALIST_REVIEW) and `explain.py` (grounded
reviewer note; any number not in the Decision's facts -> template note). Then remove T12/T13 from `cli.LLM_CASES`
and wire them into `run_case`.

---

## Status after Session 2 (validate.py + impact.py). Date: 2026-11-02
Branch: `returnguard/session-2-validate-impact`, merged into `main`.

### Done
- **Step 0**
  - `pytest.ini` (`[pytest] pythonpath = .`); `sys.path` hack removed from `tests/test_models.py`. 70 Session 1 tests still pass.
  - IRS pages: `www.irs.gov` is **still blocked** in this cloud session (proxy 403 / DNS failure for
    i1040gi, i1040sd, i1099div). To let Claude read them, add `www.irs.gov` under Allowed domains in the
    environment's Network access settings.
  - Sakshi opened the IRS pages herself on 2026-11-02 and supplied quotes. Those items are now quoted in config
    comments and marked "confirmed by Sakshi from the IRS page, 2026-11-02" (table below).
  - Comment fixes: forms.yaml header no longer claims W-2 / W-2c labels were checked (marked # UNVERIFIED);
    the no-Schedule-D note now says Form 1040 **line 7a** (confirmed); the 1099-DIV:4 comment no longer
    claims the source names box 4; the 1099-DIV instructions (Rev. 01/2024) are noted as "continuous use"
    (last reviewed 30-Apr-2026), not as an old edition.
- **`returnguard/validate.py`**: `Finding`, `FieldChange`, `ValidationResult` (frozen pydantic) + `load_forms`,
  `parse_amount`, `check_identity`, `check_correction_link`, `check_prior_values`, `check_form_rules`,
  `check_supported_fields`, `diff_fields`, `validate`. Pure and deterministic; all rules read from forms.yaml.
- **`returnguard/impact.py`**: `ImpactItem`, `load_dependencies`, `find_impact`, `stale_approval_ids`. No box
  names, lines or approval IDs in the code (grep `'"(1a|1b|2a|4|box)'` finds nothing).
- **Tests**: `tests/test_validate.py` (50), `tests/test_impact.py` (15). Total 135.

### pytest -q (real output, Session 2)
```
........................................................................ [ 53%]
...............................................................          [100%]
135 passed in 0.45s
```

### Finding codes (Session 3 maps categories -> statuses; validate.py decides no status)
| Code | Category | Raised when |
| --- | --- | --- |
| MALFORMED_AMOUNT | INVALID | raw amount has letters / bad comma grouping / empty / not text (e.g. `"86,5OO"`) |
| NEGATIVE_AMOUNT | INVALID | raw amount starts with `-` |
| BAD_PRECISION | INVALID | more than 2 decimal places |
| FORM_RULE_VIOLATION | INVALID | a `rules:` entry in forms.yaml fails (e.g. QUALIFIED_LE_ORDINARY 1b <= 1a) |
| IDENTITY_MISMATCH | SPECIALIST | form family (`correction.corrects`) or any `identity_fields` value differs |
| NOT_MARKED_CORRECTED | SPECIALIST | `requires_corrected_flag: true` and CORRECTED not ticked |
| UNSUPPORTED_FIELD_CHANGE | SPECIALIST | a changed box is not in `fields` or not `supported` |
| SPECIALIST_FIELD_CHANGE | SPECIALIST | a changed box has `on_change: SPECIALIST_REVIEW` (W-2c box 2) |
| PRIOR_DOC_MISMATCH | CONFLICT | correction STATES a `corrects_doc_id` different from the accepted doc_id |
| PRIOR_VALUE_MISMATCH | CONFLICT | style `previous_and_correct` (W-2c): previously reported != accepted (exact Decimal) |
| NO_SUPPORTED_CHANGE | INFO | no supported field changed |

Results on the fixtures (real run):
| Case | Findings | Changes | Stale approvals (find_impact) |
| --- | --- | --- | --- |
| T1, T3 | none | 1099-DIV 1b 2400.00 -> 1600.00 (-800.00) | APR-1040-L3A, APR-QDCG-WS |
| T2 | none | 1a 3200.00 -> 3700.00 (+500.00) | APR-1040-L3B |
| T4 | none | W-2 1 82000.00 -> 86500.00 (+4500.00) | APR-1040-L1A, APR-WAGE-WP |
| T5 | PRIOR_VALUE_MISMATCH / CONFLICT | (box 1 diff still reported) | (see known issue 1) |
| T6 | SPECIALIST_FIELD_CHANGE / SPECIALIST | W-2 2 9000.00 -> 9800.00 | APR-1040-L25A |
| T8 | IDENTITY_MISMATCH / SPECIALIST (payer_tin 00-0000001 vs 00-0000009) | 1b diff reported | — |
| T9 | FORM_RULE_VIOLATION / INVALID (1b=3500.00, 1a=3200.00) | 1b diff reported | — |
| T10 | MALFORMED_AMOUNT / INVALID (W-2c:1, "86,5OO") + NO_SUPPORTED_CHANGE / INFO | none | none |
| T11 | NOT_MARKED_CORRECTED / SPECIALIST | 1a, 1b, 2a diffs reported | — |
| T14 | NO_SUPPORTED_CHANGE / INFO | none | none |
| T15 | UNSUPPORTED_FIELD_CHANGE / SPECIALIST (box 7 Foreign tax paid) + NO_SUPPORTED_CHANGE / INFO | none | none |
T7, T12, T13 not tested here (duplicates = Session 3; LLM cases = Session 4).

### Decisions made (Session 2)
1. **Models live in validate.py** (models.py untouched). `FieldChange.form_type` is the form the value lives on in
   the return: W-2c changes are reported as `W-2` (from `correction.corrects`), so impact keys are `W-2:1`.
2. **`check_identity`, `check_correction_link`, `check_prior_values` take `config` as a 3rd argument** (the brief
   showed two); form family, identity fields, corrected-flag policy and correction style all come from config.
3. **Missing `corrects_doc_id` is not a conflict** (T11 has none); only a stated, different ID is PRIOR_DOC_MISMATCH.
4. **A box missing from the accepted doc counts as old = 0.00** (T15 box 7: 0.00 -> 45.00 is a change).
   A box missing from the correction counts as unchanged (no finding).
5. **`allow_commas: true`** in forms.yaml `amount_rules` (agreed with Sakshi): incoming forms may show
   `"3,200.00"` / `"$3,200.00"`; correct thousands grouping only. `models.parse_money` (accepted docs) is unchanged
   and still strict. No code reads `allow_commas`; it documents the rule `parse_amount` enforces.
6. **`on_change: SPECIALIST_REVIEW` on W-2c box 2 is the specialist marker** (reused; no new key added).
7. **UNVERIFIED data flag**: YAML comments are invisible to code, so mappings that are still unverified carry
   `unverified: true`. `ImpactItem.unverified` is True and `source` is prefixed `"UNVERIFIED: "` for them.
   Set on: APR-QDCG-WS (both edges), APR-1040-L3B, APR-1040-L25B, APR-1040-L1A, APR-1040-L25A
   (the last four because Sakshi listed them as still unverified). Remove the flag when a page confirms it.
8. **1b -> line 3a source URL changed to i1040sd**, because that is the page the confirming quote came from.
9. **find_impact de-duplicates on (field, return line, approval)**, so an approval reached via two fields
   (1b and 2a -> APR-QDCG-WS) shows both paths; `stale_approval_ids()` gives the distinct set in first-seen order.
10. Findings order is fixed: parse, identity, link, prior values, form rules, supported fields, info.

### IRS mappings (tax year 2025) — current status
| Item | Source | Status |
| --- | --- | --- |
| 1099-DIV 2a -> Schedule D line 13 | i1040sd | **confirmed by Sakshi, 2026-11-02** (quoted) |
| No Schedule D -> Form 1040 line **7a** | i1040sd | **confirmed by Sakshi, 2026-11-02** (quoted) |
| 1099-DIV 1b -> Form 1040 line 3a | i1040sd | **confirmed by Sakshi, 2026-11-02** (quoted) |
| QDCG worksheet is in 1040 instructions, line 16 | i1040sd | **confirmed by Sakshi, 2026-11-02** (quoted) |
| Rule 1b <= 1a ("Box 1a includes amounts entered in boxes 1b and 2e") | i1099div | **confirmed by Sakshi, 2026-11-02** (quoted) |
| 1099-DIV box 4 label, box 7 label | i1099div | **confirmed by Sakshi, 2026-11-02** (quoted) |
| 1099-DIV instructions Rev. 01/2024 current ("continuous use", reviewed 30-Apr-2026) | i1099div | **confirmed by Sakshi, 2026-11-02** |

**Still UNVERIFIED** (marked `# UNVERIFIED` in config and `unverified: true` where it is a mapping):
- 1099-DIV 1a -> Form 1040 line 3b
- W-2 box 1 -> Form 1040 line 1a
- W-2 box 2 -> Form 1040 line 25a
- 1099 withholding (1099-DIV box 4) -> Form 1040 line 25b
- Which Qualified Dividends and Capital Gain Tax Worksheet LINES take 1b / 2a
- W-2 / W-2c box labels (forms.yaml header)

### Known issues / notes for Session 3
1. **`changes` are reported even when a blocking finding exists** (T5, T8, T9, T11 list diffs). That is on purpose
   (validation reports facts); decide.py must NOT apply changes or mark approvals stale when any
   INVALID / SPECIALIST / CONFLICT finding exists, and must show "nothing changed" for T5.
2. W-2c with a box that has no `previously_reported` is not flagged (fixtures always have one). Could add a
   `PRIOR_VALUE_MISSING` (CONFLICT) code if wanted.
3. A reissued 1099-DIV that omits a box is treated as "unchanged" for that box, not flagged.
4. Status mapping is Session 3's job: suggested INVALID -> REJECTED_INVALID_INPUT, SPECIALIST -> SPECIALIST_REVIEW,
   CONFLICT -> CONFLICT, then duplicates (fingerprints), FILED -> POSSIBLE_AMENDMENT, NO_SUPPORTED_CHANGE alone ->
   DUPLICATE_NO_CHANGE (T14), else APPLY_AND_REREVIEW. Priority order: docs/project_plan.md §5.
5. Use `python3 -m pytest -q` (pytest.ini handles the import path).

### Next: Session 3
`decide.py` (category -> status, priority order, filing status), `audit.py` (SHA-256 evidence fingerprints over
each approval's `based_on` fields, append-only log, T7 duplicate), `cli.py`, + tests.

---

## Status after Session 1 (skeleton, schemas, config, fixtures). Date: 2026-11-02

### Done
- `requirements.txt` (pinned: pydantic 2.13.5, PyYAML 6.0.3, pytest 9.2.0, streamlit 1.66.1) and `.gitignore` (Python, `.env`, `out/`).
- `docs/project_plan.md` and `docs/memo_v1.md` created verbatim from Sakshi's pasted text (explicitly allowed this session).
  (`docs/memo_v1.md` was later removed from the repo in the final cleanup.)
- `returnguard/models.py`: pydantic v2 models.
  - `Money` = `Decimal`, parsed by `parse_money`: non-negative, at most 2 dp, quantized to 0.01;
    rejects floats, bools, commas, letters, signs, `$`, exponents, NaN.
  - `AcceptedDocument` (checked `FieldValue` amounts), `CorrectionDocument` (RAW amount strings),
    `CorrectionField` (`value`, `previously_reported` for W-2c), `ReturnState` (status DRAFT | IN_REVIEW | APPROVED | FILED,
    `status_source` labelled MOCKED), `Approval` (id, item, approved_by, approved_at, based_on, evidence_fingerprint),
    `Decision` (status = the six CLAUDE.md statuses, reasons, changed_fields, stale_approvals, evidence,
    `clears_approvals: Literal[False]`), `ChangedField`, `Evidence`, and `CaseFixture`/`ExpectedResult` for the test-case files.
  - All models `extra="forbid"`, frozen; every data model requires `"synthetic": true`.
- `config/forms.yaml`: 1099-DIV boxes 1a, 1b, 2a, 4 (box 7 listed as known-unsupported); W-2 boxes 1, 2; W-2c boxes 1, 2
  (Box 2 `on_change: SPECIALIST_REVIEW`); rule `QUALIFIED_LE_ORDINARY` (1b <= 1a -> REJECTED_INVALID_INPUT);
  correction styles (`reissue` vs `previous_and_correct`); identity fields; amount rules.
- `config/dependencies.yaml`: field -> return line -> approval item, with an IRS URL per mapping.
- `data/synthetic/`: `accepted_1099div_C-001_2025.json`, `accepted_w2_C-001_2025.json`, `return_state_C-001_2025.json`
  (8 approvals, status APPROVED), and `cases/T1.json` … `cases/T15.json`. Each case file holds `return_status`,
  one or more `submissions` (T7 has two identical ones) and an `expected` block (status, deltas, stale approvals, must_show).
  Every file has `"synthetic": true` and a `_label` "SYNTHETIC: …".
- `tests/test_models.py`: 70 tests (fixtures load, labels, Decimal parsing, bad amounts raise, model guards, config consistency).

### pytest -q (real output, Session 1)
```
......................................................................   [100%]
70 passed in 0.17s
```

### Not done (by design: later sessions)
- No validation, impact, decision, audit, extraction, explanation logic, CLI or UI.
- `evidence_fingerprint` is `null` in the baseline approvals: Session 3 (`audit.py`) computes it.
- T12 / T13 are placeholders: `llm_cache` points to `data/llm_cache/T12_extraction.json` and `T13_note.json`,
  which Session 4 must create (labelled MOCKED). T12's `fields` is empty on purpose (extraction fills it).
- `data/llm_cache/` directory not created yet (git doesn't track empty dirs).

### Decisions made (and why)
1. **Correction amounts stay raw strings** in `CorrectionDocument`; validate.py (Session 2) parses them with
   `parse_money`. Reason: T10 (`"86,5OO"`) must become a REJECTED_INVALID_INPUT decision naming the field,
   not a crash when the file loads. Accepted documents use parsed `Money` because they were already checked.
2. **Negative amounts are rejected by `parse_money`** (no supported box may be negative). `ChangedField.delta`
   is a plain Decimal so it can be negative (T1 delta -800.00).
3. **W-2c maps onto W-2 fields**: dependency keys are `W-2:1` / `W-2:2`; forms.yaml says `W-2c.correction.corrects: W-2`.
4. **Approvals carry `based_on`** ("FORM:box" list) in addition to the fields asked for, so impact.py can fingerprint
   exactly the fields each approval relied on.
5. **Only direct dependencies are modelled.** Knock-on effects through totals (line 9, line 15 taxable income) are out of
   scope (no tax computation). So T2 (1a change) marks only line 3b stale, as in the plan table.
6. **2a also feeds the QDCG worksheet approval** (APR-QDCG-WS) and Schedule D line 13. No test case changes 2a yet.
7. **T7 expected**: `status` = DUPLICATE_NO_CHANGE (the second submission), with `status_sequence` =
   [APPLY_AND_REREVIEW, DUPLICATE_NO_CHANGE].
8. **T8** uses a payer-TIN mismatch only (00-0000009). A tax-year-mismatch variant is easy to add as another fixture.
9. **T10** fixture uses `"86,5OO"`; the negative-amount variant is covered in `tests/test_models.py`.
10. **T13** expected status = APPLY_AND_REREVIEW (same correction as T1; "status unchanged").
11. Each case file states `return_status` explicitly (T3 = FILED, all others APPROVED) instead of overriding the baseline file.
12. ~~`tests/test_models.py` sys.path hack~~ removed in Session 2; `pytest.ini` now sets `pythonpath = .`.

(Session 1's mapping table is superseded by the Session 2 table above.)
