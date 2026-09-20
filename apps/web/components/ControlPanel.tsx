import React, { useState } from "react";
import { ControlAck, ControlCommandType } from "@/lib/api/types";
import { Button } from "./Button";
import { Pause, Play, Square, Trash2 } from "lucide-react";
import { useI18n } from "@/lib/i18n/I18nProvider";
import { useToast } from "@/lib/toast/ToastProvider";
import { ConfirmDialog } from "./ConfirmDialog";

interface ControlPanelProps {
  status: string;
  sendCommand: (command: ControlCommandType) => Promise<ControlAck>;
  onDeleted?: () => void;
  onDeletePending?: () => void;
}

export function ControlPanel({ status, sendCommand, onDeleted, onDeletePending }: ControlPanelProps) {
  const { t } = useI18n();
  const { pushToast } = useToast();
  const [loadingCmd, setLoadingCmd] = useState<ControlCommandType | null>(null);
  const [inlineFeedback, setInlineFeedback] = useState<string | null>(null);
  const [showDeleteConfirmation, setShowDeleteConfirmation] = useState(false);

  const showInlineFeedback = (message: string) => {
    setInlineFeedback(message);
    window.setTimeout(() => {
      setInlineFeedback((current) => (current === message ? null : current));
    }, 4200);
  };

  const handleCommand = async (cmd: ControlCommandType) => {
    if (cmd === "cancel") {
      const message = t("control.cancelAccepted");
      pushToast({ level: "info", message });
      showInlineFeedback(message);
    }
    if (cmd === "delete") {
      const message = t("control.deleteRequested");
      pushToast({ level: "info", message });
      showInlineFeedback(message);
    }
    setLoadingCmd(cmd);
    try {
      const ack = await sendCommand(cmd);
      if (!ack.accepted) {
        const message = t("control.reject", { reason: ack.reason ?? "-" });
        pushToast({ level: "error", message });
        showInlineFeedback(message);
        return;
      }
      if (ack.code === "DELETE_PENDING_CLEANUP") {
        const message = t("control.deletePendingCleanup");
        pushToast({ level: "warning", message });
        showInlineFeedback(message);
        onDeletePending?.();
        return;
      }
      if (cmd === "delete" && ack.reason === "job deleted") {
        onDeleted?.();
        return;
      }
      if (ack.code && ack.reason) {
        const message = t("control.acceptedInfo", { reason: ack.reason });
        pushToast({ level: "info", message });
        showInlineFeedback(message);
        return;
      }
      if (ack.reason) {
        const message = t("control.acceptedInfo", { reason: ack.reason });
        pushToast({ level: "info", message });
        showInlineFeedback(message);
      }
    } catch (e) {
      console.error(e);
      const message = t("control.fail");
      pushToast({ level: "error", message });
      showInlineFeedback(message);
    } finally {
      setLoadingCmd(null);
    }
  };

  const isTerminal = ["succeeded", "failed", "cancelled"].includes(status);
  const canPause = status === "running";
  const canResume = status === "paused" || status === "interrupted";
  const canInterrupt = !isTerminal;
  const canDelete = true;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          onClick={() => handleCommand("pause")}
          isLoading={loadingCmd === "pause"}
          disabled={!canPause}
        >
          <Pause className="mr-2 h-4 w-4" /> {t("control.pause")}
        </Button>

        <Button
          variant="outline"
          onClick={() => handleCommand("resume")}
          isLoading={loadingCmd === "resume"}
          disabled={!canResume}
        >
          <Play className="mr-2 h-4 w-4" /> {t("control.resume")}
        </Button>

        <Button
          variant="destructive"
          onClick={() => handleCommand("cancel")}
          isLoading={loadingCmd === "cancel"}
          disabled={!canInterrupt}
        >
          <Square className="mr-2 h-4 w-4" /> {t("control.cancel")}
        </Button>

        {/* Always allow delete, even if running (it will cancel first) */}
        <Button
          variant="outline"
          className="border-destructive/50 text-red-300 hover:bg-destructive/20 hover:text-red-100"
          disabled={!canDelete}
          onClick={() => setShowDeleteConfirmation(true)}
          isLoading={loadingCmd === "delete"}
        >
          <Trash2 className="mr-2 h-4 w-4" /> {t("control.delete")}
        </Button>
      </div>
      {inlineFeedback ? <p className="text-xs text-muted-foreground">{inlineFeedback}</p> : null}
      <ConfirmDialog
        open={showDeleteConfirmation}
        title={t("control.delete")}
        description={t("control.confirmDelete")}
        confirmLabel={t("control.delete")}
        cancelLabel={t("common.cancel")}
        busy={loadingCmd === "delete"}
        onCancel={() => setShowDeleteConfirmation(false)}
        onConfirm={() => {
          setShowDeleteConfirmation(false);
          void handleCommand("delete");
        }}
      />
    </div>
  );
}
