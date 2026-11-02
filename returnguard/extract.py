"""AI step: an LLM reads corrected-form TEXT into a fixed schema; code checks every value against the text.

AI suggests -> code verifies -> decide.py decides -> a CPA decides what to do.

Modes
- cached (default): replay data/llm_cache/<case_id>.json. Those files are labelled
  "MOCKED: hand-written stand-in for an LLM output, not a real model call" ("mocked": true, "source":
  "hand-written", "model": null). No network, no API key, no cost. Every test runs in this mode.
- live (optional): only when env RETURNGUARD_LLM=live AND ANTHROPIC_API_KEY is set. One call with the fixed
  prompt below (default model claude-haiku-5-5, override with RETURNGUARD_LLM_MODEL); the SDK
  (requirements-llm.txt, NOT requirements.txt) is imported inside the function. The real output is recorded to
  data/llm_cache/<case_id>.live.json labelled LIVE (the hand-written MOCKED files are never overwritten).
- use_live_cache=True: replay data/llm_cache/<case_id>.live.json (a real recorded live output, labelled LIVE)
  when it exists, else fall back to the MOCKED file. No API call.
A missing cache file with live mode off is an error, never a guess.

Verification (verify_extraction)
- For each extracted box, find the ONE text line for that box (box id at the start of the line + the box
  label from config/forms.yaml, else _FALLBACK_LABELS) and check the extracted amount is the amount ON THAT
  LINE (Decimal compare after stripping "$" and commas). W-2c: the "Previously reported" and "Correct
  information" segments of the line are checked separately.
- The corrected flag, payer/employer TIN, tax year and form type must also appear in the text.
- A failed check -> Finding EXTRACTION_UNVERIFIED (category SPECIALIST) naming the box, the extracted value
  and what the text shows. The extracted value is NEVER replaced by the text value: flag it, don't fix it.

The schema has no status, no decision and no advice: the LLM never decides anything.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from .decide import Decision, ProcessingState, decide
from .models import AcceptedDocument, CorrectionDocument, ReturnState
from .validate import Finding

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "llm_cache"

PROMPT_VERSION = "extract-v1"
DEFAULT_LIVE_MODEL = "claude-haiku-5-5"  # fast, low-cost extraction; override with env RETURNGUARD_LLM_MODEL

# ---------------------------------------------------------------------------
# The fixed extraction schema (JSON Schema). Nothing else: no status, no decision, no advice.
# ---------------------------------------------------------------------------

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["form_type", "corrected", "payer_or_employer_tin", "tax_year", "fields"],
    "properties": {
        "form_type": {"type": "string", "description": 'Form name as printed, e.g. "1099-DIV" or "W-2c".'},
        "corrected": {"type": "boolean", "description": "True if the form is marked CORRECTED or is a W-2c."},
        "payer_or_employer_tin": {"type": "string", "description": "Payer's TIN (1099) or employer's EIN (W-2c)."},
        "tax_year": {"type": "integer"},
        "fields": {
            "type": "object",
            "description": 'One entry per box, keyed by box id ("1a", "1b", "2a", "4", "1", "2").',
            "additionalProperties": {
                "type": "object",
                "additionalProperties": False,
                "required": ["value"],
                "properties": {
                    "value": {"type": "string", "description": 'Amount exactly as printed (W-2c: "Correct information").'},
                    "previously_reported": {"type": "string", "description": 'W-2c only: "Previously reported" amount as printed.'},
                },
            },
        },
    },
}

EXTRACTION_PROMPT = """You are reading the text of ONE corrected US tax information form (Form 1099-DIV or Form W-2c).
Copy what is printed into JSON that matches this JSON Schema exactly:

{schema}

Rules:
- Copy amounts exactly as printed (keep commas and decimals; you may drop the "$"). Do not calculate, round or fix anything.
- Include every box that shows an amount. Box ids are the printed box numbers, e.g. "1a", "1b", "2a", "4", "1", "2".
- For a W-2c, "value" is the "Correct information" amount and "previously_reported" is the "Previously reported" amount.
- For a 1099-DIV, do not include "previously_reported".
- corrected is true only if the form is marked CORRECTED (or is a Form W-2c).
- Output only the JSON object. Do not add a status, a decision, advice or any other key.

