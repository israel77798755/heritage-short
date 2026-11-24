"""Mocked tests for the Gemini image adapter; no network calls are made."""

from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from pipeline.cached_generation import run_cached_generation_call
from pipeline.gemini_image import GeminiImageProvider
from pipeline.providers import (
    GenerationRequest,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)


_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lS8AAAAASUVORK5CYII="
)


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class TestGeminiImageProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.output_path = self.root / "generated.png"
        self.provider = GeminiImageProvider(
            "gemini-nano-banana-2.1",
            api_key="test-key",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _response(self, image_bytes: bytes = _PNG_BYTES) -> bytes:
        return json.dumps(
            {
                "output_image": {
                    "mime_type": "image/png",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }
        ).encode("utf-8")

    def test_initialization_does_not_make_an_api_request(self) -> None:
        with patch("pipeline.gemini_image.urlopen") as post:
            GeminiImageProvider("gemini-nano-banana-2.1", api_key="test-key")

        post.assert_not_called()

    def test_sends_prompt_and_reference_without_exposing_key_in_payload(self) -> None:
        reference = self.root / "reference.png"
        reference.write_bytes(b"fictional reference image")
        request = GenerationRequest(
            prompt="Create a fictional Ethiopian highland scene.",
            output_path=self.output_path,
            reference_paths=(reference,),
        )
        response = FakeResponse(self._response())

        with patch("pipeline.gemini_image.urlopen", return_value=response) as post:
            result = self.provider.generate_image(request)

        http_request = post.call_args.args[0]
        payload = json.loads(http_request.data.decode("utf-8"))
        self.assertEqual(http_request.full_url, "https://generativelanguage.googleapis.com/v1beta/interactions")
        self.assertEqual(http_request.get_header("X-goog-api-key"), "test-key")
        self.assertEqual(payload["model"], "gemini-nano-banana-2.1")
        self.assertEqual(payload["input"][0]["text"], request.prompt)
        self.assertEqual(
            payload["input"][1]["data"],
            base64.b64encode(reference.read_bytes()).decode("ascii"),
        )
        self.assertNotIn("test-key", json.dumps(payload))
        self.assertEqual(result.output_path, self.output_path)
        self.assertEqual(result.provider, "gemini")
        self.assertIsNone(result.seed)
        self.assertEqual(self.output_path.read_bytes(), _PNG_BYTES)

    def test_missing_image_response_is_reported(self) -> None:
        with patch(
            "pipeline.gemini_image.urlopen",
            return_value=FakeResponse(b'{"output_text":"no image"}'),
        ):
            with self.assertRaisesRegex(ProviderError, "did not contain an output image"):
                self.provider.generate_image(
                    GenerationRequest("A scene", self.output_path)
                )

    def test_unsupported_parameters_are_rejected_before_api_call(self) -> None:
        with patch("pipeline.gemini_image.urlopen") as post:
            with self.assertRaisesRegex(ValueError, "not supported yet"):
                self.provider.generate_image(
                    GenerationRequest(
                        "A scene",
                        self.output_path,
                        parameters={"guidance": 7},
                    )
                )
        post.assert_not_called()

    def test_cached_call_logs_metadata_once_without_prompt_or_key(self) -> None:
        log_path = self.root / "runs.jsonl"
        request = GenerationRequest(
            prompt="A private fictional scene",
            output_path=self.root / "shot.png",
            seed=17,
        )

        with patch(
            "pipeline.gemini_image.urlopen",
            return_value=FakeResponse(self._response()),
        ) as post:
            first = run_cached_generation_call(
                self.provider.generate_image,
                request,
                provider="gemini",
                model="gemini-nano-banana-2.1",
                stage="keyframes",
                outputs_dir=self.root / "outputs",
                log_path=log_path,
                sleep=lambda _delay: None,
            )
            second = run_cached_generation_call(
                self.provider.generate_image,
                request,
                provider="gemini",
                model="gemini-nano-banana-2.1",
                stage="keyframes",
                outputs_dir=self.root / "outputs",
                log_path=log_path,
                sleep=lambda _delay: None,
            )

        records = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.cache_key, second.cache_key)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["provider"], "gemini")
        self.assertEqual(records[0]["model"], "gemini-nano-banana-2.1")
        self.assertIsNone(records[0]["seed"])
        self.assertIsNone(records[0]["cost"])
        self.assertEqual(records[0]["status"], "succeeded")
        prompt_hash = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()
        self.assertEqual(
            records[0]["parameters"]["prompt_sha256"],
            prompt_hash,
        )
        log_contents = log_path.read_text(encoding="utf-8")
        self.assertNotIn(request.prompt, log_contents)
        self.assertNotIn("test-key", log_contents)
        post.assert_called_once()

    def test_non_png_image_response_is_rejected(self) -> None:
        body = json.dumps(
            {
                "output_image": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(_PNG_BYTES).decode("ascii"),
                }
            }
        ).encode("utf-8")
        with patch(
            "pipeline.gemini_image.urlopen",
            return_value=FakeResponse(body),
        ):
            with self.assertRaisesRegex(ProviderError, "must be PNG"):
                self.provider.generate_image(
                    GenerationRequest("A scene", self.output_path)
                )

    def test_png_signature_is_accepted_when_mime_type_is_omitted(self) -> None:
        body = json.dumps(
            {
                "output_image": {
                    "data": base64.b64encode(_PNG_BYTES).decode("ascii"),
                }
            }
        ).encode("utf-8")
        with patch(
            "pipeline.gemini_image.urlopen",
            return_value=FakeResponse(body),
        ):
            result = self.provider.generate_image(
                GenerationRequest("A scene", self.output_path)
            )

        self.assertEqual(result.output_path.read_bytes(), _PNG_BYTES)

    def test_rate_limit_and_timeout_map_to_retryable_provider_errors(self) -> None:
        rate_limit = HTTPError(
            "https://generativelanguage.googleapis.com",
            429,
            "rate limited",
            hdrs=None,
            fp=BytesIO(b""),
        )
        with patch("pipeline.gemini_image.urlopen", side_effect=rate_limit):
            with self.assertRaises(ProviderRateLimitError):
                self.provider.generate_image(
                    GenerationRequest("A scene", self.output_path)
                )
        rate_limit.close()

        with patch("pipeline.gemini_image.urlopen", side_effect=TimeoutError()):
            with self.assertRaises(ProviderTimeoutError):
                self.provider.generate_image(
                    GenerationRequest("A scene", self.output_path)
                )

    def test_missing_key_and_existing_output_fail_without_overwrite(self) -> None:
        provider = GeminiImageProvider("gemini-nano-banana-2.1")
        with (
            patch("pipeline.gemini_image.get_env", side_effect=EnvironmentError("missing")),
            patch("pipeline.gemini_image.urlopen") as post,
        ):
            with self.assertRaisesRegex(EnvironmentError, "missing"):
                provider.generate_image(GenerationRequest("A scene", self.output_path))
        post.assert_not_called()

        self.output_path.write_bytes(b"keep existing")
        with patch(
            "pipeline.gemini_image.urlopen",
            return_value=FakeResponse(self._response()),
        ) as post:
            with self.assertRaises(FileExistsError):
                self.provider.generate_image(
                    GenerationRequest("A scene", self.output_path)
                )
        post.assert_not_called()
        self.assertEqual(self.output_path.read_bytes(), b"keep existing")


if __name__ == "__main__":
    unittest.main()
