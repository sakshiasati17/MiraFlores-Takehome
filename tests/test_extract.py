"""Session 4: extract.py. Cached (MOCKED) extraction only: no network, no API key, live code never called."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

import pytest

import returnguard.extract as X
from cli import CASES, RAW, envelope_from, load_accepted, load_config_default, load_fixture, load_return_state, run_case
from returnguard.decide import ProcessingState, decide
from returnguard.models import DecisionStatus as S

ALL_CASES = sorted((p.stem for p in CASES.glob("T*.json")), key=lambda s: int(s[1:]))
TEXT_CASES = ["T1", "T4", "T5", "T12"]
REAL_CALL_LIVE = X._call_live  # kept before the autouse fixture replaces it; only ever used with a fake SDK


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    """No network: live mode is off and the live function raises if anything ever reaches it."""
    monkeypatch.delenv("RETURNGUARD_LLM", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def boom(*a, **k):
        raise AssertionError("live LLM call attempted in a test")

    monkeypatch.setattr(X, "_call_live", boom)


@pytest.fixture(scope="module")
def cfg():
    return load_config_default()


def text(cid):
    return (RAW / f"{cid}.txt").read_text()


def from_text(cid, cfg, envelope=True):
    fx = load_fixture(CASES / f"{cid}.json")
    rs = load_return_state().model_copy(update={"status": fx.return_status})
    return X.run_from_text(text(cid), cid, load_accepted(), rs, cfg, ProcessingState(),
                           envelope=envelope_from(fx) if envelope else None)


# --- raw text + cache files -------------------------------------------------------------------


@pytest.mark.parametrize("cid", TEXT_CASES)
def test_raw_text_is_labelled_synthetic(cid):
    assert text(cid).startswith("SYNTHETIC - NOT A REAL TAX DOCUMENT")


@pytest.mark.parametrize("cid", TEXT_CASES + ["T13_note"])
def test_cache_files_labelled_mocked(cid):
    rec = json.loads((X.CACHE_DIR / f"{cid}.json").read_text())
    assert rec["mocked"] is True and "live" not in rec
    assert rec["_label"] == "MOCKED: hand-written stand-in for an LLM output, not a real model call"
    assert rec["source"] == "hand-written"
    assert rec["model"] is None  # no model produced these files
    assert rec["prompt_version"]
    assert "recorded" not in json.dumps(rec).lower()  # only real live outputs may say "recorded"


def test_T12_cache_says_misread_is_deliberate():
    rec = json.loads((X.CACHE_DIR / "T12.json").read_text())
    assert rec["note"] == "deliberate misread injected for testing"


@pytest.mark.parametrize("cid", TEXT_CASES)
def test_cache_matches_fixed_schema_and_has_no_decision(cid):
    rec = json.loads((X.CACHE_DIR / f"{cid}.json").read_text())
    X.check_schema(rec["extraction"])
    flat = json.dumps(rec["extraction"]).lower()
    assert "status" not in flat and "decision" not in flat and "advice" not in flat


def test_schema_has_no_status_decision_or_advice():
    assert set(X.EXTRACTION_SCHEMA["properties"]) == {"form_type", "corrected", "payer_or_employer_tin", "tax_year", "fields"}
    assert X.EXTRACTION_SCHEMA["additionalProperties"] is False


def test_schema_rejects_extra_keys():
    rec = json.loads((X.CACHE_DIR / "T1.json").read_text())["extraction"]
    with pytest.raises(X.ExtractionError):
        X.check_schema({**rec, "status": "APPLY_AND_REREVIEW"})
    with pytest.raises(X.ExtractionError):
        X.check_schema({**rec, "fields": {"1b": {"value": "1,600.00", "advice": "apply"}}})


def test_raw_text_values_match_fixtures():
    """Text amounts (commas stripped) equal the existing fixture values exactly."""
    for cid in ["T1", "T12"]:
        sub = load_fixture(CASES / f"{cid}.json").submissions[0]
        expected = (load_fixture(CASES / "T1.json").submissions[0] if cid == "T12" else sub).fields
        for box, f in expected.items():
            line = X._box_lines(text(cid), box, X.box_label(load_config_default(), "1099-DIV", box))
            assert len(line) == 1 and X._amounts(line[0]) == [Decimal(f.value)]
    for cid in ["T4", "T5"]:
        f = load_fixture(CASES / f"{cid}.json").submissions[0].fields["1"]
        (line,) = X._box_lines(text(cid), "1", "Wages, tips, other compensation")
        assert X._amounts(X._segment(line, "previously_reported")) == [Decimal(f.previously_reported)]
        assert X._amounts(X._segment(line, "value")) == [Decimal(f.value)]


# --- extract() modes ----------------------------------------------------------------------------


def test_default_mode_is_cached_and_mocked():
    ex = X.extract(text("T1"), "T1")
    assert ex.mode_label == "MOCKED" and ex.fields["1b"]["value"] == "1,600.00"
    assert ex.source == "hand-written" and ex.model == "" and not ex.replayed_live


def test_missing_cache_is_a_clear_error_not_a_guess():
    with pytest.raises(X.ExtractionError, match="no cached extraction"):
        X.extract(text("T1"), "T999")


def test_live_mode_refused_without_key(monkeypatch):
    with pytest.raises(X.ExtractionError, match="ANTHROPIC_API_KEY"):
        X.extract(text("T1"), "T1", mode="live")
    assert X.extract(text("T1"), "T1").mode_label == "MOCKED"


def test_env_alone_never_turns_live_on(monkeypatch):
    """RETURNGUARD_LLM=live plus a key does nothing: only an explicit mode="live" (CLI --live) calls the API."""
    monkeypatch.setenv("RETURNGUARD_LLM", "live")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    ex = X.extract(text("T1"), "T1")  # _call_live is patched to raise (autouse fixture): any call would fail here
    assert ex.mode_label == "MOCKED" and not ex.replayed_live


def test_live_path_saves_labelled_live_record(monkeypatch, tmp_path):
    """The live branch with a stubbed SDK call (no network): result saved as LIVE with model + timestamp."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    stub = json.loads((X.CACHE_DIR / "T1.json").read_text())["extraction"]
    monkeypatch.setattr(X, "_call_live", lambda prompt, model: stub)
    ex = X.extract(text("T1"), "T1", mode="live", cache_dir=tmp_path)
    assert ex.mode_label == "LIVE"
    rec = json.loads((tmp_path / "T1.live.json").read_text())
    assert rec["live"] is True and rec["model"] == "claude-haiku-5-5" and rec["recorded_at"] and "mocked" not in rec
    assert rec["source"] == "live" and rec["_label"].startswith("LIVE:")
    assert not (tmp_path / "T1.json").exists()  # MOCKED recordings are never overwritten


