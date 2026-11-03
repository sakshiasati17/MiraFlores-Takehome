# ReturnGuard: Catching Stale Approvals When Corrected Tax Forms Arrive

2 Nov 2026 · @Sakshi

## 1. Three problems I'd like to solve

All three come down to the same thing: data that looks current, but isn't anymore.

**A. Corrected tax forms that arrive after review.** Employers send W-2c corrections, and brokers often reissue 1099s weeks after the originals, sometimes after a return has already been filed [1][2]. Preparers and reviewers then have to work out what changed and which already-reviewed work depended on it. If something is missed, an approved return rests on old numbers, which can mean an amended return or an IRS mismatch notice (CP2000) later [3]. I haven't worked in tax, so I found this one by reading IRS instructions and practitioner sources. But I recognized the pattern from my own work.

**B. Visa sponsorship data that's out of date.** I'm on STEM OPT. During my job search, I kept finding employers like Capital One and Atlassian listed as sponsors on aggregator sites, because of their past H-1B filings, while their actual postings ruled out OPT candidates [4]. International students waste applications on roles that were never open to them, and miss the ones that are.

**C. Upstream changes that quietly break data pipelines.** For two years at Cognizant, I supported 100+ daily production pipelines for a banking client. The incidents I handled came from missing upstream files, schema changes and delayed Kafka feeds. Each time, loads failed or finished with incomplete data, and someone had to trace the cause and work out which downstream reports were affected.

## 2. Why I picked A

My question is simple: when a corrected form shows up after work has been reviewed, which approvals can you still trust?

**Why it interests me.** During our Hadoop-to-AWS migration at Cognizant, we ran the legacy schedulers and Airflow side by side, and part of my job was checking that the new pipelines produced the same results as the old ones. Problem A is the same kind of work, in a setting where a stale number ends up on someone's tax return. It's also the kind of problem I want to work on long term: systems that look healthy but are quietly wrong.

**Why someone else should care.** A reviewer's sign-off says "I checked this against the documents." If a document changes and the sign-off doesn't, the sign-off is now saying something that isn't true, and nothing on screen shows it.

**Why A over the other two.** B matters to me personally, but job postings are free text, so it's hard to say exactly when the tool is right. A has exact amounts, documented form rules and a clear right answer, so I can test it properly in four hours. C is real, but data-quality and observability tools already cover a lot of it. A has much less public tooling around the review step, and it sits right inside the kind of source-linked, CPA-reviewed work MiraFlores does.

### What I observed vs. what I'm assuming

| Observed (checked) | Assumed (to validate) |
| --- | --- |
| Corrected W-2s and 1099s are a regular part of tax season [1][2] | How often corrections arrive after review at a firm like MiraFlores |
| A widely used document tool replaces data from a corrected copy and moves the original to a "superseded" folder; its public docs don't say what happens to earlier review sign-offs [5] | Whether MiraFlores already resets affected approvals |
| MiraFlores publicly describes source-linked values, automated tie-outs and CPA review [6] | Which dependencies CPAs consider material, and how much an unnecessary hold costs them |
| I've validated outputs after upstream changes in production banking pipelines | That this transfers well to tax review |

I'm not claiming MiraFlores has a gap here. I haven't seen its internal systems, and finding out is the first thing I'd do.

## 3. How it's handled today, and what I'd change

**Today.** I can only go on public documentation, not MiraFlores internals. In one widely used document tool, a corrected copy either replaces the original's fields entirely or overwrites them field by field, and the original moves to a "superseded" folder [5]. The numbers get updated. Working out what changed, and which reviewed items relied on the old values, is left to the preparer.

**A better outcome.** When a correction comes in, the reviewer should see right away what changed and by how much, whether the correction actually matches the version it claims to fix, and which approved items now rest on old numbers. Nothing approved gets silently overwritten, and nothing gets cleared automatically. A person decides.

**Direction.** Tie every approval to a fingerprint of the evidence it was based on. When the evidence changes, the approval visibly goes stale until someone confirms it again.

**Smallest useful first step (what I built).** Two form types, a corrected 1099-DIV and a W-2c, a few supported boxes, synthetic data and a small map of which return lines and approvals depend on which boxes. One workflow runs end to end: corrected-form text, then AI extraction, then code checks, then the impact on approvals, then a decision and a reviewer note. It doesn't calculate tax, file anything or connect to real systems.

