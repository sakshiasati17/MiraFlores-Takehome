# REVIEW — Session 6 fresh-eyes review (ReturnGuard)

> Update after final polish (16:47 PST): findings F5, F6, F9, F10, F12 and F13 are fixed on main
> (364 tests pass). F4 is now listed as a README limitation; F8 and F11 are unchanged.

Reviewer role: a strict MiraFlores reviewer who had not seen the repo. Report only: no code, test, data or config
changed. The only files touched are this one, a README quick-start reorder (section 10) and a short HANDOFF entry.
Date: 2026-11-02. Reviewed commit: `main` @ `0dc82ed`. Python 3.13.18, Linux.

## 1. Summary verdict

**PASS for the prototype.** A clean clone of `main` installs, and all 341 tests pass. All 15 cases match their expected status, deltas and stale approvals. The UI renders every demo case correctly, and no API key or network is needed.
Safety holds under my own checks: 24 decisions checked, 0 with `clears_approvals` True, and the UI makes 0 API calls even in live mode with a key set.
A full read of `main` adds two caveats: a new *form* needs a 2-line Python change (F10), and the AI-note number check is loose (F9).
**Not ready to submit as-is:** `docs/writeup.md` (the ≤4-page explanation) is not in the repo. The GitHub default branch still serves an older
version, and the README time totals are still placeholders.

## 2. Clean-run log (STEP 1)

Run in a new folder, in a new venv, with `ANTHROPIC_API_KEY`, `RETURNGUARD_LLM` and `RETURNGUARD_LLM_MODEL` unset.

| # | Command (README word for word) | Real result |
| --- | --- | --- |
| 0 | `git clone https://github.com/sakshiasati17/MiraFlores-Takehome` (no `-b`) | **Branch `returnguard-setup` @ `24069f0`**: older code without Session 5b (README says 339 tests; the UI still warns that live mode calls the API). **Finding F1.** |
| 1 | `git clone -b main https://github.com/sakshiasati17/MiraFlores-Takehome.git` | OK, branch `main` @ `0dc82ed` |
| 2 | `cd MiraFlores-Takehome` | OK |
| 3 | `python3 -m venv .venv` | OK |
| 4 | `source .venv/bin/activate` | OK |
| 5 | `pip install -r requirements.txt` | OK: pydantic 2.13.5, PyYAML 6.0.3, pytest 9.2.0, streamlit 1.66.1 (+ deps). `anthropic` NOT installed (correct: optional). |
| 6 | `streamlit run app.py` | Server starts ("Local URL: http://localhost:8501") and **holds the terminal**. Steps 7–8 cannot run until Ctrl+C or a second terminal, and the README didn't say so. **Finding F2 (fixed in section 10).** |
| 7 | `python3 -m pytest -q` | `341 passed in 7.30s` |
| 8 | `python3 cli.py --all` | 15 rows `match`, exit 0 |

No step needed a key or network access. `git status` was clean after every run, including a failed live call.

## 3. Tests and every case (STEP 2)

### `python3 -m pytest -q` (full output)
```
........................................................................ [ 21%]
........................................................................ [ 42%]
........................................................................ [ 63%]
........................................................................ [ 84%]
.....................................................                    [100%]
341 passed in 7.30s
```

### `python3 cli.py --all` (exit 0)
```
case  expected                                 actual                                                          match
T1    APPLY_AND_REREVIEW                       APPLY_AND_REREVIEW                                              match
T2    APPLY_AND_REREVIEW                       APPLY_AND_REREVIEW                                              match
T3    POSSIBLE_AMENDMENT                       POSSIBLE_AMENDMENT                                              match
T4    APPLY_AND_REREVIEW                       APPLY_AND_REREVIEW                                              match
T5    CONFLICT                                 CONFLICT                                                        match
T6    SPECIALIST_REVIEW                        SPECIALIST_REVIEW                                               match
T7    APPLY_AND_REREVIEW, DUPLICATE_NO_CHANGE  APPLY_AND_REREVIEW, DUPLICATE_NO_CHANGE                         match
T8    SPECIALIST_REVIEW                        SPECIALIST_REVIEW                                               match
T9    REJECTED_INVALID_INPUT                   REJECTED_INVALID_INPUT                                          match
T10   REJECTED_INVALID_INPUT                   REJECTED_INVALID_INPUT                                          match
T11   SPECIALIST_REVIEW                        SPECIALIST_REVIEW                                               match
T12   SPECIALIST_REVIEW                        SPECIALIST_REVIEW (from text, MOCKED extraction, 1 UNVERIFIED)  match
T13   APPLY_AND_REREVIEW                       APPLY_AND_REREVIEW (LLM note rejected: 900.00; TEMPLATE note)   match
T14   DUPLICATE_NO_CHANGE                      DUPLICATE_NO_CHANGE                                             match
T15   SPECIALIST_REVIEW                        SPECIALIST_REVIEW                                               match
```