def test_default_live_model_is_haiku_and_overridable(monkeypatch, tmp_path):
    assert X.DEFAULT_LIVE_MODEL == "claude-haiku-5-5"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-real-key")
    monkeypatch.setenv("RETURNGUARD_LLM_MODEL", "claude-sonnet-5-5")
    seen = {}
    stub = json.loads((X.CACHE_DIR / "T1.json").read_text())["extraction"]
    monkeypatch.setattr(X, "_call_live", lambda prompt, model: seen.setdefault("model", model) and stub)
    X.extract(text("T1"), "T1", mode="live", cache_dir=tmp_path)
    assert seen["model"] == "claude-sonnet-5-5"


def test_live_request_leaves_out_params_haiku_rejects(monkeypatch, cfg):
    """Run the real _call_live body against a fake SDK module (no network) and inspect the request."""
    import sys
    import types

    calls = []
    stub = json.loads((X.CACHE_DIR / "T1.json").read_text())["extraction"]

    class FakeMessages:
        def create(self, **kw):
            calls.append(kw)
            block = types.SimpleNamespace(type="text", text=json.dumps(stub))
            return types.SimpleNamespace(stop_reason="end_turn", content=[types.SimpleNamespace(type="thinking"), block])

    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda: types.SimpleNamespace(messages=FakeMessages())
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    out = REAL_CALL_LIVE(X.build_prompt(text("T1"), cfg), "claude-haiku-5-5")  # real request code, fake transport
    assert out == stub
    (kw,) = calls
    assert kw["model"] == "claude-haiku-5-5"
    assert not {"temperature", "top_p", "top_k", "thinking", "tool_choice"} & set(kw)
    assert kw["messages"][-1]["role"] == "user"  # no assistant prefill
    assert kw["output_config"] == {"effort": "low"}


