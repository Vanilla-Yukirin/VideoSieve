/** @jest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { ConfirmDialog } from "../../apps/web/components/ConfirmDialog";

describe("ConfirmDialog focus management", () => {
  it("traps focus, handles Escape, and restores focus after closing", () => {
    const onCancel = jest.fn();
    const onConfirm = jest.fn();
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();

    const { rerender } = render(
      <ConfirmDialog
        open
        title="Delete job"
        description="This cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    );

    const cancel = screen.getByRole("button", { name: "Cancel" });
    const confirm = screen.getByRole("button", { name: "Delete" });
    expect(cancel).toHaveFocus();

    confirm.focus();
    fireEvent.keyDown(window, { key: "Tab" });
    expect(cancel).toHaveFocus();

    fireEvent.keyDown(window, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(1);

    rerender(
      <ConfirmDialog
        open={false}
        title="Delete job"
        description="This cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    );
    expect(trigger).toHaveFocus();
    trigger.remove();
  });
});
