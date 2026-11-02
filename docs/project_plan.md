# ReturnGuard — Current Project Plan (source of truth for the design)

This is the CURRENT design. It replaces docs/memo_v1 wherever they differ.
CLAUDE.md holds the rules; this file explains what we're building and why.
Role: AI Engineer (Tax) take-home for MiraFlores AI.

## 1. Problem (one sentence)
A corrected tax form arrives after a CPA has already approved work based on the original, and nobody
can easily see what changed, whether the correction can be trusted, or which approvals are now stale.

## 2. Why this problem
- Corrected forms are real and recurring: brokers reissue corrected 1099s (often after funds reclassify
  dividends), and employers issue W-2c corrections; some arrive after returns are filed.
- A widely used document tool (Thomson Reuters SurePrep) replaces the data from a corrected copy and moves
  the original to a "superseded" folder; its public documentation doesn't describe what happens to earlier
  review sign-offs. ReturnGuard focuses on that review side.
- Fits MiraFlores: source-linked values, automated tie-outs, CPA review. ReturnGuard keeps approvals honest
  over time when the evidence changes. We do NOT claim MiraFlores lacks this; we don't know.
- Personal link: at Cognizant (banking client, 100+ daily pipelines) Sakshi handled incidents from missing
  upstream files, schema changes and delayed Kafka feeds, and during the Hadoop-to-AWS migration ran legacy
  schedulers and Airflow side by side, checking the new pipelines produced the same results.

## 3. What makes this an AI Engineer project (the core idea)
AI suggests -> code verifies -> a CPA decides.
1. AI reads: an LLM extracts fields from the corrected form's text into a fixed JSON schema.
   Default mode replays recorded outputs (labelled MOCKED) so it runs free with no API key.
2. Code verifies the AI: every extracted amount must appear in the source text next to its box label.
   If not, the field is UNVERIFIED and the case goes to SPECIALIST_REVIEW. Never silently "fixed".
3. Code checks the correction: identity (client, tax year, payer/employer TIN), CORRECTED flag,
   W-2c "previously reported" equals the accepted value, form rules (1b <= 1a, non-negative, 2 dp),
   supported fields only. Exact Decimal math.
4. Code finds impact: walks config/dependencies.yaml (field -> 1040 line -> approval) and marks
   approvals stale using evidence fingerprints (SHA-256 of the fields an approval was based on).
5. Code decides one status; AI may draft the reviewer note but any number not in the checked facts
   rejects the note and a template note is used.
6. A CPA decides what to do. Nothing is ever approved or cleared automatically.

## 4. Forms and fields (rules live in config, not code)
- Corrected 1099-DIV (headline): 1a total ordinary dividends, 1b qualified dividends,
  2a total capital gain distributions, 4 federal income tax withheld.
- W-2c (second form): Box 1 wages, Box 2 federal withholding (Box 2 changes -> SPECIALIST_REVIEW).
- Line mappings to VERIFY against IRS 2025 instructions (cite URL, else mark # UNVERIFIED):
  1b -> 1040 line 3a; 1a -> 3b; 2a -> Schedule D line 13; 1099-DIV Box 4 -> 25b;
  W-2 Box 1 -> 1a; W-2 Box 2 -> 25a.

## 5. Statuses (priority order, first match wins)
REJECTED_INVALID_INPUT > SPECIALIST_REVIEW > CONFLICT > DUPLICATE_NO_CHANGE >
POSSIBLE_AMENDMENT (return already FILED; filing status is entered by hand, labelled mocked,
since MiraFlores doesn't yet track IRS acceptance) > APPLY_AND_REREVIEW.

## 6. Synthetic baseline
Client C-001, tax year 2025, payer "Synthetic Growth Fund" (TIN 00-0000001),
employer TIN 00-0000002.
Accepted 1099-DIV: 1a 3200.00, 1b 2400.00, 2a 500.00, 4 0.00.
Accepted W-2: Box 1 82000.00, Box 2 9000.00.

## 7. Test cases (expected results)
| ID | Angle | Input | Expected status | Must also show |
| --- | --- | --- | --- | --- |
| T1 | Headline demo | Corrected 1099-DIV: 1b 2400 -> 1600, 1a unchanged | APPLY_AND_REREVIEW | 1b -800; line 3a + qualified-dividend worksheet approvals stale; naive total-income diff shows 0 |
| T2 | Typical | 1a 3200 -> 3700 | APPLY_AND_REREVIEW | +500; line 3b approval stale |
| T3 | Timing | T1 but return FILED | POSSIBLE_AMENDMENT | CPA decides whether to amend; nothing auto-applied |
| T4 | Second form | W-2c prev 82000, correct 86500 | APPLY_AND_REREVIEW | +4500; line 1a + wage workpaper stale |
| T5 | Invalid (required) | W-2c prev 81000 vs accepted 82000 | CONFLICT | both values + both doc IDs; nothing changed |
| T6 | Unsupported | W-2c changes Box 2 | SPECIALIST_REVIEW | withholding corrections need professional review |
| T7 | Duplicate | Same corrected doc twice | DUPLICATE_NO_CHANGE | same fingerprint; no double change |
| T8 | Identity | Payer TIN or tax year differs | SPECIALIST_REVIEW | no silent cross-client/year match |
| T9 | Form rule | 1b 3500 > 1a 3200 | REJECTED_INVALID_INPUT | qualified can't exceed ordinary |
| T10 | Malformed | "86,5OO" or negative | REJECTED_INVALID_INPUT | field name + bad value |
| T11 | Ambiguous | CORRECTED not ticked, values differ | SPECIALIST_REVIEW | may be a second account |
| T12 | AI mistake | LLM says 1b 1060, text says 1600 | SPECIALIST_REVIEW | field UNVERIFIED |
| T13 | AI note | Note has a number not in checked facts | (unchanged) | note rejected; template used |
| T14 | No-op | Corrected, all values identical | DUPLICATE_NO_CHANGE | no supported field changed |
| T15 | Unknown field | 1099-DIV Box 7 changes | SPECIALIST_REVIEW | field not supported |
Safety invariant: across all fixtures, nothing is ever approved or cleared automatically.
Baseline comparison: a naive "did total income change?" check misses T1; ReturnGuard catches it.

## 8. Demo (15 min) priorities
T1 (dividend reclassification the naive diff misses) -> T12 (AI misread caught) -> T5 (conflict)
-> T3 (already filed) -> config + pytest -> implemented/mocked/deferred.

## 9. Live case (30 min) readiness
Requirements will change. Adding a form or field (e.g. 1099-INT) must be a config change
(forms.yaml + dependencies.yaml + a fixture + a test), not new Python logic.

## 10. Out of scope (deferred)
Tax computation, OCR of scanned PDFs, filing, amendment decisions, real integrations,
persistence/databases, reviewer permissions, K-1s and 1099-Bs.
