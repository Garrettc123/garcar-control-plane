"""
RHNS Base Agent v1.0
All RHNS agents inherit from this. Enforces:
- Capability manifest declaration
- Governance check before every action
- Episodic memory logging after every action
"""
from abc import ABC, abstractmethod
from typing import Any
from rhns.governance.policy_axioms import GovernanceEngine, GovernanceDecision
from rhns.memory.memory_manager import MemoryManager, EpisodicMemoryRecord
import uuid

class BaseAgent(ABC):
    def __init__(self, agent_id: str, domain: str):
        self.agent_id = agent_id
        self.domain = domain
        self.governance = GovernanceEngine()
        self.memory = MemoryManager()
        self.capability_manifest = self._declare_capabilities()

    @abstractmethod
    def _declare_capabilities(self) -> dict[str, Any]:
        """Every agent must declare what it can do."""
        ...

    @abstractmethod
    async def _execute_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Core task execution — implemented per agent."""
        ...

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """
        Governed execution wrapper.
        1. Governance check
        2. Execute if authorized
        3. Log episode
        """
        operation = task.get("operation", "unknown")
        policy = self.governance.evaluate(operation, task)

        if policy.decision == GovernanceDecision.BLOCK:
            outcome = {"success": False, "blocked": True, "reason": policy.rationale}
        elif policy.decision == GovernanceDecision.REQUIRE_HUMAN:
            outcome = {"success": False, "escalated": True, "reason": policy.rationale}
        else:
            outcome = await self._execute_task(task)

        # Log episode to memory
        self.memory.record_episode(EpisodicMemoryRecord(
            episode_id=str(uuid.uuid4()),
            agent_id=self.agent_id,
            goal_context=str(task.get("goal", operation)),
            action_taken=task,
            outcome=outcome,
            success=outcome.get("success", False),
            reasoning_trace=[f"Governance: {policy.decision} | Risk: {policy.risk_tier}"]
        ))

        return outcome
