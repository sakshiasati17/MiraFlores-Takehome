"""Session 3: decide.py. Real fixtures from data/synthetic/cases/; in-memory variants only (no fixture edits)."""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

import pytest

from cli import CASES, LLM_CASES, load_accepted, load_config_default, load_fixture, load_return_state, run_case
from returnguard.decide import NEXT_ACTION, ProcessingState, decide, naive_total_changed, signed
from returnguard.models import DecisionStatus as S
from returnguard.models import ReturnStatus

ALL_CASES = sorted((p.stem for p in CASES.glob("T*.json")), key=lambda s: int(s[1:]))
RUNNABLE = [c for c in ALL_CASES if c not in LLM_CASES]
BLOCKING = {S.REJECTED_INVALID_INPUT, S.SPECIALIST_REVIEW, S.CONFLICT, S.DUPLICATE_NO_CHANGE}


@pytest.fixture(scope="module")
def cfg() -> dict:
    return load_config_default()


def fx(cid):
    return load_fixture(CASES / f"{cid}.json")


def decisions(cid, cfg):
    return [d for _, d in run_case(fx(cid), cfg)]


def one(cid, cfg):
    (d,) = decisions(cid, cfg)
    return d


def rs(status=ReturnStatus.APPROVED):
    return load_return_state().model_copy(update={"status": status})


def variants():
    """In-memory variants (name, accepted, correction, return_state)."""
    acc = load_accepted()
    t5 = fx("T5").submissions[0]
    t4 = fx("T4").submissions[0]
    t1 = fx("T1").submissions[0]
    return [
        ("T5+TIN mismatch", acc["W-2"], t5.model_copy(update={"payer_tin": "00-0000099"}), rs()),
        ("T4 no prior", acc["W-2"],
         t4.model_copy(update={"fields": {"1": t4.fields["1"].model_copy(update={"previously_reported": None})}}), rs()),
        ("T1 missing 2a", acc["1099-DIV"],
         t1.model_copy(update={"fields": {k: v for k, v in t1.fields.items() if k != "2a"}}), rs()),
        ("T4 filed", acc["W-2"], t4, rs(ReturnStatus.FILED)),
    ]


# --- every fixture gets its expected status ---------------------------------------------------


@pytest.mark.parametrize("cid", RUNNABLE)
def test_status_matches_fixture_expected(cid, cfg):
    f = fx(cid)
    expected = f.expected.status_sequence or [f.expected.status]
    assert [d.status for d in decisions(cid, cfg)] == expected


def test_T7_sequence(cfg):
    assert [d.status for d in decisions("T7", cfg)] == [S.APPLY_AND_REREVIEW, S.DUPLICATE_NO_CHANGE]


@pytest.mark.parametrize("cid", RUNNABLE)
def test_exactly_one_status_and_matching_next_action(cid, cfg):
    for d in decisions(cid, cfg):
        assert d.next_action == NEXT_ACTION[d.status]


# --- deltas and stale approvals ----------------------------------------------------------------


@pytest.mark.parametrize("cid", ["T1", "T2", "T4"])
def test_deltas_and_stale_equal_fixture(cid, cfg):
    d = one(cid, cfg)
    f = fx(cid)
    # Fixture deltas are signed only when negative ("4500.00", "-800.00"): compare as Decimals.
    assert {f"{c.form_type}:{c.field}": c.delta for c in d.proposed_changes} == {
        k: Decimal(v) for k, v in f.expected.deltas.items()}
    assert [s.approval_id for s in d.stale_approvals] == f.expected.stale_approvals
    assert all(c.applied and c.applied_as_new_version for c in d.proposed_changes)
    assert d.new_version is not None


def test_T1_stale_paths_and_unverified_flags(cfg):
    d = one("T1", cfg)
    by = {s.approval_id: s for s in d.stale_approvals}
    assert by["APR-1040-L3A"].paths == ["1099-DIV:1b -> Form 1040 line 3a -> APR-1040-L3A"]
    assert by["APR-1040-L3A"].unverified is False
    assert by["APR-QDCG-WS"].unverified is True
    assert by["APR-QDCG-WS"].sources[0].startswith("UNVERIFIED: ")
    assert all(s.fingerprint_before and s.fingerprint_after and s.fingerprint_before != s.fingerprint_after
               for s in d.stale_approvals)


def test_T3_possible_amendment_nothing_applied(cfg):
    d = one("T3", cfg)
    assert d.status == S.POSSIBLE_AMENDMENT
    assert [s.approval_id for s in d.stale_approvals] == ["APR-1040-L3A", "APR-QDCG-WS"]
    assert d.proposed_changes and all(not c.applied for c in d.proposed_changes)
    assert all(c.applied_as_new_version for c in d.proposed_changes)
    assert "amended return" in d.next_action and "Nothing has been changed automatically" in d.next_action
    assert any("FILED" in r for r in d.reasons)


