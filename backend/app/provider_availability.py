"""Safe availability checks and guarded calls for OpenAI-compatible vision APIs."""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import random
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from PIL import Image
import io

from . import config


ERROR_TYPES = {
    "dns_error", "tls_error", "connect_timeout", "read_timeout",
    "authentication_error", "permission_error", "endpoint_not_found",
    "model_not_found", "rate_limited", "quota_exceeded",
    "payload_too_large", "invalid_request", "provider_5xx",
    "invalid_json", "schema_validation_failed", "unknown_provider_error",
}
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class CallPolicy:
    connect_timeout: float = 10
    read_timeout: float = 120
    write_timeout: float = 30
    pool_timeout: float = 10
    max_retries: int = 2
    backoff_base: float = 1
    jitter_max: float = 0.5


class ProviderCallError(RuntimeError):
    def __init__(
        self,
        error_type: str,
        message: str,
        *,
        status_code: int | None = None,
        provider_error_code: str = "",
        request_id: str = "",
        retry_after: float | None = None,
        entered_provider: bool = False,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code
        self.provider_error_code = provider_error_code
        self.request_id = request_id
        self.retry_after = retry_after
        self.entered_provider = entered_provider

    @property
    def retryable(self) -> bool:
        if self.error_type == "quota_exceeded":
            return False
        return self.error_type in {
            "connect_timeout", "read_timeout", "rate_limited", "provider_5xx"
        } or self.status_code in RETRYABLE_STATUS

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "http_status": self.status_code,
            "provider_error_code": self.provider_error_code,
            "request_id": self.request_id,
            "entered_provider": self.entered_provider,
            "message": str(self),
        }


class CircuitBreaker:
    """Process-local circuit breaker; three consecutive failures open it."""

    def __init__(self, failure_threshold: int = 3):
        self.failure_threshold = failure_threshold
        self.consecutive_failures = 0
        self.is_open = False
        self._lock = threading.Lock()

    def before_call(self) -> None:
        if self.is_open:
            raise ProviderCallError(
                "unknown_provider_error", "provider circuit is open"
            )

    def record_success(self) -> None:
        with self._lock:
            self.consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.failure_threshold:
                self.is_open = True


GLOBAL_BREAKER = CircuitBreaker()


def is_real_model_success(analyzed_by: str, generation_mode: str = "model") -> bool:
    """Fallback output is operationally useful but never a provider success."""
    return bool(
        analyzed_by
        and analyzed_by != "启发式规则"
        and "fallback" not in analyzed_by.lower()
        and "fallback" not in generation_mode.lower()
        and generation_mode == "model"
    )


def safe_config_summary() -> dict[str, Any]:
    parsed = urlparse(config.VISION_BASE_URL)
    host = parsed.hostname or ""
    region = "not_inferred"
    if host.startswith("ark.") and len(host.split(".")) > 1:
        region = host.split(".")[1]
    config_errors = []
    if parsed.path.rstrip("/").endswith("/chat/completions"):
        config_errors.append("base_url_must_not_include_chat_completions")
    if parsed.path.count("/api/v3") > 1:
        config_errors.append("base_url_contains_duplicate_api_path")
    if config.VISION_PROVIDER == "volcengine" and not config.VISION_MODEL.startswith("ep-"):
        config_errors.append("volcengine_model_is_not_endpoint_id")
    return {
        "provider": config.VISION_PROVIDER,
        "api_key": "configured" if config.VISION_API_KEY else "missing",
        "base_url": config.VISION_BASE_URL,
        "region": region,
        "model": config.VISION_MODEL,
        "model_configured": bool(config.VISION_MODEL),
        "trust_environment_proxy": config.VISION_TRUST_ENV,
        "environment_sources": [
            {
                "path": str(path), "exists": path.is_file(),
            }
            for path in (config.PROJECT_DIR / ".env", config.BASE_DIR / ".env")
        ],
        "httpx_version": httpx.__version__,
        "proxy_environment_present": {
            name: bool(os.getenv(name))
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
        },
        "configuration_errors": config_errors,
        "timeouts": {
            "connect_seconds": config.VISION_CONNECT_TIMEOUT,
            "read_seconds": config.VISION_READ_TIMEOUT,
        },
        "max_retries": config.VISION_MAX_RETRIES,
        "batch_concurrency": config.BATCH_CONCURRENCY,
        "image_encoding": "base64 data URI; JPEG after bounded resize",
        "max_tokens": config.VISION_MAX_TOKENS,
    }


def _provider_details(response: httpx.Response) -> tuple[str, str, float | None]:
    request_id = (
        response.headers.get("x-request-id")
        or response.headers.get("x-tt-logid")
        or response.headers.get("request-id")
        or ""
    )
    code = ""
    try:
        body = response.json()
        error = body.get("error", body) if isinstance(body, dict) else {}
        if isinstance(error, dict):
            code = str(error.get("code") or error.get("type") or "")
    except (ValueError, json.JSONDecodeError):
        pass
    retry_after = None
    try:
        if response.headers.get("retry-after"):
            retry_after = float(response.headers["retry-after"])
    except ValueError:
        pass
    return code, request_id, retry_after


