"""
RHNS Supabase Persistence v1.0
Connects the four-tier memory hierarchy to live Supabase tables.
"""
import os
from typing import Any
from supabase import create_client, Client

def get_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)

class SupabaseStore:
    def __init__(self):
        self.client = get_client()

    # ── Knowledge Graph ──────────────────────────────────────────
    def write_knowledge(
        self,
        subject_id: str,
        predicate: str,
        object_literal: str,
        object_type: str,
        provenance: str,
        epistemic_status: str,
        confidence: float = 1.0
    ) -> dict[str, Any]:
        return (
            self.client.table("rhns_knowledge_graph")
            .insert({
                "subject_id": subject_id,
                "predicate": predicate,
                "object_literal": object_literal,
                "object_type": object_type,
                "provenance": provenance,
                "epistemic_status": epistemic_status,
                "confidence": confidence
            })
            .execute()
            .data[0]
        )

    def query_knowledge(
        self,
        subject_id: str | None = None,
        predicate: str | None = None,
        min_confidence: float = 0.5
    ) -> list[dict[str, Any]]:
        q = (
            self.client.table("rhns_knowledge_graph")
            .select("*")
            .gte("confidence", min_confidence)
            .is_("valid_until", "null")   # only currently-valid facts
        )
        if subject_id:
            q = q.eq("subject_id", subject_id)
        if predicate:
            q = q.eq("predicate", predicate)
        return q.execute().data

    # ── Episodic Memory ──────────────────────────────────────────
    def log_episode(self, episode: dict[str, Any]) -> dict[str, Any]:
        return (
            self.client.table("rhns_episodic_memory")
            .insert(episode)
            .execute()
            .data[0]
        )

    def get_recent_episodes(
        self,
        agent_id: str,
        limit: int = 10
    ) -> list[dict[str, Any]]:
        return (
            self.client.table("rhns_episodic_memory")
            .select("*")
            .eq("agent_id", agent_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )

    # ── Failure Log ──────────────────────────────────────────────
    def log_failure(
        self,
        failure_class: str,
        agent_id: str,
        diagnostic: dict[str, Any],
        episode_id: str | None = None,
        recovery_action: str | None = None
    ) -> dict[str, Any]:
        return (
            self.client.table("rhns_failure_log")
            .insert({
                "failure_class": failure_class,
                "agent_id": agent_id,
                "diagnostic": diagnostic,
                "episode_id": episode_id,
                "recovery_action": recovery_action,
                "resolved": False
            })
            .execute()
            .data[0]
        )

    def get_unresolved_failures(self, limit: int = 20) -> list[dict[str, Any]]:
        return (
            self.client.table("rhns_failure_log")
            .select("*")
            .eq("resolved", False)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )

    # ── Agent Registry ───────────────────────────────────────────
    def register_agent(
        self,
        agent_name: str,
        version: str,
        capability_manifest: dict[str, Any]
    ) -> dict[str, Any]:
        # Upsert: update if agent+version exists, insert if not
        existing = (
            self.client.table("rhns_agent_registry")
            .select("id")
            .eq("agent_name", agent_name)
            .eq("version", version)
            .execute()
            .data
        )
        if existing:
            return existing[0]
        return (
            self.client.table("rhns_agent_registry")
            .insert({
                "agent_name": agent_name,
                "version": version,
                "capability_manifest": capability_manifest,
                "status": "active"
            })
            .execute()
            .data[0]
        )

    # ── Confidence Calibration ───────────────────────────────────
    def log_calibration(
        self,
        domain: str,
        predicted_confidence: float,
        actual_outcome: bool
    ) -> dict[str, Any]:
        error = abs(predicted_confidence - (1.0 if actual_outcome else 0.0))
        return (
            self.client.table("rhns_confidence_calibration")
            .insert({
                "domain": domain,
                "predicted_confidence": predicted_confidence,
                "actual_outcome": actual_outcome,
                "calibration_error": error
            })
            .execute()
            .data[0]
        )

    def get_calibration_score(self, domain: str) -> float:
        """Mean calibration error for a domain. Lower is better."""
        rows = (
            self.client.table("rhns_confidence_calibration")
            .select("calibration_error")
            .eq("domain", domain)
            .execute()
            .data
        )
        if not rows:
            return 0.0
        return sum(r["calibration_error"] for r in rows) / len(rows)
