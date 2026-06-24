"""
RHNS Neural Grounder v1.0
Bridges neural (LLM) outputs to symbolic (knowledge graph) predicates.
Implements post-extraction correction pattern (May 2026).
"""
import re
from dataclasses import dataclass
from typing import Any

@dataclass
class GroundedPredicate:
    subject: str
    predicate: str
    object_: str
    object_type: str
    confidence: float
    raw_source: str
    correction_applied: bool = False
    correction_reason: str | None = None

class NeuralGrounder:
    """
    Extracts structured predicates from LLM free-text output.
    Validates against ontology constraints.
    Batches corrections for efficiency (single post-extraction pass).
    """

    VALID_PREDICATES = {
        "is_a", "has_property", "belongs_to", "caused_by",
        "precedes", "follows", "contradicts", "supports",
        "has_value", "has_status", "has_owner", "has_domain"
    }

    VALID_OBJECT_TYPES = {
        "entity", "value", "status", "domain", "timestamp",
        "agent", "goal", "action", "outcome", "belief"
    }

    def extract(self, llm_output: str, context: dict[str, Any]) -> list[GroundedPredicate]:
        """
        Extract structured predicates from LLM free text.
        Returns list of grounded predicates ready for knowledge graph insertion.
        """
        predicates = self._parse_assertions(llm_output)
        violations = self._check_constraints(predicates)
        corrected = self._apply_corrections(predicates, violations)
        return corrected

    def _parse_assertions(self, text: str) -> list[GroundedPredicate]:
        """
        Parse [ASSERT: subject | predicate | object | type | confidence] tags
        embedded in LLM output by prompt engineering.
        """
        pattern = r'[ASSERT:s*([^|]+)|([^|]+)|([^|]+)|([^|]+)|([0-9.]+)]'
        results = []
        for match in re.finditer(pattern, text):
            subject, predicate, obj, obj_type, conf = [m.strip() for m in match.groups()]
            results.append(GroundedPredicate(
                subject=subject,
                predicate=predicate.lower(),
                object_=obj,
                object_type=obj_type.lower(),
                confidence=float(conf),
                raw_source=match.group(0)
            ))
        return results

    def _check_constraints(
        self,
        predicates: list[GroundedPredicate]
    ) -> dict[int, list[str]]:
        """Check ontology constraints. Return {index: [violations]}."""
        violations: dict[int, list[str]] = {}
        for i, p in enumerate(predicates):
            v = []
            if p.predicate not in self.VALID_PREDICATES:
                v.append(f"Unknown predicate '{p.predicate}'")
            if p.object_type not in self.VALID_OBJECT_TYPES:
                v.append(f"Unknown object type '{p.object_type}'")
            if not (0.0 <= p.confidence <= 1.0):
                v.append(f"Confidence {p.confidence} out of range [0,1]")
            if v:
                violations[i] = v
        return violations

    def _apply_corrections(
        self,
        predicates: list[GroundedPredicate],
        violations: dict[int, list[str]]
    ) -> list[GroundedPredicate]:
        """
        Post-extraction correction pass (batched for efficiency).
        Soft corrections applied inline. Hard violations → mark invalid.
        """
        corrected = list(predicates)
        for i, violation_list in violations.items():
            p = corrected[i]
            # Soft correction: clamp confidence
            if any("out of range" in v for v in violation_list):
                p.confidence = max(0.0, min(1.0, p.confidence))
                p.correction_applied = True
                p.correction_reason = "Confidence clamped to [0,1]"
            # Hard correction: unknown predicate → mark as hypothesis
            if any("Unknown predicate" in v for v in violation_list):
                p.confidence = min(p.confidence, 0.3)
                p.correction_applied = True
                p.correction_reason = f"Unknown predicate — confidence penalized: {violation_list}"
        return corrected
