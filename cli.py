"""ReturnGuard command line. SYNTHETIC data only; no network, no API key.

  python3 cli.py data/synthetic/cases/T1.json          readable report
  python3 cli.py data/synthetic/cases/T1.json --json   the Decision(s) as JSON
  python3 cli.py --all                                 every fixture: expected vs actual

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
from returnguard.models import AcceptedDocument, CaseFixture, ReturnState

ROOT = Path(__file__).resolve().parent
SYN = ROOT / "data" / "synthetic"
CASES = SYN / "cases"
LLM_CASES = {"T12", "T13"}  # need LLM extraction / note: Session 4


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


# ---------------------------------------------------------------------------
# Text report
# ---------------------------------------------------------------------------


def report(fixture: CaseFixture, results: list[tuple[AcceptedDocument, Decision]]) -> str:
    lines = [f"ReturnGuard  |  case {fixture.case_id} ({fixture.angle})  |  SYNTHETIC data", fixture.description, ""]
    for n, (acc, d) in enumerate(results, 1):
        sub = fixture.submissions[n - 1]
        bar = "=" * (len(d.status.value) + 16)
        if len(results) > 1:
            lines.append(f"--- Submission {n} of {len(results)}: {sub.doc_id} ---")
        lines += [bar, f"  STATUS:  {d.status.value}", bar]
        lines.append(f"Accepted: {d.evidence.accepted_doc_id}   Correction: {d.evidence.correction_doc_id}")
        lines.append(f"Return status: {d.evidence.return_status} ({d.evidence.return_status_source})")
        lines.append("")
        lines.append("What changed:")
        if d.proposed_changes:
            for c in d.proposed_changes:
                tag = "applied as new version" if c.applied else (
                    "recorded as new version, NOT applied" if c.applied_as_new_version else "proposed, not applied")
                lines.append(f"  {c.form_type} box {c.field} {c.label}: {c.old} -> {c.new}  delta {signed(c.delta)}  [{tag}]")
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
        lines += [f"  - {r}" for r in d.reasons]
        naive = naive_total_changed(acc, sub)
        if naive is not None:
            lines.append("")
            lines.append(f"Naive check (did total income change?): {'yes' if naive else 'no'}")
        lines.append("")
        lines.append(f"NEXT ACTION: {d.next_action}")
        lines.append(f"Correction fingerprint: {d.correction_fingerprint}")
        lines.append("")
    return "\n".join(lines)


def run_all(config: dict, log: AuditLog | None) -> tuple[str, bool]:
    paths = sorted(CASES.glob("T*.json"), key=lambda p: int(p.stem[1:]))
    rows = [("case", "expected", "actual", "match")]
    ok = True
    for p in paths:
        fx = load_fixture(p)
        if fx.case_id in LLM_CASES:
            rows.append((fx.case_id, fx.expected.status.value, "LLM case: Session 4", "skipped"))
            continue
        actual = [d.status.value for _, d in run_case(fx, config, log)]
        expected = [s.value for s in (fx.expected.status_sequence or [fx.expected.status])]
        match = actual == expected
        ok &= match
        rows.append((fx.case_id, ", ".join(expected), ", ".join(actual), "match" if match else "MISMATCH"))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    text = "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)
    return text, ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ReturnGuard: corrected-form review triage (SYNTHETIC data).")
    ap.add_argument("case", nargs="?", help="path to a case fixture, e.g. data/synthetic/cases/T1.json")
    ap.add_argument("--json", action="store_true", help="print the Decision(s) as JSON")
    ap.add_argument("--all", action="store_true", help="run every fixture and print expected vs actual")
    ap.add_argument("--log", default=str(DEFAULT_LOG), help="append-only audit log path (default out/audit_log.jsonl)")
    args = ap.parse_args(argv)

    config = load_config_default()
    log = AuditLog(args.log)
    if args.all:
        text, ok = run_all(config, log)
        print(text)
        return 0 if ok else 1
    if not args.case:
        ap.error("give a case file or --all")
    fx = load_fixture(args.case)
    if fx.case_id in LLM_CASES:
        print(f"{fx.case_id}: LLM case: Session 4")
        return 0
    results = run_case(fx, config, log)
    if args.json:
        payload = [d.model_dump(mode="json") for _, d in results]
        print(json.dumps(payload[0] if len(payload) == 1 else payload, indent=2))
    else:
        print(report(fx, results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
