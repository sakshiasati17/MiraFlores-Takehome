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
    assert "NEXT ACTION: Re-review the approvals listed above" in out


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
    for row in rows:
        cid = row.split()[0]
        if cid in {"T12", "T13"}:
            assert "LLM case: Session 4" in row
        else:
            assert row.rstrip().endswith("match") and "MISMATCH" not in row, row
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
