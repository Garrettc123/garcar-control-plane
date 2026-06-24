"""
RHNS Governance Layer v1.0
Three-tier guardrail architecture.
Tier 1: Foundational | Tier 2: Risk-Based | Tier 3: Societal
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any

class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class GovernanceDecision(str, Enum):
    ALLOW = "allow"
    ALLOW_WITH_AUDIT = "allow_with_audit"
    REQUIRE_HUMAN = "require_human"
    BLOCK = "block"

@dataclass
class PolicyEvaluation:
    decision: GovernanceDecision
    risk_tier: RiskTier
    rationale: str
    audit_required: bool

# Tier 1: Foundational — never overridable
TIER_1_BLOCKED_OPERATIONS = {
    "delete_production_data",
    "disable_audit_logging",
    "override_governance_layer",
    "expose_pii_unencrypted",
}

# Tier 2: Risk classification by action domain
RISK_CLASSIFICATION = {
    "crm_read": RiskTier.LOW,
    "crm_write": RiskTier.LOW,
    "financial_read": RiskTier.MEDIUM,
    "financial_write": RiskTier.HIGH,
    "financial_transfer": RiskTier.CRITICAL,
    "code_deploy_staging": RiskTier.MEDIUM,
    "code_deploy_production": RiskTier.HIGH,
    "agent_self_modify": RiskTier.HIGH,
}

class GovernanceEngine:
    def evaluate(self, operation: str, context: dict[str, Any]) -> PolicyEvaluation:
        # Tier 1 check
        if operation in TIER_1_BLOCKED_OPERATIONS:
            return PolicyEvaluation(
                decision=GovernanceDecision.BLOCK,
                risk_tier=RiskTier.CRITICAL,
                rationale=f"Tier 1 foundational guardrail: '{operation}' is permanently blocked",
                audit_required=True
            )

        # Tier 2 risk-based check
        risk = RISK_CLASSIFICATION.get(operation, RiskTier.MEDIUM)

        if risk == RiskTier.CRITICAL:
            return PolicyEvaluation(
                decision=GovernanceDecision.REQUIRE_HUMAN,
                risk_tier=risk,
                rationale="Critical operation requires human authorization",
                audit_required=True
            )
        elif risk == RiskTier.HIGH:
            return PolicyEvaluation(
                decision=GovernanceDecision.ALLOW_WITH_AUDIT,
                risk_tier=risk,
                rationale="High-risk operation — proceeding with full audit trail",
                audit_required=True
            )
        else:
            return PolicyEvaluation(
                decision=GovernanceDecision.ALLOW,
                risk_tier=risk,
                rationale="Operation within autonomous authority",
                audit_required=False
            )
