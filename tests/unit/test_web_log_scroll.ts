import { isNearScrollBottom } from "../../apps/web/lib/logs/scroll";

describe("log tail following", () => {
  it("follows when the reader is already at the bottom", () => {
    expect(
      isNearScrollBottom({ scrollTop: 700, clientHeight: 300, scrollHeight: 1000 }),
    ).toBe(true);
  });

  it("keeps the reader's position when they scroll into history", () => {
    expect(
      isNearScrollBottom({ scrollTop: 400, clientHeight: 300, scrollHeight: 1000 }),
    ).toBe(false);
  });

  it("allows a small bottom tolerance for fractional layout and wheel movement", () => {
    expect(
      isNearScrollBottom({ scrollTop: 675, clientHeight: 300, scrollHeight: 1000 }),
    ).toBe(true);
  });
});
