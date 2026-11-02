"""Session 1 tests: every fixture loads into the models; money is strict Decimal."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

# Make `import returnguard` work under plain `pytest` from a clean clone (no install step).
# TODO(Session 2+): replace with `pythonpath = .` in a pytest.ini once that file is allowed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import yaml
from pydantic import ValidationError

from returnguard.models import (
    AcceptedDocument,
    Approval,
    CaseFixture,
    ChangedField,
    CorrectionDocument,
    Decision,
    DecisionStatus,
    FieldValue,
    ReturnState,
    ReturnStatus,
    parse_money,
)

ROOT = Path(__file__).resolve().parents[1]
SYN = ROOT / "data" / "synthetic"
CASES = sorted((SYN / "cases").glob("T*.json"), key=lambda p: int(p.stem[1:]))


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def all_fixture_files() -> list[Path]:
    return sorted(SYN.rglob("*.json"))


# --- fixtures exist and are labelled ---------------------------------------


def test_all_fifteen_cases_present():
    assert [p.stem for p in CASES] == [f"T{i}" for i in range(1, 16)]


@pytest.mark.parametrize("path", all_fixture_files(), ids=lambda p: p.name)
def test_every_file_is_labelled_synthetic(path):
    data = load(path)
    assert data["synthetic"] is True
    assert "SYNTHETIC" in data["_label"]


# --- fixtures load into models ------------------------------------------------


def test_baseline_1099div_loads_as_decimal():
    doc = AcceptedDocument.model_validate(load(SYN / "accepted_1099div_C-001_2025.json"))
    amounts = {box: fv.amount for box, fv in doc.fields.items()}
    assert amounts == {
        "1a": Decimal("3200.00"),
        "1b": Decimal("2400.00"),
        "2a": Decimal("500.00"),
        "4": Decimal("0.00"),
    }
    assert all(isinstance(a, Decimal) for a in amounts.values())
    assert (doc.client_id, doc.tax_year, doc.payer_tin) == ("C-001", 2025, "00-0000001")


def test_baseline_w2_loads_as_decimal():
    doc = AcceptedDocument.model_validate(load(SYN / "accepted_w2_C-001_2025.json"))
    assert doc.fields["1"].amount == Decimal("82000.00")
    assert doc.fields["2"].amount == Decimal("9000.00")
    assert doc.payer_tin == "00-0000002"


def test_return_state_loads():
    state = ReturnState.model_validate(load(SYN / "return_state_C-001_2025.json"))
    assert state.status is ReturnStatus.APPROVED
    assert "MOCKED" in state.status_source
    ids = {a.id for a in state.approvals}
    assert {"APR-1040-L3A", "APR-QDCG-WS", "APR-1040-L3B", "APR-1040-L1A", "APR-WAGE-WP"} <= ids


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_every_case_loads(path):
    case = CaseFixture.model_validate(load(path))
    assert case.case_id == path.stem
    assert all(isinstance(s, CorrectionDocument) for s in case.submissions)
    # every non-placeholder amount that is meant to be valid parses as Decimal
    for sub in case.submissions:
        for box, f in sub.fields.items():
            if case.case_id == "T10":
                continue  # T10 is the malformed-amount case; checked below
            assert isinstance(parse_money(f.value), Decimal), (case.case_id, box)


def test_expected_statuses_match_plan():
    expected = {
        "T1": "APPLY_AND_REREVIEW", "T2": "APPLY_AND_REREVIEW", "T3": "POSSIBLE_AMENDMENT",
        "T4": "APPLY_AND_REREVIEW", "T5": "CONFLICT", "T6": "SPECIALIST_REVIEW",
        "T7": "DUPLICATE_NO_CHANGE", "T8": "SPECIALIST_REVIEW", "T9": "REJECTED_INVALID_INPUT",
        "T10": "REJECTED_INVALID_INPUT", "T11": "SPECIALIST_REVIEW", "T12": "SPECIALIST_REVIEW",
        "T13": "APPLY_AND_REREVIEW", "T14": "DUPLICATE_NO_CHANGE", "T15": "SPECIALIST_REVIEW",
    }
    got = {p.stem: CaseFixture.model_validate(load(p)).expected.status.value for p in CASES}
    assert got == expected


def test_t1_headline_values():
    case = CaseFixture.model_validate(load(SYN / "cases" / "T1.json"))
    sub = case.submissions[0]
    assert sub.corrected is True
    assert parse_money(sub.fields["1b"].value) == Decimal("1600.00")
    assert parse_money(sub.fields["1a"].value) == Decimal("3200.00")  # 1a unchanged
    assert Decimal(case.expected.deltas["1099-DIV:1b"]) == Decimal("-800.00")
    assert case.expected.stale_approvals == ["APR-1040-L3A", "APR-QDCG-WS"]


def test_t10_bad_amount_is_kept_raw_and_fails_parsing():
    case = CaseFixture.model_validate(load(SYN / "cases" / "T10.json"))
    raw = case.submissions[0].fields["1"].value
    assert raw == "86,5OO"
    with pytest.raises(ValueError):
        parse_money(raw)


def test_t7_has_two_identical_submissions():
    case = CaseFixture.model_validate(load(SYN / "cases" / "T7.json"))
    a, b = case.submissions
    assert a == b
    assert case.expected.status_sequence == [
        DecisionStatus.APPLY_AND_REREVIEW,
        DecisionStatus.DUPLICATE_NO_CHANGE,
    ]


# --- money parsing --------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [("3200", "3200.00"), ("3200.5", "3200.50"), ("0.00", "0.00"), (" 1600.00 ", "1600.00"),
     (86500, "86500.00"), (Decimal("12.3"), "12.30")],
)
def test_money_parses_as_two_dp_decimal(raw, expected):
    value = FieldValue(amount=raw).amount
    assert isinstance(value, Decimal)
    assert value == Decimal(expected)
    assert value.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "bad",
    ["86,5OO", "86,500.00", "-800.00", "-1", "12.345", "", "abc", "$100.00", "1e3", "NaN",
     1.5, True, None, Decimal("-5"), Decimal("NaN")],
)
def test_bad_amounts_raise(bad):
    with pytest.raises(ValidationError):
        FieldValue(amount=bad)


def test_changed_field_allows_negative_delta_but_not_negative_amounts():
    cf = ChangedField(form_type="1099-DIV", box="1b", old="2400.00", new="1600.00", delta=Decimal("-800.00"))
    assert cf.new - cf.old == cf.delta
    with pytest.raises(ValidationError):
        ChangedField(form_type="1099-DIV", box="1b", old="-1.00", new="1600.00", delta=Decimal("0"))


# --- model guards -------------------------------------------------------------


def test_non_synthetic_document_rejected():
    data = load(SYN / "accepted_w2_C-001_2025.json")
    data["synthetic"] = False
    with pytest.raises(ValidationError):
        AcceptedDocument.model_validate(data)


def test_unknown_keys_rejected():
    data = load(SYN / "accepted_w2_C-001_2025.json")
    data["ssn"] = "000-00-0000"
    with pytest.raises(ValidationError):
        AcceptedDocument.model_validate(data)


def test_decision_can_never_clear_approvals():
    d = Decision(status="APPLY_AND_REREVIEW", reasons=["test"])
    assert d.clears_approvals is False
    with pytest.raises(ValidationError):
        Decision(status="APPLY_AND_REREVIEW", reasons=["test"], clears_approvals=True)


def test_decision_status_is_exactly_the_six():
    assert {s.value for s in DecisionStatus} == {
        "APPLY_AND_REREVIEW", "POSSIBLE_AMENDMENT", "CONFLICT",
        "SPECIALIST_REVIEW", "DUPLICATE_NO_CHANGE", "REJECTED_INVALID_INPUT",
    }
    with pytest.raises(ValidationError):
        Decision(status="APPROVED", reasons=[])


def test_return_status_values():
    assert {s.value for s in ReturnStatus} == {"DRAFT", "IN_REVIEW", "APPROVED", "FILED"}


def test_approval_fields():
    a = Approval(id="X", item="i", approved_by="SYN-CPA-01", approved_at="t", based_on=["W-2:1"])
    assert a.evidence_fingerprint is None


# --- config sanity (loads; every dependency field is defined in forms.yaml) ------


def test_config_is_consistent():
    forms = yaml.safe_load((ROOT / "config" / "forms.yaml").read_text())["forms"]
    deps = yaml.safe_load((ROOT / "config" / "dependencies.yaml").read_text())
    items = set(deps["approval_items"])
    for key, edges in deps["dependencies"].items():
        form, box = key.split(":")
        assert box in forms[form]["fields"], key
        for e in edges:
            assert e["approval"] in items, (key, e)
            assert e["source"], (key, e)
    rule = forms["1099-DIV"]["rules"][0]
    assert (rule["left"], rule["type"], rule["right"]) == ("1b", "lte", "1a")
    # every approval in the baseline return state exists in the dependency map
    state = load(SYN / "return_state_C-001_2025.json")
    assert {a["id"] for a in state["approvals"]} <= items
