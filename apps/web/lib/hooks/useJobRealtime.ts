import { useEffect, useRef, useReducer } from "react";
import { api } from "../api/client";
import { jobReducer, initialState } from "../state/jobReducer";

const API_ORIGIN = (process.env.NEXT_PUBLIC_API_ORIGIN || "http://127.0.0.1:8040").replace(/\/+$/, "");

function toWebSocketOrigin(origin: string): string {
  if (origin.startsWith("https://")) {
    return `wss://${origin.slice("https://".length)}`;
  }
  if (origin.startsWith("http://")) {
    return `ws://${origin.slice("http://".length)}`;
  }
  return origin;
}

const WS_ORIGIN = toWebSocketOrigin(API_ORIGIN);
const SNAPSHOT_INTERVAL_MS = 2000;
const WS_HEARTBEAT_SNAPSHOT_MS = 5000;
const RESYNC_DEBOUNCE_MS = 350;

function isTerminalStatus(status: string): boolean {
  return status === "succeeded" || status === "failed" || status === "cancelled";
}

export function useJobRealtime(jobId: string) {
  const [state, dispatch] = useReducer(jobReducer, initialState);

  const wsRef = useRef<WebSocket | null>(null);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const resyncTimerRef = useRef<NodeJS.Timeout | null>(null);
  const latestStatusRef = useRef<string>(initialState.status);

  useEffect(() => {
    latestStatusRef.current = state.status;
  }, [state.status]);

  // WebSocket & Polling Logic
  useEffect(() => {
    if (!jobId) return;

    let isMounted = true;

    const requestSnapshot = () => {
      api.getJobSnapshot(jobId)
        .then((snap) => {
          if (!isMounted) return;
          dispatch({ type: "SNAPSHOT", payload: snap });
        })
        .catch((e) => {
          if (isMounted) {
            console.error("Snapshot error", e);
          }
        });
    };

    const scheduleResync = () => {
      if (resyncTimerRef.current) return;
      resyncTimerRef.current = setTimeout(() => {
        resyncTimerRef.current = null;
        requestSnapshot();
      }, RESYNC_DEBOUNCE_MS);
    };

    requestSnapshot();

    if (api.getRuntimeMode() === "mock") {
      const timer = setInterval(() => {
        if (isTerminalStatus(latestStatusRef.current)) {
          return;
        }
        requestSnapshot();
      }, SNAPSHOT_INTERVAL_MS);
      return () => {
        isMounted = false;
        clearInterval(timer);
      };
    }
    const wsUrl = `${WS_ORIGIN}/ws/jobs/${jobId}`;
    let heartbeatTimer: NodeJS.Timeout | null = null;

    function connect() {
      if (wsRef.current) return;
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMounted) return;
        console.log("WS Connected");
        dispatch({ type: "CONNECT" });
        stopPolling();
      };

      ws.onmessage = (event) => {
        if (!isMounted) return;
        try {
          const data = JSON.parse(event.data);
          dispatch({ type: "EVENT", eventType: data.event_type, payload: data.payload });
          if (
            data.event_type === "snapshot" ||
            data.event_type === "stage_changed" ||
            data.event_type === "progress"
          ) {
            scheduleResync();
          }
        } catch (e) {
          console.error("WS parse error", e);
        }
      };

      ws.onclose = () => {
        if (!isMounted) return;
        console.log("WS Closed");
        wsRef.current = null;
        dispatch({ type: "DISCONNECT" });
        startPolling();
        // Retry connection in 3s
        setTimeout(() => {
            if(isMounted && !wsRef.current) connect();
        }, 3000);
      };

      ws.onerror = (e) => {
        console.error("WS Error", e);
        // Close will trigger onclose
      };
    }

    function startPolling() {
      if (pollTimerRef.current) return;
      console.log("Starting polling fallback");
      dispatch({ type: "POLL_START" });
      pollTimerRef.current = setInterval(() => {
        if (isTerminalStatus(latestStatusRef.current)) {
          return;
        }
        requestSnapshot();
      }, SNAPSHOT_INTERVAL_MS);
    }

    function stopPolling() {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
        dispatch({ type: "POLL_END" });
      }
    }

    connect();
    heartbeatTimer = setInterval(() => {
      if (isTerminalStatus(latestStatusRef.current)) {
        return;
      }
      const socket = wsRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        requestSnapshot();
      }
    }, WS_HEARTBEAT_SNAPSHOT_MS);

    return () => {
      isMounted = false;
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (resyncTimerRef.current) {
        clearTimeout(resyncTimerRef.current);
        resyncTimerRef.current = null;
      }
      stopPolling();
    };
  }, [jobId]);

  return state;
}
