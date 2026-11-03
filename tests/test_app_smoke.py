"""Smoke tests for the Streamlit UI (app.py). No API key, no network.

Drives the real page with streamlit.testing.v1.AppTest (select a case in the sidebar, re-run, read what is
rendered), and also checks two render helpers directly. The UI only displays results from cli.py's functions.
"""

from __future__ import annotations

import os

import pytest

from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.delenv("RETURNGUARD_LLM", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def page_text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [c.value for c in at.code]
    return "\n".join(str(p) for p in parts)


def run_case(case_id: str, use_live: bool = True) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    at.sidebar.selectbox(key="case").select(case_id)
    at.sidebar.toggle(key="use_live").set_value(use_live)
    at.run()
    assert not at.exception, [x.value for x in at.exception]
    return at


def test_t1_headline():
    at = run_case("T1")
    txt = page_text(at)
    assert "APPLY_AND_REREVIEW" in txt
    assert "-800.00" in txt
    assert "APR-1040-L3A" in txt and "APR-QDCG-WS" in txt
    assert "Naive check: did total income change?" in txt and "→ No" in txt
    assert "LIVE · claude-haiku-5-5" in txt  # toggle ON replays the recorded live output
    assert "Nothing is ever approved automatically." in txt


def test_t1_toggle_off_uses_mocked_with_same_status():
    txt = page_text(run_case("T1", use_live=False))
    assert "MOCKED · hand-written stand-in" in txt
    assert "APPLY_AND_REREVIEW" in txt and "-800.00" in txt


def test_t12_misread_caught():
    txt = page_text(run_case("T12"))
    assert "SPECIALIST_REVIEW" in txt
    assert "UNVERIFIED" in txt
    assert "1060.00" in txt
    assert "AI read 1,060.00 — form says 1,600.00" in txt
    assert "(unverified extracted value)" in txt
    assert "MOCKED · hand-written stand-in" in txt  # T12 has no live output, even with the toggle ON


def test_t5_conflict():
    txt = page_text(run_case("T5"))
    assert "CONFLICT" in txt
    assert "None. Nothing was applied." in txt
    assert "proposed, not applied" in txt


def test_json_case_has_no_ai_step():
    txt = page_text(run_case("T3"))
    assert "POSSIBLE_AMENDMENT" in txt
    assert "Structured input (no AI step)" in txt


def test_t13_shows_rejected_note_numbers():
    txt = page_text(run_case("T13"))
    assert "LLM note REJECTED" in txt and "900.00" in txt and "TEMPLATE" in txt


def test_all_cases_tab_15_of_15():
    at = run_case("T1")
    txt = page_text(at)
    assert "15 of 15 match expected" in txt
    assert txt.count("✓ match") == 15


def test_every_case_renders_its_expected_status():
    import json
    import re
    from pathlib import Path

    cases = Path(APP).parent / "data" / "synthetic" / "cases"
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert len(at.sidebar.selectbox(key="case").options) == 15
    for path in sorted(cases.glob("T*.json")):
        fx = json.loads(path.read_text())
        at.sidebar.selectbox(key="case").select(fx["case_id"])
        at.run()
        assert not at.exception, (fx["case_id"], [x.value for x in at.exception])
        banner = re.search(r'rg-status-label" style="color:#\w+;">(\w+)<', page_text(at)).group(1)
        assert banner == fx["expected"]["status"], fx["case_id"]


def test_app_never_calls_the_api_even_in_live_mode(monkeypatch):
    """Even with RETURNGUARD_LLM=live and a key in the environment, the app must never call the API: live mode needs an
    explicit mode="live" (CLI --live), which the app never passes. The live call is patched to blow up."""
    import returnguard.extract as extract_mod

    def _boom(*_a, **_k):
        raise AssertionError("the UI must never call the live API")

    monkeypatch.setenv("RETURNGUARD_LLM", "live")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key-for-test")
    monkeypatch.setattr(extract_mod, "_call_live", _boom)
    assert extract_mod.has_api_key()  # a key really is set
    for use_live in (True, False):
        txt = page_text(run_case("T1", use_live=use_live))
        assert "APPLY_AND_REREVIEW" in txt and "-800.00" in txt
        assert ("LIVE · claude-haiku-5-5" if use_live else "MOCKED · hand-written stand-in") in txt
        assert "replayed, no API call this run" in txt or not use_live
    txt = page_text(run_case("T12"))
    assert "SPECIALIST_REVIEW" in txt and "1060.00" in txt


def test_fixture_descriptions_have_no_placeholder():
    txt = page_text(run_case("T12"))
    assert "AI misread: extraction says 1b 1060.00, form text says 1600.00" in txt
    assert "PLACEHOLDER" not in txt
    assert "Re-review the approvals listed in this report" in page_text(run_case("T1"))
