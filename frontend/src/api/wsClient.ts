import { getActiveApiBaseUrl } from "./client";

type WSEventHandler = (event: Record<string, unknown>) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private sessionId: string | null = null;
  private handlers: Record<string, WSEventHandler[]> = {};
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectAttempts = 0;

  on(event: string, handler: WSEventHandler) {
    this.handlers[event] = this.handlers[event] ?? [];
    this.handlers[event].push(handler);
  }

  off(event: string, handler: WSEventHandler) {
    if (!this.handlers[event]) return;
    this.handlers[event] = this.handlers[event].filter((h) => h !== handler);
  }

  private emit(event: string, data: Record<string, unknown>) {
    (this.handlers[event] ?? []).forEach((h) => h(data));
  }

  connect(sessionId: string) {
    if (this.ws && this.sessionId === sessionId) return;
    this.disconnect();
    this.sessionId = sessionId;
    this.reconnectAttempts = 0;
    this._connect();
  }

  private _connect() {
    if (!this.sessionId) return;
    const url = buildWebSocketUrl(this.sessionId);

    try {
      this.ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.startHeartbeat();
      this.emit("connected", {});
    };

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "ping") {
          this.ws?.send(JSON.stringify({ type: "pong" }));
        } else if (data.type) {
          this.emit(data.type as string, data);
        }
      } catch { /* invalid JSON */ }
    };

    this.ws.onclose = () => {
      this.stopHeartbeat();
      this.ws = null;
      this.scheduleReconnect();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  disconnect() {
    this.stopHeartbeat();
    if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null; }
    if (this.ws) { this.ws.onclose = null; this.ws.close(); this.ws = null; }
    this.sessionId = null;
    this.reconnectAttempts = 0;
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "pong" }));
      }
    }, 25000);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) { clearInterval(this.heartbeatTimer); this.heartbeatTimer = null; }
  }

  private scheduleReconnect() {
    if (!this.sessionId) return;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => this._connect(), delay);
  }
}

export function buildWebSocketUrl(
  sessionId: string,
  apiBase = getActiveApiBaseUrl(),
  locationLike: Pick<Location, "protocol" | "host" | "origin"> = window.location,
): string {
  const base = new URL(apiBase || "/api", locationLike.origin);
  const protocol = base.protocol === "https:" ? "wss:" : "ws:";
  const prefix = stripApiSuffix(base.pathname);
  return `${protocol}//${base.host}${prefix}/ws/sessions/${encodeURIComponent(sessionId)}`;
}

function stripApiSuffix(pathname: string): string {
  const normalized = pathname.replace(/\/+$/, "");
  if (!normalized || normalized === "/api") return "";
  if (normalized.endsWith("/api")) return normalized.slice(0, -"/api".length);
  return normalized;
}
