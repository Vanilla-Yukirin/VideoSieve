export interface JsonlCursor {
  byteOffset: number;
  remainder: string;
}

export interface JsonlParseResult<T> {
  records: T[];
  remainder: string;
  malformedLines: number;
}

export interface JsonlDelta<T> extends JsonlParseResult<T> {
  cursor: JsonlCursor;
  reset: boolean;
}

export const EMPTY_JSONL_CURSOR: JsonlCursor = { byteOffset: 0, remainder: "" };

export function parseJsonlText<T>(text: string, includeTrailingLine = true): JsonlParseResult<T> {
  const lines = text.split("\n");
  let remainder = "";
  if (!includeTrailingLine && !text.endsWith("\n")) {
    remainder = lines.pop() ?? "";
  }

  const records: T[] = [];
  let malformedLines = 0;
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      records.push(JSON.parse(trimmed) as T);
    } catch {
      malformedLines += 1;
    }
  }
  return { records, remainder, malformedLines };
}

export async function fetchJsonl<T>(url: string): Promise<T[] | null> {
  const response = await fetch(url);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const parsed = parseJsonlText<T>(await response.text());
  return parsed.records;
}

function contentRangeSize(response: Response): number | null {
  const raw = response.headers.get("content-range");
  const match = raw?.match(/^bytes \*\/(\d+)$/i);
  if (!match) return null;
  const size = Number(match[1]);
  return Number.isFinite(size) ? size : null;
}

export async function fetchJsonlDelta<T>(
  url: string,
  cursor: JsonlCursor,
  options: { complete?: boolean } = {},
): Promise<JsonlDelta<T> | null> {
  const headers = cursor.byteOffset > 0 ? { Range: `bytes=${cursor.byteOffset}-` } : undefined;
  const response = await fetch(url, { headers });
  if (response.status === 404) return null;

  if (response.status === 416 && cursor.byteOffset > 0) {
    const size = contentRangeSize(response);
    if (size === cursor.byteOffset) {
      return {
        records: [],
        remainder: cursor.remainder,
        malformedLines: 0,
        cursor,
        reset: false,
      };
    }
    return fetchJsonlDelta<T>(url, EMPTY_JSONL_CURSOR, options);
  }

  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  const bytes = await response.arrayBuffer();
  const reset = response.status !== 206 || cursor.byteOffset === 0;
  const prefix = reset ? "" : cursor.remainder;
  const text = prefix + new TextDecoder().decode(bytes);
  const parsed = parseJsonlText<T>(text, options.complete ?? false);
  const byteOffset = (reset ? 0 : cursor.byteOffset) + bytes.byteLength;

  return {
    ...parsed,
    cursor: { byteOffset, remainder: parsed.remainder },
    reset,
  };
}