def test_T5_conflict_nothing_changed(cfg):
    d = one("T5", cfg)
    assert d.status == S.CONFLICT
    assert d.proposed_changes and all(not c.applied and not c.applied_as_new_version for c in d.proposed_changes)
    assert d.stale_approvals == []
    assert d.new_version is None
    text = " ".join(d.reasons)
    assert "Nothing changed" in text
    assert "81000.00" in text and "82000.00" in text
    assert "SYN-W2C-C001-2025-T5" in text and "SYN-W2-C001-2025-v1" in text
    assert d.evidence.accepted_doc_id == "SYN-W2-C001-2025-v1"
    assert d.evidence.correction_doc_id == "SYN-W2C-C001-2025-T5"


@pytest.mark.parametrize("cid", ["T5", "T6", "T8", "T9", "T10", "T11", "T14", "T15"])
def test_blocking_statuses_have_no_stale_and_say_nothing_changed(cid, cfg):
    d = one(cid, cfg)
    assert d.status in BLOCKING
    assert d.stale_approvals == [] and d.new_version is None
    assert all(not c.applied and not c.applied_as_new_version for c in d.proposed_changes)
    assert any("Nothing changed" in r for r in d.reasons)


def test_T10_reason_names_field_and_bad_value(cfg):
    assert any("W-2c:1" in r and "86,5OO" in r for r in one("T10", cfg).reasons)


def test_specialist_beats_conflict(cfg):
    name, acc, corr, state = variants()[0]
    d = decide(acc, corr, state, cfg)
    cats = {f.category for f in d.evidence.findings}
    assert {"SPECIALIST", "CONFLICT"} <= cats
    assert d.status == S.SPECIALIST_REVIEW


@pytest.mark.parametrize("idx,expected", [(1, S.SPECIALIST_REVIEW), (2, S.SPECIALIST_REVIEW), (3, S.POSSIBLE_AMENDMENT)])
def test_in_memory_variants(idx, expected, cfg):
    _, acc, corr, state = variants()[idx]
    assert decide(acc, corr, state, cfg).status == expected


# --- safety invariant --------------------------------------------------------------------------


def test_safety_invariant_nothing_approved_or_cleared(cfg):
    all_decisions = [d for cid in RUNNABLE for d in decisions(cid, cfg)]
    all_decisions += [decide(a, c, s, cfg) for _, a, c, s in variants()]
    baseline = load_return_state()
    for d in all_decisions:
        assert d.clears_approvals is False
        dumped = d.model_dump(mode="json")
        assert dumped["clears_approvals"] is False
        # The Decision has no field that grants or clears an approval.
        assert not {"approved", "cleared", "approvals_cleared", "approved_by"} & set(dumped)
        for s in dumped["stale_approvals"]:
            assert not {"approved", "cleared", "approved_by", "approved_at"} & set(s)
    # The return state's approvals are untouched (still the CPA's, nothing new granted).
    assert load_return_state() == baseline


def test_clears_approvals_cannot_be_set_true(cfg):
    d = one("T1", cfg)
    with pytest.raises(Exception):
        type(d).model_validate({**d.model_dump(), "clears_approvals": True})


# --- duplicates --------------------------------------------------------------------------------


def test_same_state_twice_gives_duplicate(cfg):
    acc = load_accepted()["1099-DIV"]
    sub = fx("T7").submissions[0]
    state = ProcessingState()
    first = decide(acc, sub, rs(), cfg, state)
    second = decide(acc, sub, rs(), cfg, state)
    assert (first.status, second.status) == (S.APPLY_AND_REREVIEW, S.DUPLICATE_NO_CHANGE)
    assert first.correction_fingerprint == second.correction_fingerprint
    assert second.stale_approvals == [] and second.new_version is None
    assert any("already processed" in r for r in second.reasons)
    assert len(state.versions) == 1  # delta applied once


def test_fresh_state_per_fixture_T1_and_T13_not_duplicates(cfg):
    # T1 and T13 carry identical values; separate fixtures never share a state.
    assert one("T1", cfg).status == S.APPLY_AND_REREVIEW
    t13 = fx("T13")
    acc = load_accepted()["1099-DIV"]
    assert decide(acc, t13.submissions[0], rs(), cfg, ProcessingState()).status == S.APPLY_AND_REREVIEW


# --- naive baseline ----------------------------------------------------------------------------


def test_naive_check_misses_T1(cfg):
    acc = load_accepted()["1099-DIV"]
    sub = fx("T1").submissions[0]
    assert naive_total_changed(acc, sub) is False
    assert decide(acc, sub, rs(), cfg).status == S.APPLY_AND_REREVIEW


# --- determinism and untouched inputs ----------------------------------------------------------


@pytest.mark.parametrize("cid", RUNNABLE)
def test_deterministic(cid, cfg):
    a = [d.model_dump(mode="json") for d in decisions(cid, cfg)]
    b = [d.model_dump(mode="json") for d in decisions(cid, cfg)]
    assert a == b


@pytest.mark.parametrize("cid", RUNNABLE)
def test_inputs_not_modified(cid, cfg):
    acc_all = load_accepted()
    state = rs()
    f = fx(cid)
    before = (copy.deepcopy(acc_all), copy.deepcopy(f), copy.deepcopy(state))
    ps = ProcessingState()
    for sub in f.submissions:
        target = "W-2" if sub.form_type == "W-2c" else sub.form_type
        decide(acc_all[target], sub, state, cfg, ps)
    assert (acc_all, f, state) == before
