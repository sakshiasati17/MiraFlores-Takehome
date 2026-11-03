"""ReturnGuard review console (Streamlit). SYNTHETIC data only; no API key, no network.

    streamlit run app.py

This file only DISPLAYS results. Every decision comes from the same functions cli.py uses:
  cli.run_text_case  (T1, T4, T5, T12: form text -> extraction -> source check -> decide)
  cli.run_case       (every other case: structured JSON fixture -> decide)
  cli.run_all        (the "All cases" tab: the exact table `python3 cli.py --all` prints)
  explain.grounded_note, decide.naive_total_changed
No business logic lives here. The UI never writes the audit log (Streamlit re-runs the whole
script on every click); the CLI does.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Optional

import streamlit as st

import cli
from returnguard.decide import Decision, naive_total_changed, signed
from returnguard.explain import UNVERIFIED_TAG, NoteResult, grounded_note, load_cached_note, unverified_boxes
from returnguard.extract import ExtractionReport, FieldCheck, to_decimal
from returnguard.models import AcceptedDocument, CaseFixture, CorrectionDocument

# ---------------------------------------------------------------------------
# Case list (display only)
# ---------------------------------------------------------------------------

TEXT_CASES = ("T1", "T4", "T5", "T12")  # run from data/synthetic/raw/<case>.txt through the AI step
LIVE_CACHE_CASES = ("T1", "T4", "T5")  # have a recorded LIVE output (data/llm_cache/<case>.live.json)
HEADLINE_LABELS = {
    "T1": "Dividend reclassification (headline)",
    "T12": "AI misread caught",
    "T5": "W-2c conflict",
    "T3": "Already filed",
    "T4": "W-2c wage correction",
}
CASE_ORDER = ["T1", "T12", "T5", "T3", "T4", "T2", "T6", "T7", "T8", "T9", "T10", "T11", "T13", "T14", "T15"]

STATUS_COLOURS = {
    "APPLY_AND_REREVIEW": "#B7791F",  # amber
    "POSSIBLE_AMENDMENT": "#B7791F",  # amber
    "CONFLICT": "#C0362C",  # red
    "REJECTED_INVALID_INPUT": "#C0362C",  # red
    "SPECIALIST_REVIEW": "#D9622B",  # orange
    "DUPLICATE_NO_CHANGE": "#6B7280",  # grey
}
TEAL = "#0F6E6E"
FOOTER = "Synthetic data. Not tax advice. Decisions require CPA review. Nothing is ever approved automatically."


@lru_cache(maxsize=None)
def config() -> dict:
    return cli.load_config_default()


@lru_cache(maxsize=None)
def fixture(case_id: str) -> CaseFixture:
    return cli.load_fixture(cli.CASES / f"{case_id}.json")


def case_label(case_id: str) -> str:
    return f"{case_id} · {HEADLINE_LABELS.get(case_id) or fixture(case_id).angle}"


# ---------------------------------------------------------------------------
# Running a case (calls existing functions only)
# ---------------------------------------------------------------------------


@dataclass
class CaseView:
    case_id: str
    fixture: CaseFixture
    results: list[tuple[AcceptedDocument, Decision]]  # one per submission (T7 has two)
    submissions: list[CorrectionDocument]
    note: NoteResult
    text: Optional[str] = None  # raw form text (text cases only)
    rep: Optional[ExtractionReport] = None  # extraction + source checks (text cases only)

    @property
    def decision(self) -> Decision:
        return self.results[-1][1]

    @property
    def accepted(self) -> AcceptedDocument:
        return self.results[-1][0]

    @property
    def submission(self) -> CorrectionDocument:
        return self.submissions[-1]


def run_view(case_id: str, use_live_cache: bool = True) -> CaseView:
    fx = fixture(case_id)
    if case_id in TEXT_CASES:
        text = (cli.RAW / f"{case_id}.txt").read_text()
        acc, d, rep = cli.run_text_case(text, case_id, config(), fx, log=None,
                                         use_live_cache=use_live_cache, mode="cached")  # never calls the API
        note = grounded_note(d, load_cached_note(case_id))
        return CaseView(case_id, fx, [(acc, d)], [rep.correction], note, text, rep)
    results = cli.run_case(fx, config(), log=None)
    note = grounded_note(results[-1][1], load_cached_note(case_id))
    return CaseView(case_id, fx, results, list(fx.submissions), note)


@lru_cache(maxsize=1)
def all_cases() -> tuple[list[dict], bool]:
    """Run exactly what `python3 cli.py --all` runs (cli.run_all, no audit log) and split its table into rows."""
    text, ok = cli.run_all(config(), None, mode="cached")  # never calls the API
    lines = text.splitlines()
    rows = []
    for ln in lines[1:]:
        case, expected, actual, match = re.split(r"\s{2,}", ln.strip(), maxsplit=3)
        rows.append({"case": case, "expected": expected, "actual": actual, "match": match})
    return rows, ok


# ---------------------------------------------------------------------------
# Small formatting helpers (pure; return HTML strings)
# ---------------------------------------------------------------------------

e = html.escape


def money(raw) -> str:
    """'1600.00' / '$1,600.00' / Decimal -> '1,600.00'; anything else shown as given."""
    d = raw if isinstance(raw, Decimal) else to_decimal(None if raw is None else str(raw))
    return f"{d:,.2f}" if d is not None else ("—" if raw is None else str(raw))


def pill(text: str, colour: str, solid: bool = False, dashed: bool = False) -> str:
    style = (f"background:{colour};color:#fff;border:1px solid {colour};" if solid
             else f"color:{colour};border:1px {'dashed' if dashed else 'solid'} {colour};background:transparent;")
    return f'<span class="rg-pill" style="{style}">{e(text)}</span>'


def status_pill(status: str) -> str:
    return pill(status, STATUS_COLOURS.get(status, "#6B7280"), solid=True)


def status_banner(d: Decision, sequence: Optional[list[str]] = None) -> str:
    colour = STATUS_COLOURS[d.status.value]
    seq = ""
    if sequence and len(sequence) > 1:
        seq = (f'<div class="rg-muted">Submissions in this case, in order: {e(" → ".join(sequence))}. '
               f"Showing the last one.</div>")
    return (f'<div class="rg-card rg-status" style="border-left:6px solid {colour};">'
            f'<div class="rg-status-label" style="color:{colour};">{e(d.status.value)}</div>'
            f'<div class="rg-next">{e(d.next_action)}</div>{seq}'
            f'<div class="rg-muted">Nothing is ever approved automatically.</div></div>')


def naive_cards(view: CaseView) -> Optional[str]:
    """Naive 'did total income change?' (decide.naive_total_changed) vs ReturnGuard. 1099-DIV only."""
    if view.submission.form_type != "1099-DIV":
        return None
    naive = naive_total_changed(view.accepted, view.submission)
    answer = "could not compute" if naive is None else ("Yes" if naive else "No")
    d = view.decision
    n = len(d.stale_approvals)
    rg = f"{d.status.value}, {n} approval{'s' if n != 1 else ''} stale"
    return (
        '<div class="rg-two">'
        '<div class="rg-card rg-naive"><div class="rg-kicker">Naive check: did total income change?</div>'
        f'<div class="rg-big">→ {e(answer)}</div>'
        '<div class="rg-muted">Compares only the 1099-DIV total (box 1a). For comparison; never used to decide.</div></div>'
        f'<div class="rg-card rg-rg" style="border-color:{TEAL};"><div class="rg-kicker" style="color:{TEAL};">ReturnGuard</div>'
        f'<div class="rg-big" style="color:{TEAL};">→ {e(rg)}</div>'
        '<div class="rg-muted">Checks every box, the source text and each approval\'s dependencies.</div></div>'
        "</div>"
    )


def _check_annotation(checks: list[FieldCheck]) -> tuple[str, str]:
    """(css class, annotation) for one source line, from the checks that point at it."""
    if all(c.verified for c in checks):
        return "rg-ok", "✓ verified"
    bad = []
    for c in checks:
        if c.verified:
            continue
        where = c.name.split("(", 1)[1].rstrip(")") + ": " if "(" in c.name else ""
        bad.append(f"{where}AI read {money(c.extracted)} — form says {money(c.found) if c.found else 'nothing'}")
    return "rg-bad", "✗ " + "; ".join(bad)


def evidence_panel(text: str, checks: list[FieldCheck]) -> str:
    """The form text, monospace, with every line the AI read highlighted by its source-check result."""
    by_line: dict[str, list[FieldCheck]] = {}
    for c in checks:
        if c.line:
            by_line.setdefault(c.line.strip(), []).append(c)
    out = []
    for ln in text.splitlines():
        hits = by_line.get(ln.strip())
        if hits:
            cls, note = _check_annotation(hits)
            out.append(f'<div class="rg-line {cls}"><span>{e(ln)}</span><span class="rg-ann">{e(note)}</span></div>')
        else:
            out.append(f'<div class="rg-line">{e(ln) or "&nbsp;"}</div>')
    return '<div class="rg-mono">' + "".join(out) + "</div>"


def extraction_pill(rep: ExtractionReport) -> str:
    ex = rep.extraction
    if ex.mode_label == "LIVE":
        when = str(ex.raw.get("recorded_at", "")).replace("T", " ").replace("+00:00", " UTC")
        how = "replayed, no API call this run" if ex.replayed_live else "live call"
        return pill(f"LIVE · {ex.model} · recorded {when}", TEAL, solid=True) + f' <span class="rg-muted">{e(how)}</span>'
    return pill("MOCKED · hand-written stand-in", "#6B7280", solid=True) + ' <span class="rg-muted">no model was called</span>'


def checks_table(checks: list[FieldCheck]) -> str:
    rows = []
    for c in checks:
        res = pill("VERIFIED", "#2E7D32") if c.verified else pill("UNVERIFIED", "#C0362C", solid=True)
        found = "" if c.verified else e(c.found if c.found is not None else "nothing") + (
            f'<div class="rg-muted">{e(c.note)}</div>' if c.note else "")
        rows.append(f"<tr><td>{e(c.name)}</td><td class='rg-num'>{e(c.extracted)}</td><td>{res}</td><td class='rg-num'>{found}</td></tr>")
    return ("<table class='rg-table'><thead><tr><th>Box / field</th><th>Extracted value</th><th>Check</th>"
            "<th>Source text shows</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def changes_table(d: Decision) -> str:
    if not d.proposed_changes:
        return '<div class="rg-muted">No supported value changed. Nothing was applied.</div>'
    unverified = unverified_boxes(d)
    rows = []
    for c in d.proposed_changes:
        if c.applied:
            tag = pill("applied as new version", TEAL)
        elif c.applied_as_new_version:
            tag = pill("recorded as new version, NOT applied", "#B7791F")
        else:
            tag = pill("proposed, not applied", "#6B7280")
        uv = f' <span class="rg-uv">{e(UNVERIFIED_TAG)}</span>' if c.field in unverified else ""
        cls = "rg-neg" if c.delta < 0 else "rg-pos" if c.delta > 0 else ""
        rows.append(f"<tr><td>{e(c.form_type)} box {e(c.field)}<div class='rg-muted'>{e(c.label)}</div></td>"
                    f"<td class='rg-num'>{e(str(c.old))}</td><td class='rg-num'>{e(str(c.new))}{uv}</td>"
                    f"<td class='rg-num {cls}'>{e(signed(c.delta))}</td><td>{tag}</td></tr>")
    return ("<table class='rg-table'><thead><tr><th>Field</th><th>Before</th><th>After</th><th>Delta</th>"
            "<th>Applied?</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def approvals_html(d: Decision) -> str:
    if not d.stale_approvals:
        return '<div class="rg-muted">None. Nothing was applied.</div>'
    blocks = []
    for s in d.stale_approvals:
        paths = []
        for p in s.paths:
            parts = [x.strip() for x in p.split("->")]
            if parts:
                parts[0] = parts[0].replace(":", " ", 1)
            chips = ' <span class="rg-arrow">→</span> '.join(
                f'<span class="rg-chip{" rg-chip-uv" if s.unverified else ""}">{e(x)}</span>' for x in parts)
            paths.append(f'<div class="rg-path">{chips}</div>')
        uv = ' <span class="rg-uv">unverified mapping</span>' if s.unverified else ""
        srcs = "".join(f"<div class='rg-muted rg-src'>source: {e(x)}</div>" for x in s.sources)
        blocks.append(f'<div class="rg-appr"><div><b>{e(s.approval_id)}</b> · {e(s.item)}{uv}</div>{"".join(paths)}{srcs}</div>')
    return "".join(blocks)


def note_html(note: NoteResult) -> str:
    src = pill(note.source, TEAL if note.source.startswith("LLM") else "#6B7280")
    out = [f"<div>{src}</div>"]
    if note.llm_rejected:
        out.append(f'<div class="rg-reject">LLM note REJECTED: numbers not in the checked facts: '
                   f'<b>{e(", ".join(note.rejected_numbers))}</b><div class="rg-muted">Rejected draft: {e(note.llm_text or "")}</div>'
                   f'<div class="rg-muted">Safe template note used instead:</div></div>')
    out.append(f'<div class="rg-note">{e(note.text)}</div>')
    return "".join(out)


def all_cases_html(rows: list[dict]) -> str:
    body = []
    for r in rows:
        statuses = re.findall(r"[A-Z_]{8,}", r["actual"].split(" (")[0])
        detail = r["actual"][len(r["actual"].split(" (")[0]):].strip()
        pills = " ".join(status_pill(s) for s in statuses)
        ok = r["match"] == "match"
        m = pill("✓ match", "#2E7D32") if ok else pill("✗ " + r["match"], "#C0362C", solid=True)
        body.append(f"<tr><td><b>{e(r['case'])}</b></td><td>{e(r['expected'])}</td><td>{pills}"
                    f"{f'<div class=rg-muted>{e(detail)}</div>' if detail else ''}</td><td>{m}</td></tr>")
    return ("<table class='rg-table'><thead><tr><th>Case</th><th>Expected</th><th>Actual</th><th>Match</th></tr></thead><tbody>"
            + "".join(body) + "</tbody></table>")


# ---------------------------------------------------------------------------
# Styling: small inline CSS. Colours use the theme's text colour and translucent tints,
# so the page also reads correctly with a dark theme (no hard-coded white backgrounds).
# ---------------------------------------------------------------------------

CSS = """
<style>
[data-testid="stMainBlockContainer"], .block-container { max-width: 1100px; padding-top: 64px; }
.rg-head { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:8px; }
.rg-title { font-size:1.75rem; font-weight:700; letter-spacing:-0.01em; }
.rg-sub { opacity:.75; margin-top:4px; }
.rg-tag { font-size:.75rem; padding:4px 8px; border-radius:8px; opacity:.7; border:1px solid rgba(127,127,127,.35); white-space:nowrap; }
.rg-card { border:1px solid rgba(127,127,127,.25); border-radius:12px; padding:16px 24px; margin:8px 0 16px 0;
           background:rgba(127,127,127,.04); }
