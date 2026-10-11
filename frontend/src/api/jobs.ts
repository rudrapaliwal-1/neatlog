import { request } from "./client";
import type { Evidence, Finding, Job, Patch, VerificationResult, WorkflowEvent } from "./types";

type BackendJob = { id: string; status: string; finding?: Finding; attempt?: number; created_at?: string; updated_at?: string; [key: string]: unknown };
type BackendEvent = { event_type: string; created_at: string; event?: { timestamp?: string; to?: string; attempt?: number; patch_hash?: string; reason?: string; from?: string; status?: string; feedback?: { tests_total?: number; tests_failed?: number } } };
function normalizeJob(data: BackendJob): Job {
  if (!data.id) throw new Error("Backend returned a job without an ID.");
  return { ...data, job_id: data.id } as Job;
}
function normalizePatch(data: Patch): Patch {
  const diff = data.patch_text || "";
  const lines = diff.split("\n");
  return { ...data, diff, files: (data.files_changed || []).map(file_path => ({
    file_path, diff,
    additions: lines.filter(line => line.startsWith("+") && !line.startsWith("+++")).length,
    deletions: lines.filter(line => line.startsWith("-") && !line.startsWith("---")).length,
  })) };
}
function normalizeEvent(data: BackendEvent): WorkflowEvent {
  const event = data.event || {};
  const summary = data.event_type === "REFLECTION_STARTED" && event.feedback
    ? `Agent B received sanitized feedback: ${event.feedback.tests_failed} of ${event.feedback.tests_total} tests failed.`
    : data.event_type === "REFLECTION_COMPLETED" ? "Agent B revision guidance validated for the next proposal."
    : data.event_type === "VERIFICATION_COMPLETED" && event.status ? `Docker verdict: ${event.status}.`
    : event.reason || (event.to ? `${event.from || "New finding"} → ${event.to}` : data.event_type.replaceAll("_", " "));
  return { timestamp: event.timestamp || data.created_at, event_type: event.to || data.event_type,
    attempt: event.attempt, patch_hash: event.patch_hash, summary, details: data };
}
export function verificationFromEvidence(evidence: Evidence): VerificationResult | null {
  const runs = evidence.verification_runs as Array<{ status: string; patch_hash: string; result: VerificationResult }> | undefined;
  const latest = runs?.filter(run => run.status !== "RUNNING").at(-1);
  if (!latest) return null;
  return { ...latest.result, job_id: String(evidence.job_id), patch_hash: latest.patch_hash, status: latest.status };
}
export const api = {
  health: () => request<Record<string, unknown>>("/health"),
  createFinding: (payload: { target_app_id: string; finding: Finding }) =>
    request<{ job_id: string; status: string }>("/api/findings", { method: "POST", body: JSON.stringify(payload) }),
  jobs: async () => (await request<BackendJob[]>("/api/jobs")).map(normalizeJob),
  job: async (id: string) => normalizeJob(await request<BackendJob>(`/api/jobs/${encodeURIComponent(id)}`)),
  patch: async (id: string) => normalizePatch(await request<Patch>(`/api/jobs/${encodeURIComponent(id)}/patch`)),
  approval: (id: string, patch_hash: string, decision: "APPROVE" | "REJECT") =>
    request<Record<string, unknown>>(`/api/jobs/${encodeURIComponent(id)}/approval`, { method: "POST", body: JSON.stringify({ patch_hash, decision }) }),
  verify: (id: string) => request<VerificationResult>(`/api/jobs/${encodeURIComponent(id)}/verify`, { method: "POST" }, 1_020_000),
  evidence: (id: string) => request<Evidence>(`/api/jobs/${encodeURIComponent(id)}/evidence`),
  events: async (id: string) => (await request<BackendEvent[]>(`/api/jobs/${encodeURIComponent(id)}/events`)).map(normalizeEvent),
};
export function unwrapList<T>(data: T[] | Record<string, T[]> , key: string): T[] {
  if (Array.isArray(data)) return data;
  const list = data[key];
  return Array.isArray(list) ? list : [];
}
