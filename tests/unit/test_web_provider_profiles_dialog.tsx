/** @jest-environment jsdom */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { ProviderProfilesManager } from "../../apps/web/components/ProviderProfilesManager";

const mockTestProviderProfileDraft = jest.fn();

jest.mock("@/lib/api/client", () => ({
  api: {
    testProviderProfileDraft: (...args: unknown[]) => mockTestProviderProfileDraft(...args),
  },
}));

jest.mock("@/lib/i18n/I18nProvider", () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}));

describe("ProviderProfilesManager dialog", () => {
  beforeEach(() => {
    mockTestProviderProfileDraft.mockReset();
  });

  it("opens the selected capability editor as a modal and restores trigger focus", () => {
    render(<ProviderProfilesManager profiles={[]} onProfilesChange={jest.fn()} />);

    const asrAddButton = screen.getAllByRole("button", { name: /providers.add/ })[0];
    asrAddButton.focus();
    fireEvent.click(asrAddButton);

    const dialog = screen.getByRole("dialog", { name: "providers.addTitle" });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByLabelText("providers.displayName")).toHaveFocus();
    expect(screen.getByDisplayValue("CapsWriter")).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(asrAddButton).toHaveFocus();
  });

  it("tests current editor values without saving the profile", async () => {
    mockTestProviderProfileDraft.mockResolvedValue({
      status: "succeeded",
      capability: "asr",
      protocol: "capswriter_ws",
      model: "",
      latency_ms: 12,
      message: "ok",
    });
    const onProfilesChange = jest.fn();
    render(<ProviderProfilesManager profiles={[]} onProfilesChange={onProfilesChange} />);

    fireEvent.click(screen.getAllByRole("button", { name: /providers.add/ })[0]);
    fireEvent.change(screen.getByLabelText("providers.serviceUrl"), {
      target: { value: "ws://draft.example:6016" },
    });
    fireEvent.change(screen.getByLabelText("providers.credential"), {
      target: { value: "draft-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "providers.test" }));

    await waitFor(() => expect(mockTestProviderProfileDraft).toHaveBeenCalledTimes(1));
    expect(mockTestProviderProfileDraft).toHaveBeenCalledWith(expect.objectContaining({
      api_root: "ws://draft.example:6016",
      credential: "draft-token",
      capability: "asr",
      protocol: "capswriter_ws",
    }));
    expect(onProfilesChange).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "providers.addTitle" })).toBeInTheDocument();
    expect(await screen.findByText("providers.testSucceeded")).toBeInTheDocument();
  });
});
