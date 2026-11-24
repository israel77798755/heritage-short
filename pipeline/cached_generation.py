"""Content-addressed caching for provider-backed generation calls."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from pipeline.cache import (
    build_cache_key,
    cache_output_path,
    find_cached_asset,
)
from pipeline.provider_runner import GenerationOperation, run_generation_call
from pipeline.providers import (
    GenerationRequest,
    GenerationResult,
    ProviderRateLimitError,
    ProviderTimeoutError,
)


@dataclass(frozen=True)
class CachedGenerationResult:
    """Result metadata for a generated asset or a cache hit."""

    result: GenerationResult
    cache_key: str
    cache_hit: bool


def run_cached_generation_call(
    operation: GenerationOperation,
    request: GenerationRequest,
    *,
    provider: str,
    model: str,
    stage: str,
    outputs_dir: Path,
    log_path: Path,
    shot_id: str | None = None,
    max_attempts: int = 3,
    retry_on: tuple[type[Exception], ...] = (
        ProviderRateLimitError,
        ProviderTimeoutError,
    ),
    sleep: Callable[[float], None] = time.sleep,
) -> CachedGenerationResult:
    """Reuse unchanged outputs, otherwise run and log one provider operation.

    The cache key includes the prompt, generation parameters, seed, provider,
    model, file type, and the contents of every reference image. Cache hits do
    not call a provider or add a model-call log record.
    """
    if not isinstance(request, GenerationRequest):
        raise TypeError("request must be a GenerationRequest.")
    if not callable(operation):
        raise TypeError("operation must be callable.")
    if not isinstance(request.prompt, str):
        raise TypeError("request.prompt must be a string.")
    if not isinstance(request.output_path, Path):
        raise TypeError("request.output_path must be a Path.")
    for name, value in (("provider", provider), ("model", model)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("{} must be a non-empty string.".format(name))
    extension = request.output_path.suffix
    if not extension:
        raise ValueError("request.output_path must include a file extension.")

    reference_files = {
        "reference_{:03d}".format(index): path
        for index, path in enumerate(request.reference_paths)
    }
    cache_key = build_cache_key(
        stage,
        {
            "provider": provider,
            "model": model,
            "shot_id": shot_id,
            "prompt": request.prompt,
            "parameters": dict(request.parameters),
            "seed": request.seed,
            "file_extension": extension,
        },
        reference_files,
    )
    cached_path = cache_output_path(outputs_dir, stage, cache_key, extension)
    cached_asset = find_cached_asset(cached_path)
    if cached_asset is not None:
        return CachedGenerationResult(
            result=GenerationResult(
                provider=provider,
                model=model,
                output_path=cached_asset,
                seed=request.seed,
            ),
            cache_key=cache_key,
            cache_hit=True,
        )

    cached_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = cached_path.with_name(
        "{}.tmp-{}{}".format(cached_path.stem, uuid.uuid4().hex, extension)
    )
    cached_request = replace(request, output_path=temporary_path)
    try:
        result = run_generation_call(
            operation,
            cached_request,
            provider=provider,
            model=model,
            stage=stage,
            log_path=log_path,
            shot_id=shot_id,
            max_attempts=max_attempts,
            retry_on=retry_on,
            sleep=sleep,
        )
        temporary_path.replace(cached_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    return CachedGenerationResult(
        result=replace(result, output_path=cached_path),
        cache_key=cache_key,
        cache_hit=False,
    )
