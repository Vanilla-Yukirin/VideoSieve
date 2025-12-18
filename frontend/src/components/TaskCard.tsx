"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type { Task, TaskStatus } from "@/types/task";
import { connectTaskStream } from "@/lib/sse";

interface TaskCardProps {
  task: Task;
  onDelete?: () => void;
  onViewDetails?: () => void;
}

// 状态配置：标签和颜色
const statusConfig: Record<TaskStatus, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  pending: { label: "等待中", variant: "secondary" },
  downloading: { label: "下载中", variant: "default" },
  transcribing: { label: "转录中", variant: "default" },
  processing: { label: "处理中", variant: "default" },
  completed: { label: "已完成", variant: "outline" },
  failed: { label: "失败", variant: "destructive" },
};

export function TaskCard({ task: initialTask, onDelete, onViewDetails }: TaskCardProps) {
  const [task, setTask] = useState(initialTask);

  useEffect(() => {
    // 连接 SSE 进行实时更新
    if (task.status !== "completed" && task.status !== "failed") {
      const eventSource = connectTaskStream(
        task.id,
        (event) => {
          setTask((prev) => ({
            ...prev,
            status: event.status,
            progress: event.progress,
            logs: event.logs,
            error_message: event.error_message,
          }));
        }
      );

      return () => {
        eventSource.close();
      };
    }
  }, [task.id, task.status]);

  const statusInfo = statusConfig[task.status];
  const lastLog = task.logs && task.logs.length > 0 ? task.logs[task.logs.length - 1] : null;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-lg truncate">{task.video_url}</CardTitle>
            <CardDescription className="mt-1">
              {new Date(task.created_at).toLocaleString("zh-CN")}
            </CardDescription>
          </div>
          <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div>
            <div className="flex justify-between text-sm mb-2">
              <span className="text-muted-foreground">进度</span>
              <span className="font-medium">{task.progress}%</span>
            </div>
            <Progress value={task.progress} />
          </div>

          {lastLog && (
            <div className="text-sm text-muted-foreground">
              {lastLog.message}
            </div>
          )}

          {task.error_message && (
            <div className="text-sm text-destructive">
              错误: {task.error_message}
            </div>
          )}

          <div className="flex gap-2">
            {task.status === "completed" && (
              <Button onClick={onViewDetails} variant="default" size="sm">
                查看结果
              </Button>
            )}
            <Button onClick={onDelete} variant="destructive" size="sm">
              删除
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
