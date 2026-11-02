"""Session 2: impact.py. Dependency walk is driven only by config/dependencies.yaml."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from returnguard.impact import ImpactItem, find_impact, load_dependencies, stale_approval_ids
from returnguard.models import AcceptedDocument, CaseFixture
from returnguard.validate import FieldChange, load_forms, validate

ROOT = Path(__file__).resolve().parents[1]
SYN = ROOT / "data" / "synthetic"
D = Decimal


@pytest.fixture(scope="module")
def deps() -> dict:
    return load_dependencies(ROOT / "config" / "dependencies.yaml")


@pytest.fixture(scope="module")
def cfg() -> dict:
    return load_forms(ROOT / "config" / "forms.yaml")


def change(form: str, field: str, old: str, new: str) -> FieldChange:
    return FieldChange(form_type=form, field=field, old=D(old), new=D(new), delta=D(new) - D(old))


def case_impact(cid: str, cfg: dict, deps: dict) -> list[ImpactItem]:
    fx = CaseFixture.model_validate_json((SYN / "cases" / f"{cid}.json").read_text())
    c = fx.submissions[0]
    name = "accepted_w2_C-001_2025.json" if c.form_type == "W-2c" else "accepted_1099div_C-001_2025.json"
    a = AcceptedDocument.model_validate_json((SYN / name).read_text())
    return find_impact(validate(a, c, cfg).changes, deps)


@pytest.mark.parametrize(
    "cid,expected",
    [("T1", ["APR-1040-L3A", "APR-QDCG-WS"]), ("T2", ["APR-1040-L3B"]), ("T3", ["APR-1040-L3A", "APR-QDCG-WS"]),
     ("T4", ["APR-1040-L1A", "APR-WAGE-WP"]), ("T6", ["APR-1040-L25A"]), ("T14", []), ("T15", [])],
)
def test_case_impact_matches_fixture_expectation(cid, expected, cfg, deps):
    assert stale_approval_ids(case_impact(cid, cfg, deps)) == expected


def test_case_impact_equals_fixture_expected_block(cfg, deps):
    for cid in ("T1", "T2", "T4"):
        fx = CaseFixture.model_validate_json((SYN / "cases" / f"{cid}.json").read_text())
        assert stale_approval_ids(case_impact(cid, cfg, deps)) == fx.expected.stale_approvals


def test_T1_paths_and_sources(cfg, deps):
    items = case_impact("T1", cfg, deps)
    assert [i.path for i in items] == [
        "1099-DIV:1b -> Form 1040 line 3a -> APR-1040-L3A",
        "1099-DIV:1b -> Qualified Dividends and Capital Gain Tax Worksheet -> APR-QDCG-WS",
    ]
    assert items[0].source == "https://www.irs.gov/instructions/i1040sd"
    assert items[0].unverified is False


def test_unverified_flag_carried_from_config(cfg, deps):
    items = {i.approval_id: i for i in case_impact("T1", cfg, deps)}
    qdcg = items["APR-QDCG-WS"]
    assert qdcg.unverified is True
    assert qdcg.source.startswith("UNVERIFIED: ")
    assert "irs.gov" in qdcg.source


def test_2a_maps_to_schedule_d_and_worksheet(deps):
    items = find_impact([change("1099-DIV", "2a", "500.00", "650.00")], deps)
    assert [i.approval_id for i in items] == ["APR-SCHD-L13", "APR-QDCG-WS"]
    assert items[0].return_line == "Schedule D line 13"
    assert items[0].unverified is False and items[1].unverified is True


def test_dedup_and_stable_order(deps):
    ch = [change("1099-DIV", "1b", "2400.00", "1600.00"), change("1099-DIV", "2a", "500.00", "600.00")]
    items = find_impact(ch + ch, deps)  # duplicated input
    assert [i.path for i in items] == [
        "1099-DIV:1b -> Form 1040 line 3a -> APR-1040-L3A",
        "1099-DIV:1b -> Qualified Dividends and Capital Gain Tax Worksheet -> APR-QDCG-WS",
        "1099-DIV:2a -> Schedule D line 13 -> APR-SCHD-L13",
        "1099-DIV:2a -> Qualified Dividends and Capital Gain Tax Worksheet -> APR-QDCG-WS",
    ]
    assert stale_approval_ids(items) == ["APR-1040-L3A", "APR-QDCG-WS", "APR-SCHD-L13"]
    assert find_impact(ch, deps) == find_impact(ch, deps)


def test_unmapped_field_has_no_impact(deps):
    assert find_impact([change("1099-DIV", "7", "0.00", "45.00")], deps) == []
    assert find_impact([], deps) == []


def test_new_mapping_picked_up_from_config_without_code_change(tmp_path):
    cfg_file = tmp_path / "deps.yaml"
    cfg_file.write_text(yaml.safe_dump({
        "version": 1,
        "dependencies": {
            "1099-INT:1": [
                {"return_line": "Form 1040 line 2b", "approval": "APR-1040-L2B", "source": "https://example.invalid/i1040gi", "unverified": True},
            ],
        },
    }))
    items = find_impact([change("1099-INT", "1", "100.00", "150.00")], load_dependencies(cfg_file))
    assert items == [ImpactItem(
        form_type="1099-INT", field="1", return_line="Form 1040 line 2b", approval_id="APR-1040-L2B",
        path="1099-INT:1 -> Form 1040 line 2b -> APR-1040-L2B",
        source="UNVERIFIED: https://example.invalid/i1040gi", unverified=True,
    )]


def test_every_mapping_has_a_source(deps):
    for key, edges in deps["dependencies"].items():
        for e in edges:
            assert e.get("source"), key
