"""Policy lifecycle: draft -> published -> archived, plus read models for the API."""

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine.catalog import CATALOG
from app.engine.formatting import format_expected
from app.engine.operators import OPERATORS
from app.models import Lender, PolicyRule, PolicyVersion, Program
from app.models.enums import PolicyStatus
from app.services.policy_mapper import rule_to_dict, to_engine_policy


class PolicyStateError(Exception):
    """The requested change is not allowed in the version's current state (HTTP 409)."""


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80]


def describe_condition(condition: dict[str, Any]) -> str:
    fdef, op = CATALOG.get(condition.get("field", "")), OPERATORS.get(condition.get("operator", ""))
    if fdef is None or op is None:
        return f"{condition.get('field')} {condition.get('operator')} {condition.get('value')}"
    return f"{fdef.label} {op.label} {format_expected(fdef, op, condition.get('value'))}".strip()


def describe_rule(rule: PolicyRule) -> str:
    if rule.kind == "any_of":
        return " OR ".join(c.get("label") or describe_condition(c) for c in rule.alternatives)
    return describe_condition(
        {"field": rule.field_key, "operator": rule.operator, "value": rule.value}
    )


def validation_errors(version: PolicyVersion) -> list[str]:
    errors = []
    if not version.programs:
        errors.append("A policy needs at least one program before it can be published.")
    ranks = [p.rank for p in version.programs]
    if len(ranks) != len(set(ranks)):
        errors.append(
            "Duplicate program ranks found in policy. Each program must have a unique rank."
        )
    try:
        to_engine_policy(version)
    except ValidationError as error:
        errors += [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()]
    return errors


def require_draft(version: PolicyVersion) -> None:
    if version.status != PolicyStatus.DRAFT:
        raise PolicyStateError(
            f"Version {version.version_number} is {version.status}; only drafts can be edited. "
            "Create a draft from the published version first."
        )


def get_version(lender: Lender, status: PolicyStatus) -> PolicyVersion | None:
    return next((v for v in lender.policy_versions if v.status == status), None)


def _clone_rule(rule: PolicyRule) -> PolicyRule:
    data = rule_to_dict(rule)
    return PolicyRule(
        kind=data["kind"], label=data["label"], category=data["category"],
        severity=data["severity"], field_key=data["field"], operator=data["operator"],
        value=data["value"], alternatives=data["alternatives"],
        applies_when=data["applies_when"], message_template=data["message_template"],
        source_document=data.get("source_document"),
        source_quote=data.get("source_quote"),
        source_page=data.get("source_page"),
        sort_order=rule.sort_order,
    )  # fmt: skip


def create_draft(session: Session, lender: Lender) -> PolicyVersion:
    """Returns the existing draft, or clones the published version into a new one."""
    existing = get_version(lender, PolicyStatus.DRAFT)
    if existing:
        return existing
    published = get_version(lender, PolicyStatus.PUBLISHED)
    latest = session.scalar(
        select(func.max(PolicyVersion.version_number)).where(PolicyVersion.lender_id == lender.id)
    )
    draft = PolicyVersion(
        lender_id=lender.id,
        version_number=(latest or 0) + 1,
        status=PolicyStatus.DRAFT,
        source_document=published.source_document if published else None,
        notes=f"Draft based on version {published.version_number}." if published else None,
    )
    if published:
        draft.rules = [_clone_rule(r) for r in published.rules if r.program_id is None]
        for program in published.programs:
            clone = Program(
                name=program.name, rank=program.rank, decision_mode=program.decision_mode,
                description=program.description, applies_when=program.applies_when,
                details=program.details,
            )  # fmt: skip
            draft.programs.append(clone)
            for rule in program.rules:
                copy = _clone_rule(rule)
                copy.policy_version = draft
                clone.rules.append(copy)
    lender.policy_versions.append(draft)
    session.flush()
    return draft


def publish(session: Session, version: PolicyVersion) -> PolicyVersion:
    require_draft(version)
    errors = validation_errors(version)
    if errors:
        raise PolicyStateError("Cannot publish: " + " ".join(errors))
    current = get_version(version.lender, PolicyStatus.PUBLISHED)
    if current:
        current.status = PolicyStatus.ARCHIVED
        # Flush first: the partial unique index allows only one published row per lender.
        session.flush()
    version.status = PolicyStatus.PUBLISHED
    version.published_at = datetime.now(UTC)
    session.flush()
    return version
