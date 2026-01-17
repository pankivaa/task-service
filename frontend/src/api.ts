import type { Task, TaskCreate, TaskList, TaskStatus } from "./types";

const API_BASE = "http://localhost:8000/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listTasks: (params?: { limit?: number; offset?: number; status?: string; site_type?: string; q?: string }) => {
    const sp = new URLSearchParams();
    if (params?.limit != null) sp.set("limit", String(params.limit));
    if (params?.offset != null) sp.set("offset", String(params.offset));
    if (params?.status) sp.set("status", params.status);
    if (params?.site_type) sp.set("site_type", params.site_type);
    if (params?.q) sp.set("q", params.q);
    const qs = sp.toString();
    return req<TaskList>(`/tasks${qs ? `?${qs}` : ""}`);
  },

  createTask: (payload: TaskCreate) =>
    req<Task>("/tasks", { method: "POST", body: JSON.stringify(payload) }),

  deleteTask: (id: string) =>
    req<void>(`/tasks/${id}`, { method: "DELETE" }),

  updateStatus: (id: string, status: TaskStatus) =>
    req<Task>(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
};
