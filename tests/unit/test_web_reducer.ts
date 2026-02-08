import { jobReducer, initialState, RealtimeState } from "../../apps/web/lib/state/jobReducer";

describe("jobReducer", () => {
  it("should handle initial snapshot", () => {
    const snapshot: any = {
      project_id: "p1",
      job_id: "j1",
      status: "running",
      current_stage: "ingest",
      progress: 10,
      latest_logs: ["log1"],
      artifacts: [],
    };
    const newState = jobReducer(initialState, { type: "SNAPSHOT", payload: snapshot });
    expect(newState).toEqual({
      ...initialState,
      ...snapshot,
    });
  });

  it("should merge log events", () => {
    const state: RealtimeState = {
      ...initialState,
      latest_logs: ["line1"],
    };
    const newState = jobReducer(state, {
      type: "EVENT",
      eventType: "log",
      payload: { level: "info", message: "line2" },
    });
    expect(newState.latest_logs).toEqual(["line1", "[info] line2"]);
  });

  it("should update progress", () => {
    const state = { ...initialState };
    const newState = jobReducer(state, {
      type: "EVENT",
      eventType: "progress",
      payload: { pct: 50.5, stage: "asr" },
    });
    expect(newState.progress).toBe(50.5);
    expect(newState.current_stage).toBe("asr");
  });

  it("should switch connection state", () => {
    let state = jobReducer(initialState, { type: "CONNECT" });
    expect(state.isConnected).toBe(true);
    expect(state.isPolling).toBe(false);

    state = jobReducer(state, { type: "DISCONNECT" });
    expect(state.isConnected).toBe(false);
    expect(state.isPolling).toBe(true);
  });
});
