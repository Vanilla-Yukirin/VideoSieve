import React, { useState } from "react";
import { ControlCommandType } from "@/lib/api/types";
import { api } from "@/lib/api/client";
import { Button } from "./Button";
import { Square, Trash2 } from "lucide-react";
import { useI18n } from "@/lib/i18n/I18nProvider";

interface ControlPanelProps {
  jobId: string;
  status: string;
}

export function ControlPanel({ jobId, status }: ControlPanelProps) {
  const { t } = useI18n();
  const [loadingCmd, setLoadingCmd] = useState<ControlCommandType | null>(null);

  const handleCommand = async (cmd: ControlCommandType) => {
    setLoadingCmd(cmd);
    try {
      const ack = await api.controlJob(jobId, cmd);
      if (!ack.accepted) {
        alert(t("control.reject", { reason: ack.reason ?? "-" }));
      }
    } catch (e) {
      console.error(e);
      alert(t("control.fail"));
    } finally {
      setLoadingCmd(null);
    }
  };

  const isTerminal = ["succeeded", "failed", "cancelled"].includes(status);
  const isInterrupting = status === "cancel_requested";
  const canInterrupt = !isTerminal && !isInterrupting;
  const canDelete = true;

  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant="destructive"
        onClick={() => handleCommand("cancel")}
        isLoading={loadingCmd === "cancel"}
        disabled={!canInterrupt}
      >
        <Square className="mr-2 h-4 w-4" /> {isInterrupting ? t("control.cancelling") : t("control.cancel")}
      </Button>

      {/* Always allow delete, even if running (it will cancel first) */}
      <Button
        variant="outline"
        className="text-red-600 hover:text-red-700 hover:bg-red-50"
        disabled={!canDelete}
        onClick={() => {
            if(confirm(t("control.confirmDelete"))) {
                handleCommand("delete");
            }
        }}
        isLoading={loadingCmd === "delete"}
      >
        <Trash2 className="mr-2 h-4 w-4" /> {t("control.delete")}
      </Button>
    </div>
  );
}
