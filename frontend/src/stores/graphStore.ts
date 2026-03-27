import { create } from "zustand";
import type { Snapshot } from "@/types";

interface GraphStore {
  snapshots: Record<string, Snapshot[]>; // run_id -> snapshots
  selectedSnapshotId: string | null;
  compareRunId: string | null; // run being compared for diff view

  setSnapshots: (runId: string, snapshots: Snapshot[]) => void;
  appendSnapshot: (snapshot: Snapshot) => void;
  selectSnapshot: (snapshotId: string | null) => void;
  setCompareRun: (runId: string | null) => void;
}

export const useGraphStore = create<GraphStore>((set) => ({
  snapshots: {},
  selectedSnapshotId: null,
  compareRunId: null,

  setSnapshots: (runId, snapshots) =>
    set((state) => ({
      snapshots: { ...state.snapshots, [runId]: snapshots },
    })),

  appendSnapshot: (snapshot) =>
    set((state) => {
      const existing = state.snapshots[snapshot.run_id] ?? [];
      // Avoid duplicates
      if (existing.find((s) => s.id === snapshot.id)) return state;
      return {
        snapshots: {
          ...state.snapshots,
          [snapshot.run_id]: [...existing, snapshot].sort(
            (a, b) => a.sequence_number - b.sequence_number
          ),
        },
      };
    }),

  selectSnapshot: (snapshotId) => set({ selectedSnapshotId: snapshotId }),
  setCompareRun: (runId) => set({ compareRunId: runId }),
}));
