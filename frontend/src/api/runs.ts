import { apiFetch } from "./client";
import type { Fork, ReplayBundle, Run, StatePatch } from "@/types";

export interface RunsQuery {
  agent_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export function listRuns(q: RunsQuery = {}): Promise<Run[]> {
  const params = new URLSearchParams();
  if (q.agent_id) params.set("agent_id", q.agent_id);
  if (q.status) params.set("status", q.status);
  if (q.limit) params.set("limit", String(q.limit));
  if (q.offset) params.set("offset", String(q.offset));
  return apiFetch(`/api/v1/runs/?${params}`);
}

export function getRun(runId: string): Promise<Run> {
  return apiFetch(`/api/v1/runs/${runId}`);
}

export function getReplayBundle(runId: string): Promise<ReplayBundle> {
  return apiFetch(`/api/v1/runs/${runId}/replay-bundle`);
}

export function forkRun(
  runId: string,
  snapshotId: string,
  patch?: StatePatch,
  reason?: string
): Promise<{ fork: Fork; forked_run: Run }> {
  return apiFetch(`/api/v1/runs/${runId}/fork`, {
    method: "POST",
    body: JSON.stringify({ snapshot_id: snapshotId, patch, reason }),
  });
}

export function deleteRun(runId: string): Promise<void> {
  return apiFetch(`/api/v1/runs/${runId}`, { method: "DELETE" });
}

// Not yet in types/index.ts — define locally
interface ReplayBundle {
  run: Run;
  snapshots: import("@/types").Snapshot[];
  forks: Fork[];
}
