import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listRuns, getRun, forkRun, deleteRun } from "@/api/runs";
import { listSnapshots } from "@/api/snapshots";
import { useGraphStore } from "@/stores/graphStore";
import { useEffect } from "react";
import type { StatePatch } from "@/types";

export function useRuns(agentId?: string) {
  return useQuery({
    queryKey: ["runs", agentId],
    queryFn: () => listRuns({ agent_id: agentId, limit: 100 }),
    refetchInterval: 5000,
  });
}

export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId!),
    enabled: !!runId,
  });
}

export function useSnapshots(runId: string | null) {
  const setSnapshots = useGraphStore((s) => s.setSnapshots);
  const query = useQuery({
    queryKey: ["snapshots", runId],
    queryFn: () => listSnapshots(runId!),
    enabled: !!runId,
  });

  useEffect(() => {
    if (runId && query.data) {
      setSnapshots(runId, query.data);
    }
  }, [runId, query.data, setSnapshots]);

  return query;
}

export function useForkRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      snapshotId,
      patch,
      reason,
    }: {
      runId: string;
      snapshotId: string;
      patch?: StatePatch;
      reason?: string;
    }) => forkRun(runId, snapshotId, patch, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}

export function useDeleteRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => deleteRun(runId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
  });
}
