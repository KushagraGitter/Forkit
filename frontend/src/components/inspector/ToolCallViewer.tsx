import React, { useState } from "react";
import type { ToolCall, ToolResult } from "@/types";
import { ChevronDown, ChevronRight, AlertCircle, CheckCircle } from "lucide-react";

interface Props {
  toolCalls: ToolCall[];
  toolResults: ToolResult[];
}

export function ToolCallViewer({ toolCalls, toolResults }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (toolCalls.length === 0) {
    return <div className="p-4 text-gray-500 text-sm">No tool calls at this snapshot.</div>;
  }

  const resultMap = Object.fromEntries(toolResults.map((r) => [r.tool_call_id, r]));

  return (
    <div className="p-3 space-y-2">
      {toolCalls.map((tc) => {
        const result = resultMap[tc.id];
        const isExpanded = expanded.has(tc.id);
        const hasError = result?.error;

        return (
          <div key={tc.id} className="rounded-lg border border-gray-700 overflow-hidden">
            <button
              className="flex items-center gap-2 w-full px-3 py-2 bg-gray-800 hover:bg-gray-750 text-left"
              onClick={() =>
                setExpanded((s) => {
                  const next = new Set(s);
                  next.has(tc.id) ? next.delete(tc.id) : next.add(tc.id);
                  return next;
                })
              }
            >
              {isExpanded ? (
                <ChevronDown size={12} className="text-gray-400" />
              ) : (
                <ChevronRight size={12} className="text-gray-400" />
              )}
              <span className="text-sm font-medium text-amber-300">{tc.name}</span>
              {hasError ? (
                <AlertCircle size={12} className="ml-auto text-red-400" />
              ) : result ? (
                <CheckCircle size={12} className="ml-auto text-emerald-400" />
              ) : null}
            </button>

            {isExpanded && (
              <div className="border-t border-gray-700">
                <div className="px-3 py-2 bg-gray-900">
                  <div className="text-xs text-gray-400 mb-1">Arguments</div>
                  <pre className="text-xs text-gray-200 whitespace-pre-wrap break-all">
                    {JSON.stringify(tc.arguments, null, 2)}
                  </pre>
                </div>
                {result && (
                  <div className="px-3 py-2 bg-gray-900 border-t border-gray-700">
                    <div className="text-xs text-gray-400 mb-1">
                      {hasError ? (
                        <span className="text-red-400">Error</span>
                      ) : (
                        "Result"
                      )}
                    </div>
                    <pre className="text-xs text-gray-200 whitespace-pre-wrap break-all max-h-40 overflow-auto">
                      {hasError
                        ? result.error
                        : JSON.stringify(result.result, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
