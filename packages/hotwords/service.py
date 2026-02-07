"""Rule-based hotwords extraction from title/description/tags."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from infra import WorkspaceStore

from .models import HotwordItem, HotwordsDocument, HotwordsResult

_EN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+._-]{1,}")
_ZH_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

_EN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
}

_ZH_STOPWORDS = {
    "我们",
    "一个",
    "一些",
    "以及",
    "介绍",
    "内容",
    "视频",
    "课程",
    "基础",
    "本期",
}


def _lang_of(term: str) -> str:
    has_zh = any("\u4e00" <= ch <= "\u9fff" for ch in term)
    has_en = any(ch.isascii() and ch.isalpha() for ch in term)
    if has_zh and has_en:
        return "mixed"
    if has_zh:
        return "zh"
    if has_en:
        return "en"
    return "unknown"


def _extract_tokens(text: str) -> list[str]:
    if not text:
        return []
    tokens: list[str] = []
    tokens.extend(_EN_TOKEN_RE.findall(text))
    tokens.extend(_ZH_TOKEN_RE.findall(text))
    return tokens


def _normalize_token(token: str) -> str:
    return token.strip("-_.+ ")


def _is_valid_token(token: str) -> bool:
    if not token:
        return False
    lang = _lang_of(token)
    if lang == "zh":
        return len(token) >= 2 and token not in _ZH_STOPWORDS
    if lang == "en":
        if len(token) < 3 and not token.isupper():
            return False
        return token.lower() not in _EN_STOPWORDS
    if lang == "mixed":
        return len(token) >= 2
    return False


def _collect_scored_tokens(title: str, description: str, tags: list[str]) -> dict[str, int]:
    scores: dict[str, int] = {}

    def add_text(text: str, score: int) -> None:
        for raw in _extract_tokens(text):
            token = _normalize_token(raw)
            if not _is_valid_token(token):
                continue
            key = token.lower() if _lang_of(token) == "en" else token
            scores[key] = scores.get(key, 0) + score

    add_text(title, 5)
    add_text(description, 2)
    for tag in tags:
        add_text(tag, 4)
    return scores


def _to_items(scores: dict[str, int], max_terms: int) -> list[HotwordItem]:
    sorted_terms = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    items: list[HotwordItem] = []
    for term, score in sorted_terms[:max_terms]:
        weight = min(10, max(1, score))
        items.append(
            HotwordItem(
                text=term,
                lang=_lang_of(term),
                weight=weight,
                aliases=[],
            )
        )
    return items


def run_hotwords(
    workspace: WorkspaceStore,
    *,
    project_id: str,
    job_id: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    max_terms: int = 30,
) -> HotwordsResult:
    """Generate rule-based hotwords from title/description/tags and persist JSON."""

    if max_terms <= 0:
        raise ValueError("max_terms must be > 0")

    tag_values = tags or []
    workspace.ensure_project_layout(project_id)
    hotwords_path = workspace.hotwords_file(project_id)

    scores = _collect_scored_tokens(title=title, description=description, tags=tag_values)
    doc = HotwordsDocument(
        project_id=project_id,
        job_id=job_id,
        generated_at=datetime.now(UTC),
        items=_to_items(scores=scores, max_terms=max_terms),
    )

    hotwords_path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    return HotwordsResult(
        project_id=project_id,
        job_id=job_id,
        hotwords_path=str(hotwords_path),
        hotwords=doc,
    )


def run_hotwords_from_meta(
    workspace: WorkspaceStore,
    *,
    project_id: str,
    job_id: str,
    max_terms: int = 30,
) -> HotwordsResult:
    """Load title/description/tags from `meta/meta.json` and generate hotwords."""

    meta_path = workspace.meta_file(project_id)
    if not meta_path.exists():
        raise FileNotFoundError(f"meta file not found: {meta_path}")

    meta_payload = json.loads(meta_path.read_text(encoding="utf-8"))
    title = str(meta_payload.get("title") or "")
    description = str(meta_payload.get("description") or "")
    tags = [str(item) for item in meta_payload.get("tags", [])]
    return run_hotwords(
        workspace,
        project_id=project_id,
        job_id=job_id,
        title=title,
        description=description,
        tags=tags,
        max_terms=max_terms,
    )
