/**
 * TypeScript mirrors of the Pydantic models from the SDK.
 * Keep in sync with sdk/forkpoint/models/events.py
 */

export type Framework = "langgraph" | "crewai" | "autogen" | "raw";
export type RunStatus = "running" | "completed" | "failed" | "replaying" | "paused";
export type NodeType =
  | "llm_call"
  | "tool_call"
  | "agent_message"
  | "agent_start"
  | "agent_end"
  | "human_input"
  | "fork_point";
export type MessageRole = "system" | "user" | "assistant" | "tool" | "function";
export type MatchType = "identical" | "modified" | "added" | "removed";

export interface Message {
  role: MessageRole;
  content: string | Record<string, unknown>[];
  name?: string;
  tool_call_id?: string;
  tool_calls?: Record<string, unknown>[];
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  timestamp: string;
}

export interface ToolResult {
  tool_call_id: string;
  name: string;
  result: unknown;
  error?: string;
  timestamp: string;
}

export interface TokenCounts {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ErrorInfo {
  type: string;
  message: string;
  traceback?: string;
}

export interface Run {
  id: string;
  parent_run_id?: string;
  fork_point_snapshot_id?: string;
  agent_id: string;
  framework: Framework;
  status: RunStatus;
  started_at: string;
  ended_at?: string;
  tags: Record<string, string>;
  metadata: Record<string, unknown>;
  root_snapshot_id?: string;
  terminal_snapshot_id?: string;
  error?: ErrorInfo;
}

export interface Snapshot {
  id: string;
  run_id: string;
  parent_snapshot_id?: string;
  sequence_number: number;
  node_id: string;
  node_type: NodeType;
  timestamp: string;
  messages_in: Message[];
  messages_out: Message[];
  tool_calls: ToolCall[];
  tool_results: ToolResult[];
  agent_state: Record<string, unknown>;
  model?: string;
  model_params: Record<string, unknown>;
  latency_ms?: number;
  token_counts?: TokenCounts;
  logprobs?: unknown[];
  alternatives_considered?: unknown[];
}

export interface StatePatch {
  message_overrides: { index: number; message: Message }[];
  state_overrides: Record<string, unknown>;
  tool_result_overrides: Record<string, unknown>;
  model_param_overrides: Record<string, unknown>;
}

export interface Fork {
  id: string;
  source_run_id: string;
  source_snapshot_id: string;
  forked_run_id: string;
  created_at: string;
  patch?: StatePatch;
  reason?: string;
}

export interface FieldDiff {
  field_path: string;
  value_a: unknown;
  value_b: unknown;
}

export interface SnapshotPair {
  snapshot_a_id?: string;
  snapshot_b_id?: string;
  node_id: string;
  match_type: MatchType;
  field_diffs: FieldDiff[];
}

export interface RunDiff {
  run_a_id: string;
  run_b_id: string;
  common_ancestor_snapshot_id?: string;
  snapshot_pairs: SnapshotPair[];
  summary: {
    total_snapshots_a: number;
    total_snapshots_b: number;
    identical: number;
    modified: number;
    added: number;
    removed: number;
    first_divergence_sequence?: number;
  };
}

export interface DriftEdge {
  from_node_id: string;
  to_node_id: string;
  from_snapshot_id: string;
  to_snapshot_id: string;
  similarity_score: number;
  flagged: boolean;
  flag_reason?: string;
  actual_content_summary: string;
}

export interface DriftReport {
  run_id: string;
  edges_analyzed: number;
  flagged_edges: DriftEdge[];
  overall_health_score: number;
  generated_at: string;
}

export interface AlternativeDecision {
  node_id: string;
  description: string;
  probability?: number;
  logprob_delta?: number;
  why_not_chosen?: string;
}

export interface CausalAnalysis {
  snapshot_id: string;
  run_id: string;
  node_id: string;
  chosen_path_summary: string;
  alternatives: AlternativeDecision[];
  reasoning: string;
  confidence: number;
  analyzed_at: string;
}

// WebSocket live events
export type LiveEvent =
  | { type: "connected"; data: { run_id: string } }
  | { type: "snapshot_created"; data: Snapshot }
  | { type: "run_status_changed"; data: { run_id: string; status: RunStatus } }
  | { type: "fork_created"; data: Fork }
  | { type: "analysis_ready"; data: { run_id: string; analysis_type: string } }
  | { type: "error"; data: { message: string; code: string } };
