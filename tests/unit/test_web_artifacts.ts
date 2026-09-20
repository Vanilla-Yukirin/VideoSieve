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