### What I considered instead

- Let an LLM read both documents and decide if the return is still OK. I didn't, because identity and amounts have to match exactly, and a free-form judgment is hard to audit. Here the model reads; code decides.
- A plain field-by-field comparison. Useful, so I kept it as a baseline, but it only shows what changed, not what it affects. In my main test case it reports nothing at all, because total dividends stay the same while the qualified part drops by $800.
- A manual checklist. Cheap and realistic. The prototype has to show it adds traceability a checklist can't. If it doesn't, the checklist wins.

## 4. Where AI, software and process each fit

| Part of the workflow | Approach | Why |
| --- | --- | --- |
| Reading the corrected form | AI (LLM extraction to a fixed schema) | Forms arrive as messy documents; this is where language models are strong |
| Checking what the AI extracted | Conventional software | Every amount must appear in the source text next to its box label, or it's marked unverified |
| Identity, prior values, form rules | Conventional software (exact decimals, config rules) | These have right answers; they must be reproducible and auditable |
| Which approvals are affected | Conventional software (dependency map in config) | Traceable paths, editable without code changes. Adding a new form (e.g. 1099-INT) is a config change only, covered by a test |
| Reviewer note | AI, constrained | May only use checked numbers; any other number rejects the note and falls back to a template |
| Whether to amend, re-approve or contact the client | Process: a CPA decides | Professional judgment; the tool never clears a hold |

**How the first step connects to the bigger opportunity.** The same pattern of versioned evidence, fingerprinted approvals and dependency-based holds applies to every corrected or late document: K-1s, consolidated brokerage statements, client-provided schedules. After filing, it could help a firm catch a missed correction before the IRS sends a CP2000.

### What I'd need to learn

- How often corrections arrive after review, and at which stage (before or after filing).
- How MiraFlores currently links approvals to evidence, and whether they already reset.
- Which field-to-approval dependencies CPAs consider material, and which holds they'd find noise.
- How reviewers would want to see this: an inline flag, a queue, or a client-level alert.

### When I'd decide it isn't worth solving

- MiraFlores already resets affected approvals when a source document is replaced. I'd then pivot to the extraction-verification half.
- Late corrections are rare enough that a manual checklist covers them.
- In a test with real reviewers, unnecessary holds cost more time than the missed changes they prevent.

## 5. The prototype and what it actually did

**Run it** (Python 3.11+, no API key): `git clone -b main https://github.com/sakshiasati17/MiraFlores-Takehome`, `pip install -r requirements.txt`, then `python3 -m pytest -q`, `python3 cli.py --all` and `streamlit run app.py`. By default, AI extraction replays saved outputs: real Claude Haiku 5.5 outputs from a live run for T1, T4 and T5 (labeled LIVE), and hand-written stand-ins for the other cases (labeled MOCKED). Repo: github.com/sakshiasati17/MiraFlores-Takehome.

**Workflow:** corrected-form text → LLM extraction → check every value against the source → identity, prior-value and form-rule checks → dependency walk to affected approvals → one status, a reviewer note and the next action → append-only audit log. All data is synthetic.

**Representative case (T1):** a fund reissues a 1099-DIV. Total ordinary dividends stay $3,200; qualified dividends drop from $2,400 to $1,600. A simple "did total income change?" check reports no change. ReturnGuard reports APPLY_AND_REREVIEW: box 1b down $800.00, and two approvals marked stale for re-review, Form 1040 line 3a and the Qualified Dividends and Capital Gain Tax Worksheet. Nothing is approved automatically.

**Difficult and invalid cases:**

- T5: a W-2c whose "previously reported" amount ($81,000) doesn't match the accepted W-2 ($82,000). Result: CONFLICT. Both amounts and both document IDs are shown, and the correction is proposed, not applied.
- T12: the AI misreads qualified dividends as $1,060 when the source says $1,600. Result: SPECIALIST_REVIEW. The code check marks 1b as unverified and shows both values; the AI's number is never substituted.

**All test cases (from the clean run in REVIEW.md):**

