"""Secret-conscious JSONL logging for actual model calls."""

from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SECRET_FIELD_PARTS = (
    "apikey",
    "token",
    "password",
    "secret",
    "authorization",
    "credential",
    "privatekey",
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE),
    re.compile(
        r"\b(api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*"
        r"(['\"]?)[A-Za-z0-9._~+/-]{8,}\2",
        re.IGNORECASE,
    ),
)
_ALLOWED_STATUSES = {"succeeded", "failed", "timeout", "rate_limited"}


def _validate_text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{} must be a non-empty string.".format(name))


def _sanitize_string(value: str) -> str:
    """Redact common credential formats from free-text parameter values."""
    for pattern in _SECRET_VALUE_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def _sanitize_for_log(value: Any) -> Any:
    """Copy JSON-compatible values while redacting sensitive fields."""
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Run-log parameter keys must be strings.")
            normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
            if any(part in normalized_key for part in _SECRET_FIELD_PARTS):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = _sanitize_for_log(item)
        return sanitized

    if isinstance(value, (list, tuple)):
        return [_sanitize_for_log(item) for item in value]

    if isinstance(value, str):
        return _sanitize_string(value)

    if value is None or isinstance(value, (bool, int, float)):
        return value

    raise TypeError(
        "Run-log parameters must contain only JSON-compatible values; "
        "unsupported type: {}.".format(type(value).__name__)
    )


def _validate_non_negative_number(name: str, value: int | float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("{} must be a non-negative number or None.".format(name))
    if not math.isfinite(value) or value < 0:
        raise ValueError("{} must be a finite, non-negative number.".format(name))


def append_model_call(
    log_path: Path,
    *,
    provider: str,
    model: str,
    stage: str,
    parameters: Mapping[str, Any],
    seed: int | None,
    latency_ms: int | float,
    cost: int | float | None,
    currency: str | None,
    cost_basis: str | None,
    status: str,
    attempt: int = 1,
    run_id: str | None = None,
    shot_id: str | None = None,
    error_type: str | None = None,
) -> dict[str, Any]:
    """Append one actual model-call record and return the safe record.

    ``parameters`` should contain non-secret generation settings. Sensitive
    fields and common credential strings are redacted before serialization.
    Raw prompts should be represented by a hash rather than copied here.
    """
    _validate_text("provider", provider)
    _validate_text("model", model)
    _validate_text("stage", stage)
    if run_id is not None:
        _validate_text("run_id", run_id)
    if not isinstance(parameters, Mapping):
        raise TypeError("parameters must be a mapping.")
    if seed is not None and (
        isinstance(seed, bool) or not isinstance(seed, int) or seed < 0
    ):
        raise ValueError("seed must be a non-negative integer or None.")
    _validate_non_negative_number("latency_ms", latency_ms)
    _validate_non_negative_number("cost", cost)
    if not isinstance(latency_ms, (int, float)) or isinstance(latency_ms, bool):
        raise TypeError("latency_ms must be a non-negative number.")
    if not isinstance(status, str) or status not in _ALLOWED_STATUSES:
        raise ValueError(
            "status must be one of: {}.".format(", ".join(sorted(_ALLOWED_STATUSES)))
        )
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("attempt must be a positive whole number.")
    if currency is not None and not isinstance(currency, str):
        raise TypeError("currency must be a string or None.")
    if cost_basis is not None and not isinstance(cost_basis, str):
        raise TypeError("cost_basis must be a string or None.")
    if error_type is not None:
        _validate_text("error_type", error_type)
    if shot_id is not None:
        _validate_text("shot_id", shot_id)

    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "run_id": _sanitize_string(run_id or str(uuid.uuid4())),
        "stage": _sanitize_string(stage),
        "shot_id": _sanitize_string(shot_id) if shot_id is not None else None,
        "attempt": attempt,
        "provider": _sanitize_string(provider),
        "model": _sanitize_string(model),
        "parameters": _sanitize_for_log(parameters),
        "seed": seed,
        "latency_ms": latency_ms,
        "cost": cost,
        "currency": _sanitize_string(currency) if currency is not None else None,
        "cost_basis": (
            _sanitize_string(cost_basis) if cost_basis is not None else None
        ),
        "status": status,
        "error_type": (
            _sanitize_string(error_type) if error_type is not None else None
        ),
    }

    serialized = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as log_file:
        log_file.write(serialized + "\n")
    return record
