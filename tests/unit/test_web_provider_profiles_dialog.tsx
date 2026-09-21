/** @jest-environment jsdom */

import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { ProviderProfilesManager } from "../../apps/web/components/ProviderProfilesManager";

jest.mock("@/lib/i18n/I18nProvider", () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}));

describe("ProviderProfilesManager dialog", () => {
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
});
