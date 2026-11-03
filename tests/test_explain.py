"""Session 4: explain.py. Reviewer notes may only use numbers from the checked Decision."""

from __future__ import annotations

from decimal import Decimal

import pytest

from cli import CASES, load_config_default, load_fixture, run_case
from returnguard.explain import LLMNote, allowed_numbers, grounded_note, load_cached_note, numbers_in, template_note
from returnguard.models import DecisionStatus as S


@pytest.fixture(scope="module")
def cfg():
    return load_config_default()


def decision(cid, cfg):
    ((_, d),) = run_case(load_fixture(CASES / f"{cid}.json"), cfg)
    return d


# --- number extraction ------------------------------------------------------------------------


def test_numbers_normalised_dollar_commas_signs():
    got = {w: d for w, d in numbers_in("fell by $1,600.00, -$800.00, +500, 3200 and 0.5")}
    assert got["$1,600.00"] == Decimal("1600.00")
    assert got["-$800.00"] == Decimal("-800.00")
    assert got["+500"] == Decimal("500")
    assert got["3200"] == Decimal("3200") and got["0.5"] == Decimal("0.5")


def test_ids_are_not_misread_as_negatives():
    vals = [d for _, d in numbers_in("C-001 SYN-1099DIV-C001-2025-T13 line 3a box 1b")]
    assert Decimal("-1") not in vals and Decimal("-2025") not in vals
    assert {Decimal("1"), Decimal("1099"), Decimal("2025"), Decimal("13"), Decimal("3")} <= set(vals)


def test_allowed_numbers_T1(cfg):
    allowed = allowed_numbers(decision("T1", cfg))
    for n in ["2400.00", "1600.00", "-800.00", "800.00", "3200.00", "500.00", "0.00", "1040", "3", "1", "2025", "1099"]:
        assert Decimal(n) in allowed, n
    assert Decimal("900.00") not in allowed


# --- T13: ungrounded LLM note -----------------------------------------------------------------


def test_T13_status_unchanged_note_rejected_template_used(cfg):
    d = decision("T13", cfg)
    assert d.status == S.APPLY_AND_REREVIEW  # the note never changes the status
    llm = load_cached_note("T13")
    assert llm is not None and llm.mode_label == "MOCKED" and "900.00" in llm.text
    n = grounded_note(d, llm)
    assert n.source == "TEMPLATE" and n.llm_rejected
    assert "900.00" in n.rejected_numbers
    assert n.text == template_note(d) and "900" not in n.text
    assert n.llm_text == llm.text  # draft kept for the audit trail
    assert decision("T13", cfg).status == d.status


# --- grounded notes accepted ------------------------------------------------------------------


def test_grounded_llm_note_accepted(cfg):
    d = decision("T1", cfg)
    text = ("Corrected 1099-DIV SYN-1099DIV-C001-2025-T1 (tax year 2025): qualified dividends in box 1b went "
            "from $2,400.00 to $1,600.00, a change of -$800.00 ($800.00 lower). Box 1a is unchanged at $3,200.00. "
            "Please re-review APR-1040-L3A (Form 1040 line 3a) and APR-QDCG-WS.")
    n = grounded_note(d, LLMNote(text=text, mode_label="MOCKED"))
    assert n.source == "LLM (MOCKED)" and n.rejected_numbers == [] and n.text == text


def test_live_label_carried(cfg):
    n = grounded_note(decision("T1", cfg), LLMNote(text="Box 1b changed by -800.00.", mode_label="LIVE"))
    assert n.source == "LLM (LIVE)"


def test_plain_string_note_defaults_to_mocked(cfg):
    assert grounded_note(decision("T1", cfg), "Box 1b: 2,400.00 -> 1,600.00.").source == "LLM (MOCKED)"


@pytest.mark.parametrize("bad", ["Qualified dividends fell by $799.99.", "Total income changed by 1,600.01.",
                                 "Line 3a rose by $8,000.00.", "Withholding is now 12.00."])
def test_any_unknown_number_rejects(bad, cfg):
    n = grounded_note(decision("T1", cfg), bad)
    assert n.source == "TEMPLATE" and n.rejected_numbers


# --- template ---------------------------------------------------------------------------------


def test_no_llm_note_uses_template(cfg):
    n = grounded_note(decision("T1", cfg))
    assert n.source == "TEMPLATE" and n.rejected_numbers == [] and n.llm_text is None


@pytest.mark.parametrize("cid", ["T1", "T3", "T4", "T5", "T6", "T9", "T10", "T14", "T15"])
def test_template_is_self_grounded(cid, cfg):
    """The template only uses Decision fields, so it always passes its own grounding check."""
    d = decision(cid, cfg)
    t = template_note(d)
    assert d.status.value in t and "No approval has been granted or cleared automatically." in t
    assert grounded_note(d, t).source == "LLM (MOCKED)"


def test_template_T1_content(cfg):
    t = template_note(decision("T1", cfg))
    assert "2400.00 -> 1600.00" in t and "-800.00" in t and "APR-1040-L3A" in t and "APR-QDCG-WS" in t


def test_template_T5_says_nothing_changed(cfg):
    t = template_note(decision("T5", cfg))
    assert "81000.00" in t and "82000.00" in t and "No approval was marked stale." in t


# --- Final polish: money-formatted numbers must be real amounts or deltas -------------------------------------


@pytest.mark.parametrize("bad", ["Qualified dividends fell by $3.00.",          # 3 is only "line 3a"
                                 "Qualified dividends fell by $2,025.00.",      # 2025 is only the tax year
                                 "4 approvals are stale and $4.00 moved.",      # 4 is only box 4
                                 "Box 1b changed by 1,040.00."])               # 1040 is only "Form 1040"
def test_ids_cannot_pass_as_money(bad, cfg):
    r = grounded_note(decision("T1", cfg), bad)
    assert r.source == "TEMPLATE" and r.llm_rejected


def test_T13_note_still_rejected(cfg):
    d = decision("T13", cfg)
    r = grounded_note(d, load_cached_note("T13"))
    assert r.source == "TEMPLATE" and r.rejected_numbers == ["900.00"]


@pytest.mark.parametrize("good", [
    "Corrected 1099-DIV SYN-1099DIV-C001-2025-T1 for tax year 2025: qualified dividends (box 1b) fell by $800.00, "
    "from $2,400.00 to $1,600.00. Approvals APR-1040-L3A (Form 1040 line 3a) and APR-QDCG-WS need re-review.",
    "Box 1b changed by -$800.00 (2,400.00 -> 1,600.00); box 1a stays $3,200.00.",
])
def test_correct_note_still_accepted(good, cfg):
    r = grounded_note(decision("T1", cfg), good)
    assert r.source == "LLM (MOCKED)" and r.rejected_numbers == []
