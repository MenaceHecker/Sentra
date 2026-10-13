// Mirrors backend/app/schemas.py. Kept as plain types, not generated,
// since the backend is small and stable enough that hand-keeping these
// in sync is cheaper than wiring up a codegen step for a portfolio project.

export type IncidentStatus =
  | "investigating"
  | "hypothesis_ready"
  | "action_pending"
  | "resolved"
  | "closed";

export type ToolCallStatus = "proposed" | "approved" | "rejected" | "executed" | "failed";

export type Confidence = "low" | "medium" | "high";

export interface User {
  id: string;
  email: string;
  display_name: string | null;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface IncidentOut {
  id: string;
  title: string;
  description: string | null;
  status: IncidentStatus;
  severity: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ToolCallOut {
  id: string;
  tool_name: string;
  tool_input_json: string;
  tool_output_json: string | null;
  is_side_effecting: boolean;
  status: ToolCallStatus;
  requested_at: string;
  decided_at: string | null;
  executed_at: string | null;
}

export interface EvidenceOut {
  id: string;
  tool_call_id: string | null;
  evidence_type: "log" | "metric" | "deploy" | "runbook";
  summary: string;
  raw_ref: string | null;
  relevance_score: number | null;
  created_at: string;
}

export interface HypothesisCitationOut {
  evidence_id: string;
}

export interface HypothesisOut {
  id: string;
  summary: string;
  confidence: Confidence;
  reasoning: string | null;
  created_at: string;
  citations: HypothesisCitationOut[];
}

export interface IncidentDetailOut extends IncidentOut {
  evidence: EvidenceOut[];
  hypotheses: HypothesisOut[];
  tool_calls: ToolCallOut[];
}

export interface InvestigateResponse {
  incident: IncidentDetailOut;
  events_summary: string[];
}

// SSE events yielded by POST /api/incidents/{id}/investigate (Phase 9).
// A "done" event always carries an InvestigateResponse as its final state.

export interface InvestigationToolCallEvent {
  tool_call_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  status: ToolCallStatus;
  output_summary: string;
}

export interface InvestigationHypothesisEvent {
  hypothesis_id: string;
  summary: string;
  confidence: Confidence;
  reasoning: string;
  proposed_actions: Record<string, unknown>[];
}

export interface InvestigationErrorEvent {
  message: string;
}

export interface AuditLogOut {
  id: string;
  incident_id: string;
  actor: "system" | "user";
  action: string;
  detail_json: string | null;
  created_at: string;
}

export interface ScenarioOut {
  id: string;
  title: string;
  service: string;
  description: string;
  active: boolean;
}

export interface InjectScenarioResponse {
  scenario_id: string;
  service: string;
  injected_at: string;
  deploy: {
    sha: string;
    service: string;
    message: string;
    deployed_at: string;
    deployed_by: string;
  } | null;
}

export interface RunbookSearchResultOut {
  document_title: string;
  start_line: number;
  end_line: number;
  content: string;
  distance: number;
}

// ---- Tool output shapes (not Pydantic schemas, just what each read-only
// tool's JSON output looks like, parsed out of ToolCallOut.tool_output_json) ----

export interface LogToolOutput {
  service: string;
  count: number;
  logs: { timestamp: string; level: string; message: string; trace_id: string | null }[];
}

export interface MetricToolOutput {
  service: string;
  metric_name: string;
  count: number;
  points: { timestamp: string; value: number }[];
}

export interface DeployToolOutput {
  service: string;
  count: number;
  deploys: { sha: string; message: string; deployed_at: string; deployed_by: string }[];
}

export interface RunbookToolOutput {
  query: string;
  count: number;
  results: { document_title: string; start_line: number; end_line: number; content: string; distance: number }[];
}

export interface ServiceStatusToolOutput {
  service: string;
  status: "healthy" | "degraded" | "unknown";
  latest_error_rate: number | null;
  as_of: string | null;
}
