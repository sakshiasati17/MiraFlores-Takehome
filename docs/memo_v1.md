# ReturnGuard — Original Design Memo (v1)

> **Note for every session:** This is Sakshi's ORIGINAL v1 memo, kept as background only.
> The design has since been updated. Where this memo and CLAUDE.md disagree, **CLAUDE.md wins**.
> Main changes since v1:
> - Forms: corrected 1099-DIV (boxes 1a, 1b, 2a, 4) is now the headline case; W-2c (boxes 1, 2) is second. v1 supported W-2c Box 1 only.
> - AI: v1 assumed structured extractions only. Now an LLM extracts fields from corrected-form text (cached by default), and code verifies every value against the source text.
> - Statuses, test cases T1–T15 and file layout are defined in CLAUDE.md and the session prompts, not here.
> - The three problems in the written submission changed (B is now out-of-date visa sponsorship data; C is upstream changes breaking pipelines).
> Text below is converted from docs/memo_v1.pdf, wording unchanged.

---

MIRAFLORES AI / CANDIDATE CASE STUDY — PROBLEM SELECTION / DECISION MEMO

## ReturnGuard

Change-aware tax review: keeping previously approved work trustworthy after corrected source evidence arrives.

STATUS: Written case study: researched proposal only. Prototype, source code, and measured results remain outstanding.

## 1 Three problems worth solving

I compared three problems using MiraFlores's publicly described tax workflow and lessons from my own data/AI engineering projects. The company describes source-backed preparation, automated review and CPA oversight [1–2]. These are hypotheses worth testing, not findings about its internal software.

| Problem / where it arose | Who experiences it | What happens if unresolved |
| --- | --- | --- |
| **A. Late corrections after review.** I have handled source-to-target reconciliation in banking pipelines; IRS W-2c and MiraFlores's review flow suggest a similar tax-evidence risk [2–4]. | Tax preparers, CPA reviewers, and clients. | An old approval could appear current even when a source amount changed; reviewers may need to retrace dependent work. |
| **B. AI conclusions without reliable evidence.** In ML engineering work, I investigated misleading assessments, stale inputs and inconsistent numeric outputs; the analogue in tax is unverified AI explanations [2]. | Preparers and reviewers evaluating AI-produced explanations. | Unverified claims may waste reviewer time or reach a client without adequate source support. |
| **C. Filing-status handoff across systems.** I have worked with parallel schedulers during data migrations; MiraFlores confirms firms use an external filing provider and plans acceptance tracking [2]. | Firm operations teams and tax preparers. | Pending or rejected returns may require follow-up across separate tools, increasing coordination effort. |

## 2 My choice: late corrections after approval

The question is specific: When corrected evidence arrives after a tax workpaper has been reviewed, which earlier decisions must be revisited? I prioritize A over B because its first-step outcome is independently checkable rather than dependent on model-judged answer quality; I prioritize it over C because it can demonstrate source-to-workpaper reasoning without a mocked filing-provider integration. These are feasibility judgments, not measured customer demand.

**What is observed vs. assumed**

- **Observed / verified:** MiraFlores advertises source-linked work and CPA review [1–2]; W-2c provides previously reported and corrected fields [3–4]. I have personally performed source-to-target reconciliation in banking data pipelines; I have not worked on MiraFlores's internal tax systems.
- **Assumed / to validate:** How often corrected documents arrive after review, what effort they cause, and whether MiraFlores already invalidates affected approvals. No MiraFlores customer incident or product gap has been verified.

## 3 Current approach and desired outcome

Plausible current workflow (inferred): a client supplies a W-2, extracted fields inform a draft, and a professional reviews the result. If a W-2c arrives later, a preparer needs to establish which earlier data it corrects and which downstream review artifacts may be affected. This description is a hypothesis for discovery, not an assertion about MiraFlores internals.

**DESIRED OUTCOME:** A reviewer can see what changed, which source establishes the change, which workpapers are potentially stale, and why the system did or did not place a hold. No approved evidence is silently overwritten.

## 4 Smallest useful first step

Use two structured, synthetic records: one previously accepted W-2 extraction and one proposed W-2c correction. Support a correction to Box 1 wages only. Produce a machine-readable decision and a short reviewer-facing explanation. Preserve existing review history; do not compute tax liability.

| Sequence | Proposed behavior |
| --- | --- |
| 1. Identify | Match client, tax year, employer, and the specific accepted source version; ambiguous identities go to manual reconciliation. |
| 2. Validate | Confirm the W-2c "previously reported" Box 1 value agrees with the accepted prior version; parse money using exact decimal arithmetic. |
| 3. Compare | Compute corrected-minus-prior amount; record both document IDs and source locations. |
| 4. Propagate | Apply a small illustrative Box 1 → wage workpaper → federal summary dependency map. |
| 5. Decide | For changed approved inputs, mark affected review artifacts as needing re-review; do not automatically authorize release. |
| 6. Explain | Produce change, evidence, dependency path, reason for hold, and next professional action. |

## 5 Why these technical choices

- **Deterministic validation for values and identity.** Exact comparisons, provenance, dependency mapping, and review holds must be reproducible. AI should not invent a tax amount or clear a safety hold.
- **AI is upstream and optional downstream.** Structured extractions stand in for an upstream AI document reader. A future LLM could draft a reviewer clarification using validated facts, but not make the decision.
- **Conservative abstention.** Corrections involving Box 2, tax-year/EIN exceptions, correction chains without a known prior version, or other unsupported fields are routed to specialist review. IRS rules are more nuanced than a generic two-CSV diff [3].

