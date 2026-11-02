"""ReturnGuard command line. SYNTHETIC data only; no network, no API key.

  python3 cli.py data/synthetic/cases/T1.json          readable report
  python3 cli.py data/synthetic/cases/T1.json --json   the Decision(s) as JSON
  python3 cli.py --all                                 every fixture: expected vs actual
  python3 cli.py --from-text data/synthetic/raw/T1.txt --case T1
                                                       AI pipeline: extract (MOCKED by default) -> verify -> decide -> note

Each fixture gets its own fresh ProcessingState; submissions inside one fixture (T7) share it.
Every decision is appended to the audit log (default out/audit_log.jsonl; change with --log).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from returnguard.audit import DEFAULT_LOG, AuditLog, log_record
from returnguard.decide import Decision, ProcessingState, decide, load_config, naive_total_changed, signed
from returnguard.explain import UNVERIFIED_TAG, NoteResult, grounded_note, load_cached_note, unverified_boxes
from returnguard.extract import ENVELOPE_KEYS, ExtractionReport, run_from_text
from returnguard.models import AcceptedDocument, CaseFixture, CorrectionDocument, ReturnState, ReturnStatus

ROOT = Path(__file__).resolve().parent
SYN = ROOT / "data" / "synthetic"
CASES = SYN / "cases"
RAW = SYN / "raw"
# Cases whose fixture alone is not the input (Session 4). They are no longer skipped:
#   T12: the form TEXT goes through extraction (data/synthetic/raw/T12.txt + data/llm_cache/T12.json, MOCKED).
#   T13: the fixture is decided normally, then the hand-written MOCKED note (data/llm_cache/T13_note.json) is grounded.
LLM_TEXT_CASES = {"T12"}
LLM_NOTE_CASES = {"T13"}
LLM_CASES = LLM_TEXT_CASES | LLM_NOTE_CASES


def load_config_default() -> dict:
    return load_config(ROOT / "config" / "forms.yaml", ROOT / "config" / "dependencies.yaml")


def load_accepted() -> dict[str, AcceptedDocument]:
    docs = [AcceptedDocument.model_validate_json(p.read_text()) for p in sorted(SYN.glob("accepted_*.json"))]
    return {d.form_type: d for d in docs}


def load_return_state() -> ReturnState:
    return ReturnState.model_validate_json((SYN / "return_state_C-001_2025.json").read_text())


def run_case(fixture: CaseFixture, config: dict, log: AuditLog | None = None) -> list[tuple[AcceptedDocument, Decision]]:
    """Process every submission of one fixture in order, with ONE fresh shared state."""
    accepted = load_accepted()
    rs = load_return_state().model_copy(update={"status": fixture.return_status})
    state = ProcessingState()
    out = []
    for sub in fixture.submissions:
        target = ((config["forms"].get(sub.form_type) or {}).get("correction") or {}).get("corrects", sub.form_type)
        acc = accepted[target]
        d = decide(acc, sub, rs, config, state)
        if log is not None:
            log.append(log_record(fixture.case_id, d))
        out.append((acc, d))
    return out


def load_fixture(path: str | Path) -> CaseFixture:
    return CaseFixture.model_validate_json(Path(path).read_text())


def envelope_from(fixture: CaseFixture | None) -> dict | None:
    """Intake details only (doc ID, client, payer name, prior doc ID, received time). Form type, corrected flag,
    TIN, tax year and amounts are NEVER taken from the fixture: they come only from the extraction."""
    if fixture is None:
        return None
    sub = fixture.submissions[0]
    return {k: getattr(sub, k) for k in ENVELOPE_KEYS}


def run_text_case(text: str, case_id: str, config: dict, fixture: CaseFixture | None = None,
                  log: AuditLog | None = None, use_live_cache: bool = False) -> tuple[AcceptedDocument, Decision, ExtractionReport]:
    """Form text -> extraction (MOCKED unless live mode is on, or a .live.json replay) -> source check -> decide()."""
    rs = load_return_state()
    if fixture is not None:
        rs = rs.model_copy(update={"status": fixture.return_status})
    accepted = load_accepted()
    d, rep = run_from_text(text, case_id, accepted, rs, config, ProcessingState(), envelope=envelope_from(fixture),
                           use_live_cache=use_live_cache)
    if log is not None:
        log.append(log_record(case_id, d))
    target = ((config["forms"].get(rep.correction.form_type) or {}).get("correction") or {}).get(
        "corrects", rep.correction.form_type)
    return accepted[target], d, rep


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------


def report(fixture: CaseFixture | None, results: list[tuple[AcceptedDocument, Decision]],
           submissions: list[CorrectionDocument] | None = None, case_id: str | None = None) -> str:
    subs = submissions or fixture.submissions
    if fixture is not None:
        lines = [f"ReturnGuard  |  case {fixture.case_id} ({fixture.angle})  |  SYNTHETIC data", fixture.description, ""]
    else:
        lines = [f"ReturnGuard  |  case {case_id}  |  SYNTHETIC data", ""]
    for n, (acc, d) in enumerate(results, 1):
        sub = subs[n - 1]
        bar = "=" * (len(d.status.value) + 16)
        if len(results) > 1:
            lines.append(f"--- Submission {n} of {len(results)}: {sub.doc_id} ---")
        lines += [bar, f"  STATUS:  {d.status.value}", bar]
        lines.append(f"Accepted: {d.evidence.accepted_doc_id}   Correction: {d.evidence.correction_doc_id}")
        lines.append(f"Return status: {d.evidence.return_status} ({d.evidence.return_status_source})")
        lines.append("")
        lines.append("What changed:")
        unverified = unverified_boxes(d)
        if d.proposed_changes:
            for c in d.proposed_changes:
                tag = "applied as new version" if c.applied else (
                    "recorded as new version, NOT applied" if c.applied_as_new_version else "proposed, not applied")
                uv = f" {UNVERIFIED_TAG}" if c.field in unverified else ""
                lines.append(f"  {c.form_type} box {c.field} {c.label}: {c.old} -> {c.new}{uv}  delta {signed(c.delta)}  [{tag}]")
        else:
            lines.append("  nothing")
        lines.append("")
        lines.append("Stale approvals (CPA must re-review):")
        if d.stale_approvals:
            for s in d.stale_approvals:
                tag = "  [UNVERIFIED]" if s.unverified else ""
                lines.append(f"  {s.approval_id}  {s.item}{tag}")
                for p in s.paths:
                    lines.append(f"      path:   {p}")
                for src in s.sources:
                    lines.append(f"      source: {src}")
        else:
            lines.append("  none (nothing changed)")
        lines.append("")
        lines.append("Reasons:")
        for r in d.reasons:  # display only: mark change lines whose new value failed the source check
            for c in d.proposed_changes:
                if c.field in unverified and r.startswith(f"{c.form_type} box {c.field} "):
                    r = r.replace(f"-> {c.new} ", f"-> {c.new} {UNVERIFIED_TAG} ", 1)
            lines.append(f"  - {r}")
        naive = naive_total_changed(acc, sub)
        if naive is not None:
            lines.append("")
            lines.append(f"Naive check (did total income change?): {'yes' if naive else 'no'}")
        lines.append("")
        lines.append(f"NEXT ACTION: {d.next_action}")
        lines.append(f"Correction fingerprint: {d.correction_fingerprint}")
        lines.append("")
    return "\n".join(lines)


def extraction_section(rep: ExtractionReport) -> str:
    ex = rep.extraction
    where = Path(ex.cache_path).relative_to(ROOT) if ex.cache_path.startswith(str(ROOT)) else ex.cache_path
    if ex.mode_label == "MOCKED":
        detail = f"  source: hand-written stand-in, no model was called   prompt: {ex.prompt_version}   file: {where}"
    else:
        how = "replayed from a recorded live output, no API call this run" if ex.replayed_live else "live model call"
        detail = f"  source: {how}   model: {ex.model}   prompt: {ex.prompt_version}   recorded output: {where}"
    lines = [
        f"EXTRACTION: {ex.mode_label}  ({ex.raw.get('_label', '')})",
        detail,
        "  The LLM only reads the text. Code checks every value against the source line; the LLM never sets a status.",
        "Source check (code):",
    ]
    for c in rep.checks:
        if c.verified:
            lines.append(f"  VERIFIED    {c.name}: {c.extracted}")
        else:
            found = c.found if c.found is not None else "nothing"
            lines.append(f"  UNVERIFIED  {c.name}: extracted {c.extracted} | text shows {found}" + (f" ({c.note})" if c.note else ""))
            if c.line:
                lines.append(f"              source line: {c.line}")
    lines.append(f"  -> {'all values verified against the text' if rep.all_verified else 'UNVERIFIED values were NOT replaced; finding EXTRACTION_UNVERIFIED (SPECIALIST)'}")
    lines.append("")
    return "\n".join(lines)


def note_section(note: NoteResult) -> str:
    lines = [f"REVIEWER NOTE  [source: {note.source}]"]
    if note.llm_rejected:
        lines.append(f"  LLM note REJECTED: numbers not in the checked facts: {', '.join(note.rejected_numbers)}")
        lines.append(f"  rejected draft: {note.llm_text}")
        lines.append("  Safe template note used instead:")
    lines.append(f"  {note.text}")
    lines.append("")
    return "\n".join(lines)


def full_text_report(case_id: str, fixture: CaseFixture | None, acc: AcceptedDocument, d: Decision,
                     rep: ExtractionReport, note: NoteResult) -> str:
    head = report(fixture, [(acc, d)], submissions=[rep.correction], case_id=case_id)
    return extraction_section(rep) + head + "\n" + note_section(note)


def _fixture_or_none(case_id: str) -> CaseFixture | None:
    path = CASES / f"{case_id}.json"
    return load_fixture(path) if path.exists() else None


def run_all(config: dict, log: AuditLog | None) -> tuple[str, bool]:
    paths = sorted(CASES.glob("T*.json"), key=lambda p: int(p.stem[1:]))
    rows = [("case", "expected", "actual", "match")]
    ok = True
    for p in paths:
        fx = load_fixture(p)
        expected = [s.value for s in (fx.expected.status_sequence or [fx.expected.status])]
        extra_ok = True
        if fx.case_id in LLM_TEXT_CASES:
            _, d, rep = run_text_case((RAW / f"{fx.case_id}.txt").read_text(), fx.case_id, config, fx, log)
            actual = [d.status.value]
            note = f" (from text, {rep.extraction.mode_label} extraction, {sum(not c.verified for c in rep.checks)} UNVERIFIED)"
            extra_ok = not rep.all_verified  # T12 exists to show the misread is caught
        elif fx.case_id in LLM_NOTE_CASES:
            ((_, d),) = run_case(fx, config, log)
            n = grounded_note(d, load_cached_note(fx.case_id))
            actual = [d.status.value]
            note = f" (LLM note {'rejected: ' + ', '.join(n.rejected_numbers) if n.llm_rejected else 'accepted'}; {n.source} note)"
            extra_ok = n.llm_rejected
        else:
            actual = [d.status.value for _, d in run_case(fx, config, log)]
            note = ""
        match = actual == expected and extra_ok
        ok &= match
        rows.append((fx.case_id, ", ".join(expected), ", ".join(actual) + note, "match" if match else "MISMATCH"))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    text = "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)
    return text, ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ReturnGuard: corrected-form review triage (SYNTHETIC data).")
    ap.add_argument("case", nargs="?", help="path to a case fixture, e.g. data/synthetic/cases/T1.json")
    ap.add_argument("--json", action="store_true", help="print the Decision(s) as JSON")
    ap.add_argument("--all", action="store_true", help="run every fixture and print expected vs actual")
    ap.add_argument("--from-text", metavar="PATH", help="corrected-form text to run through the AI pipeline")
    ap.add_argument("--case", dest="case_id", help="case id for --from-text (selects data/llm_cache/<id>.json)")
    ap.add_argument("--use-live-cache", action="store_true",
                    help="replay data/llm_cache/<case>.live.json (a recorded LIVE output) when it exists; no API call")
    ap.add_argument("--log", default=str(DEFAULT_LOG), help="append-only audit log path (default out/audit_log.jsonl)")
    args = ap.parse_args(argv)

    config = load_config_default()
    log = AuditLog(args.log)
    if args.all:
        text, ok = run_all(config, log)
        print(text)
        return 0 if ok else 1
    if args.from_text:
        case_id = args.case_id or Path(args.from_text).stem
        fx = _fixture_or_none(case_id)
        acc, d, rep = run_text_case(Path(args.from_text).read_text(), case_id, config, fx, log,
                                    use_live_cache=args.use_live_cache)
        note = grounded_note(d, load_cached_note(case_id))
        if args.json:
            print(json.dumps({"extraction_label": rep.extraction.mode_label,
                              "extraction_source": rep.extraction.source,
                              "checks": [c.__dict__ for c in rep.checks],
                              "decision": d.model_dump(mode="json"),
                              "note": note.__dict__}, indent=2, default=str))
        else:
            print(full_text_report(case_id, fx, acc, d, rep, note))
        return 0
    if not args.case:
        ap.error("give a case file, --from-text PATH --case ID, or --all")
    fx = load_fixture(args.case)
    if fx.case_id in LLM_TEXT_CASES:
        return main([f"--from-text={RAW / (fx.case_id + '.txt')}", "--case", fx.case_id, "--log", args.log]
                    + (["--json"] if args.json else []) + (["--use-live-cache"] if args.use_live_cache else []))
    results = run_case(fx, config, log)
    if args.json:
        payload = [d.model_dump(mode="json") for _, d in results]
        print(json.dumps(payload[0] if len(payload) == 1 else payload, indent=2))
        return 0
    print(report(fx, results))
    if len(results) == 1:
        print(note_section(grounded_note(results[0][1], load_cached_note(fx.case_id))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
