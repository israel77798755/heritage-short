"""Tests for fictional character/style references with a fake image provider."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.keyframes import KeyframeReferences
from pipeline.providers import GenerationRequest, GenerationResult
from pipeline.references import generate_reference_images
from validate_storyboard import STORYBOARD_PATH


class FakeImageProvider:
    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def generate_image(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        request.output_path.write_bytes(b"fake reference image")
        return GenerationResult(
            provider="fake-image-provider",
            model="fake-image-model",
            output_path=request.output_path,
            seed=request.seed,
        )


class TestReferenceGeneration(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.storyboard = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
        self.outputs_dir = self.root / "outputs"
        self.log_path = self.root / "runs.jsonl"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _generate(self, provider: FakeImageProvider) -> KeyframeReferences:
        return generate_reference_images(
            self.storyboard,
            provider,
            provider_name="fake-image-provider",
            model="fake-image-model",
            outputs_dir=self.outputs_dir,
            log_path=self.log_path,
        )

    def test_builds_fictional_portraits_and_style_reference(self) -> None:
        provider = FakeImageProvider()

        references = self._generate(provider)

        self.assertEqual(len(provider.requests), 3)
        self.assertTrue(all(path.is_file() for path in references.paths()))
        self.assertIn("fictional", provider.requests[0].prompt.lower())
        self.assertIn("Almaz", provider.requests[0].prompt)
        self.assertIn("Dawit", provider.requests[1].prompt)
        self.assertIn("visual style reference", provider.requests[2].prompt.lower())
        self.assertTrue(
            all(
                "no text" in request.prompt.lower()
                or "without text" in request.prompt.lower()
                for request in provider.requests
            )
        )
        self.assertEqual(
            [request.seed for request in provider.requests],
            [9001, 9002, 9003],
        )

    def test_unchanged_references_are_reused(self) -> None:
        first_provider = FakeImageProvider()
        first = self._generate(first_provider)

        second_provider = FakeImageProvider()
        second = self._generate(second_provider)

        self.assertEqual(len(first_provider.requests), 3)
        self.assertEqual(second_provider.requests, [])
        self.assertEqual(first, second)

    def test_reference_prompt_change_regenerates_only_affected_portrait(self) -> None:
        self._generate(FakeImageProvider())
        self.storyboard["characters"]["mother"]["description"] += " Updated attire detail."
        second_provider = FakeImageProvider()

        self._generate(second_provider)

        self.assertEqual(len(second_provider.requests), 1)
        self.assertIn("Updated attire detail", second_provider.requests[0].prompt)

    def test_nonfictional_character_is_rejected_before_provider_calls(self) -> None:
        self.storyboard["characters"]["mother"]["fictional"] = False
        provider = FakeImageProvider()

        with self.assertRaisesRegex(ValueError, "fictional characters"):
            self._generate(provider)

        self.assertEqual(provider.requests, [])


if __name__ == "__main__":
    unittest.main()
