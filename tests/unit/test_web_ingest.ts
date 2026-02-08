import { CreateJobRequest, DualAssetIngestParams } from "../../apps/web/lib/api/types";
import {
  buildDualAssetPayload,
  isDuplicateConfig,
} from "../../apps/web/lib/ingest/helpers";

// ---- buildDualAssetPayload tests ----

describe("buildDualAssetPayload", () => {
  it("should build a valid dual-asset payload from user selections", () => {
    const result = buildDualAssetPayload(
      "https://bilibili.com/video/BV123",
      "30080", // analysis video
      "30280", // analysis audio
      "30120", // quality video
      "30290", // quality audio
    );

    expect(result).toBeDefined();
    expect(result!.source_url).toBe("https://bilibili.com/video/BV123");
    expect(result!.analysis_asset.video_format_id).toBe("30080");
    expect(result!.analysis_asset.audio_format_id).toBe("30280");
    expect(result!.quality_asset.video_format_id).toBe("30120");
    expect(result!.quality_asset.audio_format_id).toBe("30290");
  });

  it("should return undefined for empty URL", () => {
    expect(buildDualAssetPayload("", "30080", "30280", "30120", "30290")).toBeUndefined();
    expect(buildDualAssetPayload("   ", "30080", "30280", "30120", "30290")).toBeUndefined();
  });

  it("should allow empty format selections (omit keys)", () => {
    const result = buildDualAssetPayload(
      "https://youtube.com/watch?v=abc",
      "", // no analysis video
      "", // no analysis audio
      "", // no quality video
      "", // no quality audio
    );

    expect(result).toBeDefined();
    expect(result!.source_url).toBe("https://youtube.com/watch?v=abc");
    // AssetSelection objects exist but have no format_id keys
    expect(result!.analysis_asset.video_format_id).toBeUndefined();
    expect(result!.analysis_asset.audio_format_id).toBeUndefined();
    expect(result!.quality_asset.video_format_id).toBeUndefined();
    expect(result!.quality_asset.audio_format_id).toBeUndefined();
  });

  it("should trim whitespace from URL", () => {
    const result = buildDualAssetPayload(
      "  https://example.com/video  ",
      "100",
      "200",
      "100",
      "200",
    );
    expect(result!.source_url).toBe("https://example.com/video");
  });
});

// ---- isDuplicateConfig tests ----

describe("isDuplicateConfig", () => {
  it("should detect identical analysis and quality selections", () => {
    expect(isDuplicateConfig("30080", "30280", "30080", "30280")).toBe(true);
  });

  it("should detect both empty as duplicate", () => {
    expect(isDuplicateConfig("", "", "", "")).toBe(true);
  });

  it("should detect different video as non-duplicate", () => {
    expect(isDuplicateConfig("30080", "30280", "30120", "30280")).toBe(false);
  });

  it("should detect different audio as non-duplicate", () => {
    expect(isDuplicateConfig("30080", "30280", "30080", "30290")).toBe(false);
  });
});

// ---- CreateJobRequest contract tests ----

describe("CreateJobRequest contract (W08)", () => {
  it("should have summary_enabled at top level, not inside ingest", () => {
    const ingest: DualAssetIngestParams = {
      source_url: "https://bilibili.com/video/BV123",
      analysis_asset: { video_format_id: "30080", audio_format_id: "30280" },
      quality_asset: { video_format_id: "30120", audio_format_id: "30290" },
    };

    const request: CreateJobRequest = {
      project_id: "proj-001",
      summary_enabled: true,
      ingest,
    };

    expect(request.summary_enabled).toBe(true);
    expect(request.project_id).toBe("proj-001");
    expect(request.ingest?.source_url).toBe("https://bilibili.com/video/BV123");
    expect(request.ingest?.analysis_asset.video_format_id).toBe("30080");
    expect(request.ingest?.quality_asset.video_format_id).toBe("30120");

    // summary_enabled must NOT leak into ingest
    expect((request.ingest as Record<string, unknown>)["summary_enabled"]).toBeUndefined();
  });

  it("should allow omitting summary_enabled (defaults to undefined)", () => {
    const request: CreateJobRequest = {
      project_id: "proj-002",
      ingest: {
        source_url: "https://youtube.com/watch?v=abc",
        analysis_asset: {},
        quality_asset: {},
      },
    };

    expect(request.summary_enabled).toBeUndefined();
  });
});

// ---- Negative assertions: forbidden fields must not appear ----

describe("Payload negative assertions (forbidden fields)", () => {
  it("should NOT contain ytdlp_format in any part of the payload", () => {
    const payload = buildDualAssetPayload(
      "https://bilibili.com/video/BV123",
      "30080",
      "30280",
      "30120",
      "30290",
    );
    const serialized = JSON.stringify(payload);
    expect(serialized).not.toContain("ytdlp_format");
  });

  it("should NOT contain ytdlp_sort in any part of the payload", () => {
    const payload = buildDualAssetPayload(
      "https://bilibili.com/video/BV123",
      "30080",
      "30280",
      "30120",
      "30290",
    );
    const serialized = JSON.stringify(payload);
    expect(serialized).not.toContain("ytdlp_sort");
  });

  it("should NOT contain cookie_content in any part of the payload", () => {
    const payload = buildDualAssetPayload(
      "https://bilibili.com/video/BV123",
      "30080",
      "30280",
      "30120",
      "30290",
    );
    const serialized = JSON.stringify(payload);
    expect(serialized).not.toContain("cookie_content");
  });

  it("should NOT contain cookie_file_path in any part of the payload", () => {
    const payload = buildDualAssetPayload(
      "https://bilibili.com/video/BV123",
      "30080",
      "30280",
      "30120",
      "30290",
    );
    const serialized = JSON.stringify(payload);
    expect(serialized).not.toContain("cookie_file_path");
  });

  it("should NOT contain cookie_secret_ref in any part of the payload", () => {
    const payload = buildDualAssetPayload(
      "https://bilibili.com/video/BV123",
      "30080",
      "30280",
      "30120",
      "30290",
    );
    const serialized = JSON.stringify(payload);
    expect(serialized).not.toContain("cookie_secret_ref");
  });

  it("full CreateJobRequest should only contain allowed keys", () => {
    const request: CreateJobRequest = {
      project_id: "proj-001",
      summary_enabled: true,
      ingest: buildDualAssetPayload(
        "https://bilibili.com/video/BV123",
        "30080",
        "30280",
        "30120",
        "30290",
      ),
    };

    const serialized = JSON.stringify(request);
    // Must contain expected keys
    expect(serialized).toContain("project_id");
    expect(serialized).toContain("summary_enabled");
    expect(serialized).toContain("source_url");
    expect(serialized).toContain("analysis_asset");
    expect(serialized).toContain("quality_asset");
    expect(serialized).toContain("video_format_id");
    expect(serialized).toContain("audio_format_id");

    // Must NOT contain forbidden keys
    expect(serialized).not.toContain("ytdlp_format");
    expect(serialized).not.toContain("ytdlp_sort");
    expect(serialized).not.toContain("cookie_content");
    expect(serialized).not.toContain("cookie_file_path");
    expect(serialized).not.toContain("cookie_secret_ref");
  });
});
