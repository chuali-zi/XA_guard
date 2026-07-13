export type ViewId = "agents" | "ticket" | "effects" | "approvals" | "assignments" | "evidence";

export interface PublicConfig {
  oidcIssuer: string;
  oidcClientId: string;
  apiBasePath: string;
  defaultAgentId: string;
  tokenStorage: "memory";
}

export interface UserProfile {
  subject: string;
  username: string;
  tenant_id: string;
  roles: string[];
  groups: string[];
  available_agents: string[];
  assignment_version: number;
}

export interface AgentAssignment {
  agent_id: string;
  name: string;
  description?: string;
  tools: string[];
  data_domains: string[];
  assignment_version: number;
}

export interface EffectEvent {
  seq: number;
  event_type: string;
  actor_sub: string;
  occurred_at: string;
  payload?: Record<string, unknown>;
  prev_hash: string;
  record_hash: string;
}

export interface Effect {
  effect_id: string;
  tenant_id: string;
  trace_id: string;
  principal_sub: string;
  principal_username: string;
  agent_id: string;
  data_domain: string;
  tool_name: string;
  side_effect_level: string;
  reversibility: string;
  status: string;
  prepared_at: string;
  completed_at?: string;
  undo_expires_at: string;
  result_sha256?: string;
  downstream_reference?: string;
  compensation_trace_id?: string;
  retry_count?: number;
  last_error_code?: string;
  events?: EffectEvent[];
}

export interface UndoRequest {
  request_id: string;
  effect_id: string;
  tenant_id: string;
  requester_sub: string;
  requester_username: string;
  status: string;
  approver_sub?: string;
  approver_username?: string;
  requested_at: string;
  decided_at?: string;
  tool_name: string;
  undo_expires_at: string;
}

export interface Assignment {
  assignment_id: string;
  tenant_id: string;
  subject_type: "person" | "group";
  subject_id: string;
  agent_id: string;
  tools: string[];
  data_domains: string[];
  valid_from: string;
  valid_until?: string;
  version: number;
  changed_by: string;
}

export interface TicketResult {
  effect_id: string;
  trace_id: string;
  status: string;
  undo_status: string;
  result?: Record<string, unknown>;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  trace_id: string;
}