### Demo cases (key lines, real output)
- **T1 from JSON** `python3 cli.py data/synthetic/cases/T1.json`: `STATUS: APPLY_AND_REREVIEW`;
  `1099-DIV box 1b Qualified dividends: 2400.00 -> 1600.00  delta -800.00  [applied as new version]`; stale
  `APR-1040-L3A` (verified source i1040sd) and `APR-QDCG-WS [UNVERIFIED]`; `Naive check (did total income change?): no`.
- **T1 from text, live cache** `python3 cli.py --from-text data/synthetic/raw/T1.txt --case T1 --use-live-cache`:
  `EXTRACTION: LIVE`, `replayed from a recorded live output, no API call this run   model: claude-haiku-5-5`; 8 lines
  `VERIFIED`; `-> all values verified against the text`; `STATUS: APPLY_AND_REREVIEW`, same -800.00 and 2 stale approvals.
- **T12** `python3 cli.py --from-text data/synthetic/raw/T12.txt --case T12`: `EXTRACTION: MOCKED`;
  `UNVERIFIED  1099-DIV:1b: extracted 1060.00 | text shows 1600.00`; `-> UNVERIFIED values were NOT replaced; finding
  EXTRACTION_UNVERIFIED (SPECIALIST)`; `STATUS: SPECIALIST_REVIEW`; change shown as `2400.00 -> 1060.00 (unverified
  extracted value) ... [proposed, not applied]`.
- **T5** `python3 cli.py data/synthetic/cases/T5.json`: `STATUS: CONFLICT`; `W-2c box 1 previously reported 81000.00, but
  accepted W-2 SYN-W2-C001-2025-v1 shows 82000.00.`; `82000.00 -> 86500.00 delta +4500.00 [proposed, not applied]`;
  stale approvals `none`.
- **T3** `python3 cli.py data/synthetic/cases/T3.json`: `STATUS: POSSIBLE_AMENDMENT`; `Return status: FILED (MOCKED ...)`;
  `-800.00 [recorded as new version, NOT applied]`; 2 approvals listed for re-review.
- **T13** `python3 cli.py data/synthetic/cases/T13.json`: `STATUS: APPLY_AND_REREVIEW`; `LLM note REJECTED: numbers not
  in the checked facts: 900.00`; `Safe template note used instead`.
- Also replayed T4 and T5 from text with `--use-live-cache`: both LIVE, all values verified, APPLY_AND_REREVIEW and CONFLICT.

### Results table (expected = fixture `expected` block; stale lists and deltas compared by my own script)

