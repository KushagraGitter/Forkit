/**
 * StateEditor — Monaco-based JSON editor for editing agent state before forking.
 */

import React from "react";
import Editor from "@monaco-editor/react";

interface Props {
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  height?: string;
}

export function StateEditor({ value, onChange, height = "200px" }: Props) {
  const handleChange = (raw: string | undefined) => {
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw);
      onChange(parsed);
    } catch {
      // Let user finish typing — don't propagate invalid JSON
    }
  };

  return (
    <div className="rounded-lg overflow-hidden border border-gray-600">
      <Editor
        height={height}
        defaultLanguage="json"
        value={JSON.stringify(value, null, 2)}
        onChange={handleChange}
        theme="vs-dark"
        options={{
          minimap: { enabled: false },
          fontSize: 12,
          lineNumbers: "off",
          scrollBeyondLastLine: false,
          wordWrap: "on",
          folding: true,
          tabSize: 2,
        }}
      />
    </div>
  );
}