**Credible alternative rejected:** An end-to-end LLM could read both documents and recommend whether the draft remains safe. I rejected it as the first step: identity and numeric reconciliation must be exact, and a free-form model answer is harder to audit. A simple manual checklist is also credible; the prototype must show it adds useful change-to-workpaper traceability rather than just another alert.

## 6 One complete workflow to demonstrate

Input contract: source document ID and version, client ID, employer ID, tax year, review status, and supported Box 1 amount. The correction record includes its own document ID, the prior version it refers to, "previously reported" amount, "correct information" amount, and source-location metadata. Identifiers are synthetic; no real SSNs or taxpayer records are required.

| Scenario | Input (synthetic) | Expected result — not yet tested |
| --- | --- | --- |
| Representative | Accepted W-2 Box 1 = $82,000; proposed W-2c previously reported = $82,000, corrected = $86,500. | Changed by +$4,500; original retained; wage workpaper and illustrative federal summary flagged; prior approval requires reconfirmation. |
| Difficult / invalid | Accepted W-2 Box 1 = $82,000; W-2c previously reported = $81,000, corrected = $86,500. | CONFLICT: do not apply correction, do not clear review, preserve records, provide mismatch evidence for manual reconciliation. |
| Unsupported | W-2c changes Box 2 withholding without evidence of an administrative correction. | SPECIALIST REVIEW: outside the narrow supported policy; no automatic approval or overwriting [3]. |

## 7 Success criteria and evaluation

A future prototype must complete the path from synthetic input to reviewer decision. I would compare it with a naïve field-difference baseline: a diff can show +$4,500, but cannot by itself justify which approved workpapers are stale. A manual checklist is the operational alternative. The tests below are acceptance criteria, not results:

| Test / metric | Pass condition |
| --- | --- |
| Valid correction | Correct prior/new amounts, +$4,500 delta, source references, expected review dependencies. |
| Prior-value conflict | Never treated as an automatically accepted correction. |
| Identity mismatch / missing prior version | Escalated without a silent cross-client or cross-year match. |
| Malformed amount / unknown field | Controlled error or specialist review, never approval. |
| Duplicate / repeated correction | No duplicate or compounding changes when the same correction is seen twice. |
| Safety invariant | Zero unintended release/approval decisions on the designed invalid fixtures. |
| Explainability | Every review hold has an inspectable path: changed source field → affected workpaper. |

**Boundary of the demonstration:** This is a review-safety experiment, not a tax-preparation engine or legal tax determination. It does not parse PDFs, file forms, calculate tax, update live MiraFlores records, or decide whether an already filed return must be amended. Such cases require professional assessment and future integration.

## 8 What I would learn, and when to stop

Before proposing production integration, I would ask a CPA to review five synthetic correction cases and compare the resulting review actions with their normal workflow. Discovery questions: How often do corrections arrive after sign-off? Which approvals become stale? Which dependencies are truly material? Does the firm already have this control, and how expensive are false holds?

- **Measure:** Missed affected workpapers, unnecessary holds, completeness of evidence references, reviewer time to resolve a case, and whether the output changes an actual decision.
- **Stop or pivot if:** MiraFlores already provides an equivalent robust control; late corrections are too rare to matter; or the new workflow introduces more review burden than it removes.
- **Larger opportunity:** If useful, extend the same version-and-dependency pattern to 1099s, client-provided schedules, and audit evidence—but only after validating the initial tax workflow.

## 9 Time-boxed implementation plan

| Time | Deliverable |
| --- | --- |
| 0:00–0:20 | Finalize selected problem, baseline, success condition, and unsupported cases. |
| 0:20–0:40 | Specify synthetic source/correction records, source IDs, and dependency map. |
| 0:40–2:05 | Implement and run one deterministic end-to-end correction/review decision. |
| 2:05–2:40 | Add minimal runnable interface or CLI and evidence-rich output. |
| 2:40–3:15 | Test representative and invalid inputs; record actual observed results. |
| 3:15–4:00 | Package source, README, explanation, limitations, and walkthrough. |

## 10 Implementation and disclosure status

Implementation status: Not implemented or executed. Proposed: exact identity/prior-value checks, preserved versions, dependency impact, reviewer hold and an evidence-rich output. Planned mock inputs: synthetic structured extractions and illustrative workpaper dependencies. Deferred: OCR, a live AI model, production APIs, persistence, tax calculations, complex W-2c rules and reviewer authorization integration. No claim of real-world deployment or performance is made.

AI use and verification: I used ChatGPT for source discovery, brainstorming, writing and critique. Official MiraFlores pages and IRS instructions were cross-checked during drafting. No AI-generated code has been executed for this case study; prior project code has not been incorporated into this document. I must personally review factual claims and update this disclosure after implementation. Actual cumulative time spent, including research/drafting: [fill in truthfully before sending].

## Sources checked

1. MiraFlores — About / company and product origin — https://miraflores.ai/about
2. MiraFlores — CPA firm workflow and filing-provider boundary — https://miraflores.ai/solutions
3. IRS — 2026 General Instructions for Forms W-2 and W-3 (W-2c section) — https://www.irs.gov/instructions/iw2w3
4. IRS — About Form W-2c — https://www.irs.gov/forms-pubs/about-form-w-2-c
