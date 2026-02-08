import { JobSnapshot } from "../api/types";

export type RealtimeState = JobSnapshot & {
  isConnected: boolean;
  isPolling: boolean;
};

export type Action =
  | { type: "SNAPSHOT"; payload: JobSnapshot }
  | { type: "EVENT"; eventType: string; payload: any }
  | { type: "CONNECT" }
  | { type: "DISCONNECT" }
  | { type: "POLL_START" }
  | { type: "POLL_END" };

export const initialState: RealtimeState = {
  project_id: "",
  job_id: "",
  status: "unknown",
  current_stage: null,
  progress: 0,
  latest_logs: [],
  artifacts: [],
  isConnected: false,
  isPolling: false,
};

export function jobReducer(state: RealtimeState, action: Action): RealtimeState {
  switch (action.type) {
    case "SNAPSHOT":
      return {
        ...state,
        ...action.payload,
        latest_logs: action.payload.latest_logs,
      };
    case "CONNECT":
      return { ...state, isConnected: true, isPolling: false };
    case "DISCONNECT":
      return { ...state, isConnected: false, isPolling: true };
    case "POLL_START":
      return { ...state, isPolling: true };
    case "POLL_END":
      return { ...state, isPolling: false };
    case "EVENT":
      const { eventType, payload } = action;
      if (eventType === "log") {
        const msg = payload.message;
        const level = payload.level;
        const line = level ? `[${level}] ${msg}` : msg;
        return {
          ...state,
          latest_logs: [...state.latest_logs, line].slice(-100),
        };
      }
      if (eventType === "progress") {
        return {
          ...state,
          progress: payload.pct,
          current_stage: payload.stage || state.current_stage,
        };
      }
      if (eventType === "stage_changed") {
        return {
          ...state,
          current_stage: payload.to,
        };
      }
      if (eventType === "snapshot") {
         return {
            ...state,
            ...payload,
            latest_logs: payload.latest_logs || [],
         }
      }
      return state;
    default:
      return state;
  }
}
