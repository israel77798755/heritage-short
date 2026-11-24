"""Logged, bounded execution for provider-backed generation calls."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Callable
from pathlib import Path

from pipeline.providers import (
    GenerationRequest,
    GenerationResult,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from pipeline.retry import retry_call
from pipeline.runlog import append_model_call


GenerationOperation = Callable[[GenerationRequest], GenerationResult]


def run_generation_call(
    operation: GenerationOperation,
    request: GenerationRequest,
    *,
    provider: str,
    model: str,
    stage: str,
    log_path: Path,
    shot_id: str | None = None,
    max_attempts: int = 3,
    retry_on: tuple[type[Exception], ...] = (
        ProviderRateLimitError,
        ProviderTimeoutError,
    ),
    sleep: Callable[[float], None] = time.sleep,
) -> GenerationResult:
    """Run and log each provider attempt, retrying only declared transient errors.

    The raw prompt is never copied into the log; only its SHA-256 digest and
    the non-secret generation parameters are recorded.
    """
    if not callable(operation):
        raise TypeError("operation must be callable.")
    if not isinstance(request, GenerationRequest):
        raise TypeError("request must be a GenerationRequest.")
    for name, value in (("provider", provider), ("model", model), ("stage", stage)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("{} must be a non-empty string.".format(name))

    call_id = str(uuid.uuid4())
    attempt = 0
    parameters = dict(request.parameters)
    parameters["prompt_sha256"] = hashlib.sha256(
        request.prompt.encode("utf-8")
    ).hexdigest()

    def logged_operation() -> GenerationResult:
        nonlocal attempt
        attempt += 1
        started = time.perf_counter()
        try:
            result = operation(request)
            if not isinstance(result, GenerationResult):
                raise TypeError("Provider operation must return a GenerationResult.")
            if result.provider != provider or result.model != model:
                raise ValueError(
                    "Provider result metadata does not match the configured provider and model."
                )
            if Path(result.output_path) != Path(request.output_path):
                raise ValueError("Provider wrote output to an unexpected path.")
            if not Path(result.output_path).is_file():
                raise FileNotFoundError(
                    "Provider reported success but the output file is missing: "
                    "{}".format(result.output_path)
                )
            if Path(result.output_path).stat().st_size == 0:
                raise OSError(
                    "Provider reported success but the output file is empty: "
                    "{}".format(result.output_path)
                )
        except Exception as error:
            status = "failed"
            if isinstance(error, ProviderRateLimitError):
                status = "rate_limited"
            elif isinstance(error, (ProviderTimeoutError, TimeoutError)):
                status = "timeout"
            append_model_call(
                log_path,
                provider=provider,
                model=model,
                stage=stage,
                shot_id=shot_id,
                parameters=parameters,
                seed=request.seed,
                latency_ms=(time.perf_counter() - started) * 1000,
                cost=None,
                currency=None,
                cost_basis=None,
                status=status,
                attempt=attempt,
                run_id=call_id,
                error_type=type(error).__name__,
            )
            raise

        append_model_call(
            log_path,
            provider=result.provider,
            model=result.model,
            stage=stage,
            shot_id=shot_id,
            parameters=parameters,
            seed=result.seed,
            latency_ms=(time.perf_counter() - started) * 1000,
            cost=result.cost,
            currency=result.currency,
            cost_basis=result.cost_basis,
            status="succeeded",
            attempt=attempt,
            run_id=call_id,
        )
        return result

    return retry_call(
        logged_operation,
        retry_on=retry_on,
        max_attempts=max_attempts,
        sleep=sleep,
    )
