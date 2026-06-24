"""Tests for RHNS Symbolic Verifier"""
import sys
sys.path.insert(0, '/data/data/com.termux/files/home/garcar-control-plane')

from rhns.core.symbolic_verifier import SymbolicVerifier, VerificationResult

def test_pass_on_valid_action():
    v = SymbolicVerifier()
    action = {"type": "crm_write", "description": "Update lead status", "confidence": 0.9}
    report = v.verify_action(action, {})
    assert report.result == VerificationResult.PASS

def test_hard_fail_on_blocked_type():
    v = SymbolicVerifier()
    action = {"type": "financial_transfer_unverified", "description": "Send $500"}
    report = v.verify_action(action, {})
    assert report.result == VerificationResult.HARD_FAIL

def test_soft_fail_on_low_confidence():
    v = SymbolicVerifier()
    action = {"type": "crm_write", "description": "Update record", "confidence": 0.1}
    report = v.verify_action(action, {})
    assert report.result == VerificationResult.SOFT_FAIL

if __name__ == "__main__":
    test_pass_on_valid_action()
    test_hard_fail_on_blocked_type()
    test_soft_fail_on_low_confidence()
    print("All symbolic verifier tests passed.")
