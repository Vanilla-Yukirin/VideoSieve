"""Small HTTP client for the model protocols exposed in the settings UI."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import anthropic
import httpx2
import openai

from .options import ModelRequestOptions
from .telemetry import ModelCallAttempt

MODEL_PROTOCOLS = frozenset({"openai_chat_completions", "openai_responses", "anthropic_messages"})
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
        self.attempts: tuple[ModelCallAttempt, ...] = ()


@dataclass(frozen=True)
class ModelResponse:
    text: str
    attempts: tuple[ModelCallAttempt, ...]


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
    timeout_seconds: float | None = None,
    auth_mode: str | None = None,
    options: Mapping[str, object] | None = None,
) -> str:
    """Compatibility entrypoint; completion validation is never bypassed."""
    return request_model(
        protocol=protocol,
        api_root=api_root,
        model=model,
        api_key=api_key,
        system_prompt=system_prompt,
        user_text=user_text,
        image_data_url=image_data_url,
        timeout_seconds=timeout_seconds,
        auth_mode=auth_mode,
        options=options,
    ).text


def request_model(
    *,
    protocol: str,
    api_root: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_text: str,
    image_data_url: str | None = None,
    timeout_seconds: float | None = None,
    auth_mode: str | None = None,
    options: Mapping[str, object] | None = None,
    on_attempt: Callable[[ModelCallAttempt], None] | None = None,
    check_control: Callable[[], None] | None = None,
) -> ModelResponse:
    """Retry bounded transient/incomplete responses; never publish a partial answer."""

    normalized_protocol = protocol.strip().lower()
    endpoint = resolve_model_endpoint(api_root, normalized_protocol)
    if not endpoint or not model.strip() or not api_key.strip():
        raise ModelApiError(
            "MODEL_CONFIG_MISSING",
            "API root, model, and API key are required",
        )

    settings = ModelRequestOptions.model_validate(dict(options or {}))
    # A conservative UTF-8 byte guard, not a tokenizer or a usage measurement.
    if len((system_prompt + user_text).encode("utf-8")) > (
        settings.context_window_tokens - settings.max_output_tokens - 2048
    ):
        raise ModelApiError("MODEL_INPUT_BUDGET_EXCEEDED", "input exceeds the local context budget")
    body, _ = _build_request(
        protocol=normalized_protocol,
        model=model.strip(),
        api_key=api_key.strip(),
        system_prompt=system_prompt,
        user_text=user_text,
        image_data_url=image_data_url,
        auth_mode=auth_mode,
        settings=settings,
        api_root=api_root,
    )
    attempts: list[ModelCallAttempt] = []
    call_id = uuid.uuid4().hex
    for index in range(settings.max_retries + 1):
        if check_control:
            check_control()
        started = time.monotonic()
        payload: dict[str, Any] = {}
        request_id = None
        failure: ModelApiError | None = None
        try:
            payload, request_id = _send_request(
                normalized_protocol,
                endpoint,
                api_key,
                auth_mode,
                body,
                timeout_seconds or settings.timeout_seconds,
            )
            # Inspect reported stop/refusal metadata even when no text survived.
            if _finish_reason(payload, normalized_protocol) is not None:
                _validate_completion(payload, normalized_protocol)
            text = _extract_text(payload, normalized_protocol)
            if not text:
                raise ModelApiError(
                    "MODEL_EMPTY_RESPONSE", "model provider returned no text", retryable=True
                )
            _validate_completion(payload, normalized_protocol)
        except ModelApiError as exc:
            failure = exc
        elapsed_ms = max(0, round((time.monotonic() - started) * 1000))
        attempt = ModelCallAttempt(
            call_id=call_id,
            attempt=index + 1,
            protocol=normalized_protocol,
            model=model,
            elapsed_ms=elapsed_ms,
            finish_reason=_finish_reason(payload, normalized_protocol),
            usage=_reported_usage(payload.get("usage")),
            request_id=request_id,
            error_code=failure.code if failure else None,
        )
        attempts.append(attempt)
        if on_attempt:
            on_attempt(attempt)
        if check_control:
            check_control()
        if failure is None:
            return ModelResponse(text=text, attempts=tuple(attempts))
        if not failure.retryable or index == settings.max_retries:
            failure.attempts = tuple(attempts)
            raise failure
        # Retry with the same evidence and configured cap. No blind concatenation
        # or silent budget increase; shortening is requested only after truncation.
        if failure.code == "MODEL_OUTPUT_TRUNCATED":
            body, _ = _build_request(
                protocol=normalized_protocol,
                model=model,
                api_key=api_key,
                system_prompt=system_prompt
                + (
                    "\nA previous attempt reached its output limit. Return a complete, concise "
                    "answer within the output budget, preserving all key evidence."
                ),
                user_text=user_text,
                image_data_url=image_data_url,
                auth_mode=auth_mode,
                settings=settings,
                api_root=api_root,
            )
        deadline = time.monotonic() + min(2**index, 8)
        while time.monotonic() < deadline:
            if check_control:
                check_control()
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    raise AssertionError("unreachable retry exit")


def _send_request(
    protocol: str,
    endpoint: str,
    api_key: str,
    auth_mode: str | None,
    body: dict[str, Any],
    timeout: float,
) -> tuple[dict[str, Any], str | None]:
    """Official SDK transports, with SDK retries off so each attempt is observable."""
    route = _PROTOCOL_PATHS[protocol]
    root = endpoint.removesuffix(route)
    try:
        if protocol == "anthropic_messages":
            client: Any = anthropic.Anthropic(
                api_key="" if auth_mode == "bearer" else api_key,
                auth_token=api_key if auth_mode == "bearer" else "",
                base_url=root,
                timeout=timeout,
                max_retries=0,
            )
        else:
            client = openai.OpenAI(api_key=api_key, base_url=root, timeout=timeout, max_retries=0)
        with client:
            response = client.post(route, body=body, cast_to=httpx2.Response)
            payload = response.json()
            request_id = response.headers.get("x-request-id") or response.headers.get("request-id")
        if not isinstance(payload, dict):
            raise ValueError("response must be an object")
        return payload, request_id
    except (openai.APIStatusError, anthropic.APIStatusError) as exc:
        raise ModelApiError(
            "MODEL_PROVIDER_HTTP_ERROR",
            f"model provider returned HTTP {exc.status_code}",
            retryable=exc.status_code in {408, 409, 429} or exc.status_code >= 500,
        ) from exc
    except (openai.APIConnectionError, anthropic.APIConnectionError, TimeoutError) as exc:
        raise ModelApiError(
            "MODEL_PROVIDER_UNAVAILABLE", "model provider request failed", retryable=True
        ) from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise ModelApiError(
            "MODEL_INVALID_RESPONSE", "model provider returned invalid JSON", retryable=True
        ) from exc


def _finish_reason(payload: dict[str, Any], protocol: str) -> str | None:
    if protocol == "openai_chat_completions":
        choices = payload.get("choices")
        value = (
            choices[0].get("finish_reason")
            if (isinstance(choices, list) and choices and isinstance(choices[0], dict))
            else None
        )
    elif protocol == "openai_responses":
        details = payload.get("incomplete_details")
        value = details.get("reason") if isinstance(details, dict) else payload.get("status")
    else:
        value = payload.get("stop_reason")
    return value if isinstance(value, str) else None


def _validate_completion(payload: dict[str, Any], protocol: str) -> None:
    reason = _finish_reason(payload, protocol)
    if reason in {"length", "max_tokens", "max_output_tokens", "model_context_window_exceeded"}:
        raise ModelApiError(
            "MODEL_OUTPUT_TRUNCATED", "model output reached a token/context limit", retryable=True
        )
    output = payload.get("output")
    output = output if isinstance(output, list) else []
    if protocol == "openai_responses" and (
        payload.get("error")
        or any(
            isinstance(item, dict) and item.get("status") in {"incomplete", "failed"}
            for item in output
        )
    ):
        raise ModelApiError(
            "MODEL_COMPLETION_INVALID", "response contains incomplete output", retryable=True
        )
    choices = payload.get("choices")
    message = (
        choices[0].get("message")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict)
        else None
    )
    if (isinstance(message, dict) and message.get("refusal")) or any(
        isinstance(item, dict)
        and isinstance(item.get("content"), list)
        and any(
            isinstance(part, dict) and part.get("type") == "refusal" for part in item["content"]
        )
        for item in output
    ):
        raise ModelApiError("MODEL_COMPLETION_INVALID", "model provider refused the request")
    expected = {
        "openai_chat_completions": {"stop"},
        "openai_responses": {"completed"},
        "anthropic_messages": {"end_turn", "stop_sequence"},
    }[protocol]
    if reason not in expected:
        raise ModelApiError(
            "MODEL_COMPLETION_INVALID",
            "model did not report normal completion",
            retryable=reason is None or reason in {"failed", "incomplete", "aborted"},
        )


def _reported_usage(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    # Only provider numeric counters; never persist arbitrary response text.
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            result[key] = _reported_usage(item)
        elif item is None or (isinstance(item, int) and not isinstance(item, bool) and item >= 0):
            result[key] = item
    return result or None


def _build_request(
    *,
    protocol: str,
    model: str,
    api_key: str,
    system_prompt: str,
    user_text: str,
    image_data_url: str | None,
    auth_mode: str | None,
    settings: ModelRequestOptions,
    api_root: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    adapter = settings.thinking_adapter
    if adapter == "auto":
        host = urlparse(api_root).hostname or ""
        adapter = (
            "anthropic_budget"
            if protocol == "anthropic_messages"
            else "deepseek"
            if host.endswith("deepseek.com")
            else "dashscope"
            if "dashscope" in host
            else "openai"
        )
    reasoning: dict[str, Any] = {}
    if protocol != "anthropic_messages":
        if settings.thinking_enabled:
            if adapter == "deepseek":
                reasoning = {
                    "thinking": {"type": "enabled"},
                    "reasoning_effort": settings.reasoning_effort,
                }
            elif adapter == "dashscope":
                reasoning = {"enable_thinking": True}
            else:
                reasoning = (
                    {"reasoning": {"effort": settings.reasoning_effort}}
                    if protocol == "openai_responses"
                    else {"reasoning_effort": settings.reasoning_effort}
                )
        elif adapter == "deepseek":
            reasoning = {"thinking": {"type": "disabled"}}
        elif adapter == "dashscope":
            reasoning = {"enable_thinking": False}
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
                **(
                    {"max_completion_tokens": settings.max_output_tokens}
                    if adapter == "openai" and settings.thinking_enabled
                    else {"max_tokens": settings.max_output_tokens}
                ),
                **reasoning,
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
                "max_output_tokens": settings.max_output_tokens,
                **reasoning,
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
            "max_tokens": settings.max_output_tokens,
            **(
                {
                    "thinking": {"type": "adaptive"},
                    "output_config": {"effort": settings.reasoning_effort},
                }
                if settings.thinking_enabled and adapter == "anthropic_adaptive"
                else {
                    "thinking": {
                        "type": "enabled",
                        "budget_tokens": min(
                            settings.thinking_budget_tokens, settings.max_output_tokens - 1
                        ),
                    }
                }
                if settings.thinking_enabled
                else {"thinking": {"type": "disabled"}}
            ),
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
