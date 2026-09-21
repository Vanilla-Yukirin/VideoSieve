"use client";

import { Button } from "@/components/Button";
import { Dialog } from "@/components/Dialog";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      title={title}
      description={description}
      role="alertdialog"
      size="md"
      showCloseButton={false}
      busy={busy}
      onClose={onCancel}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button type="button" variant="destructive" onClick={onConfirm} isLoading={busy}>
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}
