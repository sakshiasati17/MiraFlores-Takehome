"""Final polish: a NEW form is added through config only, and an unknown form never crashes.

The 1099-INT test works on a TEMPORARY COPY of the repo: it adds the form to the copy's config files, an accepted
document, a return-state approval, a fixture, a form text and a MOCKED extraction, then runs the copy's cli.py.
Every Python file in the copy is checked to be byte-identical to the repo's, so the form needs NO Python change.
The 1099-INT box meanings and 1040 line mappings used here are illustrative and marked unverified (synthetic test data).
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import cli
import returnguard.extract as X
from returnguard.decide import ProcessingState, decide
from returnguard.models import DecisionStatus as S

ROOT = Path(__file__).resolve().parents[1]
SYN_LABEL = "SYNTHETIC: invented data for the ReturnGuard prototype. No real taxpayer, payer or employer."


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("RETURNGUARD_LLM", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _py_hashes(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*.py")) if "__pycache__" not in p.parts and ".venv" not in p.parts
            and "tests" not in p.parts}


@pytest.fixture(scope="module")
def int_repo(tmp_path_factory) -> Path:
    """A copy of the repo with 1099-INT added through config + data files only."""
    dst = tmp_path_factory.mktemp("repo") / "rg"
    dst.mkdir()
    for name in ("cli.py", "returnguard", "config", "data"):
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, dst / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, dst / name)

    # config/forms.yaml: the new form (rules live in config)
    forms = yaml.safe_load((dst / "config/forms.yaml").read_text())
    forms["forms"]["1099-INT"] = {
        "title": "Interest Income",
        "kind": "source",
        "identity_fields": ["client_id", "tax_year", "payer_tin"],
        "correction": {"style": "reissue", "corrects": "1099-INT", "requires_corrected_flag": True},
        "fields": {"1": {"label": "Interest income", "supported": True},
                   "4": {"label": "Federal income tax withheld", "supported": True}},
        "unsupported_fields": {},
        "rules": [],
    }
    (dst / "config/forms.yaml").write_text(yaml.safe_dump(forms, sort_keys=False))

    # config/dependencies.yaml: field -> return line -> approval, both mappings UNVERIFIED
    deps = yaml.safe_load((dst / "config/dependencies.yaml").read_text())
    deps["approval_items"]["APR-1040-L2B"] = "Form 1040 line 2b: taxable interest"
    deps["dependencies"]["1099-INT:1"] = [{"return_line": "Form 1040 line 2b", "approval": "APR-1040-L2B",
                                           "source": "https://www.irs.gov/instructions/i1040gi", "unverified": True}]
    deps["dependencies"]["1099-INT:4"] = [{"return_line": "Form 1040 line 25b", "approval": "APR-1040-L25B",
                                           "source": "https://www.irs.gov/instructions/i1040gi", "unverified": True}]
    (dst / "config/dependencies.yaml").write_text(yaml.safe_dump(deps, sort_keys=False))

    syn = dst / "data/synthetic"
    (syn / "accepted_1099int_C-001_2025.json").write_text(json.dumps({
        "synthetic": True, "_label": SYN_LABEL, "doc_id": "SYN-1099INT-C001-2025-v1", "version": 1,
        "form_type": "1099-INT", "client_id": "C-001", "tax_year": 2025, "payer_name": "Synthetic Savings Bank",
        "payer_tin": "00-0000003", "accepted_at": "2026-02-15T12:00:00Z",
        "fields": {"1": {"amount": "100.00"}, "4": {"amount": "0.00"}}}, indent=2))
    rs = json.loads((syn / "return_state_C-001_2025.json").read_text())
    rs["accepted_doc_ids"].append("SYN-1099INT-C001-2025-v1")
    rs["approvals"].append({"id": "APR-1040-L2B", "item": "Form 1040 line 2b: taxable interest",
                            "approved_by": "SYN-CPA-01", "approved_at": "2026-03-01T15:00:00Z",
                            "based_on": ["1099-INT:1"], "evidence_fingerprint": None})
    (syn / "return_state_C-001_2025.json").write_text(json.dumps(rs, indent=2))

    text = ("SYNTHETIC - NOT A REAL TAX DOCUMENT\n"
            "FORM 1099-INT    INTEREST INCOME    TAX YEAR 2025\n[X] CORRECTED\n"
            "PAYER'S name: Synthetic Savings Bank\nPAYER'S TIN: 00-0000003\n"
            "1 Interest income ..................... $150.00\n"
            "4 Federal income tax withheld ......... $0.00\n")
    (syn / "raw/T16.txt").write_text(text)
    (syn / "cases/T16.json").write_text(json.dumps({
        "synthetic": True, "_label": SYN_LABEL, "case_id": "T16", "angle": "New form via config",
        "description": "Corrected 1099-INT: box 1 100.00 -> 150.00.", "return_status": "APPROVED",
        "submissions": [{"synthetic": True, "_label": SYN_LABEL, "doc_id": "SYN-1099INT-C001-2025-T16",
                         "form_type": "1099-INT", "client_id": "C-001", "tax_year": 2025,
                         "payer_name": "Synthetic Savings Bank", "payer_tin": "00-0000003", "corrected": True,
                         "corrects_doc_id": "SYN-1099INT-C001-2025-v1", "received_at": "2026-03-25T12:00:00Z",
                         "fields": {"1": {"value": "150.00"}, "4": {"value": "0.00"}}}],
        "expected": {"status": "APPLY_AND_REREVIEW", "deltas": {"1099-INT:1": "50.00"},
                     "stale_approvals": ["APR-1040-L2B"]}}, indent=2))
    (dst / "data/llm_cache/T16.json").write_text(json.dumps({
        "mocked": True, "_label": "MOCKED: hand-written stand-in for an LLM output, not a real model call",
        "source": "hand-written", "synthetic": True, "case_id": "T16", "model": None, "prompt_version": "extract-v2",
        "extraction": {"form_type": "1099-INT", "corrected": True, "payer_or_employer_tin": "00-0000003",
                       "tax_year": 2025, "fields": {"1": {"value": "150.00"}, "4": {"value": "0.00"}}}}, indent=2))
    return dst


def run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "cli.py", *args, "--log", str(repo / "out" / "log.jsonl")], cwd=repo,
                          capture_output=True, text=True, timeout=120)


def test_copy_has_no_python_changes(int_repo):
    copied, repo = _py_hashes(int_repo), _py_hashes(ROOT)
    assert "cli.py" in copied and "returnguard/models.py" in copied and "returnguard/extract.py" in copied
    assert {k: repo[k] for k in copied} == copied  # every Python file in the copy is byte-identical to the repo's


def test_new_form_json_case_end_to_end(int_repo):
    r = run(int_repo, "data/synthetic/cases/T16.json")
    assert r.returncode == 0, r.stderr
    assert "STATUS:  APPLY_AND_REREVIEW" in r.stdout
    assert "1099-INT box 1 Interest income: 100.00 -> 150.00  delta +50.00  [applied as new version]" in r.stdout
    assert "APR-1040-L2B  Form 1040 line 2b: taxable interest  [UNVERIFIED]" in r.stdout
    assert "1099-INT:1 -> Form 1040 line 2b -> APR-1040-L2B" in r.stdout


def test_new_form_from_text_end_to_end(int_repo):
    r = run(int_repo, "--from-text", "data/synthetic/raw/T16.txt", "--case", "T16")
    assert r.returncode == 0, r.stderr
    assert "EXTRACTION: MOCKED" in r.stdout and "-> all values verified against the text" in r.stdout
    assert "VERIFIED    1099-INT:1: 150.00" in r.stdout and "STATUS:  APPLY_AND_REREVIEW" in r.stdout


def test_new_form_in_all_and_old_cases_unchanged(int_repo):
    r = run(int_repo, "--all")
    assert r.returncode == 0, r.stdout
    rows = r.stdout.strip().splitlines()[1:]
    assert len(rows) == 16 and all(row.rstrip().endswith("match") and "MISMATCH" not in row for row in rows)
    assert any(row.startswith("T16 ") for row in rows)


def test_live_prompt_lists_forms_from_config(int_repo):
    code = ("import returnguard.extract as X; p = X.build_prompt('TEXT', X.default_config()); "
            "print(p)")
    r = subprocess.run([sys.executable, "-c", code], cwd=int_repo, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "- Form 1099-INT (Interest Income): boxes 1 (Interest income), 4 (Federal income tax withheld)" in r.stdout
    assert "Form 1099-DIV" in r.stdout and "Form W-2c" in r.stdout


def test_repo_prompt_is_built_from_repo_config():
    p = X.build_prompt("TEXT", cli.load_config_default())
    assert "Form 1099-DIV (Dividends and Distributions)" in p and "Form W-2c (Corrected Wage and Tax Statement)" in p
    assert "1099-INT" not in p


# --- unknown form type: a finding, never a crash ------------------------------------------------------


def _t1_as(form_type: str):
    fx = cli.load_fixture(cli.CASES / "T1.json")
    sub = fx.submissions[0].model_copy(update={"form_type": form_type})
    return fx.model_copy(update={"submissions": [sub]})


def test_unknown_form_type_is_specialist_review_not_a_crash():
    cfg = cli.load_config_default()
    ((acc, d),) = cli.run_case(_t1_as("1099-INT"), cfg)  # 1099-INT is NOT in the repo's config
    assert d.status == S.SPECIALIST_REVIEW
    codes = [f.code for f in d.evidence.findings]
    assert codes == ["UNKNOWN_FORM_TYPE"]
    assert d.evidence.findings[0].category == "SPECIALIST"
    assert d.stale_approvals == [] and d.new_version is None and d.proposed_changes == []
    assert any("not defined in config/forms.yaml" in r for r in d.reasons)
    assert any("Nothing was applied" in r for r in d.reasons)
    assert d.clears_approvals is False


def test_unknown_form_type_via_decide_directly():
    cfg = cli.load_config_default()
    acc = cli.load_accepted()["1099-DIV"]
    corr = _t1_as("1099-XYZ").submissions[0]
    d = decide(acc, corr, cli.load_return_state(), cfg, ProcessingState())
    assert d.status == S.SPECIALIST_REVIEW and d.evidence.findings[0].code == "UNKNOWN_FORM_TYPE"


def test_unknown_form_type_from_text_is_specialist_review(monkeypatch):
    """The AI reads a form type config does not define: SPECIALIST_REVIEW, values not applied, no exception."""
    real = X.extract
    monkeypatch.setattr(X, "extract", lambda *a, **k: dataclasses.replace(real(*a, **k), form_type="1099-INT"))
    cfg = cli.load_config_default()
    acc, d, rep = cli.run_text_case((cli.RAW / "T1.txt").read_text(), "T1", cfg, cli.load_fixture(cli.CASES / "T1.json"))
    assert d.status == S.SPECIALIST_REVIEW
    assert "UNKNOWN_FORM_TYPE" in [f.code for f in d.evidence.findings]
    assert not rep.all_verified  # boxes of an unknown form have no labels, so they cannot be verified
    assert d.stale_approvals == [] and d.new_version is None
