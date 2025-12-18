"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { Task } from "@/types/task";
import { api } from "@/lib/api";

interface TaskDetailsProps {
  task: Task;
  onClose?: () => void;
}

export function TaskDetails({ task, onClose }: TaskDetailsProps) {
  const [transcript, setTranscript] = useState<string>("");
  const [optimized, setOptimized] = useState<string>("");
  const [summary, setSummary] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (task.status === "completed") {
      loadDetails();
    }
  }, [task.id, task.status]);

  const loadDetails = async () => {
    setLoading(true);
    try {
      const [transcriptData, optimizedData, summaryData] = await Promise.all([
        api.getTranscript(task.id).catch(() => ""),
        api.getOptimized(task.id).catch(() => ""),
        api.getSummary(task.id).catch(() => ""),
      ]);
      setTranscript(transcriptData);
      setOptimized(optimizedData);
      setSummary(summaryData);
    } catch (error) {
      console.error("加载任务详情失败:", error);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">任务详情</h2>
        {onClose && (
          <Button onClick={onClose} variant="outline">
            关闭
          </Button>
        )}
      </div>

      {loading ? (
        <div className="text-center py-8">加载中...</div>
      ) : (
        <div className="space-y-4">
          {summary && (
            <Card>
              <CardHeader>
                <div className="flex justify-between items-center">
                  <CardTitle>摘要</CardTitle>
                  <Button onClick={() => copyToClipboard(summary)} variant="outline" size="sm">
                    复制
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap">{summary}</p>
              </CardContent>
            </Card>
          )}

          {optimized && (
            <Card>
              <CardHeader>
                <div className="flex justify-between items-center">
                  <CardTitle>优化文本</CardTitle>
                  <Button onClick={() => copyToClipboard(optimized)} variant="outline" size="sm">
                    复制
                  </Button>
                </div>
                <CardDescription>AI 优化后的转录文本</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap">{optimized}</p>
              </CardContent>
            </Card>
          )}

          {transcript && (
            <Card>
              <CardHeader>
                <div className="flex justify-between items-center">
                  <CardTitle>原始转录</CardTitle>
                  <Button onClick={() => copyToClipboard(transcript)} variant="outline" size="sm">
                    复制
                  </Button>
                </div>
                <CardDescription>Whisper 转录原文</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="whitespace-pre-wrap">{transcript}</p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