| Case | Scenario | Result |
| --- | --- | --- |
| T1 | Dividend reclassification (1b −$800) | APPLY_AND_REREVIEW |
| T2 | Ordinary dividends +$500 | APPLY_AND_REREVIEW |
| T3 | T1 after the return was filed | POSSIBLE_AMENDMENT |
| T4 | W-2c wages +$4,500 | APPLY_AND_REREVIEW |
| T5 | W-2c prior value doesn't match | CONFLICT |
| T6 | W-2c withholding change | SPECIALIST_REVIEW |
| T7 | Same correction sent twice | APPLY_AND_REREVIEW, then DUPLICATE_NO_CHANGE |
| T8 | Payer TIN mismatch | SPECIALIST_REVIEW |
| T9 | Qualified exceeds ordinary dividends | REJECTED_INVALID_INPUT |
| T10 | Malformed amount | REJECTED_INVALID_INPUT |
| T11 | Not marked CORRECTED | SPECIALIST_REVIEW |
| T12 | AI misread caught | SPECIALIST_REVIEW |
| T13 | Ungrounded AI note rejected | APPLY_AND_REREVIEW (template note used) |
| T14 | Corrected form, nothing changed | DUPLICATE_NO_CHANGE |
| T15 | Unsupported box (foreign tax) | SPECIALIST_REVIEW |

**Results:** 15 of 15 matched expected, and 364 automated tests pass from a fresh clone. Safety invariant (nothing ever approved automatically): PASS across every decision checked. Measured on my own synthetic cases only; no real-world accuracy is claimed.

## 6. Status, AI use and time

| Implemented | Mocked (labeled) | Deferred |
| --- | --- | --- |
| Extraction verification against source text | LLM extraction for cases other than T1, T4 and T5 (hand-written stand-ins; T12's misread is deliberately injected) | OCR of scanned PDFs |
| Identity, prior-value and form-rule checks (exact decimals) | Return filing status (entered by hand; MiraFlores doesn't yet track IRS acceptance) | Tax computation and amendment decisions |
| Config-driven dependency map and stale-approval detection | All taxpayer, payer and employer data (synthetic) | Other forms (K-1, 1099-B), real integrations, persistence, reviewer permissions |
| Evidence fingerprints and an append-only audit log | | Confirming six IRS line mappings still marked unverified in the config: 1099-DIV 1a → 1040 line 3b, W-2 box 1 → line 1a, W-2 box 2 → line 25a, 1099 withholding → line 25b, and which worksheet lines take 1b and 2a |
| Decision statuses, grounded reviewer note, CLI, Streamlit UI, tests | | |

**How I used AI, and how I checked it.**

- ChatGPT and Claude helped with research, brainstorming and editing this write-up. I checked factual claims against the sources below. Each form-to-return-line mapping in the config cites its IRS source, and any I couldn't confirm from the IRS page itself is marked unverified.
- I ran live extraction on T1, T4 and T5 with Claude Haiku 5.5. All 20 extracted values passed the source check, and all three decisions matched the expected result. Those outputs are saved in the repo and replayed by default, so no key is needed to run it. I built the code with Claude Code in six separate sessions, each with a scoped prompt, a fixed list of files it could change, and a handoff note.
- After each session I checked the real test output and read the changed code.
- A final review session with no prior context re-ran everything from a clean clone, checked the app in a browser (including that it makes no API calls), checked every requirement in the brief, and audited the README's claims against actual output (REVIEW.md in the repo).
- Reused prior work: none.

**Time spent:** build about 2 h 48 min (10:41–12:31 and 15:49–16:47 PST from the git history; I paused for about three hours after hitting a daily usage limit and did no work in between), plus about [MEMO] of earlier research, problem selection and the original design memo. Total about [TOTAL].

### What I'd investigate next

1. Interview two or three reviewers on how often corrections arrive after sign-off, and which holds they'd find useful versus noisy.
2. Run the extraction check on real (redacted) corrected forms, especially consolidated brokerage statements with many pages.
3. Extend to K-1s and 1099-Bs, where corrections are common and dependencies run deeper.
4. Measure reviewer time to resolve a correction with and without the tool.

## Sources

1. Journal of Accountancy, Here's how to fix problems caused by late and amended Forms 1099 (2015; describes a long-running pattern)
2. IRS, About Form W-2c and General Instructions for Forms W-2 and W-3
3. IRS, Understanding your CP2000 notice (open and confirm before sending)
4. Capital One, Careers FAQ (sponsorship language)
5. Thomson Reuters SurePrep, Amended/Corrected K-1s and Consolidated Statements
6. MiraFlores, Solutions and About

*Before sending: replace every [BRACKET], check the length is no more than 4 pages, and read it aloud once so it sounds like you.*
