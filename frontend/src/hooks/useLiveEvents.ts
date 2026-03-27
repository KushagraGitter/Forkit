import { useEffect, useRef } from "react";
import { RunWebSocket } from "@/api/ws";
import { useLiveStore } from "@/stores/liveStore";

export function useLiveEvents(runId: string | null) {
  const handleEvent = useLiveStore((s) => s.handleEvent);
  const setConnected = useLiveStore((s) => s.setConnected);
  const wsRef = useRef<RunWebSocket | null>(null);

  useEffect(() => {
    if (!runId) return;

    const ws = new RunWebSocket(runId);
    wsRef.current = ws;

    const unsub = ws.onEvent((event) => {
      if (event.type === "connected") setConnected(runId, true);
      handleEvent(event);
    });

    return () => {
      unsub();
      ws.close();
      setConnected(runId, false);
      wsRef.current = null;
    };
  }, [runId, handleEvent, setConnected]);
}
