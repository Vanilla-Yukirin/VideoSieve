import { jobReducer, initialState, RealtimeState } from "../../apps/web/lib/state/jobReducer";

describe("jobReducer", () => {
  it("converges usage events and ignores totals older than an authoritative snapshot", () => {
    const usage = { calls: 3, failed_calls: 1, elapsed_ms: 500, stages: {} };
    const state = { ...initialState, model_usage: usage };
    const updated = jobReducer(state, { type: "EVENT", eventType: "model_usage",
      payload: { ...usage, calls: 4 }, cursor: 5 });
    expect(updated.model_usage?.calls).toBe(4);
    const stale = jobReducer(updated, { type: "EVENT", eventType: "model_usage",
      payload: { ...usage, calls: 2 }, cursor: 6 });
    expect(stale.model_usage?.calls).toBe(4);
    expect(stale.lastCursor).toBe(6);
  });

  it.each(["pause", "cancel"])("keeps final usage when %s advances the task version", (command) => {
    const state = {
      ...initialState,
      status: "running",
      state_version: 1,
      lastCursor: 1,
    };
    const acknowledged = jobReducer(state, {
      type: "EVENT",
      eventType: "control_ack",
      payload: { command, accepted: true, phase: "accepted" },
      cursor: 2,
      stateVersion: 2,
    });
    const usage = { calls: 1, failed_calls: 0, elapsed_ms: 50, stages: {} };
    const updated = jobReducer(acknowledged, {
      type: "EVENT",
      eventType: "model_usage",
      payload: usage,
      cursor: 3,
      stateVersion: 1,
    });
    expect(updated.model_usage).toEqual(usage);
    expect(updated.state_version).toBe(2);
    expect(updated.status).toBe("running");
    expect(updated.lastCursor).toBe(3);
  });

  it("still rejects duplicate cursors and decreasing usage after control", () => {
    const usage = { calls: 4, failed_calls: 1, elapsed_ms: 500, stages: {} };
    const state = { ...initialState, state_version: 8, lastCursor: 12, model_usage: usage };
    const duplicate = jobReducer(state, {
      type: "EVENT",
      eventType: "model_usage",
      payload: { ...usage, calls: 5 },
      cursor: 12,
      stateVersion: 7,
    });
    expect(duplicate).toBe(state);
    const lowerTotal = jobReducer(state, {
      type: "EVENT",
      eventType: "model_usage",
      payload: { ...usage, calls: 3 },
      cursor: 13,
      stateVersion: 7,
    });
    expect(lowerTotal.model_usage).toBe(usage);
    expect(lowerTotal.state_version).toBe(8);
    expect(lowerTotal.lastCursor).toBe(13);
  });
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

  it("should update execution state from websocket events", () => {
    const state = { ...initialState, status: "running", current_stage: "asr" };
    const newState = jobReducer(state, {
      type: "EVENT",
      eventType: "job_state_changed",
      payload: { from: "running", to: "paused", stage: "asr" },
    });
    expect(newState.status).toBe("paused");
    expect(newState.current_stage).toBe("asr");
  });

  it("should ignore duplicate cursors and stale state versions", () => {
    const state: RealtimeState = {
      ...initialState,
      status: "running",
      state_version: 8,
      lastCursor: 12,
    };
    const duplicate = jobReducer(state, {
      type: "EVENT",
      eventType: "job_state_changed",
      payload: { to: "failed" },
      cursor: 12,
      stateVersion: 9,
    });
    expect(duplicate).toBe(state);

    const stale = jobReducer(state, {
      type: "EVENT",
      eventType: "job_state_changed",
      payload: { to: "queued" },
      cursor: 13,
      stateVersion: 7,
    });
    expect(stale.status).toBe("running");
    expect(stale.state_version).toBe(8);
    expect(stale.lastCursor).toBe(13);
  });

  it("should switch connection state", () => {
    let state = jobReducer(initialState, { type: "CONNECT" });
    expect(state.isConnected).toBe(true);

    state = jobReducer(state, { type: "DISCONNECT" });
    expect(state.isConnected).toBe(false);
  });
});
