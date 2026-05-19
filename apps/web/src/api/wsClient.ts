export type ClientEvent = {
  event: string;
  payload: Record<string, unknown>;
};

type MessageHandler = (event: ClientEvent) => void;
type SocketHandler = () => void;
type SocketErrorHandler = (event: Event) => void;

export function createSessionSocket(sessionId: string) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.hostname}:8000/ws/session/${sessionId}`;
  const ws = new WebSocket(wsUrl);
  let manuallyClosed = false;
  const handlers: MessageHandler[] = [];
  const openHandlers: SocketHandler[] = [];
  const closeHandlers: SocketHandler[] = [];
  const errorHandlers: SocketErrorHandler[] = [];

  ws.onopen = () => {
    if (manuallyClosed) {
      ws.close();
      return;
    }
    ws.send(JSON.stringify({ event: 'session.init', payload: {} }));
    openHandlers.forEach((handler) => handler());
  };

  ws.onclose = () => {
    if (manuallyClosed) return;
    closeHandlers.forEach((handler) => handler());
  };

  ws.onerror = (event) => {
    if (manuallyClosed) return;
    errorHandlers.forEach((handler) => handler(event));
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
    onOpen(handler: SocketHandler) {
      openHandlers.push(handler);
    },
    onClose(handler: SocketHandler) {
      closeHandlers.push(handler);
    },
    onError(handler: SocketErrorHandler) {
      errorHandlers.push(handler);
    },
    readyState() {
      return ws.readyState;
    },
    close() {
      manuallyClosed = true;
      if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    },
  };
}
