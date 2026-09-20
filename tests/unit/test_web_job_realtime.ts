/** @jest-environment jsdom */

import { act, renderHook } from "@testing-library/react";
import { useJobRealtime } from "../../apps/web/lib/hooks/useJobRealtime";

class _MockWebSocket {
  static readonly OPEN = 1;
  static instances: _MockWebSocket[] = [];

  readonly url: string;
  readyState = 0;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    _MockWebSocket.instances.push(this);
  }

  send(payload: string) {
    this.sent.push(payload);
  }

  close() {
    this.readyState = 3;
  }

  open() {
    this.readyState = _MockWebSocket.OPEN;
    this.onopen?.();
  }

  message(payload: object) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }

  disconnect(code = 1006) {
    this.readyState = 3;
    this.onclose?.({ code } as CloseEvent);
  }
}

describe("useJobRealtime", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    _MockWebSocket.instances = [];
    Object.defineProperty(globalThis, "WebSocket", {
      configurable: true,
      value: _MockWebSocket,
    });
    Object.defineProperty(globalThis, "fetch", {
      configurable: true,
      value: jest.fn(),
    });
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it("reconnects with the last SQLite event cursor and does not poll HTTP", () => {
    const { result, unmount } = renderHook(() => useJobRealtime("job-1"));
    const first = _MockWebSocket.instances[0];

    act(() => {
      first.open();
      first.message({
        event_type: "snapshot",
        cursor: 17,
        payload: {
          project_id: "project-1",
          job_id: "job-1",
          status: "running",
          current_stage: "asr",
          progress: 20,
          latest_logs: [],
          artifacts: [],
        },
      });
      first.disconnect();
      jest.advanceTimersByTime(2_000);
    });

    expect(result.current.status).toBe("running");
    expect(_MockWebSocket.instances[1].url).toContain("after_cursor=17");
    expect(globalThis.fetch).not.toHaveBeenCalled();
    unmount();
  });

  it("round-trips control acknowledgements by request_id", async () => {
    const { result, unmount } = renderHook(() => useJobRealtime("job-2"));
    const socket = _MockWebSocket.instances[0];
    act(() => socket.open());

    let ackPromise: ReturnType<typeof result.current.sendCommand>;
    act(() => {
      ackPromise = result.current.sendCommand("pause");
    });
    const request = JSON.parse(socket.sent[0]) as { command: string; request_id: string };
    act(() => {
      socket.message({
        event_type: "control_ack",
        payload: {
          command: "pause",
          accepted: true,
          request_id: request.request_id,
        },
      });
    });

    await expect(ackPromise!).resolves.toMatchObject({ command: "pause", accepted: true });
    unmount();
  });
});
