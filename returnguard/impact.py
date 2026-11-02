"""Dependency walk: which approvals does a set of field changes make stale?

Everything comes from config/dependencies.yaml. No box names, return lines or approval IDs
live in this file: adding a field mapping is a config change only.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from .validate import FieldChange


class ImpactItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    form_type: str
    field: str
    return_line: str
    approval_id: str
    path: str  # e.g. "1099-DIV:1b -> Form 1040 line 3a -> APR-1040-L3A"
    source: str  # IRS URL from config, prefixed "UNVERIFIED: " when config flags the mapping
    unverified: bool = False


def load_dependencies(path: str | Path) -> dict:
    """Load config/dependencies.yaml as a plain dict."""
    return yaml.safe_load(Path(path).read_text())


def find_impact(changes: list[FieldChange], dependencies: dict) -> list[ImpactItem]:
    """One ImpactItem per (changed field, mapped return line). Order follows the changes, then config.

    De-duplicated on (field key, return line, approval). An approval reached through two changed
    fields appears once per field so the reviewer sees every path; use stale_approval_ids() for the set.
    """
    deps = dependencies.get("dependencies") or {}
    items: list[ImpactItem] = []
    seen: set[tuple[str, str, str]] = set()
    for ch in changes:
        key = f"{ch.form_type}:{ch.field}"
        for edge in deps.get(key) or []:
            ident = (key, edge["return_line"], edge["approval"])
            if ident in seen:
                continue
            seen.add(ident)
            unverified = bool(edge.get("unverified", False))
            source = str(edge.get("source", ""))
            items.append(
                ImpactItem(
                    form_type=ch.form_type,
                    field=ch.field,
                    return_line=edge["return_line"],
                    approval_id=edge["approval"],
                    path=f"{key} -> {edge['return_line']} -> {edge['approval']}",
                    source=f"UNVERIFIED: {source}" if unverified else source,
                    unverified=unverified,
                )
            )
    return items


def stale_approval_ids(items: list[ImpactItem]) -> list[str]:
    """Distinct approval IDs in first-seen order."""
    return list(dict.fromkeys(i.approval_id for i in items))
