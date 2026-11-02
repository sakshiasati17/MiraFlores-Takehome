# HANDOFF — ReturnGuard

> **Every session: read `docs/project_plan.md` first. It is the CURRENT design.**
> `CLAUDE.md` holds the rules; `docs/brief.md` is the MiraFlores brief;
> `docs/memo_v1.md` is the old v1 design (background only; project_plan.md wins where they differ).
> `docs/brief.docx` and `docs/memo_v1.pdf` (named in CLAUDE.md) are intentionally absent from the repo.
> Ignore them: `docs/brief.md` and `docs/project_plan.md` are the sources of truth.

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
