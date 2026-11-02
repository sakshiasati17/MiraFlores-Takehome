"""Validation of an incoming correction against the accepted document it claims to correct.

Pure functions: inputs are never modified; the same input always gives the same output.
Every form-specific rule (identity fields, corrected-flag policy, correction style,
supported boxes, specialist markers, cross-field rules) comes from config/forms.yaml.

This module produces FINDINGS (code + category) and FIELD CHANGES only. It does not
decide a status: Session 3 (decide.py) maps finding categories to statuses.

Categories (exactly these):
  INVALID     the input itself is bad (malformed amount, form rule broken)
  SPECIALIST  a professional must look (identity mismatch, unsupported/marked field, not marked CORRECTED)
  CONFLICT    the correction disagrees with what was accepted (prior value / prior doc mismatch)
  INFO        informational (nothing supported changed)
"""

from __future__ import annotations

import operator
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .models import AcceptedDocument, CorrectionDocument

Category = Literal["INVALID", "SPECIALIST", "CONFLICT", "INFO"]

# Finding code -> category. Codes are ReturnGuard's own vocabulary (not tax facts).
CATEGORY: dict[str, Category] = {
    "MALFORMED_AMOUNT": "INVALID",
    "NEGATIVE_AMOUNT": "INVALID",
    "BAD_PRECISION": "INVALID",
    "FORM_RULE_VIOLATION": "INVALID",
    "IDENTITY_MISMATCH": "SPECIALIST",
    "NOT_MARKED_CORRECTED": "SPECIALIST",
    "UNSUPPORTED_FIELD_CHANGE": "SPECIALIST",
    "SPECIALIST_FIELD_CHANGE": "SPECIALIST",
    "MISSING_PRIOR_VALUE": "SPECIALIST",
    "MISSING_FIELD": "SPECIALIST",
    "PRIOR_DOC_MISMATCH": "CONFLICT",
    "PRIOR_VALUE_MISMATCH": "CONFLICT",
    "NO_SUPPORTED_CHANGE": "INFO",
}

CENT = Decimal("0.01")


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Finding(_Frozen):
    code: str
    category: Category
    field: Optional[str] = None  # "FORM:box", e.g. "W-2c:1"
    message: str
    evidence: dict[str, Any] = Field(default_factory=dict)  # values as strings, doc IDs


class FieldChange(_Frozen):
    form_type: str  # the form the value lives on in the return (W-2c changes are reported as W-2)
    field: str  # box, e.g. "1b"
    old: Decimal
    new: Decimal
    delta: Decimal  # new - old; may be negative


class ValidationResult(_Frozen):
    findings: list[Finding] = Field(default_factory=list)
    changes: list[FieldChange] = Field(default_factory=list)

    def codes(self) -> list[str]:
        return [f.code for f in self.findings]


def _finding(code: str, message: str, field: Optional[str] = None, **evidence: Any) -> Finding:
    return Finding(code=code, category=CATEGORY[code], field=field, message=message, evidence=evidence)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_forms(path: str | Path) -> dict:
    """Load config/forms.yaml as a plain dict."""
    return yaml.safe_load(Path(path).read_text())


def _form_cfg(config: dict, form_type: str) -> dict:
    try:
        return config["forms"][form_type]
    except KeyError as exc:
        raise KeyError(f"form {form_type!r} is not defined in forms.yaml") from exc


def _target_form(config: dict, correction_form: str) -> str:
    """The form a correction corrects (W-2c -> W-2). Defaults to itself."""
    return (_form_cfg(config, correction_form).get("correction") or {}).get("corrects", correction_form)


# ---------------------------------------------------------------------------
# Amounts
# ---------------------------------------------------------------------------

# Digits with correct thousands grouping, or plain digits; optional fraction of any length
# (length is checked separately so we can report BAD_PRECISION rather than MALFORMED).
_AMOUNT_RE = re.compile(r"^(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")


