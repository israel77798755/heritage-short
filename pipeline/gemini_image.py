"""Explicit, standard-library Gemini image generation adapter."""

from __future__ import annotations

import base64
import binascii
import json
import math
import mimetypes
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as HttpRequest
from urllib.request import urlopen

from pipeline.config import get_env
from pipeline.providers import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)


_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_API_REVISION = "2026-05-20"
_SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


class GeminiImageProvider:
    """Image provider for Gemini's Interactions API.

    Constructing this class makes no network call. An API request occurs only
    when ``generate_image`` is explicitly invoked. The API does not expose a
    generation seed for this operation, so result metadata reports ``None``.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 120,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string.")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be greater than zero.")
        if api_key is not None and (
            not isinstance(api_key, str) or not api_key.strip()
        ):
            raise ValueError("api_key must be non-empty when supplied.")
        self.model = model.strip()
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds

    def generate_image(self, request: GenerationRequest) -> GenerationResult:
        """Generate one PNG from a prompt and optional local image references."""
        if not isinstance(request, GenerationRequest):
            raise TypeError("request must be a GenerationRequest.")
        if not isinstance(request.prompt, str) or not request.prompt.strip():
            raise ValueError("request.prompt must be a non-empty string.")
        if not isinstance(request.output_path, Path):
            raise TypeError("request.output_path must be a Path.")
        if request.output_path.suffix.lower() != ".png":
            raise ValueError("Gemini image output_path must use the .png extension.")
        if not isinstance(request.parameters, Mapping):
            raise TypeError("request.parameters must be a mapping.")
        if request.parameters:
            raise ValueError(
                "Gemini image parameters are not supported yet; express direction "
                "in the prompt instead."
            )
        output_path = Path(request.output_path)
        if output_path.exists():
            raise FileExistsError(
                "Refusing to overwrite an existing image: {}".format(output_path)
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        input_parts: list[dict[str, str]] = [
            {"type": "text", "text": request.prompt}
        ]
        for reference_path in request.reference_paths:
            path = Path(reference_path)
            if not path.is_file():
                raise FileNotFoundError("Reference image does not exist: {}".format(path))
            mime_type = mimetypes.guess_type(path.name)[0]
            if mime_type not in _SUPPORTED_IMAGE_TYPES:
                raise ValueError(
                    "Unsupported Gemini reference image type for {}.".format(path)
                )
            image_bytes = path.read_bytes()
            if not image_bytes:
                raise ValueError("Reference image is empty: {}".format(path))
            input_parts.append(
                {
                    "type": "image",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                    "mime_type": mime_type,
                }
            )

        payload = {
            "model": self.model,
            "input": input_parts,
        }
        http_request = HttpRequest(
            _INTERACTIONS_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._get_api_key(),
                "Api-Revision": _API_REVISION,
            },
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self.timeout_seconds) as response:
                response_data = response.read()
        except HTTPError as error:
            status_code = error.code
            error.close()
            if status_code == 429:
                raise ProviderRateLimitError(
                    "Gemini rejected the image request with HTTP 429."
                ) from error
            raise ProviderError(
                "Gemini image request failed with HTTP {}.".format(status_code)
            ) from error
        except TimeoutError as error:
            raise ProviderTimeoutError("Gemini image request timed out.") from error
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise ProviderTimeoutError("Gemini image request timed out.") from error
            raise ProviderError("Could not reach the Gemini image API.") from error

        image_bytes = self._extract_png(response_data)
        output_path.write_bytes(image_bytes)
        return GenerationResult(
            provider="gemini",
            model=self.model,
            output_path=output_path,
            seed=None,
        )

    def _get_api_key(self) -> str:
        if self._api_key is not None:
            return self._api_key
        api_key = get_env("GEMINI_API_KEY")
        if api_key is None:
            raise EnvironmentError("GEMINI_API_KEY is required for Gemini image generation.")
        return api_key

    @staticmethod
    def _extract_png(response_data: bytes) -> bytes:
        try:
            response: Any = json.loads(response_data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError("Gemini returned an invalid JSON image response.") from error
        output_image = response.get("output_image") if isinstance(response, dict) else None
        if not isinstance(output_image, dict):
            raise ProviderError("Gemini response did not contain an output image.")
        mime_type = output_image.get("mime_type")
        if mime_type is not None and mime_type != "image/png":
            raise ProviderError("Gemini response image must be PNG.")
        encoded_image = output_image.get("data")
        if not isinstance(encoded_image, str) or not encoded_image:
            raise ProviderError("Gemini response contained no image data.")
        try:
            image_bytes = base64.b64decode(encoded_image, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ProviderError("Gemini returned invalid base64 image data.") from error
        if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ProviderError("Gemini image data is not a valid PNG file.")
        return image_bytes
