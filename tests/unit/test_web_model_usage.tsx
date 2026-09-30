/** @jest-environment jsdom */
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ModelUsagePanel } from "../../apps/web/components/ModelUsagePanel";

jest.mock("@/lib/i18n/I18nProvider", () => ({ useI18n: () => ({ t: (key: string) => key }) }));

it("distinguishes reported zero, unknown and partial usage without summing reasoning again", () => {
  render(<ModelUsagePanel usage={{ calls: 2, failed_calls: 1, elapsed_ms: 1234, stages: {
    deliverables: { calls: 2, failed_calls: 1, elapsed_ms: 1234, input_tokens: 123,
      output_tokens: 80, total_tokens: null, cached_tokens: 0, reasoning_tokens: null,
      usage_missing_calls: 1, missing_fields: { input_tokens: 1, output_tokens: 1 } },
  } }} />);
  expect(screen.getByText("123 *")).toBeInTheDocument();
  expect(screen.getByText("80 *")).toBeInTheDocument();
  expect(screen.getByText("0")).toBeInTheDocument();
  expect(screen.getByText("usage.unknown")).toBeInTheDocument();
  expect(screen.getByText("1.23 s")).toBeInTheDocument();
});
