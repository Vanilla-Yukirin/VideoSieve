import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { ControlAck, ControlCommandType, JobSnapshot } from "../api/types";
import { jobReducer, initialState } from "../state/jobReducer";

const API_ORIGIN = (process.env.NEXT_PUBLIC_API_ORIGIN || "http://127.0.0.1:8040").replace(/\/+$/, "");
const COMMAND_TIMEOUT_MS = 10_000;
const RECONNECT_DELAY_MS = 2_000;

function toWebSocketOrigin(origin: string): string {
  if (origin.startsWith("https://")) return `wss://${origin.slice("https://".length)}`;
  if (origin.startsWith("http://")) return `ws://${origin.slice("http://".length)}`;
  return origin;
}

const WS_ORIGIN = toWebSocketOrigin(API_ORIGIN);

type PendingCommand = {
  resolve: (ack: ControlAck) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
};

export function useJobRealtime(jobId: string) {
  const [state, dispatch] = useReducer(jobReducer, initialState);
  const [isMissing, setIsMissing] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const cursorRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingCommandsRef = useRef(new Map<string, PendingCommand>());

  const sendCommand = useCallback(
    (command: ControlCommandType): Promise<ControlAck> => {
      const socket = wsRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        return Promise.reject(new Error("job websocket is not connected"));
      }
      const requestId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      return new Promise<ControlAck>((resolve, reject) => {
        const timer = setTimeout(() => {
          pendingCommandsRef.current.delete(requestId);
          reject(new Error(`control command timed out: ${command}`));
        }, COMMAND_TIMEOUT_MS);
        pendingCommandsRef.current.set(requestId, { resolve, reject, timer });
        socket.send(JSON.stringify({ command, request_id: requestId }));
      });
    },
    [],
  );

  useEffect(() => {
    if (!jobId) return;
    cursorRef.current = 0;
    let active = true;

    const rejectPending = (message: string) => {
      pendingCommandsRef.current.forEach((pending) => {
        clearTimeout(pending.timer);
        pending.reject(new Error(message));
      });
      pendingCommandsRef.current.clear();
    };

    const connect = () => {
      if (!active || wsRef.current) return;
      const cursorQuery = cursorRef.current > 0 ? `?after_cursor=${cursorRef.current}` : "";
      const socket = new WebSocket(`${WS_ORIGIN}/ws/jobs/${jobId}${cursorQuery}`);
      wsRef.current = socket;

      socket.onopen = () => {
        if (!active) return;
        setIsMissing(false);
        dispatch({ type: "CONNECT" });
      };

      socket.onmessage = (event) => {
        if (!active) return;
        try {
          const data = JSON.parse(event.data) as {
            event_type?: string;
            cursor?: number;
            state_version?: number;
            payload?: Record<string, unknown>;
          };
          const previousCursor = cursorRef.current;
          if (
            data.event_type !== "snapshot" &&
            typeof data.cursor === "number" &&
            data.cursor <= previousCursor
          ) {
            return;
          }
          if (typeof data.cursor === "number" && data.cursor > previousCursor) {
            cursorRef.current = data.cursor;
          }
          if (data.event_type === "snapshot" && data.payload) {
            dispatch({
              type: "SNAPSHOT",
              payload: data.payload as unknown as JobSnapshot,
              cursor: data.cursor,
            });
            return;
          }
          if (data.event_type === "control_ack" && data.payload) {
            const ack = data.payload as unknown as ControlAck;
            if (ack.request_id) {
              const pending = pendingCommandsRef.current.get(ack.request_id);
              if (pending) {
                clearTimeout(pending.timer);
                pendingCommandsRef.current.delete(ack.request_id);
                pending.resolve(ack);
              }
            }
          }
          if (data.event_type && data.payload) {
            dispatch({
              type: "EVENT",
              eventType: data.event_type,
              payload: data.payload,
              cursor: data.cursor,
              stateVersion: data.state_version,
            });
          }
        } catch (error) {
          console.error("WS parse error", error);
        }
      };

      socket.onclose = (event) => {
        if (wsRef.current === socket) wsRef.current = null;
        rejectPending("job websocket disconnected");
        if (!active) return;
        dispatch({ type: "DISCONNECT" });
        if (event.code === 4404) {
          setIsMissing(true);
          return;
        }
        reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();
    return () => {
      active = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
      const socket = wsRef.current;
      wsRef.current = null;
      if (socket) socket.close();
      rejectPending("job websocket closed");
    };
  }, [jobId]);

  return { ...state, isMissing, sendCommand };
}
