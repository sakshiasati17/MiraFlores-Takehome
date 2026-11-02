"""Pydantic v2 schemas for ReturnGuard.

Design notes
- All money is decimal.Decimal, exactly 2 decimal places, never float.
- Accepted documents hold already-checked money (FieldValue / Money).
- Correction documents hold the RAW amount strings exactly as they appear on the
  incoming form (or as an extractor read them). Raw strings are parsed into Money
  later by validate.py (Session 2), so a malformed amount like "86,5OO" becomes a
  REJECTED_INVALID_INPUT decision naming the field, instead of a load crash.
- Nothing in these models can grant or clear an approval: Decision.clears_approvals
  is the literal False.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

# Plain digits, optional "." and 1-2 decimals. No sign, no commas, no letters,
# no currency symbol, no exponent. Negative amounts are rejected here because no
# supported box in this prototype may be negative (see config/forms.yaml).
_MONEY_RE = re.compile(r"^\d+(\.\d{1,2})?$")


class MoneyError(ValueError):
    """Raised when an amount is not a valid non-negative 2-dp money string."""


def parse_money(raw: Any) -> Decimal:
    """Parse a money amount strictly. Returns a Decimal quantized to 0.01.

    Accepts: str like "3200" / "3200.5" / "3200.00", int, Decimal.
    Rejects: float (binary rounding), bool, negatives, commas, letters,
    more than 2 decimal places, NaN/Infinity, empty strings.
    """
    if isinstance(raw, bool) or isinstance(raw, float):
        raise MoneyError(f"amount must be a string or integer, not {type(raw).__name__}: {raw!r}")
    if isinstance(raw, int):
        raw = str(raw)
    if isinstance(raw, Decimal):
        if not raw.is_finite():
            raise MoneyError(f"amount is not a finite number: {raw!r}")
        raw = format(raw, "f")
    if not isinstance(raw, str):
        raise MoneyError(f"amount must be a string: {raw!r}")
    text = raw.strip()
    if not _MONEY_RE.match(text):
        raise MoneyError(
            f"invalid amount {raw!r}: expected a non-negative number with at most "
            "2 decimal places and no commas, signs or letters"
        )
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation as exc:  # pragma: no cover - regex already guards this
        raise MoneyError(f"invalid amount {raw!r}") from exc


Money = Annotated[Decimal, BeforeValidator(parse_money)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class _Synthetic(_Strict):
    """Base for every data file: must carry "synthetic": true (CLAUDE.md rule)."""

    synthetic: Literal[True]
    label: Optional[str] = Field(default=None, alias="_label")  # human-readable SYNTHETIC note


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReturnStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    FILED = "FILED"


class DecisionStatus(str, Enum):
    """Exactly the six statuses in CLAUDE.md (priority order in docs/project_plan.md §5)."""

    APPLY_AND_REREVIEW = "APPLY_AND_REREVIEW"
    POSSIBLE_AMENDMENT = "POSSIBLE_AMENDMENT"
    CONFLICT = "CONFLICT"
    SPECIALIST_REVIEW = "SPECIALIST_REVIEW"
    DUPLICATE_NO_CHANGE = "DUPLICATE_NO_CHANGE"
    REJECTED_INVALID_INPUT = "REJECTED_INVALID_INPUT"


AcceptedFormType = Literal["1099-DIV", "W-2"]
CorrectionFormType = Literal["1099-DIV", "W-2c"]

# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class FieldValue(_Strict):
    """One checked money value on an accepted document."""

    amount: Money
    source: Optional[str] = None  # where on the source document it came from


class AcceptedDocument(_Synthetic):
    """A source document whose values a CPA already relied on."""

    doc_id: str
    version: int = Field(ge=1)
    form_type: AcceptedFormType
    client_id: str
    tax_year: int
    payer_name: str
    payer_tin: str
    accepted_at: str  # ISO-8601 timestamp (synthetic)
    fields: dict[str, FieldValue]


class CorrectionField(_Strict):
    """One box on an incoming form, kept RAW (string) until validate.py parses it.

    value:               the amount on the incoming form (W-2c: "Correct information").
    previously_reported: W-2c only, the "Previously reported" amount.
    """

    value: str
    previously_reported: Optional[str] = None


class CorrectionDocument(_Synthetic):
    """An incoming (possibly corrected) form. Amounts are raw strings."""

    doc_id: str
    form_type: CorrectionFormType
    client_id: str
    tax_year: int
    payer_name: str
    payer_tin: str
    corrected: bool  # CORRECTED box ticked (always true for a W-2c)
    corrects_doc_id: Optional[str] = None  # accepted doc this claims to correct, if stated
    received_at: str
    fields: dict[str, CorrectionField] = Field(default_factory=dict)
    source_text: Optional[str] = None  # synthetic form text, for extraction checks (Session 4)


# ---------------------------------------------------------------------------
# Return state and approvals
# ---------------------------------------------------------------------------


class Approval(_Strict):
    """A CPA sign-off on one return item.

    based_on lists the "FORM:box" fields the approval relied on.
    evidence_fingerprint is the SHA-256 of those fields; it is computed by
    returnguard/audit.py (Session 3), so baseline fixtures leave it null.
    """

    id: str
    item: str
    approved_by: str
    approved_at: str
    based_on: list[str]
    evidence_fingerprint: Optional[str] = None


class ReturnState(_Synthetic):
    client_id: str
    tax_year: int
    status: ReturnStatus
    # MOCKED: filing status is entered by hand; MiraFlores doesn't yet track IRS acceptance.
    status_source: str = "MOCKED: entered by hand"
    accepted_doc_ids: list[str]
    approvals: list[Approval]


# ---------------------------------------------------------------------------
# Decision (output)
# ---------------------------------------------------------------------------


class ChangedField(_Strict):
    form_type: str
    box: str
    old: Money
    new: Money
    delta: Decimal  # new - old; may be negative, so not Money


class Evidence(_Strict):
    doc_id: str
    field: Optional[str] = None
    value: Optional[str] = None
    note: Optional[str] = None


class Decision(_Strict):
    status: DecisionStatus
    reasons: list[str]
    changed_fields: list[ChangedField] = Field(default_factory=list)
    stale_approvals: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    # Safety invariant: ReturnGuard never approves or clears anything. A CPA decides.
    clears_approvals: Literal[False] = False


# ---------------------------------------------------------------------------
# Test-case fixture wrapper (data/synthetic/cases/T*.json)
# ---------------------------------------------------------------------------


class ExpectedResult(_Strict):
    status: DecisionStatus
    # For multi-submission cases (T7): the status expected for each submission in order.
    status_sequence: Optional[list[DecisionStatus]] = None
    deltas: dict[str, str] = Field(default_factory=dict)  # "FORM:box" -> signed amount
    stale_approvals: list[str] = Field(default_factory=list)
    must_show: list[str] = Field(default_factory=list)


class CaseFixture(_Synthetic):
    case_id: str
    angle: str
    description: str
    return_status: ReturnStatus
    submissions: list[CorrectionDocument] = Field(min_length=1)
    # Informational only (no code reads it): where the case's MOCKED LLM stand-in lives in data/llm_cache/.
    llm_cache: Optional[dict[str, str]] = None
    expected: ExpectedResult