| Case | Expected | Actual | Match | Note |
| --- | --- | --- | --- | --- |
| T1 | APPLY_AND_REREVIEW | APPLY_AND_REREVIEW | ✓ | 1b -800.00; stale L3A + QDCG-WS; naive check says "no" |
| T2 | APPLY_AND_REREVIEW | APPLY_AND_REREVIEW | ✓ | 1a +500.00; stale L3B (unverified mapping) |
| T3 | POSSIBLE_AMENDMENT | POSSIBLE_AMENDMENT | ✓ | FILED: new version recorded, not applied |
| T4 | APPLY_AND_REREVIEW | APPLY_AND_REREVIEW | ✓ | W-2c +4500.00; stale L1A + wage workpaper |
| T5 | CONFLICT | CONFLICT | ✓ | prev 81,000 vs accepted 82,000; nothing applied |
| T6 | SPECIALIST_REVIEW | SPECIALIST_REVIEW | ✓ | W-2c box 2 withholding change |
| T7 | APPLY_AND_REREVIEW → DUPLICATE_NO_CHANGE | same | ✓ | second identical copy is a no-op |
| T8 | SPECIALIST_REVIEW | SPECIALIST_REVIEW | ✓ | payer TIN mismatch |
| T9 | REJECTED_INVALID_INPUT | REJECTED_INVALID_INPUT | ✓ | 1b 3500 > 1a 3200 |
| T10 | REJECTED_INVALID_INPUT | REJECTED_INVALID_INPUT | ✓ | "86,5OO" rejected, no crash |
| T11 | SPECIALIST_REVIEW | SPECIALIST_REVIEW | ✓ | CORRECTED not ticked, values differ |
| T12 | SPECIALIST_REVIEW | SPECIALIST_REVIEW | ✓ | AI misread 1060 vs 1600 caught, not replaced |
| T13 | APPLY_AND_REREVIEW | APPLY_AND_REREVIEW | ✓ | ungrounded note (900.00) rejected |
| T14 | DUPLICATE_NO_CHANGE | DUPLICATE_NO_CHANGE | ✓ | corrected copy, all values identical |
| T15 | SPECIALIST_REVIEW | SPECIALIST_REVIEW | ✓ | box 7 not supported |

**15 of 15 match.** For blocked cases (T5, T6, T8, T9, T11) the code still lists the claimed change as "proposed, not applied". The fixtures expect
`deltas: {}` there, which is consistent: nothing is applied and nothing goes stale.

## 4. App check (STEP 3)

`streamlit run app.py --server.headless true` gives `HTTP 200`, and `/_stcore/health` returns `ok`. I drove it with headless Chromium (Playwright).

| Check | Result |
| --- | --- |
| T1 | `APPLY_AND_REREVIEW`; naive card "→ No" next to "→ APPLY_AND_REREVIEW, 2 approvals stale"; LIVE pill "claude-haiku-5-5 · recorded 2026-11-02 19:52:13 UTC replayed, no API call this run"; every form line "✓ verified" (green); What changed `2400.00 1600.00 -800.00 applied as new version`; APR-QDCG-WS shows "unverified mapping" ✓ |
| T12 | `SPECIALIST_REVIEW`; line "✗ AI read 1,060.00 — form says 1,600.00" on `div.rg-line.rg-bad` (red background `rgba(192,54,44,0.16)`, red border); checks table `1060.00 UNVERIFIED 1600.00`; MOCKED pill ✓ |
| T5 | `CONFLICT`; LIVE pill; `+4500.00 proposed, not applied`; "None. Nothing changed." ✓ |
| T3 | `POSSIBLE_AMENDMENT`; "recorded as new version, NOT applied" ✓ |
| All cases tab | "15 of 15 match expected", 15 "✓ match" ✓ |
| External requests from the browser | none |
| Form-text wrap at 1100px (HANDOFF claim) | T5 panel scrollWidth 344 == clientWidth 344 ✓ |
| **Live mode + fake key** | Installed the optional `anthropic` 2.4.0. Ran with `RETURNGUARD_LLM=live ANTHROPIC_API_KEY=fake-key-not-real ANTHROPIC_BASE_URL=http://127.0.0.1:9911`, where a local listener recorded every request. I first proved the listener works: the CLI live path sent `POST /v1/messages` ×3 to it. **UI run: all four cases and the 15-of-15 tab rendered as above, listener hits = 0, no errors in the server log.** ✓ |

Server stopped after each run. The browser check was complete, so no fallback was needed.

## 5. Safety and honesty checks (STEP 4, my own scripts, not the repo tests)

- **No approval is ever cleared: PASS.** I ran every fixture through `cli.run_case` → `decide()` (16 decisions, T7 gives two), plus
  the 4 text cases in cached and live-cache mode (8 decisions). That's 24 decisions, and `clears_approvals` was True for 0 of them.
  Building a `Decision` with `clears_approvals=True` raises a pydantic `ValidationError`. SHA-256 of
  `return_state_*.json` and both `accepted_*.json` is unchanged after all runs.
- **SYNTHETIC labels: PASS.** All 18 JSON files in `data/synthetic/` have `"synthetic": true` and `_label: "SYNTHETIC: ..."`.
  All 4 `raw/*.txt` files start with `SYNTHETIC - NOT A REAL TAX DOCUMENT`.
