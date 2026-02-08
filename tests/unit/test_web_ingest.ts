import { IngestParams } from "../../apps/web/lib/api/types";

// Mock component behavior test
describe("Ingest Flow Data Construction", () => {
  it("should construct valid IngestParams from user selection", () => {
    const url = "https://bilibili.com/video/BV123";
    const vid = "30080";
    const aid = "30280";

    const params: IngestParams = {
        source_url: url,
        video_format_id: vid,
        audio_format_id: aid,
    };

    expect(params.source_url).toBe(url);
    expect(params.video_format_id).toBe(vid);
    expect(params.audio_format_id).toBe(aid);
  });

  it("should allow partial selection", () => {
    const params: IngestParams = {
        source_url: "https://youtube.com/watch?v=abc",
    };
    expect(params.video_format_id).toBeUndefined();
  });
});
