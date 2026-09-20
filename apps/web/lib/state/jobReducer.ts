import { JobSnapshot } from "../api/types";

export type RealtimeState = JobSnapshot & {
  isConnected: boolean;
  lastCursor: number;
};

export type Action =
  | { type: "SNAPSHOT"; payload: JobSnapshot; cursor?: number }
  | {
      type: "EVENT";
      eventType: string;
      payload: any;
      cursor?: number;
      stateVersion?: number;
    }
  | { type: "CONNECT" }
  | { type: "DISCONNECT" };

export const initialState: RealtimeState = {
  project_id: "",
  job_id: "",
  state_version: 0,
  status: "unknown",
  current_stage: null,
  requested_action: null,
  control_phase: null,
  control_request_id: null,
  attempt: 0,
  progress: 0,
  error_code: null,
  error_message: null,
  latest_logs: [],
  artifacts: [],
  isConnected: false,
  lastCursor: 0,
};

export function jobReducer(state: RealtimeState, action: Action): RealtimeState {
  switch (action.type) {
    case "SNAPSHOT":
      return {
        ...state,
        ...action.payload,
        latest_logs: action.payload.latest_logs,
        lastCursor: Math.max(state.lastCursor, action.cursor ?? 0),
      };
    case "CONNECT":
      return { ...state, isConnected: true };
    case "DISCONNECT":
      return { ...state, isConnected: false };
    case "EVENT":
      const { eventType, payload, cursor, stateVersion } = action;
      if (cursor !== undefined && cursor <= state.lastCursor) return state;
      const nextCursor = Math.max(state.lastCursor, cursor ?? 0);
      if (stateVersion !== undefined && stateVersion < state.state_version) {
        return { ...state, lastCursor: nextCursor };
      }
      const nextStateVersion = Math.max(state.state_version, stateVersion ?? 0);
      if (eventType === "log") {
        const msg = payload.message;
        const level = payload.level;
        const line = level ? `[${level}] ${msg}` : msg;
        return {
          ...state,
          state_version: nextStateVersion,
          lastCursor: nextCursor,
          latest_logs: [...state.latest_logs, line].slice(-100),
        };
      }
      if (eventType === "progress") {
        return {
          ...state,
          state_version: nextStateVersion,
          lastCursor: nextCursor,
          progress: payload.pct,
          current_stage: payload.stage || state.current_stage,
        };
      }
      if (eventType === "stage_changed") {
        return {
          ...state,
          state_version: nextStateVersion,
          lastCursor: nextCursor,
          current_stage: payload.to,
        };
      }
      if (eventType === "job_state_changed") {
        return {
          ...state,
          state_version: nextStateVersion,
          lastCursor: nextCursor,
          status: typeof payload.to === "string" ? payload.to : state.status,
          current_stage:
            typeof payload.stage === "string" || payload.stage === null
              ? payload.stage
              : state.current_stage,
        };
      }
      if (eventType === "error") {
        return {
          ...state,
          state_version: nextStateVersion,
          lastCursor: nextCursor,
          error_code: typeof payload.code === "string" ? payload.code : state.error_code,
          error_message:
            typeof payload.message === "string" ? payload.message : state.error_message,
        };
      }
      return {
        ...state,
        state_version: nextStateVersion,
        lastCursor: nextCursor,
      };
    default:
      return state;
  }
}
