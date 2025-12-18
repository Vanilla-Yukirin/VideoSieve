/**
 * Backend API client.
 */
import type { Task, TaskCreateRequest, TaskListResponse } from "@/types/task";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export const api = {
  /**
   * Create a new task.
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
      throw new Error(`Failed to create task: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * Get list of all tasks.
   */
  async getTasks(): Promise<TaskListResponse> {
    const response = await fetch(`${API_URL}/tasks/`);

    if (!response.ok) {
      throw new Error(`Failed to fetch tasks: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * Get a specific task.
   */
  async getTask(taskId: string): Promise<Task> {
    const response = await fetch(`${API_URL}/tasks/${taskId}`);

    if (!response.ok) {
      throw new Error(`Failed to fetch task: ${response.statusText}`);
    }

    return response.json();
  },

  /**
   * Delete a task.
   */
  async deleteTask(taskId: string): Promise<void> {
    const response = await fetch(`${API_URL}/tasks/${taskId}`, {
      method: "DELETE",
    });

    if (!response.ok) {
      throw new Error(`Failed to delete task: ${response.statusText}`);
    }
  },

  /**
   * Get task transcript.
   */
  async getTranscript(taskId: string): Promise<string> {
    const response = await fetch(`${API_URL}/tasks/${taskId}/transcript`);

    if (!response.ok) {
      throw new Error(`Failed to fetch transcript: ${response.statusText}`);
    }

    const data = await response.json();
    return data.transcript;
  },

  /**
   * Get optimized text.
   */
  async getOptimized(taskId: string): Promise<string> {
    const response = await fetch(`${API_URL}/tasks/${taskId}/optimized`);

    if (!response.ok) {
      throw new Error(`Failed to fetch optimized text: ${response.statusText}`);
    }

    const data = await response.json();
    return data.optimized_text;
  },

  /**
   * Get task summary.
   */
  async getSummary(taskId: string): Promise<string> {
    const response = await fetch(`${API_URL}/tasks/${taskId}/summary`);

    if (!response.ok) {
      throw new Error(`Failed to fetch summary: ${response.statusText}`);
    }

    const data = await response.json();
    return data.summary;
  },
};
