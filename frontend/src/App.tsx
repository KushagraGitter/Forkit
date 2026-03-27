import React, { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useRuns, useSnapshots } from "@/hooks/useRun";
import { useLiveEvents } from "@/hooks/useLiveEvents";
import { useRunStore } from "@/stores/runStore";
import { useGraphStore } from "@/stores/graphStore";
import { ExecutionGraph } from "@/components/graph/ExecutionGraph";
import { SnapshotInspector } from "@/components/inspector/SnapshotInspector";
import { RunList } from "@/components/shared/RunList";
import { RunDiff } from "@/components/diff/RunDiff";
import type { Run } from "@/types";
import { GitBranch, Layers, GitCompare, Zap } from "lucide-react";
import clsx from "clsx";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 2000 } },
});

type PanelMode = "graph" | "diff";

function AppInner() {
  const activeRunId = useRunStore((s) => s.activeRunId);
  const setActiveRun = useRunStore((s) => s.setActiveRun);
  const compareRunId = useGraphStore((s) => s.compareRunId);
  const setCompareRun = useGraphStore((s) => s.setCompareRun);
  const selectedSnapshotId = useGraphStore((s) => s.selectedSnapshotId);

  const [panelMode, setPanelMode] = useState<PanelMode>("graph");
  const [comparePickerOpen, setComparePickerOpen] = useState(false);

  const { data: runs = [] } = useRuns();
  useSnapshots(activeRunId);
  useLiveEvents(activeRunId);

  const handleSelectRun = (run: Run) => {
    setActiveRun(run.id);
    setCompareRun(null);
    setPanelMode("graph");
  };

  const activeRun = runs.find((r) => r.id === activeRunId);

  return (
    <div className="flex h-screen bg-gray-950 text-white overflow-hidden">
      {/* Sidebar — run list */}
      <div className="w-72 flex-shrink-0 flex flex-col border-r border-gray-800">
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 py-4 border-b border-gray-800">
          <Zap size={18} className="text-indigo-400" />
          <span className="font-bold text-lg tracking-tight">Forkpoint</span>
          <span className="text-xs text-gray-500 ml-auto">v0.1</span>
        </div>

        {/* Run list */}
        <div className="flex-1 overflow-auto">
          <div className="px-4 py-2 text-xs font-medium text-gray-500 uppercase tracking-wider">
            Runs
          </div>
          <RunList runs={runs} onSelect={handleSelectRun} />
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-3 px-4 py-2 border-b border-gray-800 bg-gray-900">
          {activeRun && (
            <>
              <div className="text-sm font-medium">{activeRun.agent_id}</div>
              <span className="text-gray-600">·</span>
              <span className="text-xs font-mono text-gray-400">{activeRun.id}</span>
              <StatusBadge status={activeRun.status} />
            </>
          )}
          <div className="ml-auto flex items-center gap-2">
            {activeRunId && (
              <button
                onClick={() => setPanelMode("graph")}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors",
                  panelMode === "graph"
                    ? "bg-indigo-600 text-white"
                    : "text-gray-400 hover:text-white"
                )}
              >
                <Layers size={12} /> Graph
              </button>
            )}
            {activeRunId && (
              <button
                onClick={() => {
                  setPanelMode("diff");
                  setComparePickerOpen(true);
                }}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors",
                  panelMode === "diff"
                    ? "bg-indigo-600 text-white"
                    : "text-gray-400 hover:text-white"
                )}
              >
                <GitCompare size={12} /> Diff
              </button>
            )}
          </div>
        </div>

        {/* Graph / Diff area */}
        <div className="flex flex-1 min-h-0">
          <div className="flex-1 min-w-0">
            {!activeRunId && (
              <div className="flex h-full items-center justify-center">
                <div className="text-center space-y-3">
                  <Zap size={40} className="text-indigo-400 mx-auto" />
                  <div className="text-xl font-semibold">Welcome to Forkpoint</div>
                  <div className="text-gray-400 text-sm max-w-xs">
                    Select a run from the sidebar, or instrument your agent with the SDK
                    to see the execution graph here.
                  </div>
                  <code className="block bg-gray-800 rounded p-3 text-xs text-indigo-300 text-left">
                    {`from forkpoint import ForkpointTracer\n\nwith ForkpointTracer(agent_id="my-agent") as t:\n    result = my_agent.run(inputs)`}
                  </code>
                </div>
              </div>
            )}
            {activeRunId && panelMode === "graph" && (
              <ExecutionGraph runId={activeRunId} />
            )}
            {activeRunId && panelMode === "diff" && compareRunId && (
              <RunDiff runAId={activeRunId} runBId={compareRunId} />
            )}
            {activeRunId && panelMode === "diff" && !compareRunId && (
              <div className="flex h-full items-center justify-center">
                <div className="text-center space-y-3">
                  <GitBranch size={32} className="text-indigo-400 mx-auto" />
                  <div className="text-gray-300 text-sm">Select a run to compare against</div>
                  <div className="w-64 bg-gray-800 rounded-lg overflow-hidden">
                    {runs
                      .filter((r) => r.id !== activeRunId)
                      .slice(0, 10)
                      .map((r) => (
                        <button
                          key={r.id}
                          onClick={() => {
                            setCompareRun(r.id);
                            setComparePickerOpen(false);
                          }}
                          className="w-full text-left px-4 py-2 hover:bg-gray-700 text-sm border-b border-gray-700 last:border-0"
                        >
                          <span className="font-mono text-gray-400 text-xs mr-2">
                            {r.id.slice(0, 8)}
                          </span>
                          {r.agent_id}
                        </button>
                      ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right panel — inspector (only in graph mode) */}
          {panelMode === "graph" && (selectedSnapshotId || true) && (
            <div
              className={clsx(
                "w-96 flex-shrink-0 border-l border-gray-800 transition-all duration-200",
                selectedSnapshotId ? "translate-x-0" : "translate-x-full"
              )}
              style={{
                transform: selectedSnapshotId ? "translateX(0)" : "translateX(100%)",
                width: selectedSnapshotId ? undefined : 0,
                overflow: "hidden",
              }}
            >
              <SnapshotInspector />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: Run["status"] }) {
  const colors: Record<string, string> = {
    running: "bg-blue-900 text-blue-300",
    completed: "bg-emerald-900 text-emerald-300",
    failed: "bg-red-900 text-red-300",
    replaying: "bg-indigo-900 text-indigo-300",
    paused: "bg-amber-900 text-amber-300",
  };
  return (
    <span
      className={clsx(
        "text-xs px-2 py-0.5 rounded-full font-medium capitalize",
        colors[status] ?? "bg-gray-800 text-gray-300"
      )}
    >
      {status}
    </span>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  );
}
