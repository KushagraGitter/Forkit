/**
 * RunDiff — side-by-side comparison of two runs.
 * Shows which snapshots are identical, modified, added, or removed.
 */

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { diffRuns } from "@/api/snapshots";
import type { MatchType, RunDiff as RunDiffType, SnapshotPair } from "@/types";
import clsx from "clsx";

const MATCH_TYPE_STYLES: Record<MatchType, string> = {
  identical: "bg-gray-800 text-gray-400",
  modified: "bg-yellow-900 text-yellow-200 border-l-2 border-yellow-500",
  added: "bg-green-900 text-green-200 border-l-2 border-green-500",
  removed: "bg-red-900 text-red-200 border-l-2 border-red-500",
};

const MATCH_TYPE_LABELS: Record<MatchType, string> = {
  identical: "=",
  modified: "~",
  added: "+",
  removed: "-",
};

interface Props {
  runAId: string;
  runBId: string;
}

export function RunDiff({ runAId, runBId }: Props) {
  const { data: diff, isLoading, error } = useQuery({
    queryKey: ["diff", runAId, runBId],
    queryFn: () => diffRuns(runAId, runBId),
    enabled: !!(runAId && runBId),
  });

  if (isLoading) return <div className="p-4 text-gray-400 text-sm">Computing diff…</div>;
  if (error) return <div className="p-4 text-red-400 text-sm">{String(error)}</div>;
  if (!diff) return null;

  return (
    <div className="flex flex-col h-full bg-gray-900 text-white">
      {/* Summary */}
      <div className="flex items-center gap-4 px-4 py-3 border-b border-gray-700 bg-gray-800 text-xs">
        <span className="font-medium">Diff</span>
        <span className="text-gray-400">
          {runAId.slice(0, 8)} ↔ {runBId.slice(0, 8)}
        </span>
        <div className="ml-auto flex gap-3">
          <DiffCount label="identical" count={diff.summary.identical} color="text-gray-400" />
          <DiffCount label="modified" count={diff.summary.modified} color="text-yellow-400" />
          <DiffCount label="added" count={diff.summary.added} color="text-green-400" />
          <DiffCount label="removed" count={diff.summary.removed} color="text-red-400" />
        </div>
      </div>

      {diff.summary.first_divergence_sequence != null && (
        <div className="px-4 py-2 bg-yellow-950 text-yellow-300 text-xs border-b border-yellow-800">
          First divergence at sequence #{diff.summary.first_divergence_sequence}
        </div>
      )}

      {/* Pair list */}
      <div className="flex-1 overflow-auto">
        {diff.snapshot_pairs.map((pair, i) => (
          <SnapshotPairRow key={i} pair={pair} />
        ))}
      </div>
    </div>
  );
}

function DiffCount({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: string;
}) {
  return (
    <span className={color}>
      {count} {label}
    </span>
  );
}

function SnapshotPairRow({ pair }: { pair: SnapshotPair }) {
  const [expanded, setExpanded] = React.useState(pair.match_type === "modified");
  const style = MATCH_TYPE_STYLES[pair.match_type];
  const symbol = MATCH_TYPE_LABELS[pair.match_type];

  return (
    <div className={clsx("border-b border-gray-800", style)}>
      <button
        className="flex items-center gap-3 w-full px-4 py-2 text-left hover:opacity-90"
        onClick={() => setExpanded((e) => !e)}
      >
        <span className="font-mono text-sm font-bold w-4">{symbol}</span>
        <span className="text-sm truncate flex-1">{pair.node_id}</span>
        {pair.field_diffs.length > 0 && (
          <span className="text-xs opacity-70">
            {pair.field_diffs.length} field{pair.field_diffs.length > 1 ? "s" : ""} changed
          </span>
        )}
      </button>

      {expanded && pair.field_diffs.length > 0 && (
        <div className="px-4 pb-3 space-y-2">
          {pair.field_diffs.map((fd, i) => (
            <div key={i} className="text-xs">
              <div className="font-mono text-gray-400 mb-1">{fd.field_path}</div>
              <div className="grid grid-cols-2 gap-2">
                <pre className="bg-red-950 text-red-200 rounded p-2 overflow-auto max-h-24 whitespace-pre-wrap break-all">
                  {JSON.stringify(fd.value_a, null, 2)}
                </pre>
                <pre className="bg-green-950 text-green-200 rounded p-2 overflow-auto max-h-24 whitespace-pre-wrap break-all">
                  {JSON.stringify(fd.value_b, null, 2)}
                </pre>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
