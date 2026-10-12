import type {
  AuditLogOut,
  IncidentDetailOut,
  IncidentOut,
  InjectScenarioResponse,
  InvestigateResponse,
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

export function investigateIncident(id: string): Promise<InvestigateResponse> {
  return apiFetch<InvestigateResponse>(`/api/incidents/${id}/investigate`, { method: "POST" });
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
