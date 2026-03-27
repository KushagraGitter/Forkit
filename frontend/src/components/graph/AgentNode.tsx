/**
 * AgentNode — a single node in the execution graph.
 * Displays node type, node_id, latency, and status badge.
 * Clickable to open the SnapshotInspector.
 */

import React from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import type { Snapshot } from "@/types";
import { useGraphStore } from "@/stores/graphStore";
import clsx from "clsx";

const NODE_TYPE_LABELS: Record<string, string> = {
  llm_call: "LLM",
  tool_call: "Tool",
  agent_message: "Message",
  agent_start: "Start",
  agent_end: "End",
  human_input: "Human",
  fork_point: "Fork",
};

const NODE_TYPE_COLORS: Record<string, string> = {
  llm_call: "border-indigo-500 bg-indigo-950",
  tool_call: "border-amber-500 bg-amber-950",
  agent_message: "border-emerald-500 bg-emerald-950",
  agent_start: "border-blue-500 bg-blue-950",
  agent_end: "border-red-500 bg-red-950",
  human_input: "border-violet-500 bg-violet-950",
  fork_point: "border-pink-500 bg-pink-950",
};

export function AgentNode({ data, selected }: NodeProps) {
  const snapshot = data.snapshot as Snapshot;
  const selectedId = useGraphStore((s) => s.selectedSnapshotId);
  const isSelected = selectedId === snapshot.id || selected;

  const colorClass = NODE_TYPE_COLORS[snapshot.node_type] ?? "border-gray-500 bg-gray-900";
  const label = NODE_TYPE_LABELS[snapshot.node_type] ?? snapshot.node_type;

  const shortNodeId =
    snapshot.node_id.length > 18
      ? snapshot.node_id.slice(0, 18) + "…"
      : snapshot.node_id;

  return (
    <div
      className={clsx(
        "rounded-lg border-2 px-3 py-2 min-w-[160px] cursor-pointer transition-all",
        colorClass,
        isSelected && "ring-2 ring-white ring-offset-1 ring-offset-gray-900"
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-gray-400" />

      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-bold uppercase tracking-wide text-gray-300">
          {label}
        </span>
        <span className="ml-auto text-xs text-gray-500">#{snapshot.sequence_number}</span>
      </div>

      <div className="text-sm font-medium text-white truncate">{shortNodeId}</div>

      {snapshot.model && (
        <div className="text-xs text-gray-400 mt-1 truncate">{snapshot.model}</div>
      )}

      <div className="flex items-center gap-2 mt-2">
        {snapshot.latency_ms != null && (
          <span className="text-xs text-gray-400">{snapshot.latency_ms}ms</span>
        )}
        {snapshot.token_counts && (
          <span className="text-xs text-gray-400">
            {snapshot.token_counts.total_tokens}t
          </span>
        )}
        {snapshot.tool_calls.length > 0 && (
          <span className="text-xs bg-amber-800 text-amber-200 rounded px-1">
            {snapshot.tool_calls.length} tool{snapshot.tool_calls.length > 1 ? "s" : ""}
          </span>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-gray-400" />
    </div>
  );
}
