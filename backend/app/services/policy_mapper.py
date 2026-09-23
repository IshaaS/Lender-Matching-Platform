"""Translation between policy rows and the engine's Policy document. The only place that
knows both shapes."""

from typing import Any

from app.engine.policy import Policy
from app.models import PolicyRule, PolicyVersion, Program


def rule_to_dict(rule: PolicyRule) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "kind": rule.kind,
        "label": rule.label,
        "category": rule.category,
        "severity": rule.severity,
        "field": rule.field_key,
        "operator": rule.operator,
        "value": rule.value,
        "alternatives": rule.alternatives or [],
        "applies_when": rule.applies_when or [],
        "message_template": rule.message_template,
        "source_document": rule.source_document,
        "source_quote": rule.source_quote,
        "source_page": rule.source_page,
    }


def rule_from_dict(data: dict[str, Any], sort_order: int = 0) -> PolicyRule:
    return PolicyRule(
        kind=data.get("kind", "simple"),
        label=data["label"],
        category=data.get("category", "other"),
        severity=data.get("severity", "hard"),
        field_key=data.get("field"),
        operator=data.get("operator"),
        value=data.get("value"),
        alternatives=data.get("alternatives") or [],
        applies_when=data.get("applies_when") or [],
        message_template=data.get("message_template"),
        source_document=data.get("source_document"),
        source_quote=data.get("source_quote"),
        source_page=data.get("source_page"),
        sort_order=sort_order,
    )


def to_engine_policy(version: PolicyVersion) -> Policy:
    """Raises pydantic.ValidationError if the stored policy is not evaluable."""
    return Policy.model_validate(
        {
            "lender_id": str(version.lender_id),
            "lender_name": version.lender.name,
            "version_id": str(version.id),
            "version_number": version.version_number,
            "rules": [rule_to_dict(r) for r in version.rules if r.program_id is None],
            "programs": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "rank": p.rank,
                    "decision_mode": p.decision_mode or "automatic",
                    "description": p.description,
                    "applies_when": p.applies_when or [],
                    "details": p.details or {},
                    "rules": [rule_to_dict(r) for r in p.rules],
                }
                for p in version.programs
            ],
        }
    )


def populate_version(version: PolicyVersion, policy: dict[str, Any]) -> None:
    """Fill an empty PolicyVersion from a policy dict (seed data or an extracted draft)."""
    for order, data in enumerate(policy.get("rules", [])):
        version.rules.append(rule_from_dict(data, order))
    for program_data in policy.get("programs", []):
        program = Program(
            name=program_data["name"],
            rank=program_data["rank"],
            decision_mode=program_data.get("decision_mode", "automatic"),
            description=program_data.get("description"),
            applies_when=program_data.get("applies_when") or [],
            details=program_data.get("details") or {},
        )
        version.programs.append(program)
        for order, data in enumerate(program_data.get("rules", [])):
            rule = rule_from_dict(data, order)
            rule.policy_version = version
            program.rules.append(rule)
