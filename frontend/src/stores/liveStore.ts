import { create } from "zustand";
import type { LiveEvent } from "@/types";
import { useGraphStore } from "./graphStore";
import { useRunStore } from "./runStore";

interface LiveStore {
  connections: Record<string, boolean>; // run_id -> connected
  setConnected: (runId: string, connected: boolean) => void;
  handleEvent: (event: LiveEvent) => void;
}

export const useLiveStore = create<LiveStore>((set) => ({
  connections: {},

  setConnected: (runId, connected) =>
    set((state) => ({
      connections: { ...state.connections, [runId]: connected },
    })),

  handleEvent: (event) => {
    switch (event.type) {
      case "connected":
        set((state) => ({
          connections: { ...state.connections, [event.data.run_id]: true },
        }));
        break;

      case "snapshot_created":
        useGraphStore.getState().appendSnapshot(event.data);
        break;

      case "run_status_changed":
        useRunStore.getState().updateRunStatus(event.data.run_id, event.data.status);
        break;

      case "fork_created":
        // The fork will appear as a new run — trigger a refetch via React Query
        // (handled in useLiveEvents hook)
        break;
    }
  },
}));