def classify_http_response(response: httpx.Response) -> ProviderCallError:
    status = response.status_code
    code, request_id, retry_after = _provider_details(response)
    lowered = code.lower()
    if status == 401:
        kind = "authentication_error"
    elif status == 403:
        kind = "permission_error"
    elif status == 404:
        kind = "model_not_found" if any(
            word in lowered for word in ("model", "endpoint", "deployment")
        ) else "endpoint_not_found"
    elif status == 413:
        kind = "payload_too_large"
    elif status == 408:
        kind = "read_timeout"
    elif status == 429:
        kind = "quota_exceeded" if "quota" in lowered else "rate_limited"
    elif status >= 500:
        kind = "provider_5xx"
    elif status in {400, 405, 409, 422}:
        kind = "invalid_request"
    else:
        kind = "unknown_provider_error"
    return ProviderCallError(
        kind,
        f"provider request failed with HTTP {status}",
        status_code=status,
        provider_error_code=code,
        request_id=request_id,
        retry_after=retry_after,
        entered_provider=True,
    )


def classify_exception(error: Exception) -> ProviderCallError:
    if isinstance(error, ProviderCallError):
        return error
    if isinstance(error, httpx.ConnectTimeout):
        return ProviderCallError("connect_timeout", str(error))
    if isinstance(error, httpx.ReadTimeout):
        return ProviderCallError("read_timeout", str(error), entered_provider=True)
    if isinstance(error, httpx.ConnectError):
        cause = repr(error).lower()
        if any(word in cause for word in ("name resolution", "getaddrinfo", "nodename")):
            kind = "dns_error"
        elif any(word in cause for word in ("ssl", "tls", "certificate")):
            kind = "tls_error"
        else:
            kind = "unknown_provider_error"
        return ProviderCallError(kind, str(error))
    if isinstance(error, json.JSONDecodeError):
        return ProviderCallError("invalid_json", str(error), entered_provider=True)
    return ProviderCallError("unknown_provider_error", str(error))


def guarded_chat_request(
    payload: dict[str, Any],
    *,
    policy: CallPolicy | None = None,
    breaker: CircuitBreaker | None = None,
    client_factory: Callable[..., httpx.Client] = httpx.Client,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    policy = policy or CallPolicy(
        connect_timeout=config.VISION_CONNECT_TIMEOUT,
        read_timeout=config.VISION_READ_TIMEOUT,
        max_retries=config.VISION_MAX_RETRIES,
    )
    breaker = breaker or GLOBAL_BREAKER
    url = f"{config.VISION_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.VISION_API_KEY}",
        "Content-Type": "application/json",
    }
    attempts: list[dict[str, Any]] = []
    for attempt in range(policy.max_retries + 1):
        breaker.before_call()
        started = time.perf_counter()
        try:
            trace_times: dict[str, float] = {}
            def trace(name: str, _info: dict[str, Any]) -> None:
                if name.endswith("connect_tcp.started"):
                    trace_times["connect_started"] = time.perf_counter()
                elif name.endswith("connect_tcp.complete"):
                    trace_times["connect_finished"] = time.perf_counter()
            timeout = httpx.Timeout(
                connect=policy.connect_timeout,
                read=policy.read_timeout,
                write=policy.write_timeout,
                pool=policy.pool_timeout,
            )
            with client_factory(trust_env=config.VISION_TRUST_ENV, timeout=timeout) as client:
                before_send = time.perf_counter()
                with client.stream(
                    "POST", url, json=payload, headers=headers,
                    extensions={"trace": trace},
                ) as response:
                    first_byte_ms = round((time.perf_counter() - before_send) * 1000)
                    raw = response.read()
                    request_id = (
                        response.headers.get("x-request-id")
                        or response.headers.get("x-tt-logid")
                        or response.headers.get("request-id")
                        or ""
                    )
                    if response.status_code >= 400:
                        raise classify_http_response(response)
                    try:
                        body = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise ProviderCallError(
                            "invalid_json", str(exc), request_id=request_id,
                            status_code=response.status_code, entered_provider=True,
                        ) from exc
            total_ms = round((time.perf_counter() - started) * 1000)
            breaker.record_success()
            return {
                "body": body,
                "http_status": response.status_code,
                "provider_error_code": "",
                "request_id": request_id,
                "connect_ms": (
                    round(
                        (trace_times["connect_finished"] - trace_times["connect_started"])
                        * 1000
                    )
                    if {"connect_started", "connect_finished"}.issubset(trace_times)
                    else None
                ),
                "first_byte_ms": first_byte_ms,
                "total_ms": total_ms,
                "attempt_count": attempt + 1,
                "attempts": attempts,
                "entered_provider": True,
            }
        except Exception as exc:  # noqa: BLE001
            classified = classify_exception(exc)
            attempts.append({
                "attempt": attempt + 1,
                "error_type": classified.error_type,
                "http_status": classified.status_code,
                "provider_error_code": classified.provider_error_code,
                "request_id": classified.request_id,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
            })
            breaker.record_failure()
            if not classified.retryable or attempt >= policy.max_retries or breaker.is_open:
                classified.attempts = attempts  # type: ignore[attr-defined]
                raise classified
            delay = classified.retry_after
            if delay is None:
                delay = policy.backoff_base * (2**attempt) + random.uniform(0, policy.jitter_max)
            sleeper(min(delay, 30))
    raise AssertionError("unreachable")


