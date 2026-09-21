/** @jest-environment jsdom */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import Home from "../../apps/web/app/page";

const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockAddProject = jest.fn();
const mockCreateProject = jest.fn();
const mockListProviderProfiles = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));

jest.mock("@/lib/api/client", () => ({
  api: {
    createProject: (...args: unknown[]) => mockCreateProject(...args),
    listProviderProfiles: (...args: unknown[]) => mockListProviderProfiles(...args),
  },
}));

jest.mock("@/lib/hooks/useProjectIndex", () => ({
  useProjectIndex: () => ({
    projectIds: [],
    addProject: mockAddProject,
    removeProject: jest.fn(),
    isLoaded: true,
    loadError: null,
  }),
}));

jest.mock("@/lib/settings/providerSetup", () => ({
  isProviderSetupComplete: () => true,
}));

jest.mock("@/lib/i18n/I18nProvider", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

jest.mock("@/lib/toast/ToastProvider", () => ({
  useToast: () => ({ pushToast: jest.fn() }),
}));

jest.mock("@/components/ProjectCard", () => ({ ProjectCard: () => null }));

describe("Home project creation", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockListProviderProfiles.mockResolvedValue([]);
    mockCreateProject.mockResolvedValue({ project_id: "p-created" });
  });

  it("opens the new project immediately after it is persisted", async () => {
    render(<Home />);

    const createButton = await screen.findByRole("button", { name: "home.newProject" });
    fireEvent.click(createButton);

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/projects/p-created"));
    expect(mockAddProject).toHaveBeenCalledWith("p-created");
  });
});
