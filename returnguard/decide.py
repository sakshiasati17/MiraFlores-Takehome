"""Turn validation findings + impact into exactly ONE status per correction.

Status priority (first match wins; docs/project_plan.md §5):
  1. any INVALID finding                                   -> REJECTED_INVALID_INPUT
  2. any SPECIALIST finding                                -> SPECIALIST_REVIEW
  3. any CONFLICT finding                                  -> CONFLICT
  4. same correction already processed (same fingerprint
     in state) or NO_SUPPORTED_CHANGE                      -> DUPLICATE_NO_CHANGE
  5. return status FILED                                   -> POSSIBLE_AMENDMENT
  6. otherwise                                             -> APPLY_AND_REREVIEW

Statuses 1-4: every change is "proposed, not applied" (nothing was applied), no new version is created and no
approval is marked stale. A form type that config/forms.yaml does not define gives an UNKNOWN_FORM_TYPE finding
(SPECIALIST) instead of an error. Statuses 5-6: the correction is recorded as a NEW document version and the approvals
it touches are listed as stale for a CPA to re-review. Status 6 also makes that version the working
value (applied=True); status 5 does not, because the return is already filed.
Nothing is ever approved or cleared: Decision.clears_approvals is the literal False.
This module never computes tax and never gives tax advice.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .audit import correction_fingerprint, fingerprint, new_version, with_baseline_fingerprints
from .impact import find_impact
from .models import AcceptedDocument, CorrectionDocument, DecisionStatus, ReturnState, ReturnStatus
from .validate import Finding, ValidationResult, validate

S = DecisionStatus

NEXT_ACTION: dict[DecisionStatus, str] = {
    S.APPLY_AND_REREVIEW: "Re-review the approvals listed in this report against the corrected document. Nothing has been approved automatically.",
    S.POSSIBLE_AMENDMENT: "Return already filed. CPA to assess whether an amended return is needed. Nothing has been changed automatically.",
    S.CONFLICT: "Correction does not match the accepted document. Reconcile with the issuer before using it. Nothing has been applied.",
    S.SPECIALIST_REVIEW: "Outside what this prototype handles automatically. Route to a specialist reviewer. Nothing has been applied.",
    S.DUPLICATE_NO_CHANGE: "No new information. No action needed.",
    S.REJECTED_INVALID_INPUT: "Input could not be trusted (see reasons). Request a valid document. Nothing has been applied.",
}

_BLOCKING = {S.REJECTED_INVALID_INPUT, S.SPECIALIST_REVIEW, S.CONFLICT, S.DUPLICATE_NO_CHANGE}  # statuses 1-4

# Naive baseline, for comparison ONLY (never used to decide): "did total income change?" on the form's
# headline total box. Shown by the CLI and the tests to demonstrate what a naive diff misses (T1).
NAIVE_TOTAL_FIELD: dict[str, str] = {"1099-DIV": "1a"}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config(forms_path: str | Path, dependencies_path: str | Path) -> dict:
    """One dict holding both config files: forms.yaml keys (forms, amount_rules) and
    dependencies.yaml keys (dependencies, approval_items). validate() reads config["forms"],
    find_impact() reads config["dependencies"], so the same dict serves both."""
    forms = yaml.safe_load(Path(forms_path).read_text())
    deps = yaml.safe_load(Path(dependencies_path).read_text())
    return {**deps, **forms, "dependencies_version": deps.get("version")}


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProposedChange(_Frozen):
    form_type: str
    field: str
    label: str = ""
    old: Decimal
    new: Decimal
    delta: Decimal
    applied: bool  # True only for APPLY_AND_REREVIEW: the new version is now the working value
    applied_as_new_version: bool  # True for POSSIBLE_AMENDMENT and APPLY_AND_REREVIEW


class StaleApproval(_Frozen):
    approval_id: str
    item: str
    paths: list[str]  # e.g. "1099-DIV:1b -> Form 1040 line 3a -> APR-1040-L3A"
    sources: list[str]  # IRS URL(s); prefixed "UNVERIFIED: " when config flags the mapping
    unverified: bool
    fingerprint_before: Optional[str] = None
    fingerprint_after: Optional[str] = None


class DecisionEvidence(_Frozen):
    accepted_doc_id: str
    correction_doc_id: str
    accepted_values: dict[str, str]  # box -> "2400.00"
    correction_values: dict[str, dict[str, Optional[str]]]  # box -> raw value / previously_reported
    findings: list[Finding] = Field(default_factory=list)
    return_status: str
    return_status_source: str


class Decision(_Frozen):
    status: DecisionStatus
    reasons: list[str]
    proposed_changes: list[ProposedChange] = Field(default_factory=list)
    stale_approvals: list[StaleApproval] = Field(default_factory=list)
    evidence: DecisionEvidence
    next_action: str
    correction_fingerprint: str
    new_version: Optional[AcceptedDocument] = None  # set only for statuses 5-6
    # Safety invariant: ReturnGuard never approves or clears anything. A CPA decides.
    clears_approvals: Literal[False] = False


class ProcessingState(BaseModel):
    """Small in-memory state for one run (one fixture). Lets duplicates be detected across submissions.

    seen:     correction fingerprint -> doc_id that first carried it
    versions: new document version records created (statuses 5-6), in order
    """

    model_config = ConfigDict(extra="forbid")

    seen: dict[str, str] = Field(default_factory=dict)
    versions: list[AcceptedDocument] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def signed(d: Decimal) -> str:
    """Delta as text: '-800.00', '+500.00', '0.00'."""
    q = Decimal(d).quantize(Decimal("0.01"))
    return f"+{q}" if q > 0 else str(q)


def naive_total_changed(accepted: AcceptedDocument, correction: CorrectionDocument) -> Optional[bool]:
    """Naive baseline: did the headline total box change? None if the form has no naive total defined."""
    box = NAIVE_TOTAL_FIELD.get(correction.form_type)
    if box is None or box not in accepted.fields or box not in correction.fields:
        return None
    try:
        return Decimal(correction.fields[box].value.replace(",", "").lstrip("$")) != accepted.fields[box].amount
    except Exception:
        return None


def unknown_form_finding(form_type: str, correction_doc_id: str, accepted_doc_id: Optional[str] = None) -> Finding:
    """UNKNOWN_FORM_TYPE (SPECIALIST): the form is not defined in config/forms.yaml, so nothing can be checked."""
    return Finding(
        code="UNKNOWN_FORM_TYPE",
        category="SPECIALIST",
        field="form_type",
        message=(f"Form type {form_type!r} on {correction_doc_id} is not defined in config/forms.yaml, so it cannot be "
                 "checked. Nothing was compared or applied; add the form to config or have a specialist review it."),
        evidence={"form_type": form_type, "correction_doc_id": correction_doc_id, "accepted_doc_id": accepted_doc_id},
    )


def _status(findings: list[Finding], duplicate: bool, return_state: ReturnState) -> DecisionStatus:
    cats = {f.category for f in findings}
    if "INVALID" in cats:
        return S.REJECTED_INVALID_INPUT
    if "SPECIALIST" in cats:
        return S.SPECIALIST_REVIEW
    if "CONFLICT" in cats:
        return S.CONFLICT
    if duplicate or any(f.code == "NO_SUPPORTED_CHANGE" for f in findings):
        return S.DUPLICATE_NO_CHANGE
    if return_state.status == ReturnStatus.FILED:
        return S.POSSIBLE_AMENDMENT
    return S.APPLY_AND_REREVIEW


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def decide(
    accepted: AcceptedDocument,
    correction: CorrectionDocument,
    return_state: ReturnState,
    config: dict,
    state: Optional[ProcessingState] = None,
    extra_findings: Optional[list[Finding]] = None,
) -> Decision:
    """Exactly one Decision for one correction. Inputs are never modified.

    config: forms.yaml + dependencies.yaml merged (see load_config()).
    state:  shared between submissions of the same run so a repeated correction is DUPLICATE_NO_CHANGE.
            The state is updated (fingerprint recorded; new version stored for statuses 5-6).
    extra_findings: findings from outside validate() (Session 4: EXTRACTION_UNVERIFIED from extract.py).
            They are put first and go through exactly the same category -> status rules.
    """
    if correction.form_type in (config.get("forms") or {}):
        result = validate(accepted, correction, config)
    else:  # never crash on a form config does not define: route it to a person
        result = ValidationResult(findings=[unknown_form_finding(correction.form_type, correction.doc_id, accepted.doc_id)])
    if extra_findings:
        result = result.model_copy(update={"findings": [*extra_findings, *result.findings]})
    fp = correction_fingerprint(correction)
    first_seen = state.seen.get(fp) if state is not None else None
    status = _status(result.findings, first_seen is not None, return_state)
    blocked = status in _BLOCKING
    labels = (config["forms"].get(correction.form_type) or {}).get("fields") or {}

    # Proposed changes -------------------------------------------------------
    changes = [
        ProposedChange(
            form_type=c.form_type,
            field=c.field,
            label=(labels.get(c.field) or {}).get("label", ""),
            old=c.old,
            new=c.new,
            delta=c.delta,
            applied=status == S.APPLY_AND_REREVIEW,
            applied_as_new_version=not blocked,
        )
        for c in result.changes
    ]

    # Stale approvals (statuses 5-6 only) ---------------------------------------
    stale: list[StaleApproval] = []
    version: Optional[AcceptedDocument] = None
    if not blocked:
        version = new_version(accepted, correction, config)
        rs = with_baseline_fingerprints(return_state, [accepted])
        approvals = {a.id: a for a in rs.approvals}
        items = (config.get("approval_items") or {})
        grouped: dict[str, list] = {}
        for it in find_impact(result.changes, config):
            grouped.setdefault(it.approval_id, []).append(it)
        for aid, its in grouped.items():
            appr = approvals.get(aid)
            fields = [f for f in (appr.based_on if appr else []) if f.startswith(f"{accepted.form_type}:")]
            stale.append(
                StaleApproval(
                    approval_id=aid,
                    item=items.get(aid) or (appr.item if appr else aid),
                    paths=[i.path for i in its],
                    sources=list(dict.fromkeys(i.source for i in its)),
                    unverified=any(i.unverified for i in its),
                    fingerprint_before=appr.evidence_fingerprint if appr else None,
                    fingerprint_after=fingerprint(version, fields) if fields else None,
                )
            )

    # Reasons (plain English, for a CPA) ------------------------------------------
    blocking_findings = [f for f in result.findings if f.category != "INFO"]
    shown = blocking_findings or result.findings
    reasons = [f"Documents compared: accepted {accepted.doc_id} vs correction {correction.doc_id}."]
    reasons += [f.message for f in shown]
    if first_seen is not None:
        reasons.append(
            f"This correction was already processed in this run (first as {first_seen}); "
            f"same fingerprint {fp[:12]}. No new information."
        )
    suffix = " (proposed, not applied)" if blocked else ""
    for c in changes:
        name = f"{c.form_type} box {c.field}" + (f" ({c.label})" if c.label else "")
        reasons.append(f"{name}: {c.old} -> {c.new} (delta {signed(c.delta)}){suffix}.")
    if blocked:
        reasons.append("Nothing was applied: no new document version was recorded and no approval was marked stale.")
    else:
        reasons.append(f"Correction recorded as new version {version.version} ({version.doc_id}); "
                       f"{accepted.doc_id} is kept unchanged.")
        for s in stale:
            tag = " [UNVERIFIED mapping]" if s.unverified else ""
            reasons.append(f"Approval {s.approval_id} ({s.item}) is now stale: {'; '.join(s.paths)}{tag}.")
        if status == S.POSSIBLE_AMENDMENT:
            reasons.append(
                f"Return status is FILED ({return_state.status_source}); the correction was not applied to the return."
            )
    reasons.append("No approval has been granted or cleared automatically.")

    evidence = DecisionEvidence(
        accepted_doc_id=accepted.doc_id,
        correction_doc_id=correction.doc_id,
        accepted_values={b: str(v.amount) for b, v in sorted(accepted.fields.items())},
        correction_values={
            b: {"value": cf.value, "previously_reported": cf.previously_reported}
            for b, cf in sorted(correction.fields.items())
        },
        findings=result.findings,
        return_status=return_state.status.value,
        return_status_source=return_state.status_source,
    )

    if state is not None:
        state.seen.setdefault(fp, correction.doc_id)
        if version is not None:
            state.versions.append(version)

    return Decision(
        status=status,
        reasons=reasons,
        proposed_changes=changes,
        stale_approvals=stale,
        evidence=evidence,
        next_action=NEXT_ACTION[status],
        correction_fingerprint=fp,
        new_version=version,
    )
