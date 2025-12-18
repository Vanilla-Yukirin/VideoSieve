/**
 * Server-Sent Events (SSE) client for real-time task updates.
 */
import type { TaskStreamEvent } from "@/types/task";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export function connectTaskStream(
  taskId: string,
  onUpdate: (event: TaskStreamEvent) => void,
  onError?: (error: Event) => void
): EventSource {
  const eventSource = new EventSource(`${API_URL}/tasks/${taskId}/stream`);

  eventSource.onmessage = (event) => {
    try {
      const data: TaskStreamEvent = JSON.parse(event.data);
      onUpdate(data);

      // Close connection if task is completed or failed
      if (data.status === "completed" || data.status === "failed") {
        eventSource.close();
      }
    } catch (error) {
      console.error("Failed to parse SSE data:", error);
    }
  };

  eventSource.onerror = (error) => {
    console.error("SSE connection error:", error);
    if (onError) {
      onError(error);
    }
  };

  return eventSource;
}
