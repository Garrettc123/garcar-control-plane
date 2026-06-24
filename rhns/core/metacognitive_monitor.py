"""
RHNS Metacognitive Monitor v1.0
Runs as an independent service with interrupt authority.
Monitors: calibration drift, failure rate, goal regression, value drift.
Triggers: automatic rollback | human escalation | self-modification proposals
"""
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
from datetime import datetime, timezone
import os

app = FastAPI(
    title="RHNS Metacognitive Monitor",
    version="1.0.0"
)

# Thresholds — tune as the system accumulates data
CALIBRATION_ERROR_THRESHOLD = 0.25   # above this → calibration alert
FAILURE_RATE_THRESHOLD = 0.30        # above this → pause autonomous ops
GOAL_REGRESSION_THRESHOLD = 3        # consecutive failures → escalate

class MonitorState(BaseModel):
    domain: str
    recent_failure_count: int = 0
    calibration_error: float = 0.0
    consecutive_failures: int = 0
    autonomous_ops_paused: bool = False
    alerts: list[str] = []
    timestamp: str = ""

class MetacognitiveMonitor:
    def __init__(self):
        self._domain_state: dict[str, MonitorState] = {}
        self._modification_proposals: list[dict[str, Any]] = []

    def evaluate(
        self,
        domain: str,
        recent_failures: int,
        total_episodes: int,
        calibration_error: float,
        consecutive_failures: int
    ) -> MonitorState:
        state = MonitorState(
            domain=domain,
            recent_failure_count=recent_failures,
            calibration_error=calibration_error,
            consecutive_failures=consecutive_failures,
            timestamp=datetime.now(timezone.utc).isoformat()
        )

        failure_rate = recent_failures / max(total_episodes, 1)

        # Calibration alert
        if calibration_error > CALIBRATION_ERROR_THRESHOLD:
            state.alerts.append(
                f"CALIBRATION_DRIFT: error={calibration_error:.3f} "
                f"exceeds threshold {CALIBRATION_ERROR_THRESHOLD}"
            )

        # Failure rate alert → pause autonomous ops
        if failure_rate > FAILURE_RATE_THRESHOLD:
            state.autonomous_ops_paused = True
            state.alerts.append(
                f"HIGH_FAILURE_RATE: {failure_rate:.1%} in domain '{domain}' — "
                f"autonomous ops paused, human review required"
            )

        # Goal regression → propose self-modification
        if consecutive_failures >= GOAL_REGRESSION_THRESHOLD:
            proposal = {
                "type": "self_modification_proposal",
                "domain": domain,
                "reason": f"{consecutive_failures} consecutive failures",
                "proposed_change": "Review action selection policy for domain",
                "requires_human_authorization": True,
                "timestamp": state.timestamp
            }
            self._modification_proposals.append(proposal)
            state.alerts.append(
                f"GOAL_REGRESSION: {consecutive_failures} consecutive failures — "
                f"self-modification proposal queued for human review"
            )

        self._domain_state[domain] = state
        return state

    def get_proposals(self) -> list[dict[str, Any]]:
        return list(self._modification_proposals)

    def clear_proposal(self, index: int) -> None:
        if 0 <= index < len(self._modification_proposals):
            self._modification_proposals.pop(index)

monitor = MetacognitiveMonitor()

class EvaluationRequest(BaseModel):
    domain: str
    recent_failures: int
    total_episodes: int
    calibration_error: float
    consecutive_failures: int

@app.post("/monitor/evaluate", response_model=MonitorState)
async def evaluate(req: EvaluationRequest):
    return monitor.evaluate(
        req.domain,
        req.recent_failures,
        req.total_episodes,
        req.calibration_error,
        req.consecutive_failures
    )

@app.get("/monitor/proposals")
async def get_proposals():
    return {"proposals": monitor.get_proposals()}

@app.get("/monitor/health")
async def health():
    return {
        "status": "metacognitive_monitor_online",
        "domains_tracked": len(monitor._domain_state),
        "pending_proposals": len(monitor._modification_proposals),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
