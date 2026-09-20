import {
  EMPTY_JSONL_CURSOR,
  fetchJsonlDelta,
  parseJsonlText,
} from "../../apps/web/lib/artifacts/jsonl";
import {
  frameNameToArtifactPath,
  parseIllustratedNotes,
} from "../../apps/web/lib/artifacts/illustratedNotes";

function mockResponse(
  body: string,
  status: number,
  headers: Record<string, string> = {},
): Response {
  const bytes = new TextEncoder().encode(body);
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: {
      get: (name: string) => headers[name.toLowerCase()] ?? null,
    },
    text: async () => body,
    arrayBuffer: async () => bytes.buffer,
  } as unknown as Response;
}

function mockByteResponse(
  bytes: Uint8Array,
  status: number,
  headers: Record<string, string> = {},
): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: {
      get: (name: string) => headers[name.toLowerCase()] ?? null,
    },
    arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  } as unknown as Response;
}

describe("JSONL artifact loading", () => {
  it("keeps valid rows when a neighboring line is malformed", () => {
    const result = parseJsonlText<{ id: number }>(
      '{"id":1}\nthis is incomplete\n{"id":2}\n',
    );

    expect(result.records).toEqual([{ id: 1 }, { id: 2 }]);
    expect(result.malformedLines).toBe(1);
    expect(result.remainder).toBe("");
  });

  it("retains an incomplete trailing line until the next byte-range response", async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce(mockResponse('{"id":1}\n{"id":', 200))
      .mockResolvedValueOnce(mockResponse('2}\n', 206));
    (global as unknown as { fetch: jest.Mock }).fetch = fetchMock;

    const first = await fetchJsonlDelta<{ id: number }>("/artifact", EMPTY_JSONL_CURSOR);
    expect(first?.records).toEqual([{ id: 1 }]);
    expect(first?.remainder).toBe('{"id":');

    const second = await fetchJsonlDelta<{ id: number }>("/artifact", first!.cursor);
    expect(second?.records).toEqual([{ id: 2 }]);
    expect(second?.reset).toBe(false);
    expect(fetchMock).toHaveBeenLastCalledWith("/artifact", {
      headers: { Range: `bytes=${first!.cursor.byteOffset}-` },
    });
  });

  it("treats a range request at end-of-file as no new records", async () => {
    const cursor = { byteOffset: 24, remainder: "" };
    (global as unknown as { fetch: jest.Mock }).fetch = jest
      .fn()
      .mockResolvedValue(mockResponse("", 416, { "content-range": "bytes */24" }));

    const result = await fetchJsonlDelta<{ id: number }>("/artifact", cursor);

    expect(result?.records).toEqual([]);
    expect(result?.cursor).toBe(cursor);
  });

  it("preserves a UTF-8 character split across byte-range responses", async () => {
    const bytes = new TextEncoder().encode('{"text":"中文"}\n');
    const firstChineseByte = bytes.findIndex((value) => value >= 0x80);
    const split = firstChineseByte + 1;
    (global as unknown as { fetch: jest.Mock }).fetch = jest
      .fn()
      .mockResolvedValueOnce(mockByteResponse(bytes.slice(0, split), 200))
      .mockResolvedValueOnce(mockByteResponse(bytes.slice(split), 206));

    const first = await fetchJsonlDelta<{ text: string }>("/artifact", EMPTY_JSONL_CURSOR);
    const second = await fetchJsonlDelta<{ text: string }>("/artifact", first!.cursor);

    expect(first?.records).toEqual([]);
    expect(second?.records).toEqual([{ text: "中文" }]);
    expect(second?.malformedLines).toBe(0);
  });

  it("flushes a final JSON line when EOF returns 416 after completion", async () => {
    (global as unknown as { fetch: jest.Mock }).fetch = jest
      .fn()
      .mockResolvedValueOnce(mockResponse('{"id":1}', 200))
      .mockResolvedValueOnce(mockResponse("", 416, { "content-range": "bytes */8" }));

    const first = await fetchJsonlDelta<{ id: number }>("/artifact", EMPTY_JSONL_CURSOR);
    const completed = await fetchJsonlDelta<{ id: number }>("/artifact", first!.cursor, {
      complete: true,
    });

    expect(first?.records).toEqual([]);
    expect(completed?.records).toEqual([{ id: 1 }]);
    expect(completed?.cursor.remainder).toBe("");
  });
});

describe("illustrated notes", () => {
  it("parses published headings, frame references, and paragraphs", () => {
    expect(
      parseIllustratedNotes(
        "# Illustrated Notes\n\n[[frame:slide_000001]]\nFirst paragraph.\n\nSecond paragraph.",
      ),
    ).toEqual([
      { kind: "heading", level: 1, text: "Illustrated Notes" },
      { kind: "frame", name: "slide_000001" },
      { kind: "paragraph", text: "First paragraph." },
      { kind: "paragraph", text: "Second paragraph." },
    ]);
  });

  it("maps safe frame placeholders to workspace image paths", () => {
    expect(frameNameToArtifactPath("slide_000001")).toBe("frames/images/slide_000001.jpg");
    expect(frameNameToArtifactPath("slide_000002.png")).toBe("frames/images/slide_000002.png");
  });
});
