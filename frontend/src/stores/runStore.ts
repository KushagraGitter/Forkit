import { create } from "zustand";
import type { Run, Snapshot } from "@/types";

interface RunStore {
  runs: Run[];
  activeRunId: string | null;
  setRuns: (runs: Run[]) => void;
  upsertRun: (run: Run) => void;
  setActiveRun: (runId: string | null) => void;
  updateRunStatus: (runId: string, status: Run["status"]) => void;
}

export const useRunStore = create<RunStore>((set) => ({
  runs: [],
  activeRunId: null,

  setRuns: (runs) => set({ runs }),

  upsertRun: (run) =>
    set((state) => {
      const idx = state.runs.findIndex((r) => r.id === run.id);
      if (idx >= 0) {
        const updated = [...state.runs];
        updated[idx] = run;
        return { runs: updated };
      }
      return { runs: [run, ...state.runs] };
    }),

  setActiveRun: (runId) => set({ activeRunId: runId }),

  updateRunStatus: (runId, status) =>
    set((state) => ({
      runs: state.runs.map((r) => (r.id === runId ? { ...r, status } : r)),
    })),
}));
