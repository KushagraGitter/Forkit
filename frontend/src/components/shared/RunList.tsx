import React from "react";
import type { Run } from "@/types";
import { useRunStore } from "@/stores/runStore";
import clsx from "clsx";
import { formatDistanceToNow } from "date-fns";
import { GitBranch, Activity, CheckCircle, XCircle, Clock } from "lucide-react";

const STATUS_ICONS: Record<Run["status"], React.ReactNode> = {
  running: <Activity size={12} className="text-blue-400 animate-pulse" />,
  completed: <CheckCircle size={12} className="text-emerald-400" />,
  failed: <XCircle size={12} className="text-red-400" />,
  replaying: <Activity size={12} className="text-indigo-400 animate-pulse" />,
  paused: <Clock size={12} className="text-amber-400" />,
};

interface Props {
  runs: Run[];
  onSelect?: (run: Run) => void;
}

export function RunList({ runs, onSelect }: Props) {
  const activeRunId = useRunStore((s) => s.activeRunId);

  if (runs.length === 0) {
    return (
      <div className="p-4 text-gray-500 text-sm text-center">
        No runs yet. Instrument your agent with the Forkpoint SDK to get started.
      </div>
    );
  }

  return (
    <div className="divide-y divide-gray-800">
      {runs.map((run) => (
        <button
          key={run.id}
          onClick={() => onSelect?.(run)}
          className={clsx(
            "w-full text-left px-4 py-3 hover:bg-gray-800 transition-colors",
            activeRunId === run.id && "bg-gray-800 border-l-2 border-indigo-500"
          )}
        >
          <div className="flex items-center gap-2 mb-1">
            {STATUS_ICONS[run.status]}
            <span className="text-sm font-medium text-white truncate flex-1">
              {run.agent_id}
            </span>
            {run.parent_run_id && (
              <GitBranch size={10} className="text-pink-400" title="Forked run" />
            )}
          </div>
          <div className="text-xs text-gray-500 flex items-center gap-2">
            <span className="font-mono">{run.id.slice(0, 8)}</span>
            <span>·</span>
            <span>{formatDistanceToNow(new Date(run.started_at))} ago</span>
            {run.framework !== "raw" && (
              <>
                <span>·</span>
                <span className="capitalize">{run.framework}</span>
              </>
            )}
          </div>
          {run.error && (
            <div className="text-xs text-red-400 mt-1 truncate">
              {run.error.type}: {run.error.message}
            </div>
          )}
        </button>
      ))}
    </div>
  );
}
