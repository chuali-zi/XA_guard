import type {
  AgentAssignment,
  ApiErrorBody,
  Assignment,
  Effect,
  TicketResult,
  UndoRequest,
  UserProfile,
} from "./types";

export class ControlError extends Error {
  constructor(public status: number, public detail: ApiErrorBody) {
    super(detail.message);
  }
}

export class ControlApi {
  constructor(
    private readonly basePath: string,
    private readonly getToken: () => Promise<string>,
    private readonly getAgentId: () => string,
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = await this.getToken();
    const agentId = this.getAgentId();
    if (!agentId) throw new Error("请选择已授权 Agent");
    const headers = new Headers(init.headers);
    headers.set("authorization", `Bearer ${token}`);
    headers.set("x-agent-id", agentId);
    headers.set("x-correlation-id", crypto.randomUUID());
    headers.set("accept", "application/json");
    if (init.body) headers.set("content-type", "application/json");
    const response = await fetch(`${this.basePath}${path}`, { ...init, headers, credentials: "omit", cache: "no-store" });
    if (response.status === 204) return undefined as T;
    const body = await response.json().catch(() => ({ code: "invalid_response", message: "服务返回了不可解析的响应", trace_id: response.headers.get("x-correlation-id") || "" }));
    if (!response.ok) throw new ControlError(response.status, body as ApiErrorBody);
    return body as T;
  }

  me() { return this.request<UserProfile>("/me"); }
  agents() { return this.request<{ items: AgentAssignment[] }>("/agents"); }
  createTicket(value: Record<string, unknown>) {
    return this.request<TicketResult>("/tickets", { method: "POST", body: JSON.stringify(value) });
  }
  effects() { return this.request<{ items: Effect[] }>("/effects"); }
  effect(effectId: string) { return this.request<Effect>(`/effects/${encodeURIComponent(effectId)}`); }
  requestUndo(effectId: string, reason: string) {
    return this.request<{ request_id: string; created: boolean; status: string }>(`/effects/${encodeURIComponent(effectId)}/undo-requests`, {
      method: "POST",
      headers: { "idempotency-key": crypto.randomUUID() },
      body: JSON.stringify({ reason }),
    });
  }
  undoRequests(status = "pending") {
    return this.request<{ items: UndoRequest[] }>(`/undo-requests?status=${encodeURIComponent(status)}`);
  }
  decide(requestId: string, decision: "approve" | "reject", reason: string) {
    return this.request<UndoRequest>(`/undo-requests/${encodeURIComponent(requestId)}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision, reason }),
    });
  }
  retry(requestId: string) {
    return this.request<{ request_id: string; status: string }>(`/undo-requests/${encodeURIComponent(requestId)}/retry`, { method: "POST" });
  }
  assignments() { return this.request<{ items: Assignment[] }>("/assignments"); }
  createAssignment(value: Record<string, unknown>) {
    return this.request<Assignment>("/assignments", {
      method: "POST",
      headers: { "if-none-match": "*" },
      body: JSON.stringify(value),
    });
  }
  deleteAssignment(assignmentId: string, version: number) {
    return this.request<void>(`/assignments/${encodeURIComponent(assignmentId)}`, {
      method: "DELETE",
      headers: { "if-match": `\"v${version}\"` },
    });
  }
}