# --- --use-live-cache ---------------------------------------------------------------------------


def test_use_live_cache_replays_live_file(tmp_path):
    stub = json.loads((X.CACHE_DIR / "T1.json").read_text())["extraction"]
    (tmp_path / "T1.json").write_text((X.CACHE_DIR / "T1.json").read_text())
    (tmp_path / "T1.live.json").write_text(json.dumps({"live": True, "_label": "LIVE: test", "source": "live",
                                                        "model": "claude-haiku-5-5", "extraction": stub}))
    ex = X.extract(text("T1"), "T1", cache_dir=tmp_path, use_live_cache=True)
    assert ex.mode_label == "LIVE" and ex.replayed_live and ex.model == "claude-haiku-5-5"
    assert X.extract(text("T1"), "T1", cache_dir=tmp_path).mode_label == "MOCKED"  # flag off: MOCKED file


def test_use_live_cache_falls_back_to_mocked_when_no_live_file(tmp_path):
    (tmp_path / "T1.json").write_text((X.CACHE_DIR / "T1.json").read_text())
    ex = X.extract(text("T1"), "T1", cache_dir=tmp_path, use_live_cache=True)
    assert ex.mode_label == "MOCKED" and not ex.replayed_live


def test_live_file_must_be_labelled_live(tmp_path):
    stub = json.loads((X.CACHE_DIR / "T1.json").read_text())["extraction"]
    (tmp_path / "T1.live.json").write_text(json.dumps({"mocked": True, "extraction": stub}))
    with pytest.raises(X.ExtractionError, match="live"):
        X.extract(text("T1"), "T1", cache_dir=tmp_path, use_live_cache=True)


LIVE_FILES = sorted(X.CACHE_DIR.glob("*.live.json"))


@pytest.mark.skipif(not LIVE_FILES, reason="no data/llm_cache/*.live.json recorded yet (live mode never run)")
@pytest.mark.parametrize("path", LIVE_FILES, ids=[p.name for p in LIVE_FILES])
def test_recorded_live_outputs_verify_against_raw_text(path, cfg):
    """IF a real live output exists, its values must pass the same source check as the MOCKED files."""
    cid = path.name[: -len(".live.json")]
    raw = RAW / f"{cid}.txt"
    if not raw.exists():
        pytest.skip(f"no raw text for {cid}")
    if cid == "T12":
        pytest.skip("T12 exists to test a misread; a correct live read of it is allowed but not required")
    ex = X.extract(raw.read_text(), cid, use_live_cache=True)
    assert ex.mode_label == "LIVE" and ex.replayed_live
    bad = [c for c in X.verify_extraction(ex, raw.read_text(), cfg) if not c.verified]
    assert not bad, bad


def test_requirements_keep_sdk_optional():
    from pathlib import Path

    root = Path(X.ROOT)
    assert "anthropic" not in (root / "requirements.txt").read_text()
    assert "anthropic" in (root / "requirements-llm.txt").read_text()


# --- verification -------------------------------------------------------------------------------


@pytest.mark.parametrize("cid", ["T1", "T4", "T5"])
def test_correct_extractions_fully_verify(cid, cfg):
    checks = X.verify_extraction(X.extract(text(cid), cid), text(cid), cfg)
    assert all(c.verified for c in checks), [c for c in checks if not c.verified]
    assert {"form_type", "corrected", "payer_or_employer_tin", "tax_year"} <= {c.name for c in checks}