def parse_amount(raw: Any, field: str) -> tuple[Optional[Decimal], list[Finding]]:
    """Parse a raw amount from an incoming form.

    Accepts "3200", "3200.00", "3,200.00", "$3,200.00".
    Rejects letters/bad grouping (MALFORMED_AMOUNT), a minus sign (NEGATIVE_AMOUNT),
    more than 2 decimal places (BAD_PRECISION). Returns (None, [finding]) on failure.
    """
    shown = repr(raw)
    if isinstance(raw, bool) or isinstance(raw, float) or raw is None:
        return None, [_finding("MALFORMED_AMOUNT", f"{field}: amount {shown} is not a text amount.", field, raw=shown)]
    text = str(raw).strip()
    negative = text.startswith("-") or text.startswith("$-")
    body = text.lstrip("$").lstrip("-").lstrip("$").strip()
    if not _AMOUNT_RE.match(body):
        return None, [
            _finding("MALFORMED_AMOUNT", f"{field}: {shown} is not a valid amount.", field, raw=str(raw))
        ]
    if negative:
        return None, [
            _finding("NEGATIVE_AMOUNT", f"{field}: {shown} is negative; amounts must be 0 or more.", field, raw=str(raw))
        ]
    if "." in body and len(body.split(".")[1]) > 2:
        return None, [
            _finding("BAD_PRECISION", f"{field}: {shown} has more than 2 decimal places.", field, raw=str(raw))
        ]
    return Decimal(body.replace(",", "")).quantize(CENT), []


def _parse_correction(correction: CorrectionDocument) -> tuple[dict[str, Decimal], dict[str, Decimal], list[Finding]]:
    """Parse every raw value / previously_reported on a correction. Sorted by box for determinism."""
    values: dict[str, Decimal] = {}
    priors: dict[str, Decimal] = {}
    findings: list[Finding] = []
    for box in sorted(correction.fields):
        cf = correction.fields[box]
        name = f"{correction.form_type}:{box}"
        amount, errs = parse_amount(cf.value, name)
        findings += errs
        if amount is not None:
            values[box] = amount
        if cf.previously_reported is not None:
            prior, errs = parse_amount(cf.previously_reported, f"{name} (previously reported)")
            findings += errs
            if prior is not None:
                priors[box] = prior
    return values, priors, findings


def _changed_boxes(accepted: AcceptedDocument, correction: CorrectionDocument) -> list[tuple[str, Decimal, Decimal]]:
    """(box, old, new) for every parseable correction box whose value differs from accepted.

    A box missing from the accepted document counts as old = 0.00 (so a new non-zero box is a change).
    A box missing from the correction is treated as unchanged.
    """
    values, _, _ = _parse_correction(correction)
    out = []
    for box in sorted(values):
        old = accepted.fields[box].amount if box in accepted.fields else Decimal("0.00")
        if values[box] != old:
            out.append((box, old, values[box]))
    return out


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_identity(accepted: AcceptedDocument, correction: CorrectionDocument, config: dict) -> list[Finding]:
    """Form family + every identity field in config must match."""
    findings: list[Finding] = []
    target = _target_form(config, correction.form_type)
    if target != accepted.form_type:
        findings.append(
            _finding(
                "IDENTITY_MISMATCH",
                f"Form family differs: {correction.form_type} corrects {target}, but the accepted document is {accepted.form_type}.",
                "form_type",
                accepted=accepted.form_type,
                correction=correction.form_type,
                accepted_doc_id=accepted.doc_id,
                correction_doc_id=correction.doc_id,
            )
        )
    for name in _form_cfg(config, correction.form_type).get("identity_fields", []):
        a, c = getattr(accepted, name), getattr(correction, name)
        if a != c:
            findings.append(
                _finding(
                    "IDENTITY_MISMATCH",
                    f"{name} differs: accepted {a}, correction {c}.",
                    name,
                    accepted=str(a),
                    correction=str(c),
                    accepted_doc_id=accepted.doc_id,
                    correction_doc_id=correction.doc_id,
                )
            )
    return findings


