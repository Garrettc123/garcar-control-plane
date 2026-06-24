-- RHNS Core Schema v1.0 | Garcar Enterprise | June 24, 2026
-- Architect: Garrett Carroll

-- Enable pgvector for semantic retrieval
CREATE EXTENSION IF NOT EXISTS vector;

-- Ontology: Entity types and predicate definitions
CREATE TABLE IF NOT EXISTS rhns_ontology_types (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type_name TEXT NOT NULL UNIQUE,
  parent_type_id UUID REFERENCES rhns_ontology_types(id),
  constraints JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Knowledge Graph: Typed, attributed, temporal triples
CREATE TABLE IF NOT EXISTS rhns_knowledge_graph (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id UUID NOT NULL,
  predicate TEXT NOT NULL,
  object_id UUID,
  object_literal TEXT,
  object_type TEXT NOT NULL,
  provenance TEXT NOT NULL,
  epistemic_status TEXT NOT NULL CHECK (
    epistemic_status IN (
      'known_fact','confident_inference','hypothesis','acknowledged_ignorance'
    )
  ),
  confidence FLOAT DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
  valid_from TIMESTAMPTZ DEFAULT NOW(),
  valid_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- L2 Episodic Memory
CREATE TABLE IF NOT EXISTS rhns_episodic_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_hash TEXT NOT NULL UNIQUE,
  goal_context TEXT NOT NULL,
  cognitive_stage TEXT NOT NULL CHECK (
    cognitive_stage IN ('perception','memory_update','planning','execution','reflection')
  ),
  agent_id TEXT NOT NULL,
  action_taken JSONB,
  outcome JSONB,
  success BOOLEAN,
  reasoning_trace TEXT,
  embedding VECTOR(1536),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- L3 Procedural Memory: Compiled skill templates
CREATE TABLE IF NOT EXISTS rhns_procedural_templates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  template_name TEXT NOT NULL,
  domain TEXT NOT NULL,
  preconditions JSONB NOT NULL,
  action_sequence JSONB NOT NULL,
  postconditions JSONB NOT NULL,
  success_rate FLOAT DEFAULT 0.0,
  invocation_count INT DEFAULT 0,
  source_episode_id UUID REFERENCES rhns_episodic_memory(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_validated_at TIMESTAMPTZ
);

-- Agent Registry
CREATE TABLE IF NOT EXISTS rhns_agent_registry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name TEXT NOT NULL,
  version TEXT NOT NULL,
  capability_manifest JSONB NOT NULL,
  performance_history JSONB,
  status TEXT DEFAULT 'active' CHECK (status IN ('active','sandboxed','deprecated')),
  parent_version_id UUID REFERENCES rhns_agent_registry(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Failure Ontology
CREATE TABLE IF NOT EXISTS rhns_failure_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  failure_class TEXT NOT NULL CHECK (
    failure_class IN (
      'contradiction','goal_regression','context_overflow',
      'tool_failure','value_drift','hallucination','calibration_error'
    )
  ),
  agent_id TEXT NOT NULL,
  episode_id UUID REFERENCES rhns_episodic_memory(id),
  diagnostic JSONB NOT NULL,
  recovery_action TEXT,
  resolved BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Metacognitive Confidence Calibration
CREATE TABLE IF NOT EXISTS rhns_confidence_calibration (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain TEXT NOT NULL,
  predicted_confidence FLOAT NOT NULL,
  actual_outcome BOOLEAN,
  calibration_error FLOAT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_kg_subject ON rhns_knowledge_graph(subject_id);
CREATE INDEX IF NOT EXISTS idx_kg_predicate ON rhns_knowledge_graph(predicate);
CREATE INDEX IF NOT EXISTS idx_kg_epistemic ON rhns_knowledge_graph(epistemic_status);
CREATE INDEX IF NOT EXISTS idx_kg_valid ON rhns_knowledge_graph(valid_from, valid_until);
CREATE INDEX IF NOT EXISTS idx_episodic_agent ON rhns_episodic_memory(agent_id);
CREATE INDEX IF NOT EXISTS idx_episodic_stage ON rhns_episodic_memory(cognitive_stage);
CREATE INDEX IF NOT EXISTS idx_failure_class ON rhns_failure_log(failure_class);
CREATE INDEX IF NOT EXISTS idx_failure_resolved ON rhns_failure_log(resolved);