- **MOCKED labels: PASS.** `T1.json`, `T4.json`, `T5.json`, `T12.json`, `T13_note.json` in `data/llm_cache/` have `mocked: true`,
  `_label: "MOCKED: hand-written stand-in ..."`, `source: hand-written`, `model: null`.
- **LIVE labels: PASS.** `T1.live.json`, `T4.live.json`, `T5.live.json` have `live: true`, `source: live`,
  `model: claude-haiku-5-5`, and `recorded_at` 2026-11-02T19:52:13 / 19:52:20 / 19:52:26 +00:00.
- **Secrets: PASS.** `git grep -n "sk-ant"` finds nothing. Across all history, the only 2 matches are prose in HANDOFF.md ("git grep finds
  nothing"), since reworded. `api_key` matches are only env-var names in docs and code, plus test dummies
  (`dummy-key-for-test`, `test-not-a-real-key`). No `sk-…`, `AKIA…` or `ghp_…` strings. There are no SSN-shaped values, and the only
  EIN-shaped values are the synthetic `00-000000x`. `.env` is gitignored.
- **Config mappings marked `unverified: true` in `config/dependencies.yaml` (exact list, 6 edges):**
  1. `1099-DIV:1b` → Qualified Dividends and Capital Gain Tax Worksheet (`APR-QDCG-WS`): which worksheet lines take 1b
  2. `1099-DIV:1a` → Form 1040 line 3b (`APR-1040-L3B`)
  3. `1099-DIV:2a` → Qualified Dividends and Capital Gain Tax Worksheet (`APR-QDCG-WS`): which worksheet lines take 2a
  4. `1099-DIV:4` → Form 1040 line 25b (`APR-1040-L25B`)
  5. `W-2:1` → Form 1040 line 1a (`APR-1040-L1A`)
  6. `W-2:2` → Form 1040 line 25a (`APR-1040-L25A`)
  Also `# UNVERIFIED` in `config/forms.yaml`: the W-2 / W-2c box labels. `W-2:1 → Wage workpaper` is internal (not an IRS
  line) and has no flag. This matches README section 10 and HANDOFF.

### Further findings (not failures)
- **F3. Live-case rehearsal: config-only change works, but tests go red.** On a throwaway copy, I made 1099-DIV box 7 supported
  (`forms.yaml`) and added `1099-DIV:7 → APR-SCH3-L1` (`dependencies.yaml`). No Python changed. T15 became
  `APPLY_AND_REREVIEW` with `APR-SCH3-L1 [UNVERIFIED]` stale. `pytest` then gave **10 failed, 331 passed**:
  - 8 tests encode T15 / box 7 as unsupported (expected).
  - `test_cli.py::test_all_every_row_matches` fails because the T15 fixture still expects SPECIALIST_REVIEW.
  - `test_cli.py::test_fixture_files_untouched_after_run` fails on **any** uncommitted change under `config/`
    or `data/`, so it goes red during every live edit until the change is committed.
- **F4. The stale-approval list is not cross-checked against the return.** In that rehearsal, `APR-SCH3-L1` was reported stale
  although no such approval exists in `return_state_C-001_2025.json`. Stale IDs come from `dependencies.yaml` alone.
- **F5. A failed live call crashes the CLI.** With `RETURNGUARD_LLM=live` and an API error, it prints a raw Python traceback
  (`anthropic.InternalServerError: Error code: 500`) instead of a one-line error. It fails safe: no file written, no
  decision made.
- **F6. Wording contradiction.** For blocked cases (T5, T12), the report lists a proposed change under "What changed" and then says
  "Stale approvals: none (nothing changed)" / UI "None. Nothing changed.". "Nothing was applied" would be accurate.
- **F7. Fingerprints are content-only.** T1, T3 and T13 share the correction fingerprint `d3ac9ca6…`. That is by design
  (HANDOFF Session 3 decision 3) and safe because each fixture gets fresh state, but worth knowing if asked.
- **F8. The abbreviated-label limitation is real for the fixture source text.** `cases/T1.json` `source_text` prints
  `2a Total capital gain distr.`, which would not verify against the config label. The raw `*.txt` files use full labels.
  The README already lists this limitation.

### Findings from a full read of `main` (every source file, config, data file and test; added after the first push)
- **F9. The note check accepts numbers that happen to equal an ID.** Allowed numbers include those inside box ids, line
  names and doc IDs. For T1, `grounded_note` ACCEPTS "Qualified dividends fell by $3.00; 4 approvals are stale." and
  "fell by $2,025.00." (3 is from "line 3a", 4 from box 4, 2025 from the tax year), while "$1,000.00" is correctly rejected.
  Low exposure today, because the only AI note is the hand-written T13 stand-in and the template is the default. The README limitation
  ("checks numbers, not direction") understates it.
- **F10. A NEW FORM needs a Python change. A new FIELD does not.** `returnguard/models.py:103-104` hard-codes
  `AcceptedFormType = Literal["1099-DIV", "W-2"]` and `CorrectionFormType = Literal["1099-DIV", "W-2c"]`. With a
  1099-INT entry added only in `forms.yaml`, both models reject `form_type="1099-INT"`. After adding `"1099-INT"` to those two
  Literals (2 lines), plus config, an accepted doc and a fixture, a T16 1099-INT case ran end to end (APPLY_AND_REREVIEW, +50.00,
  stale APR-1040-L2B). Other form-specific Python: the extraction prompt names only 1099-DIV / W-2c (`extract.py`),
  `_FALLBACK_LABELS` (`extract.py`), `NAIVE_TOTAL_FIELD` (`decide.py:49`), and the naive card only for 1099-DIV (`app.py:162`).
  This contradicts README §3 and the `forms.yaml` header ("adding a form ... e.g. 1099-INT ... no new Python logic").
- **F11. Fingerprints are evidence, not the trigger.** `decide()` marks approvals stale purely from the `dependencies.yaml` walk.
  SHA-256 fingerprints are computed and reported (before/after) but don't decide staleness, and `audit.is_stale()` is never called
  by the pipeline. The README wording ("mark approvals stale, with SHA-256 evidence fingerprints") is accurate but easy to misread.
- **F12. `cli.py --all` follows the shell's live setting.** With `RETURNGUARD_LLM=live` and a key exported, `python3 cli.py --all`
  makes a real API call for T12 and writes `data/llm_cache/T12.live.json`. If the model reads 1b correctly, T12 then shows MISMATCH
  (by design T12 must catch a misread). Unset the variables before demoing `--all`.
- **F13. An unexpected form type from the AI stops with an error.** If an extraction returns a form type not in `forms.yaml` or
  not in the model Literals, `run_from_text` / pydantic raise instead of producing a SPECIALIST_REVIEW decision. That fails safe
  (nothing applied), but it isn't graceful.
- **Live-case good news.** The running UI picks up config edits on a page reload, with no restart. Tested on a copy: after
  making box 7 supported, T15 showed APPLY_AND_REREVIEW with APR-SCH3-L1, and the All cases tab showed "14 of 15" with T15 MISMATCH until
  the fixture's expected block is updated. Every value shown in the UI is passed through `html.escape`.
- No test is skipped or xfailed (`pytest -rs`: 341 passed, 0 skipped).

## 6. Brief compliance (STEP 5)

| Brief requirement | Verdict | Proof |
| --- | --- | --- |
| Three problems (where, who, what happens) | **Partly** | Only `docs/memo_v1.md` §1. Its own header says problems B and C have since changed. The final write-up is not in the repo. |
| Chosen problem, why, why ahead of the other two | **Partly** | `memo_v1.md` §2, `project_plan.md` §1–2. Final write-up missing. |
| Observed vs assumed | **Partly** | `memo_v1.md` §2 "What is observed vs. assumed". Final write-up missing. |
| Current approach and better outcome | **Partly** | `memo_v1.md` §3. Final write-up missing. |
| Direction + smallest first step | **Partly** | `memo_v1.md` §4 (v1: W-2c box 1 only), `project_plan.md` §3. |
| Credible alternative and why not | **Partly** | `memo_v1.md` §5 (end-to-end LLM; manual checklist). |
| AI vs software vs process | **Met (code) / partly (write-up)** | `project_plan.md` §3 "AI suggests → code verifies → CPA decides"; README §3, §11. |
| Broader opportunity | **Partly** | `memo_v1.md` §8; README §13. |
| What to learn, when to stop | **Partly** | `memo_v1.md` §8 "Stop or pivot if". README §13 covers next steps, not stop criteria. |
| Working prototype, one core workflow end to end | **Met** | Corrected-form text → AI extraction → source check → validation → dependency walk → status + note (section 3 above) |
| Representative case | **Met** | T1 (section 3, section 4) |
| Difficult / invalid case | **Met** | T5 CONFLICT, T12 AI misread, T9/T10 invalid input |
| Synthetic / mocked clearly labelled | **Met** | Section 5 label checks; UI pills MOCKED / LIVE; return status labelled MOCKED |
| Core logic actually runs | **Met** | 341 tests; `cli.py --all` exit 0; UI |
| ≤ 4-page explanation | **Missing in repo** | `docs/writeup.md` is not on any branch (`git log --all -- docs/writeup.md` is empty). CLAUDE.md says it is kept separately. |
| README: setup and run | **Met** (after F2 fix) | README §1 |
| README: dependencies | **Met** | README §1 (pinned) + `requirements-llm.txt` optional |
| README: sample data | **Met** | README §6 |
| README: example inputs + expected outputs | **Met** | README §5, §7 (reproduced exactly) |
| Time spent | **Partly** | README §12 commit times are correct (checked against git), but `[RESEARCH AND MEMO TIME]` and `[TOTAL]` are still placeholders |
| What I'd investigate next | **Met** | README §13 |
| How AI was used and how its output was checked | **Met** | README §11; HANDOFF per-session pytest output |
| Prior work reused | **Met (declared)** | README §11 "none". This is self-declared and can't be checked independently. |
| Implemented / mocked / deferred | **Met** | README §9 (matches what I ran) |
| No paid service or account required | **Met** | Section 2: no key, no network; `anthropic` not installed by default |

## 7. Claims audit (STEP 6)

**`docs/writeup.md` was not available** on `main` or any branch at review time, so it could not be audited. Below I audit
the factual claims in **README.md** instead (the reviewer-facing claims). Section 8 has ready-to-paste text for the write-up brackets.

| # | README claim | Verdict | Proof |
| --- | --- | --- | --- |
| 1 | No API key, no network, no paid service | VERIFIED | Section 2, env unset |
| 2 | Python 3.11+ (tested on 3.13) | 3.13 VERIFIED; 3.11 UNVERIFIED | I ran 3.13.18 only |
| 3 | Pinned deps pydantic 2.13.5, PyYAML 6.0.3, pytest 9.2.0, streamlit 1.66.1 | VERIFIED | `requirements.txt`, pip output |
| 4 | T1: naive says No, 1b 2400→1600 (-800.00), 2 approvals stale, AI read LIVE, all ✓ verified | VERIFIED | Sections 3, 4 |
| 5 | T12: AI read 1060.00, form says 1,600.00, highlighted red, not replaced, SPECIALIST_REVIEW | VERIFIED | Sections 3, 4 |
| 6 | T5: correct read, prev 81,000 vs 82,000 → CONFLICT, nothing applied, nothing stale | VERIFIED | Sections 3, 4 |
| 7 | T3: FILED → POSSIBLE_AMENDMENT, recorded as new version, not applied | VERIFIED | Sections 3, 4 |
| 8 | All cases tab 15 of 15 | VERIFIED | Section 4 |
| 9 | Extraction schema has no status / decision / advice field | VERIFIED | `EXTRACTION_SCHEMA` keys = form_type, corrected, payer_or_employer_tin, tax_year, fields; `additionalProperties: False`; adding `status` → `ExtractionError` |
| 10 | Any ungrounded number rejects the AI note | VERIFIED (for T13) | Section 3 T13 |
| 11 | CLI appends one JSON line per decision | VERIFIED | `--all --log` wrote 16 lines (15 cases + T7's second), +1 for one more T1; records carry `clears_approvals: false` |
| 12 | UI does not write the audit log | VERIFIED (code) | `app.py` passes `log=None` / `None` to every `cli` call |
| 13 | Status priority order | VERIFIED (by behaviour) | All 15 fixtures match. Order also printed at top of `decide.py` |
| 14 | Adding a form/field = config + fixture + test, no new Python | **PARTLY FALSE** | A new *field* on an existing form is config-only (F3). A new *form* (1099-INT) needs 2 lines in `models.py` (F10), and the extraction prompt for text input. Existing tests must be updated either way (F3). |
| 15 | 341 tests; `test_app_smoke.py` checks UI never calls the API | VERIFIED | Section 3; and my own listener check (section 4) |
| 16 | Live run on 2026-11-02 with claude-haiku-5-5 for T1/T4/T5, 8/8, 6/6, 6/6 VERIFIED | Recordings VERIFIED; the API call itself UNVERIFIABLE | Files carry `live: true`, model, timestamps, and every value re-verifies against the raw text (CLI replay). I can't prove a real call was made. |
| 17 | Claude Haiku 5.5 returns HTTP 400 for non-default temperature | UNVERIFIED | No key in this review |
| 18 | A live run overwrites `T1.live.json`; MOCKED files never touched | PARTLY | A failed live call wrote nothing (`git status` clean). The success path was only checked by repo tests (stubbed). |
| 19 | Time log commit times | VERIFIED | `TZ=America/Los_Angeles git log ...` gives 10:41 PST `33fde96` … 12:24 PST `4e62269`/`0dc82ed`, all rows match |
| 20 | Reused prior work: none | UNVERIFIABLE | Self-declared |
| 21 | Implemented / mocked / deferred table | VERIFIED | Matches what I ran; deferred items are absent from code |
| 22 | Known limitations (labels, note direction, unverified mappings, hand-entered status, direct deps only) | VERIFIED | Section 5 list matches; F8 confirms the label limitation |

Commands in the README: all work as written with `python3`. The quick start order was the only problem (F2, fixed).
Note for the write-up: use `python3 -m pytest -q`, not bare `pytest` (it is installed in the venv, but the README and
HANDOFF standardise on `python3 -m pytest`), and `python3`, not `python`.

## 8. Fill-ins for the write-up (ready to paste)

When `docs/writeup.md` lands, use these for its brackets. All are from real runs in this review.

- **T1 result:**
  `T1 (corrected 1099-DIV, box 1a unchanged): APPLY_AND_REREVIEW. Box 1b 2,400.00 → 1,600.00 (−800.00), applied as a new version; 2 approvals marked stale: Form 1040 line 3a (APR-1040-L3A) and the Qualified Dividends and Capital Gain Tax Worksheet (APR-QDCG-WS, mapping flagged UNVERIFIED). The naive "did total income change?" check says No. The AI read (LIVE, claude-haiku-5-5, replayed) passed 8 of 8 source checks.`
- **T5 result:**
  `T5 (W-2c): CONFLICT. The W-2c says box 1 was previously reported as 81,000.00, but the accepted W-2 shows 82,000.00. The claimed change (82,000.00 → 86,500.00, +4,500.00) is shown as proposed, not applied; no new version is recorded and no approval is marked stale. The AI read was correct (LIVE, 6 of 6 checks verified), so the conflict comes from the document, not the AI.`
- **T12 result:**
  `T12 (AI misread): SPECIALIST_REVIEW. The (MOCKED) extraction read box 1b as 1,060.00; the form text says 1,600.00. Code flagged 1b UNVERIFIED, did not replace the value, and routed the case to a specialist; the UI marks the line "✗ AI read 1,060.00 — form says 1,600.00".`
- **Results table:** use the table in section 3 above (15 rows), or the `python3 cli.py --all` block.
- **"X of 15":** `15 of 15` (cases matching their expected status; also 15 of 15 for expected deltas and stale approvals).
- **Tests:** `341 passed` (`python3 -m pytest -q`, clean clone, 7.30s).
- **Safety:** `PASS: 24 decisions checked (15 fixtures + 4 text cases in cached and live-cache mode); 0 with clears_approvals = True; forcing it to True is rejected by the schema; input files unchanged. UI makes 0 API calls even with RETURNGUARD_LLM=live and a key set (checked with a local listener).`
- **Unverified mapping list:**
  `1099-DIV 1a → Form 1040 line 3b; 1099-DIV 1b and 2a → which lines of the Qualified Dividends and Capital Gain Tax Worksheet; 1099-DIV box 4 → Form 1040 line 25b; W-2 box 1 → Form 1040 line 1a; W-2 box 2 → Form 1040 line 25a; and the W-2 / W-2c box labels. All are flagged in config and shown as "unverified mapping" in the UI.`
- **Live AI run:** `On 2026-11-02, claude-haiku-5-5 read the T1, T4 and T5 form texts (one call each). Every extracted value passed the code's source check (8/8, 6/6, 6/6) and the statuses matched expected (APPLY_AND_REREVIEW −800.00, APPLY_AND_REREVIEW +4,500.00, CONFLICT). The recordings are replayed with no API call.`
- **Time:** commits run from 10:41 PST to 12:24 PST on 2026-11-02 (1 h 43 min of build commits, setup included). Research and memo time is
  not in git: only Sakshi can fill `[RESEARCH AND MEMO TIME]` and `[TOTAL]`.

## 9. Handoff cross-check (STEP 7)

Read HANDOFF.md after steps 1–6. Claims I could **not** reproduce or that are now out of date:
1. **"`returnguard-setup` was brought up to date with `main` via PR #5".** It is no longer true: `returnguard-setup` (`24069f0`) does
   not contain Session 5b (`git log origin/returnguard-setup..origin/main` lists 3 commits), and it is still the GitHub
   default branch (F1).
2. **The live API call itself (Session 4)** can't be reproduced without a key. Only the recordings and their re-verification
   could be checked (claim 16 above).
3. **"The key was pasted in chat, so Sakshi will rotate it".** I can't check this. It's an action item, not a code claim.

Reproduced as claimed: 341 passed; `cli.py --all` 15 match; HTTP 200; the UI never calls the API in live mode; wrap 344 == 344;
T12/T13 fixture descriptions (no PLACEHOLDER); next-action wording; the unverified list; `test_fixture_files_untouched_after_run`
fails on uncommitted `data/` edits (I saw the same thing with `config/`, F3).

## 10. Top 3 risks for the 15-minute demo, and how to handle each

1. **A reviewer clones without `-b` and gets old code (F1).** The default branch `returnguard-setup` lacks Session 5b.
   *Handle:* before submitting, set the GitHub default branch to `main` (Settings → General → Default branch) or delete
   `returnguard-setup`. In the demo, say "clone with `-b main`" up front.
2. **The live requirement change: tests go red, and a new form needs Python (F3, F10).** Supporting a new box is config-only,
   but 10 tests fail until the T15 expectation and related tests are updated, and the git-clean test fails until you commit.
   A new form (e.g. 1099-INT) also needs `"1099-INT"` added to the two Literals in `returnguard/models.py:103-104`.
   *Handle:* don't claim "no Python" for a new form. Say up front: "a new field is config-only; a new form is config plus
   one line each in two type lists." Recipe tested on a copy: `forms.yaml` entry + `dependencies.yaml` edge (+ `approval_items`) +
   `data/synthetic/accepted_<form>_C-001_2025.json` + the models.py Literals + a `cases/T16.json` fixture. Then update the
   tests that encode the old rule, commit, and show `python3 -m pytest -q` green. The UI picks up config on reload (no restart).
   Be ready for "the new approval isn't in the return state" (F4).
3. **Being asked to "run the AI live" (F5).** Live mode needs a key and network, and an API error prints a raw traceback.
   *Handle:* demo with `--use-live-cache` (LIVE recordings, no call) and explain the recorded run plus the source checks.
   If you do run live, use the CLI only (the UI never calls the API), with a working key tested beforehand.

(Also have ready: the unverified mapping list in section 5, and why T12 is MOCKED on purpose.)

## 11. README fixes made

- **F2, quick start order.** `streamlit run app.py` was step 6 of 8 and holds the terminal, so the following `python3 -m pytest -q`
  and `python3 cli.py --all` could not be run as written. The fix moves those two commands before the Streamlit step and adds one line:
  "Start the UI last: it keeps running in this terminal until Ctrl+C (open http://localhost:8501)." The commands themselves are unchanged.
  Nothing else in README.md was edited.
