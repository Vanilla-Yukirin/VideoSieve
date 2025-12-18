"use client";

import { useEffect, useState } from "react";
import { TaskForm } from "@/components/TaskForm";
import { TaskCard } from "@/components/TaskCard";
import { TaskDetails } from "@/components/TaskDetails";
import type { Task } from "@/types/task";
import { api } from "@/lib/api";

export default function Home() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);

  const loadTasks = async () => {
    try {
      const response = await api.getTasks();
      setTasks(response.tasks);
    } catch (error) {
      console.error("Failed to load tasks:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTasks();
    
    // Refresh tasks every 30 seconds
    const interval = setInterval(loadTasks, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleTaskCreated = () => {
    loadTasks();
  };

  const handleDelete = async (taskId: string) => {
    if (confirm("确定要删除这个任务吗？")) {
      try {
        await api.deleteTask(taskId);
        setTasks((prev) => prev.filter((t) => t.id !== taskId));
        if (selectedTask?.id === taskId) {
          setSelectedTask(null);
        }
      } catch (error) {
        console.error("Failed to delete task:", error);
        alert("删除失败");
      }
    }
  };

  return (
    <div className="space-y-8">
      <TaskForm onTaskCreated={handleTaskCreated} />

      {selectedTask ? (
        <TaskDetails task={selectedTask} onClose={() => setSelectedTask(null)} />
      ) : (
        <>
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-semibold">任务列表</h2>
            <span className="text-sm text-muted-foreground">
              共 {tasks.length} 个任务
            </span>
          </div>

          {loading ? (
            <div className="text-center py-8">加载中...</div>
          ) : tasks.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              还没有任务，开始添加视频吧！
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {tasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onDelete={() => handleDelete(task.id)}
                  onViewDetails={() => setSelectedTask(task)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
