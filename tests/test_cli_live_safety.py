"""Final polish: the CLI only calls the API with an explicit --live flag, and a failed live call is one line + exit 1."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import cli
import returnguard.extract as X

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "llm_cache"


def _cache_state() -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(CACHE.glob("*.json"))}


@pytest.fixture
def calls(monkeypatch):
    """Record (instead of making) any live API call."""
    seen = []

    def fake(prompt, model):
        seen.append(model)
        raise AssertionError("live API call attempted")

    monkeypatch.setattr(X, "_call_live", fake)
    return seen


def test_all_never_calls_api_even_with_live_env_and_key(monkeypatch, calls, tmp_path):
    monkeypatch.setenv("RETURNGUARD_LLM", "live")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-not-real")
    before = _cache_state()
    assert cli.main(["--all", "--log", str(tmp_path / "log.jsonl")]) == 0
    assert calls == []
    assert _cache_state() == before  # no .live.json written or changed


def test_from_text_without_flag_never_calls_api(monkeypatch, calls, tmp_path, capsys):
    monkeypatch.setenv("RETURNGUARD_LLM", "live")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-not-real")
    assert cli.main(["--from-text", str(cli.RAW / "T1.txt"), "--case", "T1", "--log", str(tmp_path / "l.jsonl")]) == 0
    assert calls == [] and "EXTRACTION: MOCKED" in capsys.readouterr().out


def test_live_with_all_is_refused(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--all", "--live"])
    assert exc.value.code == 2 and "--all always replays saved outputs" in capsys.readouterr().err


def test_live_flag_does_call_the_api(monkeypatch, calls, tmp_path, capsys):
    """--live really is the switch: with a key, the (patched) live call is reached."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-not-real")
    before = _cache_state()
    rc = cli.main(["--from-text", str(cli.RAW / "T1.txt"), "--case", "T1", "--live", "--log", str(tmp_path / "l.jsonl")])
    assert rc == 1 and calls == ["claude-haiku-5-5"]
    assert _cache_state() == before


def test_live_failure_is_one_line_and_exit_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-not-real")

    def fail(prompt, model):
        raise RuntimeError("Error code: 500 - internal server error\nmore detail")

    monkeypatch.setattr(X, "_call_live", fail)
    before = _cache_state()
    rc = cli.main(["--from-text", str(cli.RAW / "T1.txt"), "--case", "T1", "--live", "--log", str(tmp_path / "l.jsonl")])
    out, err = capsys.readouterr()
    assert rc == 1 and out == ""
    assert err == ("Live extraction failed: RuntimeError: Error code: 500 - internal server error. "
                   "Re-run without --live to use saved outputs.\n")
    assert _cache_state() == before


def test_live_without_key_is_one_line_in_a_real_process(tmp_path):
    """A real process (no mocks): --live with no key prints one line, exits 1, no traceback."""
    env = {k: v for k, v in os.environ.items() if k not in {"ANTHROPIC_API_KEY", "RETURNGUARD_LLM"}}
    r = subprocess.run([sys.executable, "cli.py", "--from-text", "data/synthetic/raw/T1.txt", "--case", "T1", "--live",
                        "--log", str(tmp_path / "l.jsonl")], cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 1 and r.stdout == ""
    assert r.stderr.strip().splitlines() == [
        "Live extraction failed: ExtractionError: live mode needs ANTHROPIC_API_KEY set; refusing to call the API. "
        "Re-run without --live to use saved outputs."]
    assert "Traceback" not in r.stderr