def test_w2c_checks_both_previously_reported_and_correct(cfg):
    names = [c.name for c in X.verify_extraction(X.extract(text("T4"), "T4"), text("T4"), cfg)]
    assert "W-2c:1 (previously reported)" in names and "W-2c:1 (correct information)" in names


def test_amount_from_a_different_box_line_does_not_verify(cfg):
    """1b extracted as 3200.00 (1a's amount, present in the text) -> UNVERIFIED: it must be on 1b's line."""
    ex = X.extract(text("T1"), "T1")
    bad = replace(ex, fields={**ex.fields, "1b": {"value": "3,200.00", "previously_reported": None}})
    (c,) = [c for c in X.verify_extraction(bad, text("T1"), cfg) if c.name == "1099-DIV:1b"]
    assert not c.verified and c.found == "1600.00" and c.extracted == "3,200.00"


def test_w2c_prior_and_correct_amounts_swapped_do_not_verify(cfg):
    ex = X.extract(text("T4"), "T4")
    bad = replace(ex, fields={"1": {"value": "82,000.00", "previously_reported": "86,500.00"}})
    assert not any(c.verified for c in X.verify_extraction(bad, text("T4"), cfg) if c.name.startswith("W-2c:1"))


@pytest.mark.parametrize("change,name", [
    (dict(payer_or_employer_tin="00-0000009"), "payer_or_employer_tin"),
    (dict(tax_year=2024), "tax_year"),
    (dict(corrected=False), "corrected"),
])
def test_header_facts_verified(change, name, cfg):
    bad = replace(X.extract(text("T1"), "T1"), **change)
    (c,) = [c for c in X.verify_extraction(bad, text("T1"), cfg) if c.name == name]
    assert not c.verified


def test_box_missing_from_text_does_not_verify(cfg):
    ex = X.extract(text("T1"), "T1")
    bad = replace(ex, fields={**ex.fields, "2a": {"value": "500.00", "previously_reported": None}})
    t = text("T1").replace("2a Total capital gain distributions .... $500.00\n", "")
    (c,) = [c for c in X.verify_extraction(bad, t, cfg) if c.name == "1099-DIV:2a"]
    assert not c.verified and c.found is None


def test_comma_and_dollar_normalised():
    assert X.to_decimal("$1,600.00") == Decimal("1600.00") == X.to_decimal("1600")
    assert X.to_decimal("16OO") is None


def test_verification_never_changes_extracted_value(cfg):
    d, rep = from_text("T12", cfg)
    assert rep.extraction.fields["1b"]["value"] == "1060.00"
    assert rep.correction.fields["1b"].value == "1060.00"  # flagged, not fixed


# --- run_from_text: the required cases ---------------------------------------------------------


def test_T12_specialist_review_extraction_unverified(cfg):
    d, rep = from_text("T12", cfg)
    assert d.status == S.SPECIALIST_REVIEW
    codes = [f.code for f in d.evidence.findings]
    assert "MISSING_FIELD" not in codes  # every box came from the extraction
    unver = [f for f in d.evidence.findings if f.code == "EXTRACTION_UNVERIFIED"]
    assert len(unver) == 1
    (f,) = unver
    assert f.category == "SPECIALIST" and f.field == "1099-DIV:1b"
    assert f.evidence["extracted"] == "1060.00" and f.evidence["found_in_text"] == "1600.00"
    assert "1060.00" in f.message and "1600.00" in f.message
    assert any("EXTRACTION UNVERIFIED".lower() in r.lower() for r in d.reasons)
    assert d.stale_approvals == [] and d.new_version is None
    assert not any(c.applied or c.applied_as_new_version for c in d.proposed_changes)
    from returnguard.explain import UNVERIFIED_TAG, template_note, unverified_boxes

    assert unverified_boxes(d) == {"1b"}
    assert f"1060.00 {UNVERIFIED_TAG}" in template_note(d)


