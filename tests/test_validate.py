"""Session 2: validate.py. Loads real fixtures from data/synthetic/cases/ and asserts real values."""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

import pytest

from returnguard.models import AcceptedDocument, CaseFixture, CorrectionDocument
from returnguard.validate import (
    CATEGORY,
    FieldChange,
    check_correction_link,
    check_form_rules,
    check_identity,
    check_prior_values,
    check_supported_fields,
    diff_fields,
    load_forms,
    parse_amount,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]
SYN = ROOT / "data" / "synthetic"
D = Decimal


@pytest.fixture(scope="module")
def cfg() -> dict:
    return load_forms(ROOT / "config" / "forms.yaml")


def accepted(form: str) -> AcceptedDocument:
    name = "accepted_1099div_C-001_2025.json" if form == "1099-DIV" else "accepted_w2_C-001_2025.json"
    return AcceptedDocument.model_validate_json((SYN / name).read_text())


def case(cid: str) -> CorrectionDocument:
    return CaseFixture.model_validate_json((SYN / "cases" / f"{cid}.json").read_text()).submissions[0]


def run(cid: str, cfg: dict):
    c = case(cid)
    return validate(accepted("W-2" if c.form_type == "W-2c" else "1099-DIV"), c, cfg)


def blocking(result) -> list:
    return [f for f in result.findings if f.category != "INFO"]


# --- parse_amount -------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [("3200.00", "3200.00"), ("3,200.00", "3200.00"), ("$3,200.00", "3200.00"), ("3200", "3200.00"),
     ("1,234,567.8", "1234567.80"), ("0.00", "0.00"), ("  $500.00 ", "500.00")],
)
def test_parse_amount_ok(raw, expected):
    value, findings = parse_amount(raw, "X:1")
    assert findings == []
    assert value == D(expected) and isinstance(value, Decimal)
    assert value.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "raw,code",
    [("86,5OO", "MALFORMED_AMOUNT"), ("", "MALFORMED_AMOUNT"), ("abc", "MALFORMED_AMOUNT"),
     ("32,00.00", "MALFORMED_AMOUNT"), ("1.2.3", "MALFORMED_AMOUNT"), (None, "MALFORMED_AMOUNT"),
     (3200.0, "MALFORMED_AMOUNT"), ("-5.00", "NEGATIVE_AMOUNT"), ("$-5.00", "NEGATIVE_AMOUNT"),
     ("1.005", "BAD_PRECISION")],
)
def test_parse_amount_rejects(raw, code):
    value, findings = parse_amount(raw, "W-2c:1")
    assert value is None
    assert [f.code for f in findings] == [code]
    f = findings[0]
    assert f.category == "INVALID"
    assert f.field == "W-2c:1"
    assert "W-2c:1" in f.message


def test_every_code_has_one_of_four_categories():
    assert set(CATEGORY.values()) <= {"INVALID", "SPECIALIST", "CONFLICT", "INFO"}


# --- the case table -------------------------------------------------------------


@pytest.mark.parametrize("cid", ["T1", "T3"])
def test_T1_T3_qualified_dividend_reclassification(cid, cfg):
    r = run(cid, cfg)
    assert blocking(r) == []
    assert r.findings == []
    assert r.changes == [FieldChange(form_type="1099-DIV", field="1b", old=D("2400.00"), new=D("1600.00"), delta=D("-800.00"))]
    assert "1a" not in [c.field for c in r.changes]  # 1a unchanged: a naive total-income diff sees nothing


def test_T2_ordinary_dividends_up(cfg):
    r = run("T2", cfg)
    assert r.findings == []
    assert r.changes == [FieldChange(form_type="1099-DIV", field="1a", old=D("3200.00"), new=D("3700.00"), delta=D("500.00"))]


def test_T4_w2c_wages_reported_on_w2(cfg):
    r = run("T4", cfg)
    assert r.findings == []
    assert r.changes == [FieldChange(form_type="W-2", field="1", old=D("82000.00"), new=D("86500.00"), delta=D("4500.00"))]


def test_T5_prior_value_mismatch(cfg):
    r = run("T5", cfg)
    assert [(f.code, f.category) for f in r.findings] == [("PRIOR_VALUE_MISMATCH", "CONFLICT")]
    f = r.findings[0]
    assert f.field == "W-2c:1"
    assert f.evidence["previously_reported"] == "81000.00"
    assert f.evidence["accepted"] == "82000.00"
    assert f.evidence["correction_doc_id"] == "SYN-W2C-C001-2025-T5"
    assert f.evidence["accepted_doc_id"] == "SYN-W2-C001-2025-v1"
    for text in ("81000.00", "82000.00", "SYN-W2-C001-2025-v1"):
        assert text in f.message


