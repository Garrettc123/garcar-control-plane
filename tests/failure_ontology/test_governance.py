"""Tests for RHNS Governance Engine"""
import sys
sys.path.insert(0, '/data/data/com.termux/files/home/garcar-control-plane')

from rhns.governance.policy_axioms import GovernanceEngine, GovernanceDecision, RiskTier

def test_tier1_block():
    g = GovernanceEngine()
    result = g.evaluate("delete_production_data", {})
    assert result.decision == GovernanceDecision.BLOCK

def test_critical_requires_human():
    g = GovernanceEngine()
    result = g.evaluate("financial_transfer", {})
    assert result.decision == GovernanceDecision.REQUIRE_HUMAN

def test_low_risk_allowed():
    g = GovernanceEngine()
    result = g.evaluate("crm_read", {})
    assert result.decision == GovernanceDecision.ALLOW

def test_high_risk_audited():
    g = GovernanceEngine()
    result = g.evaluate("code_deploy_production", {})
    assert result.decision == GovernanceDecision.ALLOW_WITH_AUDIT
    assert result.audit_required == True

if __name__ == "__main__":
    test_tier1_block()
    test_critical_requires_human()
    test_low_risk_allowed()
    test_high_risk_audited()
    print("All governance tests passed.")