.rg-status-label { font-size:1.5rem; font-weight:700; letter-spacing:.02em; }
.rg-next { margin-top:8px; font-size:1.02rem; }
.rg-muted { opacity:.65; font-size:.85rem; margin-top:4px; }
.rg-two { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:8px; }
.rg-two .rg-card { margin:0; }
.rg-kicker { font-size:.8rem; text-transform:uppercase; letter-spacing:.06em; opacity:.75; font-weight:600; }
.rg-big { font-size:1.15rem; font-weight:600; margin-top:8px; }
.rg-rg { border-width:2px; background:rgba(15,110,110,.06); }
.rg-pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:.75rem; font-weight:600; line-height:1.5; white-space:nowrap; }
.rg-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:.8rem; line-height:1.6;
           border:1px solid rgba(127,127,127,.25); border-radius:8px; padding:8px 0; background:rgba(127,127,127,.05); }
.rg-line { padding:0 16px; white-space:pre-wrap; overflow-wrap:anywhere; }
.rg-ok, .rg-bad { padding-top:4px; padding-bottom:4px; }
.rg-ok > span:first-child, .rg-bad > span:first-child { white-space:pre-wrap; overflow-wrap:anywhere; }
.rg-ok { background:rgba(46,125,50,.14); border-left:3px solid #2E7D32; }
.rg-bad { background:rgba(192,54,44,.16); border-left:3px solid #C0362C; }
.rg-ann { display:block; font-weight:700; white-space:normal; font-size:.78rem; }
.rg-ok .rg-ann { color:#2E7D32; } .rg-bad .rg-ann { color:#C0362C; }
.rg-table { width:100%; border-collapse:collapse; font-size:.88rem; margin:8px 0 16px 0; }
.rg-table th { text-align:left; font-weight:600; opacity:.75; border-bottom:1px solid rgba(127,127,127,.35); padding:8px; }
.rg-table td { border-bottom:1px solid rgba(127,127,127,.15); padding:8px; vertical-align:top; }
.rg-num { font-variant-numeric: tabular-nums; }
.rg-neg { color:#C0362C; font-weight:600; } .rg-pos { color:#2E7D32; font-weight:600; }
.rg-uv { color:#C0362C; font-size:.8rem; font-weight:600; }
.rg-appr { padding:8px 0 16px 0; border-bottom:1px solid rgba(127,127,127,.15); }
.rg-path { margin-top:8px; display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
.rg-chip { display:inline-block; padding:4px 12px; border-radius:999px; font-size:.82rem;
           border:1px solid rgba(15,110,110,.55); background:rgba(15,110,110,.07); }
.rg-chip-uv { border:1px dashed #B7791F; background:rgba(183,121,31,.07); }
.rg-arrow { opacity:.55; }
.rg-src { font-size:.78rem; }
.rg-note { margin-top:8px; line-height:1.6; }
.rg-reject { margin-top:8px; padding:8px 16px; border-left:3px solid #C0362C; background:rgba(192,54,44,.08); border-radius:4px; }
.rg-foot { margin-top:32px; padding-top:16px; border-top:1px solid rgba(127,127,127,.25); font-size:.82rem; opacity:.7; }
@media (max-width: 760px) { .rg-two { grid-template-columns:1fr; } }
</style>
"""


def html_block(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


def render_case(view: CaseView, use_live_cache: bool) -> None:
    d = view.decision
    sequence = [x.status.value for _, x in view.results]
    html_block(status_banner(d, sequence))

    cards = naive_cards(view)
    if cards:
        html_block(cards)

    st.subheader("What the AI read")
    if view.rep is None:
        html_block('<div class="rg-muted">Structured input (no AI step). This case starts from a JSON fixture, '
                   "so no extraction was needed.</div>")
    else:
        html_block(f"<div>{extraction_pill(view.rep)}</div>")
        if use_live_cache and view.case_id not in LIVE_CACHE_CASES:
            html_block('<div class="rg-muted">No saved live output for this case, so the hand-written stand-in is used.</div>')
        left, right = st.columns([1.3, 1], gap="medium")
        with left:
            html_block('<div class="rg-kicker">Corrected form text, as the AI read it</div>')
            html_block(evidence_panel(view.text or "", view.rep.checks))
        with right:
            html_block('<div class="rg-kicker">Extracted values, checked by code against the text</div>')
            html_block(checks_table(view.rep.checks))
            verdict = ("All values verified against the source text." if view.rep.all_verified else
                       "UNVERIFIED values were NOT replaced. The case goes to a specialist reviewer.")
            html_block(f'<div class="rg-muted">{e(verdict)}</div>')
        with st.expander("Source form text (raw)"):
            st.code(view.text or "", language=None)

    st.subheader("What changed")
    html_block(changes_table(d))

    st.subheader("Approvals that need re-review")
    html_block(approvals_html(d))

    st.subheader("Reviewer note")
    html_block(note_html(view.note))

    with st.expander("Reasons and evidence"):
        ev = d.evidence
        st.markdown(f"**Accepted document:** `{ev.accepted_doc_id}`  \n**Correction document:** `{ev.correction_doc_id}`  \n"
                    f"**Return status:** {ev.return_status} ({ev.return_status_source})  \n"
                    f"**Correction fingerprint:** `{d.correction_fingerprint}`")
        for n, (_, x) in enumerate(view.results, 1):
            if len(view.results) > 1:
                st.markdown(f"**Submission {n} of {len(view.results)}: {x.status.value}**")
            st.markdown("\n".join(f"- {r}" for r in x.reasons))
        if ev.findings:
            st.markdown("**Findings:** " + ", ".join(f"`{f.code}` ({f.category}{', ' + f.field if f.field else ''})"
                                                     for f in ev.findings))


def render_all_cases() -> None:
    rows, ok = all_cases()
    matched = sum(r["match"] == "match" for r in rows)
    colour = "#2E7D32" if ok else "#C0362C"
    html_block(f'<div class="rg-card" style="border-left:6px solid {colour};"><div class="rg-status-label" '
               f'style="color:{colour};">{matched} of {len(rows)} match expected</div>'
               '<div class="rg-muted">Same logic as <code>python3 cli.py --all</code> (no audit log written from the UI).</div></div>')
    html_block(all_cases_html(rows))


def main() -> None:
    st.set_page_config(page_title="ReturnGuard", layout="wide")
    html_block(CSS)

    with st.sidebar:
        st.markdown("### Case")
        case_id = st.selectbox("Test case", CASE_ORDER, index=0, format_func=case_label, key="case")
        st.caption(fixture(case_id).description)
        use_live = st.toggle("Use saved live AI outputs where available", value=True, key="use_live")
        st.caption("ON: T1, T4, T5 replay their recorded LIVE outputs (no API call). "
                   "T12 uses a hand-written AI output (MOCKED); all other cases start from structured input with no AI step.")
        st.markdown("---")
        st.info("**About**  \nSynthetic data only. Not tax advice. Decisions require CPA review.")

    html_block('<div class="rg-head"><div><div class="rg-title">ReturnGuard</div>'
               '<div class="rg-sub">Catches approvals that go stale when a corrected tax form arrives.</div></div>'
               '<div class="rg-tag">Synthetic data · prototype</div></div>')

    tab_case, tab_all = st.tabs(["Case review", "All cases"])
    with tab_case:
        html_block(f'<div class="rg-muted">Case <b>{e(case_label(case_id))}</b></div>')
        render_case(run_view(case_id, use_live), use_live)
    with tab_all:
        render_all_cases()

    html_block(f'<div class="rg-foot">{e(FOOTER)}</div>')


if __name__ == "__main__":  # streamlit run / AppTest execute the script as __main__
    main()
