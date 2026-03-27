import React, { useState } from "react";
import clsx from "clsx";

interface Props {
  data: unknown;
  collapsed?: boolean;
  label?: string;
}

export function JsonViewer({ data, collapsed = false, label }: Props) {
  const [isCollapsed, setIsCollapsed] = useState(collapsed);
  const json = JSON.stringify(data, null, 2);

  return (
    <div className="font-mono text-xs">
      {label && (
        <button
          onClick={() => setIsCollapsed((c) => !c)}
          className="text-gray-400 hover:text-white mb-1 flex items-center gap-1"
        >
          <span>{isCollapsed ? "▶" : "▼"}</span>
          <span>{label}</span>
        </button>
      )}
      {!isCollapsed && (
        <pre
          className={clsx(
            "bg-gray-900 text-gray-200 rounded p-3 overflow-auto max-h-64 whitespace-pre-wrap break-all"
          )}
        >
          {json}
        </pre>
      )}
    </div>
  );
}