def network_probe() -> dict[str, Any]:
    parsed = urlparse(config.VISION_BASE_URL)
    host = parsed.hostname or ""
    port = parsed.port or 443
    checked_at = dt.datetime.now(dt.UTC).isoformat()
    started = time.perf_counter()
    result: dict[str, Any] = {
        "checked_at": checked_at, "host": host, "port": port,
        "dns": "not_run", "tcp_tls": "not_run", "elapsed_ms": 0,
        "error_type": "", "exception_type": "",
    }
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        result["dns"] = "success"
        result["resolved_address_count"] = len(addresses)
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=10) as tcp:
            with context.wrap_socket(tcp, server_hostname=host) as tls:
                result["tls_version"] = tls.version()
        result["tcp_tls"] = "success"
    except socket.gaierror as exc:
        result.update(error_type="dns_error", exception_type=type(exc).__name__)
    except (ssl.SSLError, ssl.CertificateError) as exc:
        result.update(error_type="tls_error", exception_type=type(exc).__name__)
    except (TimeoutError, socket.timeout) as exc:
        result.update(error_type="connect_timeout", exception_type=type(exc).__name__)
    except OSError as exc:
        result.update(error_type="unknown_provider_error", exception_type=type(exc).__name__)
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return result


def _minimal_text_payload() -> dict[str, Any]:
    return {
        "model": config.VISION_MODEL,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "temperature": 0,
        "max_tokens": 8,
    }


def _minimal_image_payload(image_path: Path) -> tuple[dict[str, Any], int]:
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        image.thumbnail((768, 768), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, "JPEG", quality=80, optimize=True)
    data = output.getvalue()
    uri = "data:image/jpeg;base64," + base64.b64encode(data).decode()
    return ({
        "model": config.VISION_MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Describe this image in one short sentence."},
            {"type": "image_url", "image_url": {"url": uri}},
        ]}],
        "temperature": 0,
        "max_tokens": 40,
    }, len(data))


def run_preflight(
    image_path: Path | None = None,
    *,
    policy: CallPolicy | None = None,
    breaker: CircuitBreaker | None = None,
    request: Callable[..., dict[str, Any]] = guarded_chat_request,
) -> dict[str, Any]:
    checked_at = dt.datetime.now(dt.UTC).isoformat()
    result: dict[str, Any] = {
        "checked_at": checked_at,
        "status": "blocked_by_provider_availability",
        "configuration": safe_config_summary(),
        "network": {}, "minimal_text": {"status": "not_run"},
        "minimal_image": {"status": "not_run"},
        "formal_schema": {"status": "not_run"},
        "holdout_executed": False,
    }
    missing = config.vision_missing_config()
    if missing:
        result["block_reason"] = "missing_configuration"
        result["missing_configuration"] = missing
        return result
    if result["configuration"]["configuration_errors"]:
        result["block_reason"] = "invalid_configuration"
        return result
    breaker = breaker or GLOBAL_BREAKER
    if breaker.is_open:
        result["block_reason"] = "circuit_open"
        return result
    result["network"] = network_probe()
    if result["network"].get("error_type"):
        result["block_reason"] = result["network"]["error_type"]
        return result
    try:
        text = request(_minimal_text_payload(), policy=policy, breaker=breaker)
        result["minimal_text"] = {"status": "success", **{k: v for k, v in text.items() if k != "body"}}
    except ProviderCallError as exc:
        result["minimal_text"] = {"status": "failed", **exc.to_dict(), "attempts": getattr(exc, "attempts", [])}
        result["block_reason"] = exc.error_type
        return result
    if image_path is None:
        result["block_reason"] = "minimal_image_not_supplied"
        return result
    try:
        payload, size = _minimal_image_payload(image_path)
        image = request(payload, policy=policy, breaker=breaker)
        result["minimal_image"] = {
            "status": "success", "encoded_image_bytes": size,
            **{k: v for k, v in image.items() if k != "body"},
        }
    except ProviderCallError as exc:
        result["minimal_image"] = {"status": "failed", **exc.to_dict(), "attempts": getattr(exc, "attempts", [])}
        result["block_reason"] = exc.error_type
        return result
    result["status"] = "ready"
    result["block_reason"] = ""
    return result