def check_correction_link(accepted: AcceptedDocument, correction: CorrectionDocument, config: dict) -> list[Finding]:
    """CORRECTED flag (when config requires it) and the stated prior doc ID."""
    findings: list[Finding] = []
    policy = _form_cfg(config, correction.form_type).get("correction") or {}
    if policy.get("requires_corrected_flag") and not correction.corrected:
        findings.append(
            _finding(
                "NOT_MARKED_CORRECTED",
                f"{correction.form_type} {correction.doc_id} is not marked CORRECTED; it may be a second account rather than a correction.",
                None,
                correction_doc_id=correction.doc_id,
                accepted_doc_id=accepted.doc_id,
            )
        )
    # Only a STATED different doc ID is a conflict; a missing link is not.
    if correction.corrects_doc_id is not None and correction.corrects_doc_id != accepted.doc_id:
        findings.append(
            _finding(
                "PRIOR_DOC_MISMATCH",
                f"Correction says it corrects {correction.corrects_doc_id}, but the accepted document is {accepted.doc_id}.",
                None,
                stated=correction.corrects_doc_id,
                accepted_doc_id=accepted.doc_id,
                correction_doc_id=correction.doc_id,
            )
        )
    return findings


def check_prior_values(accepted: AcceptedDocument, correction: CorrectionDocument, config: dict) -> list[Finding]:
    """Forms with style previous_and_correct (W-2c): previously reported must equal accepted, exactly."""
    policy = _form_cfg(config, correction.form_type).get("correction") or {}
    if policy.get("style") != "previous_and_correct":
        return []
    _, priors, _ = _parse_correction(correction)
    findings: list[Finding] = []
    for box in sorted(priors):
        acc = accepted.fields[box].amount if box in accepted.fields else None
        if acc is None or priors[box] != acc:
            findings.append(
                _finding(
                    "PRIOR_VALUE_MISMATCH",
                    f"{correction.form_type} box {box} previously reported {priors[box]}, "
                    f"but accepted {accepted.form_type} {accepted.doc_id} shows {acc if acc is not None else 'no value'}.",
                    f"{correction.form_type}:{box}",
                    previously_reported=str(priors[box]),
                    accepted=str(acc) if acc is not None else None,
                    correction_doc_id=correction.doc_id,
                    accepted_doc_id=accepted.doc_id,
                )
            )
    return findings


def check_completeness(accepted: AcceptedDocument, correction: CorrectionDocument, config: dict) -> list[Finding]:
    """Gaps that make a correction impossible to trust as-is (Session 3, Step 0). Style comes from config.

    previous_and_correct (W-2c): a box whose value changes but has no "previously reported" amount
                                 -> MISSING_PRIOR_VALUE (we cannot check it against the accepted value).
    reissue (1099-DIV):          a box the accepted document has but the corrected copy leaves out
                                 -> MISSING_FIELD (a reissue should show every box).
    """
    style = (_form_cfg(config, correction.form_type).get("correction") or {}).get("style")
    findings: list[Finding] = []
    if style == "previous_and_correct":
        changed = {box for box, _, _ in _changed_boxes(accepted, correction)}
        for box in sorted(correction.fields):
            if box in changed and correction.fields[box].previously_reported is None:
                findings.append(
                    _finding(
                        "MISSING_PRIOR_VALUE",
                        f"{correction.form_type} box {box} changes but has no 'previously reported' amount, "
                        f"so it cannot be checked against accepted {accepted.form_type} {accepted.doc_id}.",
                        f"{correction.form_type}:{box}",
                        correction_doc_id=correction.doc_id,
                        accepted_doc_id=accepted.doc_id,
                    )
                )
    elif style == "reissue":
        for box in sorted(accepted.fields):
            if box not in correction.fields:
                findings.append(
                    _finding(
                        "MISSING_FIELD",
                        f"Corrected {correction.form_type} {correction.doc_id} leaves out box {box}, "
                        f"which accepted {accepted.doc_id} shows as {accepted.fields[box].amount}.",
                        f"{correction.form_type}:{box}",
                        accepted=str(accepted.fields[box].amount),
                        correction_doc_id=correction.doc_id,
                        accepted_doc_id=accepted.doc_id,
                    )
                )
    return findings


_OPS = {"lte": operator.le, "lt": operator.lt, "gte": operator.ge, "gt": operator.gt, "eq": operator.eq}
_OP_WORDS = {"lte": "at most", "lt": "less than", "gte": "at least", "gt": "more than", "eq": "equal to"}