def test_T6_withholding_change_needs_specialist(cfg):
    r = run("T6", cfg)
    assert [(f.code, f.category) for f in r.findings] == [("SPECIALIST_FIELD_CHANGE", "SPECIALIST")]
    assert r.findings[0].field == "W-2c:2"
    assert "professional review" in r.findings[0].message
    assert r.changes == [FieldChange(form_type="W-2", field="2", old=D("9000.00"), new=D("9800.00"), delta=D("800.00"))]


def test_T8_payer_tin_mismatch(cfg):
    r = run("T8", cfg)
    assert [(f.code, f.category) for f in r.findings] == [("IDENTITY_MISMATCH", "SPECIALIST")]
    f = r.findings[0]
    assert f.field == "payer_tin"
    assert f.evidence["accepted"] == "00-0000001"
    assert f.evidence["correction"] == "00-0000009"
    assert "00-0000001" in f.message and "00-0000009" in f.message


def test_T8_tax_year_and_client_mismatch(cfg):
    c = case("T1").model_copy(update={"tax_year": 2024, "client_id": "C-002"})
    codes = [(f.code, f.field) for f in check_identity(accepted("1099-DIV"), c, cfg)]
    assert codes == [("IDENTITY_MISMATCH", "client_id"), ("IDENTITY_MISMATCH", "tax_year")]


def test_form_family_mismatch(cfg):
    # a 1099-DIV correction checked against the accepted W-2
    fs = check_identity(accepted("W-2"), case("T1"), cfg)
    assert ("IDENTITY_MISMATCH", "form_type") in [(f.code, f.field) for f in fs]


def test_T9_qualified_exceeds_ordinary(cfg):
    r = run("T9", cfg)
    assert [(f.code, f.category) for f in r.findings] == [("FORM_RULE_VIOLATION", "INVALID")]
    f = r.findings[0]
    assert f.evidence == {"rule": "QUALIFIED_LE_ORDINARY", "left": "1b=3500.00", "right": "1a=3200.00"}
    assert "cannot exceed" in f.message


def test_T10_malformed_amount_names_field_and_value(cfg):
    r = run("T10", cfg)
    assert [(f.code, f.category) for f in blocking(r)] == [("MALFORMED_AMOUNT", "INVALID")]
    f = blocking(r)[0]
    assert f.field == "W-2c:1"
    assert f.evidence["raw"] == "86,5OO"
    assert "86,5OO" in f.message
    assert r.changes == []


def test_T11_not_marked_corrected(cfg):
    r = run("T11", cfg)
    assert [(f.code, f.category) for f in r.findings] == [("NOT_MARKED_CORRECTED", "SPECIALIST")]


def test_prior_doc_mismatch_when_stated(cfg):
    c = case("T1").model_copy(update={"corrects_doc_id": "SYN-1099DIV-C001-2025-OTHER"})
    fs = check_correction_link(accepted("1099-DIV"), c, cfg)
    assert [(f.code, f.category) for f in fs] == [("PRIOR_DOC_MISMATCH", "CONFLICT")]
    assert fs[0].evidence["stated"] == "SYN-1099DIV-C001-2025-OTHER"
    assert fs[0].evidence["accepted_doc_id"] == "SYN-1099DIV-C001-2025-v1"


def test_T14_nothing_changed(cfg):
    r = run("T14", cfg)
    assert [(f.code, f.category) for f in r.findings] == [("NO_SUPPORTED_CHANGE", "INFO")]
    assert r.changes == []


def test_T15_unsupported_box7(cfg):
    r = run("T15", cfg)
    assert [(f.code, f.category) for f in blocking(r)] == [("UNSUPPORTED_FIELD_CHANGE", "SPECIALIST")]
    f = blocking(r)[0]
    assert f.field == "1099-DIV:7"
    assert "Foreign tax paid" in f.message and "not supported" in f.message
    assert r.changes == []
    assert "NO_SUPPORTED_CHANGE" in r.codes()


# --- individual checks / config-driven ----------------------------------------


def test_prior_values_only_for_previous_and_correct_style(cfg):
    assert check_prior_values(accepted("1099-DIV"), case("T1"), cfg) == []
    assert check_prior_values(accepted("W-2"), case("T4"), cfg) == []


