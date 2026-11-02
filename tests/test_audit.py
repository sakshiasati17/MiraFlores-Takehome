"""Session 3: audit.py (fingerprints, staleness, new version records, append-only log)."""

from __future__ import annotations

import copy
import json

import pytest

from cli import CASES, load_accepted, load_config_default, load_fixture, load_return_state, run_case
from returnguard.audit import (
    AuditLog,
    correction_fingerprint,
    fingerprint,
    is_stale,
    log_record,
    new_version,
    with_baseline_fingerprints,
)
from returnguard.impact import find_impact, stale_approval_ids
from returnguard.validate import validate


@pytest.fixture(scope="module")
def cfg() -> dict:
    return load_config_default()


def sub(cid, i=0):
    return load_fixture(CASES / f"{cid}.json").submissions[i]


def acc_for(c):
    return load_accepted()["W-2" if c.form_type == "W-2c" else c.form_type]


# --- fingerprint -------------------------------------------------------------------------------


def test_fingerprint_is_sha256_hex_and_stable():
    a = load_accepted()["1099-DIV"]
    fp = fingerprint(a, ["1099-DIV:1b"])
    assert len(fp) == 64 and int(fp, 16) >= 0
    assert fp == fingerprint(a, ["1099-DIV:1b"])
    assert fp == fingerprint(a, ["1b"])  # "FORM:box" and bare box are the same field


def test_fingerprint_order_independent_and_field_sensitive():
    a = load_accepted()["1099-DIV"]
    assert fingerprint(a, ["1b", "2a"]) == fingerprint(a, ["2a", "1b"])
    assert fingerprint(a, ["1b"]) != fingerprint(a, ["2a"])


def test_fingerprint_depends_on_identity_not_doc_id():
    a = load_accepted()["1099-DIV"]
    assert fingerprint(a.model_copy(update={"doc_id": "X", "version": 9}), ["1b"]) == fingerprint(a, ["1b"])
    assert fingerprint(a.model_copy(update={"payer_tin": "00-0000009"}), ["1b"]) != fingerprint(a, ["1b"])
    assert fingerprint(a.model_copy(update={"tax_year": 2024}), ["1b"]) != fingerprint(a, ["1b"])


def test_correction_fingerprint_normalises_amounts_and_keeps_raw_bad_ones():
    c = sub("T1")
    commas = c.model_copy(update={"fields": {**c.fields, "1a": c.fields["1a"].model_copy(update={"value": "$3,200.00"})}})
    assert correction_fingerprint(c) == correction_fingerprint(commas)
    t10 = sub("T10")
    assert len(correction_fingerprint(t10)) == 64
    assert correction_fingerprint(t10) != correction_fingerprint(sub("T4"))


def test_T7_both_submissions_same_fingerprint():
    assert correction_fingerprint(sub("T7", 0)) == correction_fingerprint(sub("T7", 1))


# --- baseline approvals ------------------------------------------------------------------------


def test_baseline_fingerprints_computed_without_editing_fixture():
    raw_before = (CASES.parent / "return_state_C-001_2025.json").read_text()
    rs = load_return_state()
    assert all(a.evidence_fingerprint is None for a in rs.approvals)
    acc = load_accepted()
    rs2 = with_baseline_fingerprints(rs, acc.values())
    assert all(a.evidence_fingerprint for a in rs2.approvals)
    assert all(a.evidence_fingerprint is None for a in rs.approvals)  # original object untouched
    by = {a.id: a for a in rs2.approvals}
    assert by["APR-QDCG-WS"].evidence_fingerprint == fingerprint(acc["1099-DIV"], ["1099-DIV:1b", "1099-DIV:2a"])
    assert by["APR-1040-L1A"].evidence_fingerprint == fingerprint(acc["W-2"], ["W-2:1"])
    assert (CASES.parent / "return_state_C-001_2025.json").read_text() == raw_before


# --- is_stale cross-check with impact.py -------------------------------------------------------


