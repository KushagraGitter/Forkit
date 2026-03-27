/**
 * WebSocket client with automatic reconnection.
 * Feeds live events into the Zustand liveStore.
 */

import type { LiveEvent } from "@/types";

type EventHandler = (event: LiveEvent) => void;

export class RunWebSocket {
  private ws: WebSocket | null = null;
  private readonly url: string;
  private handlers: EventHandler[] = [];
  private reconnectDelay = 1000;
  private maxDelay = 16000;
  private closed = false;
  private pingInterval: ReturnType<typeof setInterval> | null = null;

  constructor(runId: string) {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const host = window.location.host;
    this.url = `${proto}://${host}/ws/runs/${runId}`;
    this.connect();
  }

  onEvent(handler: EventHandler): () => void {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  close(): void {
    this.closed = true;
    if (this.pingInterval) clearInterval(this.pingInterval);
    this.ws?.close();
  }

  private connect(): void {
    if (this.closed) return;
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.reconnectDelay = 1000;
      this.pingInterval = setInterval(() => {
        if (this.ws?.readyState === WebSocket.OPEN) {
          this.ws.send("ping");
        }
      }, 20000);
    };

    this.ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as LiveEvent;
        this.handlers.forEach((h) => h(event));
      } catch {
        // ignore malformed frames
      }
    };

    this.ws.onclose = () => {
      if (this.pingInterval) clearInterval(this.pingInterval);
      if (!this.closed) {
        setTimeout(() => {
          this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxDelay);
          this.connect();
        }, this.reconnectDelay);
      }
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }
}
