# HANDOFF — ReturnGuard

> **Every session: read `docs/project_plan.md` first. It is the CURRENT design.**
> `CLAUDE.md` holds the rules; `docs/brief.md` is the MiraFlores brief;
> `docs/memo_v1.md` is the old v1 design (background only; project_plan.md wins where they differ).
> `docs/brief.docx` and `docs/memo_v1.pdf` (named in CLAUDE.md) are intentionally absent from the repo.
> Ignore them: `docs/brief.md` and `docs/project_plan.md` are the sources of truth.

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
12. `tests/test_models.py` inserts the repo root into `sys.path` so plain `pytest -q` works without installing the package.
    Cleaner: add `pytest.ini` with `pythonpath = .` (a file not on Session 1's allowed list; ask first).

### Mappings and sources (tax year 2025)
`www.irs.gov` was **blocked by this cloud session's network policy** (DNS failure), so the IRS pages could not be opened
directly. Each mapping was checked against IRS-site **search excerpts** of the cited page. Re-open each URL in a browser
once before the demo.

| Field | Return line | Approval | Source | Status |
| --- | --- | --- | --- | --- |
| 1099-DIV 1b | Form 1040 line 3a | APR-1040-L3A | https://www.irs.gov/instructions/i1040gi | confirmed via search excerpt |
| 1099-DIV 1b | QDCG Tax Worksheet | APR-QDCG-WS | https://www.irs.gov/instructions/i1040gi | **UNVERIFIED** (worksheet inputs, "line 16" from general knowledge) |
| 1099-DIV 1a | Form 1040 line 3b | APR-1040-L3B | https://www.irs.gov/instructions/i1040gi | confirmed via search excerpt |
| 1099-DIV 2a | Schedule D line 13 | APR-SCHD-L13 | https://www.irs.gov/instructions/i1040sd | confirmed via search excerpt (if no Schedule D required, goes on 1040 line 7 instead) |
| 1099-DIV 2a | QDCG Tax Worksheet | APR-QDCG-WS | https://www.irs.gov/instructions/i1040gi | **UNVERIFIED** |
| 1099-DIV 4 | Form 1040 line 25b | APR-1040-L25B | https://www.irs.gov/instructions/i1040gi ; https://www.irs.gov/pub/irs-pdf/f1040.pdf | confirmed via search excerpt |
| W-2 1 | Form 1040 line 1a | APR-1040-L1A | https://www.irs.gov/instructions/i1040gi | confirmed via search excerpt |
| W-2 1 | Wage workpaper | APR-WAGE-WP | internal (synthetic, not an IRS line) | n/a |
| W-2 2 | Form 1040 line 25a | APR-1040-L25A | https://www.irs.gov/instructions/i1040gi | confirmed via search excerpt |
| Rule 1b <= 1a | box 1b is included in 1a | — | https://www.irs.gov/instructions/i1099div (Rev. Jan 2024 PDF: https://www.irs.gov/pub/irs-pdf/i1099div.pdf) ; 1040 instr. line 3a | confirmed via search excerpt (Pub. 17 wording) |

UNVERIFIED items to check:
- The QDCG worksheet inputs (which worksheet lines take 1040 line 3a and Schedule D / 2a) and that it sits under 1040 line 16.
- Whether the 2025 Form 1040 numbers capital gains as line 7 or 7a (an IRS FAQ excerpt mentioned "line 7a").
  This only matters if a "no Schedule D" path is added.

### Next: Session 2
`returnguard/validate.py` + `returnguard/impact.py` + tests: identity checks (client, tax year, payer TIN),
CORRECTED flag (T11), W-2c previously-reported vs accepted (T5), form rule 1b <= 1a (T9), raw amount parsing
(T10), supported-field checks (T6 via `on_change`, T15 via `unsupported_fields`), and the dependency walk ->
stale approvals (T1, T2, T4). Read rules from config only.
