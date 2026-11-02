"""Session 3: cli.py smoke tests. Audit log always goes to tmp_path, never the real out/ folder."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cli(*args, tmp_path):
    return subprocess.run(
        [sys.executable, "cli.py", *args, "--log", str(tmp_path / "audit.jsonl")],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )


def test_T1_text_report(tmp_path):
    r = cli("data/synthetic/cases/T1.json", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "STATUS:  APPLY_AND_REREVIEW" in out
    assert "-800.00" in out and "2400.00 -> 1600.00" in out
    assert "APR-1040-L3A" in out and "APR-QDCG-WS" in out and "[UNVERIFIED]" in out
    assert "Naive check (did total income change?): no" in out
    assert "NEXT ACTION: Re-review the approvals listed in this report" in out


def test_T5_text_report(tmp_path):
    r = cli("data/synthetic/cases/T5.json", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "STATUS:  CONFLICT" in r.stdout and "none (nothing changed)" in r.stdout
    assert "Naive check" not in r.stdout  # W-2c has no naive total defined


def test_json_parses(tmp_path):
    r = cli("data/synthetic/cases/T1.json", "--json", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["status"] == "APPLY_AND_REREVIEW" and d["clears_approvals"] is False
    assert d["proposed_changes"][0]["delta"] == "-800.00"


def test_json_multi_submission_is_a_list(tmp_path):
    d = json.loads(cli("data/synthetic/cases/T7.json", "--json", tmp_path=tmp_path).stdout)
    assert [x["status"] for x in d] == ["APPLY_AND_REREVIEW", "DUPLICATE_NO_CHANGE"]


def test_all_every_row_matches(tmp_path):
    r = cli("--all", tmp_path=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    rows = r.stdout.strip().splitlines()[1:]
    assert len(rows) == 15
    # Session 4: T12 and T13 are no longer skipped; every one of the 15 rows must match.
    for row in rows:
        assert row.rstrip().endswith("match") and "MISMATCH" not in row and "skipped" not in row, row
    assert "UNVERIFIED" in next(r for r in rows if r.startswith("T12 "))
    assert "LLM note rejected: 900.00" in next(r for r in rows if r.startswith("T13 "))
    assert (tmp_path / "audit.jsonl").exists()


def test_cli_does_not_write_real_out_folder_in_tests(tmp_path):
    before = (ROOT / "out" / "audit_log.jsonl").read_text() if (ROOT / "out" / "audit_log.jsonl").exists() else None
    cli("data/synthetic/cases/T1.json", tmp_path=tmp_path)
    after = (ROOT / "out" / "audit_log.jsonl").read_text() if (ROOT / "out" / "audit_log.jsonl").exists() else None
    assert before == after


def test_fixture_files_untouched_after_run(tmp_path):
    cli("--all", tmp_path=tmp_path)
    r = subprocess.run(["git", "status", "--porcelain", "--", "data", "config"], cwd=ROOT, capture_output=True, text=True)
    assert r.stdout.strip() == ""


# --- Session 4: AI pipeline from text ------------------------------------------------------------


def cli_offline(*args, tmp_path):
    """Same as cli() but with live mode explicitly off and no API key in the environment."""
    import os

    env = {k: v for k, v in os.environ.items() if k not in {"RETURNGUARD_LLM", "ANTHROPIC_API_KEY"}}
    return subprocess.run(
        [sys.executable, "cli.py", *args, "--log", str(tmp_path / "audit.jsonl")],
        cwd=ROOT, capture_output=True, text=True, timeout=60, env=env,
    )


def test_from_text_T1_report(tmp_path):
    r = cli_offline("--from-text", "data/synthetic/raw/T1.txt", "--case", "T1", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "EXTRACTION: MOCKED" in out and "MOCKED: hand-written stand-in for an LLM output, not a real model call" in out
    assert "source: hand-written stand-in, no model was called" in out and "recorded" not in out.split("STATUS")[0]
    assert "VERIFIED    1099-DIV:1b: 1,600.00" in out and "UNVERIFIED  1099-DIV" not in out
    assert "all values verified against the text" in out
    assert "STATUS:  APPLY_AND_REREVIEW" in out and "-800.00" in out
    assert "REVIEWER NOTE  [source: TEMPLATE]" in out


def test_from_text_T12_shows_both_values(tmp_path):
    r = cli_offline("--from-text", "data/synthetic/raw/T12.txt", "--case", "T12", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "EXTRACTION: MOCKED" in out
    assert "UNVERIFIED  1099-DIV:1b: extracted 1060.00 | text shows 1600.00" in out
    assert "STATUS:  SPECIALIST_REVIEW" in out and "none (nothing changed)" in out
    assert "2400.00 -> 1060.00 (unverified extracted value)" in out
    assert all("(unverified extracted value)" in ln for ln in out.splitlines() if "-> 1060.00" in ln)


def test_T13_case_file_shows_rejected_note(tmp_path):
    r = cli_offline("data/synthetic/cases/T13.json", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "STATUS:  APPLY_AND_REREVIEW" in r.stdout
    assert "LLM note REJECTED: numbers not in the checked facts: 900.00" in r.stdout
    assert "[source: TEMPLATE]" in r.stdout


def test_T12_case_file_routes_through_text(tmp_path):
    r = cli_offline("data/synthetic/cases/T12.json", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "EXTRACTION: MOCKED" in r.stdout and "STATUS:  SPECIALIST_REVIEW" in r.stdout


def test_from_text_json(tmp_path):
    r = cli_offline("--from-text", "data/synthetic/raw/T4.txt", "--case", "T4", "--json", tmp_path=tmp_path)
    d = json.loads(r.stdout)
    assert d["extraction_label"] == "MOCKED" and d["decision"]["status"] == "APPLY_AND_REREVIEW"
    assert d["decision"]["proposed_changes"][0]["delta"] == "4500.00"


def test_from_text_unknown_case_is_clear_error(tmp_path):
    r = cli_offline("--from-text", "data/synthetic/raw/T1.txt", "--case", "T999", tmp_path=tmp_path)
    assert r.returncode != 0 and "no cached extraction" in r.stderr


def test_use_live_cache_without_live_file_falls_back_to_mocked(tmp_path):
    # T12 has no recorded live output (T1/T4/T5 do since the live run), so the flag must fall back to MOCKED.
    assert not (ROOT / "data" / "llm_cache" / "T12.live.json").exists()
    r = cli_offline("--from-text", "data/synthetic/raw/T12.txt", "--case", "T12", "--use-live-cache", tmp_path=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "EXTRACTION: MOCKED" in r.stdout and "STATUS:  SPECIALIST_REVIEW" in r.stdout
