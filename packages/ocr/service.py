"""Baseline OCR service that reads keyframes and writes ocr.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from infra.interfaces import WorkspaceStore

from .providers import OCRBlock, OCRFrameResult, OCRProvider


class MockOCRProvider:
    """Deterministic mock OCR provider for baseline integration."""

    def recognize(
        self,
        frame_id: str,
        image_path: Path,
        *,
        language_hint: str | None = None,
    ) -> OCRFrameResult:
        lang = language_hint or "zh"
        label = image_path.stem or frame_id
        block = OCRBlock(
            text=f"mock text for {label}",
            bbox=(10, 10, 320, 72),
            conf=0.95,
        )
        return OCRFrameResult(frame_id=frame_id, lang=lang, conf=0.95, blocks=(block,))


class OCRBaselineService:
    """Read ``frames/keyframes.jsonl`` and output ``ocr/ocr.jsonl``."""

    def __init__(self, workspace_store: WorkspaceStore, provider: OCRProvider) -> None:
        self._workspace_store = workspace_store
        self._provider = provider

    def run(self, project_id: str, *, language_hint: str | None = None) -> list[OCRFrameResult]:
        self._workspace_store.ensure_project_layout(project_id)

        keyframes_file = self._workspace_store.keyframes_file(project_id)
        if not keyframes_file.exists():
            self._write_jsonl(self._workspace_store.ocr_file(project_id), [])
            return []

        results: list[OCRFrameResult] = []
        with keyframes_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                payload = json.loads(line)
                frame_id = payload["frame_id"]
                image_path = Path(payload["path"])
                results.append(
                    self._provider.recognize(
                        frame_id,
                        image_path,
                        language_hint=language_hint,
                    )
                )

        self._write_jsonl(self._workspace_store.ocr_file(project_id), results)
        return results

    @staticmethod
    def _write_jsonl(path: Path, rows: list[OCRFrameResult]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row.to_json(), ensure_ascii=False) + "\n")