def test_form_rules_come_from_config(cfg):
    fields = {"1a": D("100.00"), "1b": D("100.01")}
    assert [f.code for f in check_form_rules(fields, "1099-DIV", cfg)] == ["FORM_RULE_VIOLATION"]
    assert check_form_rules({"1a": D("100.00"), "1b": D("100.00")}, "1099-DIV", cfg) == []
    assert check_form_rules(fields, "W-2c", cfg) == []  # W-2c has no rules
    custom = copy.deepcopy(cfg)
    custom["forms"]["1099-DIV"]["rules"] = [{"id": "X", "type": "gte", "left": "1a", "right": "2a", "message": "1a must be at least 2a."}]
    fs = check_form_rules({"1a": D("1"), "2a": D("2")}, "1099-DIV", custom)
    assert [(f.code, f.message) for f in fs] == [("FORM_RULE_VIOLATION", "1a must be at least 2a.")]


def test_specialist_marker_comes_from_config(cfg):
    custom = copy.deepcopy(cfg)
    del custom["forms"]["W-2c"]["fields"]["2"]["on_change"]
    assert check_supported_fields(accepted("W-2"), case("T6"), custom) == []
    custom["forms"]["W-2c"]["fields"]["1"]["on_change"] = "SPECIALIST_REVIEW"
    assert [f.code for f in check_supported_fields(accepted("W-2"), case("T4"), custom)] == ["SPECIALIST_FIELD_CHANGE"]


def test_supported_flag_comes_from_config(cfg):
    custom = copy.deepcopy(cfg)
    custom["forms"]["1099-DIV"]["fields"]["7"] = {"label": "Foreign tax paid", "supported": True}
    r = validate(accepted("1099-DIV"), case("T15"), custom)
    assert r.findings == []
    assert r.changes == [FieldChange(form_type="1099-DIV", field="7", old=D("0.00"), new=D("45.00"), delta=D("45.00"))]


def test_diff_fields_ignores_unsupported(cfg):
    assert diff_fields(accepted("1099-DIV"), case("T15"), cfg) == []


# --- purity / determinism -----------------------------------------------------


@pytest.mark.parametrize("cid", ["T1", "T5", "T9", "T10", "T15"])
def test_validate_does_not_modify_inputs(cid, cfg):
    c = case(cid)
    a = accepted("W-2" if c.form_type == "W-2c" else "1099-DIV")
    before = (copy.deepcopy(a.model_dump()), copy.deepcopy(c.model_dump()), copy.deepcopy(cfg))
    validate(a, c, cfg)
    assert (a.model_dump(), c.model_dump(), cfg) == before


@pytest.mark.parametrize("cid", ["T1", "T4", "T5", "T8", "T10", "T11", "T15"])
def test_validate_is_deterministic(cid, cfg):
    assert run(cid, cfg).model_dump() == run(cid, cfg).model_dump()


# --- Session 3, Step 0: completeness gaps (in-memory variants; fixture files untouched) ---------


def test_w2c_changed_box_without_previously_reported_is_missing_prior_value(cfg):
    t4 = case("T4")
    variant = t4.model_copy(update={"fields": {"1": t4.fields["1"].model_copy(update={"previously_reported": None})}})
    r = validate(accepted("W-2"), variant, cfg)
    missing = [f for f in r.findings if f.code == "MISSING_PRIOR_VALUE"]
    assert len(missing) == 1
    assert missing[0].category == "SPECIALIST"
    assert missing[0].field == "W-2c:1"
    assert "box 1" in missing[0].message


def test_w2c_unchanged_box_without_previously_reported_is_fine(cfg):
    t4 = case("T4")
    same = t4.fields["1"].model_copy(update={"value": "82000.00", "previously_reported": None})
    r = validate(accepted("W-2"), t4.model_copy(update={"fields": {"1": same}}), cfg)
    assert "MISSING_PRIOR_VALUE" not in r.codes()


def test_reissued_1099div_leaving_out_a_box_is_missing_field(cfg):
    t1 = case("T1")
    fields = {k: v for k, v in t1.fields.items() if k != "2a"}
    r = validate(accepted("1099-DIV"), t1.model_copy(update={"fields": fields}), cfg)
    missing = [f for f in r.findings if f.code == "MISSING_FIELD"]
    assert len(missing) == 1
    assert missing[0].category == "SPECIALIST"
    assert missing[0].field == "1099-DIV:2a"
    assert "box 2a" in missing[0].message and "500.00" in missing[0].message


@pytest.mark.parametrize("cid", ["T1", "T2", "T3", "T4", "T5", "T6", "T8", "T9", "T10", "T11", "T14", "T15"])
def test_completeness_checks_do_not_fire_on_existing_fixtures(cid, cfg):
    assert not {"MISSING_PRIOR_VALUE", "MISSING_FIELD"} & set(run(cid, cfg).codes())
