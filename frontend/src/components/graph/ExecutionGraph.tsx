/**
 * ExecutionGraph — the main ReactFlow canvas.
 * Renders the agent execution as a DAG: nodes are snapshots, edges are transitions.
 * Supports live updates (snapshots stream in via WebSocket).
 */

import React, { useCallback, useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  useNodesState,
  useEdgesState,
  BackgroundVariant,
} from "reactflow";
import "reactflow/dist/style.css";

import type { Snapshot } from "@/types";
import { AgentNode } from "./AgentNode";
import { useGraphStore } from "@/stores/graphStore";

const nodeTypes: NodeTypes = {
  agentNode: AgentNode,
};

function snapshotsToGraph(snapshots: Snapshot[]): {
  nodes: Node[];
  edges: Edge[];
} {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  const COL_WIDTH = 220;
  const ROW_HEIGHT = 90;

  // Group by node_id to track x positions
  const nodeColumns: Record<string, number> = {};
  let colIdx = 0;

  for (const snap of snapshots) {
    if (!(snap.node_id in nodeColumns)) {
      nodeColumns[snap.node_id] = colIdx++;
    }
  }

  // Build one ReactFlow node per snapshot
  for (const snap of snapshots) {
    const col = nodeColumns[snap.node_id] ?? 0;
    const row = snap.sequence_number;

    nodes.push({
      id: snap.id,
      type: "agentNode",
      position: { x: col * COL_WIDTH, y: row * ROW_HEIGHT },
      data: { snapshot: snap },
      draggable: true,
    });

    if (snap.parent_snapshot_id) {
      edges.push({
        id: `e-${snap.parent_snapshot_id}-${snap.id}`,
        source: snap.parent_snapshot_id,
        target: snap.id,
        animated: snap.node_type === "llm_call",
        style: { stroke: nodeTypeColor(snap.node_type) },
      });
    }
  }

  return { nodes, edges };
}

function nodeTypeColor(nodeType: Snapshot["node_type"]): string {
  const colors: Record<string, string> = {
    llm_call: "#6366f1",
    tool_call: "#f59e0b",
    agent_message: "#10b981",
    agent_start: "#3b82f6",
    agent_end: "#ef4444",
    human_input: "#8b5cf6",
    fork_point: "#ec4899",
  };
  return colors[nodeType] ?? "#6b7280";
}

interface ExecutionGraphProps {
  runId: string;
}

export function ExecutionGraph({ runId }: ExecutionGraphProps) {
  const snapshots = useGraphStore((s) => s.snapshots[runId] ?? []);
  const selectSnapshot = useGraphStore((s) => s.selectSnapshot);

  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => snapshotsToGraph(snapshots),
    [snapshots]
  );

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  // Sync when snapshots change (live updates)
  const { nodes: liveNodes, edges: liveEdges } = useMemo(
    () => snapshotsToGraph(snapshots),
    [snapshots]
  );

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const snap = node.data?.snapshot as Snapshot;
      if (snap) selectSnapshot(snap.id);
    },
    [selectSnapshot]
  );

  if (snapshots.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400 text-sm">
        No snapshots yet. Start a run to see the execution graph.
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <ReactFlow
        nodes={liveNodes}
        edges={liveEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#374151" />
        <Controls />
        <MiniMap
          nodeColor={(n) => {
            const snap = n.data?.snapshot as Snapshot | undefined;
            return snap ? nodeTypeColor(snap.node_type) : "#6b7280";
          }}
          style={{ background: "#1f2937" }}
        />
      </ReactFlow>
    </div>
  );
}
