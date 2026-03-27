import { apiFetch } from "./client";
import type { RunDiff, Snapshot } from "@/types";

export function listSnapshots(runId: string, nodeType?: string): Promise<Snapshot[]> {
  const params = new URLSearchParams();
  if (nodeType) params.set("node_type", nodeType);
  return apiFetch(`/api/v1/runs/${runId}/snapshots?${params}`);
}

export function getSnapshot(snapshotId: string): Promise<Snapshot> {
  return apiFetch(`/api/v1/snapshots/${snapshotId}`);
}

export function diffRuns(runAId: string, runBId: string): Promise<RunDiff> {
  return apiFetch(`/api/v1/diff/?run_a=${runAId}&run_b=${runBId}`);
}
