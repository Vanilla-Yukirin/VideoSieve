"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

interface TaskFormProps {
  onTaskCreated?: () => void;
}

export function TaskForm({ onTaskCreated }: TaskFormProps) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!url.trim()) {
      setError("请输入视频链接");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await api.createTask({ video_url: url });
      setUrl("");
      if (onTaskCreated) {
        onTaskCreated();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建任务失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>添加视频</CardTitle>
        <CardDescription>
          支持 YouTube、Bilibili、TikTok 等 30+ 平台
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex gap-2">
          <Input
            type="url"
            placeholder="粘贴视频链接..."
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={loading}
            className="flex-1"
          />
          <Button type="submit" disabled={loading}>
            {loading ? "提交中..." : "提交"}
          </Button>
        </form>
        {error && (
          <p className="mt-2 text-sm text-destructive">{error}</p>
        )}
      </CardContent>
    </Card>
  );
}
