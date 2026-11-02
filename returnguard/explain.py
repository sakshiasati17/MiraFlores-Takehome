"""Reviewer note: an LLM may draft it, but every number in it must come from the checked Decision.

- template_note(decision): plain-English note built ONLY from the Decision's fields (always safe).
- grounded_note(decision, llm_note): accept the LLM note only if every number in it is an allowed number;
  otherwise reject it, record the offending numbers and use template_note instead. No LLM note -> template.

Allowed numbers = every amount (accepted, raw correction, old/new), every delta with and without its sign,
the numbers inside box ids ("1b" -> 1), return line / approval ids ("Form 1040 line 3a" -> 1040, 3),
the tax year and the numbers inside both doc IDs, plus amounts in the findings' evidence.
Numbers are compared as Decimals, so "$1,600.00", "1600" and "1,600" are the same number.
The note never changes the status: explain.py only reads a Decision.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional, Union

from .decide import Decision, signed

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "llm_cache"

# A number in free text: optional sign (only when not glued to a word, so "C-001" is not -1),
# optional "$", digits with or without thousands commas, optional decimals.
_NUMBER = re.compile(
    r"(?:(?<![A-Za-z0-9])(?P<sign>[-+−]))?\$?\s?(?<![\d.,])(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?"
)


@dataclass(frozen=True)
class LLMNote:
    text: str
    mode_label: str = "MOCKED"  # "MOCKED" | "LIVE"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NoteResult:
    text: str
    source: str  # "LLM (MOCKED)" | "LLM (LIVE)" | "TEMPLATE"
    rejected_numbers: list[str] = field(default_factory=list)
    llm_text: Optional[str] = None  # the LLM draft, kept for the audit trail even when rejected

    @property
    def llm_rejected(self) -> bool:
        return self.llm_text is not None and self.source == "TEMPLATE"


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------


def numbers_in(text: str) -> list[tuple[str, Decimal]]:
    """Every number in text as (as written, Decimal). "$1,600.00" -> ("$1,600.00", 1600.00); "-$800" -> -800."""
    out = []
    for m in _NUMBER.finditer(text or ""):
        sign = "-" if m.group("sign") in ("-", "−") else ""
        body = m.group("int").replace(",", "") + (m.group("frac") or "")
        try:
            out.append((m.group(0).strip(), Decimal(sign + body)))
        except InvalidOperation:  # pragma: no cover - regex guarantees digits
            continue
    return out


def _add(allowed: set[Decimal], value: Any, both_signs: bool = False) -> None:
    if value is None:
        return
    if isinstance(value, Decimal):
        allowed.add(value)
        if both_signs:
            allowed.add(-value)
        return
    for _, d in numbers_in(str(value)):
        allowed.add(d)
        if both_signs:
            allowed.add(-d)
        allowed.add(abs(d))


def allowed_numbers(decision: Decision) -> set[Decimal]:
    """The checked facts a note may cite (see module docstring)."""
    allowed: set[Decimal] = set()
    ev = decision.evidence
    for c in decision.proposed_changes:
        _add(allowed, c.old)
        _add(allowed, c.new)
        _add(allowed, c.delta, both_signs=True)  # "-800.00", "800.00"
        _add(allowed, c.field)  # box id "1b" -> 1
        _add(allowed, c.form_type)  # "1099-DIV" -> 1099
    for v in ev.accepted_values.values():
        _add(allowed, v)
    for box, vals in ev.correction_values.items():
        _add(allowed, box)
        for v in vals.values():
            _add(allowed, v)
    for s in decision.stale_approvals:
        _add(allowed, s.approval_id)
        _add(allowed, s.item)
        for p in s.paths:
            _add(allowed, p)  # "1099-DIV:1b -> Form 1040 line 3a -> APR-1040-L3A"
    for f in ev.findings:
        _add(allowed, f.field)
        for v in f.evidence.values():
            if isinstance(v, (str, int, Decimal)) and not isinstance(v, bool):
                _add(allowed, v)
    _add(allowed, ev.accepted_doc_id)
    _add(allowed, ev.correction_doc_id)
    if decision.new_version is not None:
        _add(allowed, decision.new_version.tax_year)
        _add(allowed, decision.new_version.version)
    return allowed


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


def template_note(decision: Decision) -> str:
    """A plain-English reviewer note built only from the Decision's own fields."""
    ev = decision.evidence
    parts = [f"Status {decision.status.value}: correction {ev.correction_doc_id} compared with accepted {ev.accepted_doc_id}."]
    blocking = [f for f in ev.findings if f.category != "INFO"]
    for f in blocking:
        parts.append(f.message)
    if decision.proposed_changes:
        verb = "applied as a new version" if any(c.applied for c in decision.proposed_changes) else (
            "recorded as a new version, not applied" if any(c.applied_as_new_version for c in decision.proposed_changes)
            else "proposed, not applied")
        for c in decision.proposed_changes:
            label = f" ({c.label})" if c.label else ""
            parts.append(f"{c.form_type} box {c.field}{label}: {c.old} -> {c.new}, change {signed(c.delta)} ({verb}).")
    else:
        parts.append("No supported value changed.")
    if decision.stale_approvals:
        ids = ", ".join(f"{s.approval_id} ({s.item})" for s in decision.stale_approvals)
        parts.append(f"Approvals to re-review: {ids}.")
    else:
        parts.append("No approval was marked stale.")
    parts.append(decision.next_action)
    parts.append("No approval has been granted or cleared automatically.")
    return " ".join(parts)


def load_cached_note(case_id: str, cache_dir: Path = CACHE_DIR) -> Optional[LLMNote]:
    """data/llm_cache/<case_id>_note.json, or None if there is no recorded note."""
    path = Path(cache_dir) / f"{case_id}_note.json"
    if not path.exists():
        return None
    rec = json.loads(path.read_text())
    label = "MOCKED" if rec.get("mocked") is True else "LIVE" if rec.get("live") is True else None
    if label is None or not isinstance(rec.get("note"), str):
        raise ValueError(f"{path}: a note record needs \"mocked\"/\"live\": true and a \"note\" string")
    return LLMNote(text=rec["note"], mode_label=label, raw=rec)


def grounded_note(decision: Decision, llm_note: Union[LLMNote, str, None] = None) -> NoteResult:
    """Use the LLM note only if every number in it is a checked fact; else the template note."""
    if llm_note is None:
        return NoteResult(text=template_note(decision), source="TEMPLATE")
    if isinstance(llm_note, str):
        llm_note = LLMNote(text=llm_note)
    allowed = allowed_numbers(decision)
    rejected = [written.lstrip("$+").replace(",", "").replace("$", "") for written, d in numbers_in(llm_note.text)
                if d not in allowed]
    if rejected:
        return NoteResult(text=template_note(decision), source="TEMPLATE",
                          rejected_numbers=list(dict.fromkeys(rejected)), llm_text=llm_note.text)
    return NoteResult(text=llm_note.text, source=f"LLM ({llm_note.mode_label})", llm_text=llm_note.text)
