import React, { useState } from "react";
import { ControlCommandType } from "@/lib/api/types";
import { api } from "@/lib/api/client";
import { Button } from "./Button";
import { Play, Pause, Square, Trash2 } from "lucide-react";

interface ControlPanelProps {
  jobId: string;
  status: string;
}

export function ControlPanel({ jobId, status }: ControlPanelProps) {
  const [loadingCmd, setLoadingCmd] = useState<ControlCommandType | null>(null);

  const handleCommand = async (cmd: ControlCommandType) => {
    setLoadingCmd(cmd);
    try {
      const ack = await api.controlJob(jobId, cmd);
      if (!ack.accepted) {
        alert(`Command rejected: ${ack.reason}`);
      }
    } catch (e) {
      console.error(e);
      alert("Command failed to send");
    } finally {
      setLoadingCmd(null);
    }
  };

  const isRunning = status === "running";
  const isPaused = status === "paused";
  const isTerminated = ["succeeded", "failed", "cancelled"].includes(status);

  return (
    <div className="flex flex-wrap gap-2">
      {isRunning && (
        <>
          <Button
            variant="secondary"
            onClick={() => handleCommand("pause")}
            isLoading={loadingCmd === "pause"}
          >
            <Pause className="mr-2 h-4 w-4" /> Pause
          </Button>
          <Button
            variant="destructive"
            onClick={() => handleCommand("cancel")}
            isLoading={loadingCmd === "cancel"}
          >
            <Square className="mr-2 h-4 w-4" /> Cancel
          </Button>
        </>
      )}

      {isPaused && (
        <>
          <Button
            variant="primary"
            onClick={() => handleCommand("resume")}
            isLoading={loadingCmd === "resume"}
          >
            <Play className="mr-2 h-4 w-4" /> Resume
          </Button>
          <Button
            variant="destructive"
            onClick={() => handleCommand("cancel")}
            isLoading={loadingCmd === "cancel"}
          >
             <Square className="mr-2 h-4 w-4" /> Cancel
          </Button>
        </>
      )}

      {/* Always allow delete, even if running (it will cancel first) */}
      <Button
        variant="outline"
        className="text-red-600 hover:text-red-700 hover:bg-red-50"
        onClick={() => {
            if(confirm("Are you sure you want to delete this project?")) {
                handleCommand("delete");
            }
        }}
        isLoading={loadingCmd === "delete"}
      >
        <Trash2 className="mr-2 h-4 w-4" /> Delete Project
      </Button>
    </div>
  );
}
