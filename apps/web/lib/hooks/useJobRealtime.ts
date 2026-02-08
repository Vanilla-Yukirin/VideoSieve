import { useEffect, useRef, useReducer } from "react";
import { api } from "../api/client";
import { jobReducer, initialState } from "../state/jobReducer";

export function useJobRealtime(jobId: string) {
  const [state, dispatch] = useReducer(jobReducer, initialState);

  const wsRef = useRef<WebSocket | null>(null);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Initial Snapshot
  useEffect(() => {
    if (!jobId) return;
    api.getJobSnapshot(jobId).then((snap) => {
      dispatch({ type: "SNAPSHOT", payload: snap });
    }).catch(console.error);
  }, [jobId]);

  // WebSocket & Polling Logic
  useEffect(() => {
    if (!jobId) return;

    if (api.getRuntimeMode() === "mock") {
      const timer = setInterval(() => {
        api
          .getJobSnapshot(jobId)
          .then((snap) => dispatch({ type: "SNAPSHOT", payload: snap }))
          .catch(console.error);
      }, 2000);
      return () => clearInterval(timer);
    }

    let isMounted = true;
    const wsUrl = `ws://127.0.0.1:8000/ws/jobs/${jobId}`;

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
        api.getJobSnapshot(jobId)
          .then((snap) => {
              if(isMounted) dispatch({ type: "SNAPSHOT", payload: snap });
          })
          .catch((e) => console.error("Poll error", e));
      }, 2000);
    }

    function stopPolling() {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
        dispatch({ type: "POLL_END" });
      }
    }

    connect();

    return () => {
      isMounted = false;
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      stopPolling();
    };
  }, [jobId]);

  return state;
}
