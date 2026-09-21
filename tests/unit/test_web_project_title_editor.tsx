/** @jest-environment jsdom */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { ProjectTitleEditor } from "../../apps/web/components/ProjectTitleEditor";

jest.mock("@/lib/i18n/I18nProvider", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

describe("ProjectTitleEditor", () => {
  it("opens from the pencil action and persists a trimmed title", async () => {
    const onSave = jest.fn().mockResolvedValue(undefined);
    render(<ProjectTitleEditor title="Before" onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: "project.rename" }));
    const input = screen.getByRole("textbox", { name: "project.rename" });
    fireEvent.change(input, { target: { value: "  After  " } });
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith("After"));
    await waitFor(() => expect(screen.queryByRole("textbox")).not.toBeInTheDocument());
  });

  it("keeps the editor open for a blank title", async () => {
    const onSave = jest.fn().mockResolvedValue(undefined);
    render(<ProjectTitleEditor title="Before" onSave={onSave} />);

    fireEvent.click(screen.getByRole("button", { name: "project.rename" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "common.save" }));

    expect(await screen.findByText("project.renameRequired")).toBeInTheDocument();
    expect(onSave).not.toHaveBeenCalled();
  });
});
