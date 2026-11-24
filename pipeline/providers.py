"""Provider-neutral contracts for optional hosted generation services.

Each adapter implements only the media capabilities it actually supports.
These protocols do not make network calls or select a specific provider.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class GenerationRequest:
    """Inputs shared by generation providers."""

    prompt: str
    output_path: Path
    reference_paths: tuple[Path, ...] = ()
    seed: int | None = None
    parameters: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationResult:
    """Provider-reported output and metadata for a completed generation call."""

    provider: str
    model: str
    output_path: Path
    seed: int | None
    cost: float | None = None
    currency: str | None = None
    cost_basis: str | None = None


class ProviderError(RuntimeError):
    """Base class for errors raised by a concrete provider adapter."""


class ProviderRateLimitError(ProviderError):
    """The provider rejected the request because of a rate or quota limit."""


class ProviderTimeoutError(ProviderError):
    """The provider request timed out and may be safe to retry."""


@runtime_checkable
class TextGenerationProvider(Protocol):
    """Capability contract for a provider that generates text."""

    def generate_text(self, request: GenerationRequest) -> GenerationResult: ...


@runtime_checkable
class ImageGenerationProvider(Protocol):
    """Capability contract for a provider that generates still images."""

    def generate_image(self, request: GenerationRequest) -> GenerationResult: ...


@runtime_checkable
class VideoGenerationProvider(Protocol):
    """Capability contract for a provider that generates video clips."""

    def generate_video(self, request: GenerationRequest) -> GenerationResult: ...


@runtime_checkable
class MusicGenerationProvider(Protocol):
    """Capability contract for a provider that generates music."""

    def generate_music(self, request: GenerationRequest) -> GenerationResult: ...


@runtime_checkable
class NarrationGenerationProvider(Protocol):
    """Capability contract for a provider that generates spoken narration."""

    def generate_narration(self, request: GenerationRequest) -> GenerationResult: ...