Form text:
<<<
{text}
>>>"""

# Used only when config/forms.yaml has no label for a box.
_FALLBACK_LABELS: dict[str, dict[str, str]] = {
    "1099-DIV": {"1a": "Total ordinary dividends", "1b": "Qualified dividends", "2a": "Total capital gain distributions",
                 "4": "Federal income tax withheld", "7": "Foreign tax paid"},
    "W-2c": {"1": "Wages, tips, other compensation", "2": "Federal income tax withheld"},
}
# W-2c line segments ("Box 1 Wages ... | Previously reported $82,000.00 | Correct information $86,500.00").
_SEGMENT_LABELS = {"previously_reported": "previously reported", "value": "correct information"}
_CORRECTED_MARKERS = [r"\[\s*x\s*\]\s*corrected\b", r"\bform\s+w-2c\b"]
_MONEY_TOKEN = re.compile(r"\$?\s?(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+)\.(\d{2})(?!\d)")


class ExtractionError(RuntimeError):
    """Cache missing, live mode not allowed, or an LLM output that does not match the fixed schema."""


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionResult:
    fields: dict[str, dict[str, Optional[str]]]  # box -> {"value", "previously_reported"} as printed
    mode_label: str  # "MOCKED" | "LIVE"
    raw: dict[str, Any]  # the whole cache record (labels, model, prompt_version, extraction)
    form_type: str = ""
    corrected: bool = False
    payer_or_employer_tin: str = ""
    tax_year: int = 0
    model: str = ""  # "" for hand-written MOCKED files ("model": null)
    prompt_version: str = ""
    cache_path: str = ""
    source: str = ""  # "hand-written" (MOCKED) | "live" (real model output)
    replayed_live: bool = False  # True when a recorded .live.json was replayed (no API call this run)


@dataclass(frozen=True)
class FieldCheck:
    name: str  # "1099-DIV:1b", "W-2c:1 (previously reported)", "tax_year", ...
    extracted: str
    found: Optional[str]  # what the text shows (normalised), None if nothing found
    verified: bool
    line: Optional[str] = None  # the source line that was checked
    note: str = ""


@dataclass(frozen=True)
class ExtractionReport:
    extraction: ExtractionResult
    checks: list[FieldCheck]
    findings: list[Finding]
    correction: CorrectionDocument

    @property
    def all_verified(self) -> bool:
        return all(c.verified for c in self.checks)


# ---------------------------------------------------------------------------
# Schema check (our own, so no extra dependency)
# ---------------------------------------------------------------------------


def check_schema(obj: Any) -> dict[str, Any]:
    """Raise ExtractionError unless obj matches EXTRACTION_SCHEMA exactly (no extra keys anywhere)."""
    if not isinstance(obj, dict):
        raise ExtractionError("extraction must be a JSON object")
    want = set(EXTRACTION_SCHEMA["properties"])
    if set(obj) != want:
        raise ExtractionError(f"extraction keys must be exactly {sorted(want)}; got {sorted(obj)}")
    if not isinstance(obj["form_type"], str) or not isinstance(obj["payer_or_employer_tin"], str):
        raise ExtractionError("form_type and payer_or_employer_tin must be strings")
    if not isinstance(obj["corrected"], bool):
        raise ExtractionError("corrected must be true/false")
    if isinstance(obj["tax_year"], bool) or not isinstance(obj["tax_year"], int):
        raise ExtractionError("tax_year must be an integer")
    if not isinstance(obj["fields"], dict):
        raise ExtractionError("fields must be an object")
    for box, f in obj["fields"].items():
        if not isinstance(f, dict) or "value" not in f or not set(f) <= {"value", "previously_reported"}:
            raise ExtractionError(f"fields[{box!r}] must have 'value' and optionally 'previously_reported' only")
        if not all(isinstance(v, str) for v in f.values()):
            raise ExtractionError(f"fields[{box!r}] amounts must be strings as printed")
    return obj


# ---------------------------------------------------------------------------
# extract()
# ---------------------------------------------------------------------------


def live_enabled() -> bool:
    return os.environ.get("RETURNGUARD_LLM", "").strip().lower() == "live" and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _result(record: dict[str, Any], path: Path, replayed_live: bool = False) -> ExtractionResult:
    ex = check_schema(record.get("extraction"))
    if record.get("mocked") is True:
        label = "MOCKED"
    elif record.get("live") is True:
        label = "LIVE"
    else:
        raise ExtractionError(f"{path}: cache record must say \"mocked\": true or \"live\": true")
    return ExtractionResult(
        fields={b: {"value": f["value"], "previously_reported": f.get("previously_reported")} for b, f in ex["fields"].items()},
        mode_label=label,
        raw=record,
        form_type=ex["form_type"],
        corrected=ex["corrected"],
        payer_or_employer_tin=ex["payer_or_employer_tin"],
        tax_year=ex["tax_year"],
        model=str(record.get("model") or ""),
        prompt_version=str(record.get("prompt_version") or ""),
        cache_path=str(path),
        source=str(record.get("source") or ("live" if label == "LIVE" else "hand-written")),
        replayed_live=replayed_live,
    )


def _call_live(text: str, model: str) -> dict[str, Any]:
    """ONE call to the Claude API. Imported lazily so the core install never needs the SDK.

    Parameters left out on purpose, because Claude Haiku 5.5 (the default model) returns HTTP 400 for them:
      - temperature / top_p / top_k (non-default sampling values are rejected), so no "temperature 0";
      - thinking={"type": "enabled", "budget_tokens": N} (manual thinking budgets are rejected);
      - an assistant prefill (e.g. starting the answer with "{").
    Sent: model, max_tokens, messages, and output_config effort "low" (supported; keeps thinking short for a
    copy-the-form task). Haiku 5.5 thinks by default and thinking counts toward max_tokens, so max_tokens is
    generous and only `text` blocks are read. The output is pinned by the fixed prompt + schema, checked by
    check_schema(), then verified against the source text by code. Nothing here can set a status.
    """
    try:
        import anthropic  # noqa: PLC0415  (lazy on purpose: optional dependency)
    except ImportError as exc:  # pragma: no cover - depends on the optional install
        raise ExtractionError("live mode needs the optional SDK: pip install -r requirements-llm.txt") from exc
    client = anthropic.Anthropic()
    prompt = EXTRACTION_PROMPT.format(schema=json.dumps(EXTRACTION_SCHEMA, indent=2), text=text)
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise ExtractionError("the model declined to extract this form")
    if response.stop_reason == "max_tokens":
        raise ExtractionError("live output was cut off at max_tokens; not using a partial extraction")
    out = "".join(b.text for b in response.content if b.type == "text").strip()
    out = re.sub(r"^```(?:json)?\s*|\s*```$", "", out)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"live output is not JSON: {out[:200]!r}") from exc


def extract(text: str, case_id: str, mode: Optional[str] = None, cache_dir: Path = CACHE_DIR,
            use_live_cache: bool = False) -> ExtractionResult:
    """Structured fields from form text.

    mode None / "cached": replay data/llm_cache/<case_id>.json (MOCKED, hand-written). Default, free, offline.
        With use_live_cache=True, replay data/llm_cache/<case_id>.live.json instead when it exists (LIVE).
    mode "live": requires RETURNGUARD_LLM=live and ANTHROPIC_API_KEY (else ExtractionError).
    With mode None and live enabled by the environment, live is used.
    """
    mode = (mode or ("live" if live_enabled() else "cached")).lower()
    cache_dir = Path(cache_dir)
    if mode == "live":
        if not live_enabled():
            raise ExtractionError("live mode needs RETURNGUARD_LLM=live and ANTHROPIC_API_KEY set; refusing to call the API")
        model = os.environ.get("RETURNGUARD_LLM_MODEL", DEFAULT_LIVE_MODEL)
        extraction = check_schema(_call_live(text, model))
        record = {
            "live": True,
            "_label": "LIVE: real model output recorded by ReturnGuard (synthetic input only)",
            "source": "live",
            "synthetic": True,
            "case_id": case_id,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "extraction": extraction,
        }
        path = cache_dir / f"{case_id}.live.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + "\n")
        return _result(record, path)
    if mode != "cached":
        raise ExtractionError(f"unknown extraction mode {mode!r} (use 'cached' or 'live')")
    live_path = cache_dir / f"{case_id}.live.json"
    if use_live_cache and live_path.exists():
        record = json.loads(live_path.read_text())
        if record.get("live") is not True:
            raise ExtractionError(f"{live_path} is not labelled \"live\": true")
        return _result(record, live_path, replayed_live=True)
    path = cache_dir / f"{case_id}.json"
    if not path.exists():
        raise ExtractionError(
            f"no cached extraction for case {case_id!r} at {path} and live mode is off. "
            "Add one, or set RETURNGUARD_LLM=live with ANTHROPIC_API_KEY. ReturnGuard never guesses."
        )
    return _result(json.loads(path.read_text()), path)


# ---------------------------------------------------------------------------
# verify_extraction()
# ---------------------------------------------------------------------------


def to_decimal(raw: Optional[str]) -> Optional[Decimal]:
    """'$1,600.00' -> Decimal('1600.00'); None if it is not a plain amount."""
    if raw is None:
        return None
    s = str(raw).strip().replace("$", "").replace(",", "").strip()
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _amounts(segment: str) -> list[Decimal]:
    return [Decimal(m.group(1).replace(",", "") + "." + m.group(2)) for m in _MONEY_TOKEN.finditer(segment)]


def box_label(config: dict, form_type: str, box: str) -> Optional[str]:
    fcfg = (config.get("forms") or {}).get(form_type) or {}
    label = ((fcfg.get("fields") or {}).get(box) or {}).get("label") or (fcfg.get("unsupported_fields") or {}).get(box)
    return label or _FALLBACK_LABELS.get(form_type, {}).get(box)


def _box_lines(text: str, box: str, label: str) -> list[str]:
    """Lines that START with the box id (optionally 'Box ') and contain the label (case-insensitive)."""
    start = re.compile(rf"^\s*(?:box\s+)?{re.escape(box)}(?![0-9a-z])", re.IGNORECASE)
    return [ln.strip() for ln in text.splitlines() if start.match(ln) and label.lower() in ln.lower()]


def _segment(line: str, part: str) -> Optional[str]:
    """W-2c: the text after 'Previously reported' / 'Correct information' up to the next '|'."""
    m = re.search(rf"{_SEGMENT_LABELS[part]}([^|]*)", line, re.IGNORECASE)
    return m.group(1) if m else None


def _check_amount(name: str, extracted: str, line: Optional[str], segment: Optional[str], why_missing: str) -> FieldCheck:
    if line is None or segment is None:
        return FieldCheck(name, extracted, None, False, line, why_missing)
    found = _amounts(segment)
    shown = ", ".join(str(x) for x in found) if found else None
    value = to_decimal(extracted)
    if len(found) != 1:
        return FieldCheck(name, extracted, shown, False, line, f"expected exactly one amount on the line, found {len(found)}")
    if value is None:
        return FieldCheck(name, extracted, shown, False, line, "extracted value is not a plain amount")
    return FieldCheck(name, extracted, shown, value == found[0], line)


def verify_extraction(extraction: ExtractionResult, text: str, config: dict) -> list[FieldCheck]:
    """Check every extracted value against the source text. Never changes the extraction."""
    form = extraction.form_type
    checks: list[FieldCheck] = []
    style = (((config.get("forms") or {}).get(form) or {}).get("correction") or {}).get("style")

    # Header facts --------------------------------------------------------------------------
    form_ok = re.search(rf"(?<![\w-]){re.escape(form)}(?![\w-])", text, re.IGNORECASE) is not None if form else False
    checks.append(FieldCheck("form_type", form, form if form_ok else None, form_ok, note="" if form_ok else "form name not in text"))
    marked = any(re.search(p, text, re.IGNORECASE) for p in _CORRECTED_MARKERS)
    checks.append(FieldCheck("corrected", str(extraction.corrected).lower(), str(marked).lower(), extraction.corrected == marked))
    tin = extraction.payer_or_employer_tin
    tin_lines = [ln.strip() for ln in text.splitlines() if re.search(r"\b(TIN|EIN)\b", ln) and tin and tin in ln]
    checks.append(FieldCheck("payer_or_employer_tin", tin, tin if tin_lines else None, bool(tin_lines),
                             tin_lines[0] if tin_lines else None, "" if tin_lines else "TIN not found on a TIN/EIN line"))
    years = re.findall(r"tax\s+year\D{0,5}(\d{4})", text, re.IGNORECASE)
    ok_year = years == [str(extraction.tax_year)] or (bool(years) and set(years) == {str(extraction.tax_year)})
    checks.append(FieldCheck("tax_year", str(extraction.tax_year), ", ".join(dict.fromkeys(years)) or None, ok_year))

    # Boxes ---------------------------------------------------------------------------------
    for box in sorted(extraction.fields):
        vals = extraction.fields[box]
        name = f"{form}:{box}"
        label = box_label(config, form, box)
        lines = _box_lines(text, box, label) if label else []
        line = lines[0] if len(lines) == 1 else None
        why = ("no known label for this box" if not label else
               f"no line for box {box} ({label}) in the text" if not lines else
               f"{len(lines)} lines match box {box}; ambiguous")
        if style == "previous_and_correct":
            for part, suffix in (("previously_reported", " (previously reported)"), ("value", " (correct information)")):
                ext = vals.get(part)
                if ext is None:
                    continue  # validate.py raises MISSING_PRIOR_VALUE where it matters
                seg = _segment(line, part) if line else None
                checks.append(_check_amount(name + suffix, ext, line, seg,
                                            why if line is None else f"no '{_SEGMENT_LABELS[part]}' amount on the line"))
        else:
            if vals.get("previously_reported") is not None:
                checks.append(FieldCheck(name + " (previously reported)", vals["previously_reported"], None, False, line,
                                         "this form has no 'previously reported' amounts"))
            seg = line[re.match(rf"^\s*(?:box\s+)?{re.escape(box)}", line, re.IGNORECASE).end():] if line else None
            checks.append(_check_amount(name, vals["value"], line, seg, why))
    return checks


def findings_from_checks(checks: list[FieldCheck]) -> list[Finding]:
    """One EXTRACTION_UNVERIFIED (SPECIALIST) finding per failed check."""
    out = []
    for c in checks:
        if c.verified:
            continue
        found = c.found if c.found is not None else "nothing"
        msg = (f"Extraction UNVERIFIED: {c.name} was extracted as {c.extracted}, but the source text shows {found}"
               + (f" ({c.note})" if c.note else "") + ". The extracted value was NOT replaced; a reviewer must check the form.")
        out.append(Finding(code="EXTRACTION_UNVERIFIED", category="SPECIALIST", field=c.name, message=msg,
                           evidence={"extracted": c.extracted, "found_in_text": c.found, "line": c.line}))
    return out


# ---------------------------------------------------------------------------
# run_from_text(): extract -> verify -> CorrectionDocument -> decide()
# ---------------------------------------------------------------------------

# Intake details the form text cannot supply (where the file came from). They may NEVER carry form type,
# corrected flag, TIN, tax year or amounts: those come only from the extraction.
ENVELOPE_KEYS = {"doc_id", "client_id", "payer_name", "corrects_doc_id", "received_at"}


def build_correction(extraction: ExtractionResult, text: str, case_id: str, accepted: AcceptedDocument,
                     envelope: Optional[Mapping[str, Any]] = None) -> CorrectionDocument:
    env = dict(envelope or {})
    extra = set(env) - ENVELOPE_KEYS
    if extra:
        raise ValueError(f"envelope may only hold {sorted(ENVELOPE_KEYS)}; got extra {sorted(extra)}")
    return CorrectionDocument.model_validate({
        "synthetic": True,
        "_label": f"SYNTHETIC: built from form text by {extraction.mode_label} LLM extraction (case {case_id}).",
        "doc_id": env.get("doc_id") or f"SYN-TEXT-{case_id}",
        "client_id": env.get("client_id") or accepted.client_id,
        "payer_name": env.get("payer_name") or accepted.payer_name,
        "corrects_doc_id": env.get("corrects_doc_id"),
        "received_at": env.get("received_at") or "not stated (built from form text)",
        # From the extraction ONLY:
        "form_type": extraction.form_type,
        "corrected": extraction.corrected,
        "payer_tin": extraction.payer_or_employer_tin,
        "tax_year": extraction.tax_year,
        "fields": {b: {k: v for k, v in f.items() if v is not None} for b, f in extraction.fields.items()},
        "source_text": text,
    })


def run_from_text(
    text: str,
    case_id: str,
    accepted: Union[AcceptedDocument, Mapping[str, AcceptedDocument]],
    return_state: ReturnState,
    config: dict,
    state: Optional[ProcessingState] = None,
    envelope: Optional[Mapping[str, Any]] = None,
    mode: Optional[str] = None,
    use_live_cache: bool = False,
) -> tuple[Decision, ExtractionReport]:
    """Full AI pipeline for one form text. accepted may be one document or {form_type: document};
    with a mapping, the document the extracted form corrects is picked (W-2c -> W-2)."""
    ex = extract(text, case_id, mode=mode, use_live_cache=use_live_cache)
    if not isinstance(accepted, AcceptedDocument):
        fcfg = (config.get("forms") or {}).get(ex.form_type)
        if fcfg is None:
            raise ExtractionError(f"extracted form type {ex.form_type!r} is not defined in forms.yaml")
        target = (fcfg.get("correction") or {}).get("corrects", ex.form_type)
        if target not in accepted:
            raise ExtractionError(f"no accepted {target} document to compare against")
        accepted = accepted[target]
    checks = verify_extraction(ex, text, config)
    findings = findings_from_checks(checks)
    correction = build_correction(ex, text, case_id, accepted, envelope)
    decision = decide(accepted, correction, return_state, config, state, extra_findings=findings)
    return decision, ExtractionReport(extraction=ex, checks=checks, findings=findings, correction=correction)
