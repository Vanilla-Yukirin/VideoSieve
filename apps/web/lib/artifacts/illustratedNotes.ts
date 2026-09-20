export type IllustratedNoteBlock =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "frame"; name: string };

const FRAME_PATTERN = /^\[\[frame:([A-Za-z0-9._-]+)\]\]$/;
const HEADING_PATTERN = /^(#{1,3})\s+(.+)$/;

export function parseIllustratedNotes(markdown: string): IllustratedNoteBlock[] {
  const blocks: IllustratedNoteBlock[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length === 0) return;
    blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
    paragraph = [];
  };

  for (const rawLine of markdown.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      continue;
    }

    const frameMatch = line.match(FRAME_PATTERN);
    if (frameMatch) {
      flushParagraph();
      blocks.push({ kind: "frame", name: frameMatch[1] });
      continue;
    }

    const headingMatch = line.match(HEADING_PATTERN);
    if (headingMatch) {
      flushParagraph();
      blocks.push({
        kind: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2],
      });
      continue;
    }

    paragraph.push(rawLine.trimEnd());
  }

  flushParagraph();
  return blocks;
}

export function frameNameToArtifactPath(name: string): string {
  const extension = /\.(?:jpe?g|png|webp)$/i.test(name) ? "" : ".jpg";
  return `frames/images/${name}${extension}`;
}
