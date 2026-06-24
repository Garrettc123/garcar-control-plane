"""
RHNS Memory Manager v1.0
Four-tier hierarchy: L1 Working | L2 Episodic | L3 Procedural | L4 Semantic
"""
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone

@dataclass
class WorkingMemory:
    """L1: Active context — cleared each cognitive cycle."""
    context: dict[str, Any] = field(default_factory=dict)
    max_tokens: int = 8192

    def write(self, key: str, value: Any) -> None:
        self.context[key] = value

    def read(self, key: str) -> Any:
        return self.context.get(key)

    def clear(self) -> None:
        self.context = {}

    def broadcast(self) -> dict[str, Any]:
        """Global Workspace Theory: make all working memory available to all agents."""
        return dict(self.context)

@dataclass
class EpisodicMemoryRecord:
    """L2: Full cognitive episode."""
    episode_id: str
    agent_id: str
    goal_context: str
    action_taken: dict[str, Any]
    outcome: dict[str, Any]
    success: bool
    reasoning_trace: list[str]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

@dataclass
class ProceduralTemplate:
    """L3: Compiled skill — zero-inference execution."""
    template_name: str
    domain: str
    preconditions: dict[str, Any]
    action_sequence: list[dict[str, Any]]
    postconditions: dict[str, Any]
    success_rate: float = 0.0
    invocation_count: int = 0

class MemoryManager:
    """
    Coordinates all four memory tiers.
    Implements the Tri-Spirit habit compilation pattern:
    frequent successful episodes → procedural templates.
    """
    HABIT_COMPILATION_THRESHOLD = 10  # invocations before compiling to procedural

    def __init__(self):
        self.working = WorkingMemory()
        self._episodic_buffer: list[EpisodicMemoryRecord] = []
        self._procedural_cache: dict[str, ProceduralTemplate] = {}

    def record_episode(self, record: EpisodicMemoryRecord) -> None:
        self._episodic_buffer.append(record)
        self._check_habit_compilation(record)

    def _check_habit_compilation(self, record: EpisodicMemoryRecord) -> None:
        """Tri-Spirit: compile repeated successful patterns into procedural memory."""
        if not record.success:
            return
        key = f"{record.agent_id}:{record.goal_context}"
        if key in self._procedural_cache:
            self._procedural_cache[key].invocation_count += 1
        # Full Supabase persistence wired in Phase 2

    def get_relevant_episodes(
        self,
        goal_context: str,
        limit: int = 5
    ) -> list[EpisodicMemoryRecord]:
        """Retrieve recent episodes matching goal context."""
        return [
            ep for ep in self._episodic_buffer[-50:]
            if goal_context.lower() in ep.goal_context.lower()
        ][-limit:]
