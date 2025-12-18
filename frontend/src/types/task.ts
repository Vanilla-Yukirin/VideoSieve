/**
 * 任务相关的 TypeScript 类型定义。
 */

export interface Task {
  id: string;
  video_url: string;
  status: TaskStatus;
  progress: number;
  error_message?: string;
  audio_path?: string;
  transcript?: string;
  optimized_text?: string;
  summary?: string;
  logs: LogEntry[];
  created_at: string;
  updated_at: string;
}

export type TaskStatus = 
  | "pending"      // 等待中
  | "downloading"  // 下载中
  | "transcribing" // 转录中
  | "processing"   // 处理中
  | "completed"    // 已完成
  | "failed";      // 失败

export interface LogEntry {
  time: string;
  message: string;
}

export interface TaskCreateRequest {
  video_url: string;
}

export interface TaskListResponse {
  tasks: Task[];
  total: number;
}

export interface TaskStreamEvent {
  task_id: string;
  status: TaskStatus;
  progress: number;
  logs: LogEntry[];
  error_message?: string;
}
