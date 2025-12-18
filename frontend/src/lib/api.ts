/**
 * 后端 API 客户端。
 */
import type { Task, TaskCreateRequest, TaskListResponse } from "@/types/task";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export const api = {
  /**
   * 创建新任务。
   */
  async createTask(data: TaskCreateRequest): Promise<Task> {
    const response = await fetch(`${API_URL}/tasks/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      throw new Error(`创建任务失败: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * 获取所有任务列表。
   */
  async getTasks(): Promise<TaskListResponse> {
    const response = await fetch(`${API_URL}/tasks/`);

    if (!response.ok) {
      throw new Error(`获取任务失败: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * 获取特定任务。
   */
  async getTask(taskId: string): Promise<Task> {
    const response = await fetch(`${API_URL}/tasks/${taskId}`);

    if (!response.ok) {
      throw new Error(`获取任务失败: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * 删除任务。
   */
  async deleteTask(taskId: string): Promise<void> {
    const response = await fetch(`${API_URL}/tasks/${taskId}`, {
      method: "DELETE",
    });

    if (!response.ok) {
      throw new Error(`删除任务失败: ${response.statusText}`);
    }
  },

  /**
   * 获取任务转录。
   */
  async getTranscript(taskId: string): Promise<string> {
    const response = await fetch(`${API_URL}/tasks/${taskId}/transcript`);

    if (!response.ok) {
      throw new Error(`获取转录失败: ${response.statusText}`);
    }

    const data = await response.json();
    return data.transcript;
  },

  /**
   * 获取优化文本。
   */
  async getOptimized(taskId: string): Promise<string> {
    const response = await fetch(`${API_URL}/tasks/${taskId}/optimized`);

    if (!response.ok) {
      throw new Error(`获取优化文本失败: ${response.statusText}`);
    }

    const data = await response.json();
    return data.optimized_text;
  },

  /**
   * 获取任务摘要。
   */
  async getSummary(taskId: string): Promise<string> {
    const response = await fetch(`${API_URL}/tasks/${taskId}/summary`);

    if (!response.ok) {
      throw new Error(`获取摘要失败: ${response.statusText}`);
    }

    const data = await response.json();
    return data.summary;
  },
};
