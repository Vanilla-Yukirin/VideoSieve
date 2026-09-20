export type ArtifactLoadState = "idle" | "loading" | "ok" | "not_found" | "error";

export function shouldArmCompletionRetry(
  previousJobStatus: string,
  currentJobStatus: string,
  loadState: ArtifactLoadState,
): boolean {
  if (previousJobStatus === "succeeded" || currentJobStatus !== "succeeded") return false;
  return loadState === "loading" || loadState === "not_found" || loadState === "error";
}

export function shouldConsumeCompletionRetry(
  jobStatus: string,
  armed: boolean,
  loadState: ArtifactLoadState,
): boolean {
  return (
    jobStatus === "succeeded" &&
    armed &&
    (loadState === "not_found" || loadState === "error")
  );
}
