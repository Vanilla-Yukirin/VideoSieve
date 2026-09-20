import {
  shouldArmCompletionRetry,
  shouldConsumeCompletionRetry,
} from "../../apps/web/lib/artifacts/completionRetry";

describe("deliverable completion retries", () => {
  it("arms one retry for an attempted artifact when the job becomes succeeded", () => {
    const armed = shouldArmCompletionRetry("running", "succeeded", "not_found");

    expect(armed).toBe(true);
    expect(shouldConsumeCompletionRetry("succeeded", armed, "not_found")).toBe(true);
  });

  it("does not re-arm while the job remains succeeded", () => {
    expect(shouldArmCompletionRetry("succeeded", "succeeded", "not_found")).toBe(false);
    expect(shouldConsumeCompletionRetry("succeeded", false, "not_found")).toBe(false);
  });

  it("does not retry a tab that was never loaded before completion", () => {
    expect(shouldArmCompletionRetry("running", "succeeded", "idle")).toBe(false);
  });

  it("waits for an in-flight request to settle before consuming the retry", () => {
    const armed = shouldArmCompletionRetry("running", "succeeded", "loading");

    expect(armed).toBe(true);
    expect(shouldConsumeCompletionRetry("succeeded", armed, "loading")).toBe(false);
    expect(shouldConsumeCompletionRetry("succeeded", armed, "error")).toBe(true);
  });
});
