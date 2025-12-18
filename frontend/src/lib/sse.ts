/**
 * Server-Sent Events (SSE) 客户端，用于实时任务更新。
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

      // 如果任务完成或失败，关闭连接
      if (data.status === "completed" || data.status === "failed") {
        eventSource.close();
      }
    } catch (error) {
      console.error("解析 SSE 数据失败:", error);
    }
  };

  eventSource.onerror = (error) => {
    console.error("SSE 连接错误:", error);
    if (onError) {
      onError(error);
    }
  };

  return eventSource;
}
