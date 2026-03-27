/**
 * SnapshotInspector — right-panel detail view for a selected snapshot.
 * Shows messages, tool calls, agent state. Has Fork button that opens StateEditor.
 */

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getSnapshot } from "@/api/snapshots";
import { useGraphStore } from "@/stores/graphStore";
import { useRunStore } from "@/stores/runStore";
import { useForkRun } from "@/hooks/useRun";
import { MessageViewer } from "./MessageViewer";
import { ToolCallViewer } from "./ToolCallViewer";
import { StateEditor } from "./StateEditor";
import type { StatePatch } from "@/types";
import { GitBranch, X, Clock, Cpu } from "lucide-react";
import clsx from "clsx";

type Tab = "messages" | "tools" | "state" | "fork";

export function SnapshotInspector() {
  const selectedId = useGraphStore((s) => s.selectedSnapshotId);
  const selectSnapshot = useGraphStore((s) => s.selectSnapshot);
  const activeRunId = useRunStore((s) => s.activeRunId);
  const forkMutation = useForkRun();

  const [tab, setTab] = useState<Tab>("messages");
  const [patch, setPatch] = useState<StatePatch>({
    message_overrides: [],
    state_overrides: {},
    tool_result_overrides: {},
    model_param_overrides: {},
  });
  const [forkReason, setForkReason] = useState("");

  const { data: snapshot, isLoading } = useQuery({
    queryKey: ["snapshot", selectedId],
    queryFn: () => getSnapshot(selectedId!),
    enabled: !!selectedId,
  });

  if (!selectedId) {
    return (
      <div className="flex h-full items-center justify-center text-gray-500 text-sm p-4">
        Click a node in the graph to inspect its state.
      </div>
    );
  }

  if (isLoading || !snapshot) {
    return <div className="p-4 text-gray-400 text-sm">Loading…</div>;
  }

  const handleFork = async () => {
    if (!activeRunId) return;
    try {
      const result = await forkMutation.mutateAsync({
        runId: activeRunId,
        snapshotId: snapshot.id,
        patch,
        reason: forkReason || undefined,
      });
      useRunStore.getState().setActiveRun(result.forked_run.id);
      selectSnapshot(null);
    } catch (e) {
      console.error("Fork failed", e);
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "messages", label: "Messages" },
    { id: "tools", label: `Tools (${snapshot.tool_calls.length})` },
    { id: "state", label: "State" },
    { id: "fork", label: "Fork" },
  ];

  return (
    <div className="flex flex-col h-full bg-gray-900 text-white">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-700 bg-gray-800">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm truncate">{snapshot.node_id}</div>
          <div className="text-xs text-gray-400 flex items-center gap-3 mt-0.5">
            <span className="capitalize">{snapshot.node_type.replace("_", " ")}</span>
            {snapshot.latency_ms != null && (
              <span className="flex items-center gap-1">
                <Clock size={10} /> {snapshot.latency_ms}ms
              </span>
            )}
            {snapshot.model && (
              <span className="flex items-center gap-1">
                <Cpu size={10} /> {snapshot.model}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => selectSnapshot(null)}
          className="text-gray-400 hover:text-white p-1"
        >
          <X size={16} />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-700 bg-gray-800">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={clsx(
              "px-4 py-2 text-xs font-medium border-b-2 transition-colors",
              tab === t.id
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-gray-400 hover:text-gray-200"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {tab === "messages" && (
          <MessageViewer
            messagesIn={snapshot.messages_in}
            messagesOut={snapshot.messages_out}
          />
        )}
        {tab === "tools" && (
          <ToolCallViewer
            toolCalls={snapshot.tool_calls}
            toolResults={snapshot.tool_results}
          />
        )}
        {tab === "state" && (
          <div className="p-4">
            <pre className="text-xs text-gray-300 whitespace-pre-wrap break-all">
              {JSON.stringify(snapshot.agent_state, null, 2)}
            </pre>
          </div>
        )}
        {tab === "fork" && (
          <div className="p-4 space-y-4">
            <p className="text-sm text-gray-400">
              Fork from this snapshot and replay with modified inputs. The new run
              branches off at sequence #{snapshot.sequence_number}.
            </p>
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                State overrides (JSON merge patch)
              </label>
              <StateEditor
                value={patch.state_overrides}
                onChange={(v) => setPatch((p) => ({ ...p, state_overrides: v }))}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Reason (optional)</label>
              <input
                type="text"
                value={forkReason}
                onChange={(e) => setForkReason(e.target.value)}
                placeholder="e.g. Retry with corrected system prompt"
                className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500"
              />
            </div>
            <button
              onClick={handleFork}
              disabled={forkMutation.isPending}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-4 py-2 rounded text-sm font-medium transition-colors"
            >
              <GitBranch size={14} />
              {forkMutation.isPending ? "Forking…" : "Fork & Replay"}
            </button>
            {forkMutation.isError && (
              <p className="text-red-400 text-xs">{String(forkMutation.error)}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