@pytest.mark.parametrize("cid", ["T1", "T2", "T3", "T4"])
def test_fingerprint_staleness_equals_impact(cid, cfg):
    c = sub(cid)
    a = acc_for(c)
    rs = with_baseline_fingerprints(load_return_state(), load_accepted().values())
    by_fp = {ap.id for ap in rs.approvals if is_stale(ap, a, c, cfg)}
    by_impact = set(stale_approval_ids(find_impact(validate(a, c, cfg).changes, cfg)))
    assert by_fp == by_impact
    assert by_fp == set(load_fixture(CASES / f"{cid}.json").expected.stale_approvals)


def test_is_stale_false_for_approval_on_other_form(cfg):
    rs = load_return_state()
    wage = next(a for a in rs.approvals if a.id == "APR-1040-L1A")
    assert is_stale(wage, load_accepted()["1099-DIV"], sub("T1"), cfg) is False


# --- new version record ------------------------------------------------------------------------


def test_new_version_is_a_new_record_and_accepted_untouched(cfg):
    a = load_accepted()["1099-DIV"]
    before = copy.deepcopy(a)
    v = new_version(a, sub("T1"), cfg)
    assert a == before
    assert v.version == a.version + 1 and v.doc_id == "SYN-1099DIV-C001-2025-T1"
    assert str(v.fields["1b"].amount) == "1600.00" and str(a.fields["1b"].amount) == "2400.00"
    assert v.synthetic is True and "SYNTHETIC" in v.label


def test_new_version_for_w2c_keeps_w2_form(cfg):
    v = new_version(load_accepted()["W-2"], sub("T4"), cfg)
    assert v.form_type == "W-2" and str(v.fields["1"].amount) == "86500.00"


# --- append-only log ---------------------------------------------------------------------------


def test_log_appends_one_line_per_decision_and_never_rewrites(tmp_path, cfg):
    log = AuditLog(tmp_path / "out" / "audit_log.jsonl")
    run_case(load_fixture(CASES / "T1.json"), cfg, log)
    first = log.path.read_text()
    assert len(first.splitlines()) == 1
    run_case(load_fixture(CASES / "T5.json"), cfg, log)
    text = log.path.read_text()
    assert text.startswith(first)  # earlier line kept byte for byte
    rows = log.read()
    assert [r["status"] for r in rows] == ["APPLY_AND_REREVIEW", "CONFLICT"]
    assert rows[0]["stale_approval_ids"] == ["APR-1040-L3A", "APR-QDCG-WS"]
    assert rows[1]["stale_approval_ids"] == [] and rows[1]["applied_changes"] == []
    for r in rows:
        assert {"timestamp", "case_id", "accepted_doc_id", "correction_doc_id", "correction_fingerprint",
                "status", "stale_approval_ids"} <= set(r)
        assert r["clears_approvals"] is False


def test_log_has_no_rewrite_or_delete_api():
    public = {n for n in dir(AuditLog) if not n.startswith("_")}
    assert public == {"append", "read"}


def test_T7_duplicate_logged_without_second_applied_change(tmp_path, cfg):
    log = AuditLog(tmp_path / "audit.jsonl")
    run_case(load_fixture(CASES / "T7.json"), cfg, log)
    rows = log.read()
    assert [r["status"] for r in rows] == ["APPLY_AND_REREVIEW", "DUPLICATE_NO_CHANGE"]
    assert rows[0]["correction_fingerprint"] == rows[1]["correction_fingerprint"]
    assert rows[0]["applied_changes"] == ["1099-DIV:1b 2400.00 -> 1600.00"]
    assert rows[1]["applied_changes"] == [] and rows[1]["new_version_doc_id"] is None
    assert sum(len(r["applied_changes"]) for r in rows) == 1


def test_log_record_is_json_serialisable(cfg):
    (_, d), = run_case(load_fixture(CASES / "T4.json"), cfg)
    json.dumps(log_record("T4", d, timestamp="2026-01-01T00:00:00+00:00"))
