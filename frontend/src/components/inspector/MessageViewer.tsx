import React from "react";
import type { Message } from "@/types";
import clsx from "clsx";

const ROLE_COLORS: Record<string, string> = {
  system: "bg-gray-700 text-gray-300",
  user: "bg-blue-900 text-blue-200",
  assistant: "bg-indigo-900 text-indigo-200",
  tool: "bg-amber-900 text-amber-200",
  function: "bg-amber-900 text-amber-200",
};

interface Props {
  messagesIn: Message[];
  messagesOut: Message[];
}

export function MessageViewer({ messagesIn, messagesOut }: Props) {
  const allMessages = [
    ...messagesIn.map((m) => ({ ...m, direction: "in" as const })),
    ...messagesOut.map((m) => ({ ...m, direction: "out" as const })),
  ];

  if (allMessages.length === 0) {
    return (
      <div className="p-4 text-gray-500 text-sm">No messages at this snapshot.</div>
    );
  }

  return (
    <div className="p-3 space-y-2">
      {allMessages.map((msg, i) => {
        const content =
          typeof msg.content === "string"
            ? msg.content
            : JSON.stringify(msg.content, null, 2);
        const roleColor = ROLE_COLORS[msg.role] ?? "bg-gray-800 text-gray-200";
        return (
          <div key={i} className="rounded-lg overflow-hidden">
            <div className={clsx("flex items-center gap-2 px-3 py-1.5 text-xs font-medium", roleColor)}>
              <span className="uppercase">{msg.role}</span>
              {msg.direction === "in" && (
                <span className="ml-auto text-gray-400 text-xs">input</span>
              )}
              {msg.direction === "out" && (
                <span className="ml-auto text-xs">output</span>
              )}
            </div>
            <pre className="bg-gray-800 text-gray-200 text-xs p-3 whitespace-pre-wrap break-all max-h-48 overflow-auto">
              {content}
            </pre>
          </div>
        );
      })}
    </div>
  );
}
