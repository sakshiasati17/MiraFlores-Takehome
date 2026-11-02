"""Evidence fingerprints, new-version records and the append-only audit log.

- fingerprint(): SHA-256 over a canonical JSON of selected field values + form type + document
  identity (client, tax year, payer TIN). doc_id and version are deliberately NOT part of the
  identity, so a new version of the same document can be compared field by field, and the same
  correction re-sent under a new doc ID is still recognised as a duplicate.
- Baseline approvals carry evidence_fingerprint = null in the fixtures. with_baseline_fingerprints()
  computes them at load time from the accepted documents; fixture files are never edited.
- A correction is stored as a NEW version record (new_version()); the accepted document object is
  never modified.
- AuditLog only ever appends one JSON line per decision. It has no method that rewrites or deletes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional

from .models import AcceptedDocument, Approval, CorrectionDocument, ReturnState
from .validate import diff_fields, parse_amount

CENT = Decimal("0.01")
IDENTITY = ("client_id", "tax_year", "payer_tin")
DEFAULT_LOG = Path("out") / "audit_log.jsonl"


def _sha(payload: dict) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _box(field: str) -> str:
    """'1099-DIV:1b' -> '1b'; '1b' -> '1b'."""
    return field.split(":", 1)[1] if ":" in field else field


def _form(field: str) -> Optional[str]:
    return field.split(":", 1)[0] if ":" in field else None


def _money(value: Decimal) -> str:
    return str(Decimal(value).quantize(CENT))


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------


def fingerprint(doc: AcceptedDocument, fields: Iterable[str]) -> str:
    """SHA-256 hex of the given fields' values on doc (2 dp strings, sorted keys) + form type + identity.

    fields may be "FORM:box" (as in Approval.based_on) or bare boxes. A box the document does not
    have is recorded as null, so "missing" and "0.00" fingerprint differently.
    """
    values = {}
    for f in fields:
        box = _box(f)
        values[box] = _money(doc.fields[box].amount) if box in doc.fields else None
    return _sha(
        {
            "form_type": doc.form_type,
            "identity": {k: str(getattr(doc, k)) for k in IDENTITY},
            "fields": values,
        }
    )


def correction_fingerprint(correction: CorrectionDocument) -> str:
    """Fingerprint of an incoming correction (all boxes, incl. W-2c "previously reported").

    Amounts that parse are normalised to 2 dp ("3,200" == "3200.00"); amounts that do not parse
    (e.g. T10 "86,5OO") are recorded as the raw text, prefixed "RAW:".
    """

    def norm(raw: Optional[str], name: str) -> Optional[str]:
        if raw is None:
            return None
        amount, errs = parse_amount(raw, name)
        return _money(amount) if amount is not None and not errs else f"RAW:{raw}"

    boxes = {
        box: {
            "value": norm(cf.value, box),
            "previously_reported": norm(cf.previously_reported, box),
        }
        for box, cf in correction.fields.items()
    }
    return _sha(
        {
            "form_type": correction.form_type,
            "identity": {k: str(getattr(correction, k)) for k in IDENTITY},
            "corrected": correction.corrected,
            "fields": boxes,
        }
    )


def _relevant(approval: Approval, doc: AcceptedDocument) -> list[str]:
    """based_on fields that live on this document's form."""
    return [f for f in approval.based_on if _form(f) in (None, doc.form_type)]


def with_baseline_fingerprints(return_state: ReturnState, accepted_docs: Iterable[AcceptedDocument]) -> ReturnState:
    """A copy of return_state whose approvals carry evidence_fingerprint computed from the accepted docs.

    Each approval is fingerprinted over its based_on fields on the accepted document of that form.
    An approval already carrying a fingerprint keeps it. The input object is not modified.
    """
    by_form = {d.form_type: d for d in accepted_docs}
    approvals = []
    for a in return_state.approvals:
        if a.evidence_fingerprint is None:
            forms = {_form(f) for f in a.based_on}
            if len(forms) == 1 and (form := forms.pop()) in by_form:
                a = a.model_copy(update={"evidence_fingerprint": fingerprint(by_form[form], a.based_on)})
        approvals.append(a)
    return return_state.model_copy(update={"approvals": approvals})


# ---------------------------------------------------------------------------
# New version record + staleness
# ---------------------------------------------------------------------------


def new_version(accepted: AcceptedDocument, correction: CorrectionDocument, config: dict) -> AcceptedDocument:
    """A NEW document version: the accepted document with the correction's supported changes applied.

    The accepted object is untouched. The new record keeps the accepted form type (W-2c -> W-2),
    takes the correction's doc_id and version + 1. It is a proposal for CPA re-review, not an approval.
    """
    data = accepted.model_dump(mode="json", by_alias=True)
    for ch in diff_fields(accepted, correction, config):
        data["fields"][ch.field] = {"amount": _money(ch.new), "source": f"{correction.doc_id} box {ch.field}"}
    data.update(
        doc_id=correction.doc_id,
        version=accepted.version + 1,
        accepted_at=correction.received_at,
        _label=(
            f"SYNTHETIC: version {accepted.version + 1} of {accepted.doc_id}, built from correction "
            f"{correction.doc_id}. Proposed for CPA re-review; not approved."
        ),
    )
    return AcceptedDocument.model_validate(data)


def is_stale(approval: Approval, accepted: AcceptedDocument, correction: CorrectionDocument, config: dict) -> bool:
    """True when the fingerprint of the approval's based_on fields would change under the correction.

    Only based_on fields on the accepted document's form are considered (an approval resting on a
    different form is not affected). config (forms.yaml) is needed to parse the correction and to
    map W-2c onto W-2.
    """
    fields = _relevant(approval, accepted)
    if not fields:
        return False
    before = approval.evidence_fingerprint or fingerprint(accepted, fields)
    return fingerprint(new_version(accepted, correction, config), fields) != before


# ---------------------------------------------------------------------------
# Append-only audit log
# ---------------------------------------------------------------------------


class AuditLog:
    """Append-only JSONL log. One line per decision. There is no rewrite or delete method."""

    def __init__(self, path: str | Path = DEFAULT_LOG):
        self.path = Path(path)

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, default=str)
        with self.path.open("a", encoding="utf-8") as fh:  # "a": never truncates
            fh.write(line + "\n")

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


def log_record(case_id: Optional[str], decision: Any, timestamp: Optional[str] = None) -> dict[str, Any]:
    """The audit line for one decision (decision = returnguard.decide.Decision)."""
    ev = decision.evidence
    return {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_id": case_id,
        "accepted_doc_id": ev.accepted_doc_id,
        "correction_doc_id": ev.correction_doc_id,
        "correction_fingerprint": decision.correction_fingerprint,
        "status": decision.status.value,
        "stale_approval_ids": [s.approval_id for s in decision.stale_approvals],
        "applied_changes": [
            f"{c.form_type}:{c.field} {_money(c.old)} -> {_money(c.new)}" for c in decision.proposed_changes if c.applied
        ],
        "new_version_doc_id": decision.new_version.doc_id if decision.new_version else None,
        "clears_approvals": decision.clears_approvals,
    }
