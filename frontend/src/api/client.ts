import type { Session, Message } from "../types";

const API_BASE = "/api";

export async function fetchSessions(): Promise<Session[]> {
  const res = await fetch(`${API_BASE}/sessions`);
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function createSession(title?: string, agentName?: string): Promise<Session> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title || "新对话", agentName: agentName || "claude" }),
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function fetchMessages(sessionId: string): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}

export function createChatStream(
  sessionId: string,
  content: string,
  onToken: (token: string) => void,
  onDone: (messageId?: string, error?: string) => void,
): () => void {
  const url = `${API_BASE}/sessions/${sessionId}/chat`;
  const abortCtrl = new AbortController();

  (async () => {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
      signal: abortCtrl.signal,
    });

    if (!response.ok) {
      onDone(undefined, `HTTP ${response.status}`);
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) return;

    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    let completed = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const dataStr = line.slice(6);
          try {
            const data = JSON.parse(dataStr);
            if (data.token) onToken(data.token);
            if (data.done) {
              completed = true;
              onDone(data.messageId, data.error);
              return;
            }
          } catch (e) {
            console.warn("SSE parse error:", dataStr, e);
          }
        }
      }
    }

    if (!completed) {
      onDone(undefined, "Stream ended unexpectedly");
    }
  })();

  return () => abortCtrl.abort();
}
