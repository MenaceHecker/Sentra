import type {
  AuditLogOut,
  IncidentDetailOut,
  IncidentOut,
  InjectScenarioResponse,
  InvestigateResponse,
  InvestigationErrorEvent,
  InvestigationHypothesisEvent,
  InvestigationToolCallEvent,
  RunbookSearchResultOut,
  ScenarioOut,
  Token,
  User,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "sentra_token";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Private browsing / blocked storage: the session just won't persist
    // across a reload. Not worth surfacing an error for this.
  }
}

export function clearToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // see setToken
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    const text = await res.text();
    let message = text;
    try {
      const parsed = JSON.parse(text);
      message = parsed.detail ?? text;
    } catch {
      // not JSON, use the raw text
    }
    throw new ApiError(res.status, message || `API error ${res.status}`);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

// ---- Auth ----

export function register(email: string, password: string): Promise<Token> {
  return apiFetch<Token>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string): Promise<Token> {
  return apiFetch<Token>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function me(): Promise<User> {
  return apiFetch<User>("/api/auth/me");
}

// ---- Incidents ----

export function listIncidents(): Promise<IncidentOut[]> {
  return apiFetch<IncidentOut[]>("/api/incidents");
}

export function createIncident(title: string, description?: string): Promise<IncidentOut> {
  return apiFetch<IncidentOut>("/api/incidents", {
    method: "POST",
    body: JSON.stringify({ title, description: description ?? null }),
  });
}

export function getIncident(id: string): Promise<IncidentDetailOut> {
  return apiFetch<IncidentDetailOut>(`/api/incidents/${id}`);
}

export interface InvestigationStreamHandlers {
  onToolCall?: (event: InvestigationToolCallEvent) => void;
  onHypothesis?: (event: InvestigationHypothesisEvent) => void;
  onError?: (event: InvestigationErrorEvent) => void;
}

// Native EventSource can't do this: it's GET-only and can't send the
// Authorization header, but /investigate is a POST that needs a bearer
// token. So this reads the response body as a stream by hand and parses
// SSE frames itself. Resolves with the final "done" event's payload, which
// carries the fully refreshed incident, so the caller doesn't need a
// separate GET once the stream ends.
export async function streamInvestigation(
  id: string,
  handlers: InvestigationStreamHandlers,
  signal?: AbortSignal,
): Promise<InvestigateResponse> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_URL}/api/incidents/${id}/investigate`, {
    method: "POST",
    headers,
    signal,
  });

  if (!res.ok) {
    const text = await res.text();
    let message = text;
    try {
      message = JSON.parse(text).detail ?? text;
    } catch {
      // not JSON, use the raw text
    }
    throw new ApiError(res.status, message || `API error ${res.status}`);
  }
  if (!res.body) {
    throw new ApiError(0, "Streaming not supported by this browser");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done: InvestigateResponse | null = null;

  while (true) {
    const { done: streamDone, value } = await reader.read();
    if (streamDone) break;
    // Normalize CRLF (sse-starlette's default line separator) to LF so
    // frame/line splitting below doesn't need to care which one it got.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      let eventType = "message";
      const dataLines: string[] = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
      }
      if (dataLines.length === 0) continue;
      const data = JSON.parse(dataLines.join("\n"));

      switch (eventType) {
        case "tool_call":
          handlers.onToolCall?.(data as InvestigationToolCallEvent);
          break;
        case "hypothesis":
          handlers.onHypothesis?.(data as InvestigationHypothesisEvent);
          break;
        case "error":
          handlers.onError?.(data as InvestigationErrorEvent);
          break;
        case "done":
          done = data as InvestigateResponse;
          break;
      }
    }
  }

  if (done === null) {
    throw new ApiError(0, "Investigation stream ended without a result");
  }
  return done;
}

export function approveAction(incidentId: string, actionId: string) {
  return apiFetch(`/api/incidents/${incidentId}/actions/${actionId}/approve`, { method: "POST" });
}

export function rejectAction(incidentId: string, actionId: string) {
  return apiFetch(`/api/incidents/${incidentId}/actions/${actionId}/reject`, { method: "POST" });
}

export function getIncidentAuditLog(id: string): Promise<AuditLogOut[]> {
  return apiFetch<AuditLogOut[]>(`/api/incidents/${id}/audit-log`);
}

// ---- Global audit log ----

export function getAuditLog(filters?: { incidentId?: string; action?: string }): Promise<AuditLogOut[]> {
  const params = new URLSearchParams();
  if (filters?.incidentId) params.set("incident_id", filters.incidentId);
  if (filters?.action) params.set("action", filters.action);
  const query = params.toString();
  return apiFetch<AuditLogOut[]>(`/api/audit-log${query ? `?${query}` : ""}`);
}

// ---- Scenarios (simulated-system proxy) ----

export function listScenarios(): Promise<ScenarioOut[]> {
  return apiFetch<ScenarioOut[]>("/api/scenarios");
}

export function injectScenario(scenarioId: string): Promise<InjectScenarioResponse> {
  return apiFetch<InjectScenarioResponse>(`/api/scenarios/${scenarioId}/inject`, { method: "POST" });
}

// ---- Runbooks ----

export function searchRunbooks(query: string, topK = 5): Promise<RunbookSearchResultOut[]> {
  return apiFetch<RunbookSearchResultOut[]>(
    `/api/runbooks/search?q=${encodeURIComponent(query)}&top_k=${topK}`,
  );
}