def test_T1_from_text_equals_T1_from_json(cfg):
    d_text, rep = from_text("T1", cfg)
    ((_, d_json),) = run_case(load_fixture(CASES / "T1.json"), cfg)
    assert rep.extraction.mode_label == "MOCKED" and rep.all_verified
    assert d_text.status == d_json.status == S.APPLY_AND_REREVIEW
    assert [(c.form_type, c.field, c.delta) for c in d_text.proposed_changes] == \
        [(c.form_type, c.field, c.delta) for c in d_json.proposed_changes]
    assert [s.approval_id for s in d_text.stale_approvals] == [s.approval_id for s in d_json.stale_approvals]
    assert d_text.correction_fingerprint == d_json.correction_fingerprint  # same content, commas or not


def test_T4_from_text(cfg):
    d, _ = from_text("T4", cfg)
    assert d.status == S.APPLY_AND_REREVIEW
    assert [(c.field, c.delta) for c in d.proposed_changes] == [("1", Decimal("4500.00"))]
    assert [s.approval_id for s in d.stale_approvals] == ["APR-1040-L1A", "APR-WAGE-WP"]


def test_T5_from_text_conflict(cfg):
    d, rep = from_text("T5", cfg)
    assert rep.all_verified  # the AI read it right; the CONFLICT is in the document itself
    assert d.status == S.CONFLICT
    assert any(f.code == "PRIOR_VALUE_MISMATCH" for f in d.evidence.findings)


def test_identity_comes_only_from_extraction(cfg):
    """Without an envelope the TIN/year/form/flag still come from the extraction, never the fixture."""
    d, rep = from_text("T1", cfg, envelope=False)
    assert rep.correction.payer_tin == "00-0000001" and rep.correction.tax_year == 2025
    assert rep.correction.doc_id == "SYN-TEXT-T1" and d.status == S.APPLY_AND_REREVIEW
    with pytest.raises(ValueError):
        X.build_correction(rep.extraction, text("T1"), "T1", load_accepted()["1099-DIV"], {"payer_tin": "x"})


def test_wrong_tin_from_extraction_reaches_identity_check(cfg):
    """A misread TIN is flagged UNVERIFIED and validate() also sees the mismatch: both route to a specialist."""
    ex = replace(X.extract(text("T1"), "T1"), payer_or_employer_tin="00-0000009")
    checks = X.verify_extraction(ex, text("T1"), cfg)
    corr = X.build_correction(ex, text("T1"), "T1", load_accepted()["1099-DIV"])
    d = decide(load_accepted()["1099-DIV"], corr, load_return_state(), cfg, extra_findings=X.findings_from_checks(checks))
    codes = {f.code for f in d.evidence.findings}
    assert d.status == S.SPECIALIST_REVIEW and {"EXTRACTION_UNVERIFIED", "IDENTITY_MISMATCH"} <= codes


def test_decide_without_extra_findings_unchanged(cfg):
    corr = load_fixture(CASES / "T1.json").submissions[0]
    a = decide(load_accepted()["1099-DIV"], corr, load_return_state(), cfg)
    b = decide(load_accepted()["1099-DIV"], corr, load_return_state(), cfg, extra_findings=[])
    assert a == b


# --- safety invariant across ALL fixtures, now including T12 and T13 ---------------------------


def test_safety_invariant_all_cases_including_llm_cases(cfg):
    from returnguard.explain import grounded_note, load_cached_note

    baseline = load_return_state()
    decisions = []
    for cid in ALL_CASES:
        if cid == "T12":
            decisions.append(from_text("T12", cfg)[0])
        else:
            decisions += [d for _, d in run_case(load_fixture(CASES / f"{cid}.json"), cfg)]
    decisions += [from_text(c, cfg)[0] for c in ["T1", "T4", "T5"]]
    assert len(decisions) >= 16
    for d in decisions:
        assert d.clears_approvals is False
        dumped = d.model_dump(mode="json")
        assert dumped["clears_approvals"] is False
        assert not {"approved", "cleared", "approvals_cleared", "approved_by"} & set(dumped)
        note = grounded_note(d, load_cached_note("T13") if d.evidence.correction_doc_id.endswith("T13") else None)
        assert "granted or cleared automatically" in note.text or note.source.startswith("LLM")
    assert load_return_state() == baseline
