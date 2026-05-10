export type ClientEvent = {
  event: string;
  payload: Record<string, unknown>;
};

type MessageHandler = (event: ClientEvent) => void;

export function createSessionSocket(sessionId: string) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.hostname}:8000/ws/session/${sessionId}`;
  const ws = new WebSocket(wsUrl);
  const handlers: MessageHandler[] = [];

  ws.onopen = () => {
    ws.send(JSON.stringify({ event: 'session.init', payload: {} }));
  };

  ws.onmessage = (message) => {
    try {
      const event: ClientEvent = JSON.parse(message.data);
      handlers.forEach((h) => h(event));
    } catch {
      // ignore parse errors
    }
  };

  return {
    send(event: ClientEvent) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(event));
      }
    },
    onMessage(handler: MessageHandler) {
      handlers.push(handler);
      return () => {
        const idx = handlers.indexOf(handler);
        if (idx >= 0) handlers.splice(idx, 1);
      };
    },
    close() {
      ws.close();
    },
  };
}