def check_form_rules(fields: dict[str, Decimal], form_type: str, config: dict) -> list[Finding]:
    """Cross-field rules from forms.yaml (e.g. 1b <= 1a) on parsed values. Missing fields: rule skipped."""
    findings: list[Finding] = []
    for rule in _form_cfg(config, form_type).get("rules") or []:
        op = _OPS.get(rule["type"])
        if op is None:
            raise ValueError(f"unknown rule type {rule['type']!r} in forms.yaml rule {rule.get('id')}")
        left, right = rule["left"], rule["right"]
        if left not in fields or right not in fields:
            continue
        if not op(fields[left], fields[right]):
            findings.append(
                _finding(
                    "FORM_RULE_VIOLATION",
                    rule.get("message")
                    or f"Box {left} must be {_OP_WORDS[rule['type']]} box {right}.",
                    f"{form_type}:{left}",
                    rule=rule.get("id"),
                    left=f"{left}={fields[left]}",
                    right=f"{right}={fields[right]}",
                )
            )
    return findings


def check_supported_fields(accepted: AcceptedDocument, correction: CorrectionDocument, config: dict) -> list[Finding]:
    """Changed boxes that config does not support, or marks for professional review (on_change)."""
    cfg = _form_cfg(config, correction.form_type)
    defined = cfg.get("fields") or {}
    known_unsupported = cfg.get("unsupported_fields") or {}
    findings: list[Finding] = []
    for box, old, new in _changed_boxes(accepted, correction):
        name = f"{correction.form_type}:{box}"
        fdef = defined.get(box)
        ev = dict(old=str(old), new=str(new), correction_doc_id=correction.doc_id, accepted_doc_id=accepted.doc_id)
        if fdef is None or not fdef.get("supported"):
            label = known_unsupported.get(box) or (fdef or {}).get("label") or "unknown box"
            findings.append(
                _finding(
                    "UNSUPPORTED_FIELD_CHANGE",
                    f"{correction.form_type} box {box} ({label}) changed ({old} -> {new}); this field is not supported.",
                    name,
                    **ev,
                )
            )
        elif fdef.get("on_change") == "SPECIALIST_REVIEW":
            reason = fdef.get("on_change_reason") or "this field needs professional review."
            findings.append(
                _finding(
                    "SPECIALIST_FIELD_CHANGE",
                    f"{correction.form_type} box {box} ({fdef.get('label', '')}) changed ({old} -> {new}). {reason}",
                    name,
                    **ev,
                )
            )
    return findings


def diff_fields(accepted: AcceptedDocument, correction: CorrectionDocument, config: dict) -> list[FieldChange]:
    """Changes to SUPPORTED fields only, in config field order, reported on the target form (W-2c -> W-2)."""
    defined = _form_cfg(config, correction.form_type).get("fields") or {}
    target = _target_form(config, correction.form_type)
    changed = {box: (old, new) for box, old, new in _changed_boxes(accepted, correction)}
    return [
        FieldChange(form_type=target, field=box, old=changed[box][0], new=changed[box][1], delta=changed[box][1] - changed[box][0])
        for box, fdef in defined.items()
        if fdef.get("supported") and box in changed
    ]


def validate(accepted: AcceptedDocument, correction: CorrectionDocument, config: dict) -> ValidationResult:
    """Run every check. Findings order: parse, identity, link, prior values, completeness, rules, supported fields, info."""
    values, _, findings = _parse_correction(correction)
    findings = list(findings)
    findings += check_identity(accepted, correction, config)
    findings += check_correction_link(accepted, correction, config)
    findings += check_prior_values(accepted, correction, config)
    findings += check_completeness(accepted, correction, config)
    findings += check_form_rules(values, correction.form_type, config)
    findings += check_supported_fields(accepted, correction, config)
    changes = diff_fields(accepted, correction, config)
    if not changes:
        findings.append(
            _finding(
                "NO_SUPPORTED_CHANGE",
                f"No supported field changed between {accepted.doc_id} and {correction.doc_id}.",
                None,
                accepted_doc_id=accepted.doc_id,
                correction_doc_id=correction.doc_id,
            )
        )
    return ValidationResult(findings=findings, changes=changes)
