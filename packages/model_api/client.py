"""Small HTTP client for the model protocols exposed in the settings UI."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

MODEL_PROTOCOLS = frozenset(
    {"openai_chat_completions", "openai_responses", "anthropic_messages"}
)
_PROTOCOL_PATHS = {
    "openai_chat_completions": "chat/completions",
    "openai_responses": "responses",
    "anthropic_messages": "messages",
}


class ModelApiError(RuntimeError):
    """One normalized model API failure without leaking response bodies or secrets."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def resolve_model_endpoint(api_root: str, protocol: str) -> str:
    """Append the protocol route to a stored API root.

    Legacy snapshots may already contain a full request URL. They remain valid so
    jobs queued before the profile migration can still run.
    """

    normalized_protocol = protocol.strip().lower()
    if normalized_protocol not in MODEL_PROTOCOLS:
        raise ValueError(f"unsupported model protocol: {protocol}")
    root = api_root.strip().rstrip("/")
    if not root:
        return ""
    route = _PROTOCOL_PATHS[normalized_protocol]
    if root.endswith(f"/{route}"):
        return root
    return f"{root}/{route}"


def request_model_text(
    *,
    protocol: str,
    api_root: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_text: str,
    image_data_url: str | None = None,
    timeout_seconds: float = 120.0,
    auth_mode: str | None = None,
) -> str:
    """Send one request and return its first text result."""

    normalized_protocol = protocol.strip().lower()
    endpoint = resolve_model_endpoint(api_root, normalized_protocol)
    if not endpoint or not model.strip() or not api_key.strip():
        raise ModelApiError(
            "MODEL_CONFIG_MISSING",
            "API root, model, and API key are required",
        )

    body, headers = _build_request(
        protocol=normalized_protocol,
        model=model.strip(),
        api_key=api_key.strip(),
        system_prompt=system_prompt,
        user_text=user_text,
        image_data_url=image_data_url,
        auth_mode=auth_mode,
    )
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ModelApiError(
            "MODEL_PROVIDER_HTTP_ERROR",
            f"model provider returned HTTP {exc.code}",
            retryable=exc.code == 429 or exc.code >= 500,
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        raise ModelApiError(
            "MODEL_PROVIDER_UNAVAILABLE",
            "model provider request failed",
            retryable=True,
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelApiError(
            "MODEL_INVALID_RESPONSE",
            "model provider returned invalid JSON",
        ) from exc

    text = _extract_text(payload, normalized_protocol)
    if not text:
        raise ModelApiError(
            "MODEL_EMPTY_RESPONSE",
            "model provider returned no text",
        )
    return text


def _build_request(
    *,
    protocol: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_text: str,
    image_data_url: str | None,
    auth_mode: str | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    if protocol == "openai_chat_completions":
        user_content: str | list[dict[str, Any]] = user_text
        if image_data_url:
            user_content = [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ]
        return (
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.2,
            },
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    if protocol == "openai_responses":
        content: list[dict[str, str]] = [{"type": "input_text", "text": user_text}]
        if image_data_url:
            content.append({"type": "input_image", "image_url": image_data_url})
        return (
            {
                "model": model,
                "instructions": system_prompt,
                "input": [{"role": "user", "content": content}],
            },
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    media_type, image_data = _split_image_data_url(image_data_url)
    anthropic_content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    if image_data is not None:
        anthropic_content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data,
                },
            }
        )
    anthropic_headers = {
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    if auth_mode == "bearer":
        anthropic_headers["Authorization"] = f"Bearer {api_key}"
    else:
        anthropic_headers["x-api-key"] = api_key
    return (
        {
            "model": model,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": [{"role": "user", "content": anthropic_content}],
        },
        anthropic_headers,
    )


def _split_image_data_url(value: str | None) -> tuple[str, str | None]:
    if not value:
        return "image/jpeg", None
    prefix, separator, encoded = value.partition(",")
    if not separator or not prefix.startswith("data:image/") or ";base64" not in prefix:
        raise ValueError("image_data_url must contain a base64 image data URL")
    return prefix.removeprefix("data:").split(";", 1)[0], encoded


def _extract_text(payload: Any, protocol: str) -> str:
    if not isinstance(payload, dict):
        return ""
    if protocol == "openai_chat_completions":
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return ""
        message = choices[0].get("message")
        return _content_text(message.get("content")) if isinstance(message, dict) else ""
    if protocol == "openai_responses":
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        output = payload.get("output")
        if not isinstance(output, list):
            return ""
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                    text = part.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
        return "\n".join(chunks).strip()
    return _content_text(payload.get("content"))


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") in {None, "text"}:
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks).strip()
