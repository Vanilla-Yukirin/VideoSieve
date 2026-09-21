import { clearLegacyAuthStorage, LEGACY_AUTH_STORAGE_KEYS } from "./legacyAuth";

describe("legacy authentication storage cleanup", () => {
  it("removes every retired browser key", () => {
    const removeItem = jest.fn();

    clearLegacyAuthStorage({ removeItem });

    expect(removeItem.mock.calls.map(([key]) => key)).toEqual(LEGACY_AUTH_STORAGE_KEYS);
  });
});
