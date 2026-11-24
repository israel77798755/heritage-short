"""Tests for storyboard-driven keyframes using a local fake image provider."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.keyframes import KeyframeReferences, generate_keyframes
from pipeline.providers import GenerationRequest, GenerationResult
from validate_storyboard import STORYBOARD_PATH


class FakeImageProvider:
    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def generate_image(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        request.output_path.write_bytes(b"fake generated image")
        return GenerationResult(
            provider="fake-image-provider",
            model="fake-image-model",
            output_path=request.output_path,
            seed=request.seed,
        )


class TestKeyframeStage(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.storyboard = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
        self.references = KeyframeReferences(
            almaz=self.root / "almaz.png",
            dawit=self.root / "dawit.png",
            visual_style=self.root / "style.png",
        )
        for path in self.references.paths():
            path.write_bytes(b"approved fictional reference")
        self.outputs_dir = self.root / "outputs"
        self.log_path = self.root / "runs.jsonl"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _generate(self, provider: FakeImageProvider) -> dict[int, Path]:
        return generate_keyframes(
            self.storyboard,
            provider,
            provider_name="fake-image-provider",
            model="fake-image-model",
            references=self.references,
            outputs_dir=self.outputs_dir,
            log_path=self.log_path,
        )

    def test_generates_one_consistent_keyframe_request_per_scene(self) -> None:
        provider = FakeImageProvider()

        results = self._generate(provider)

        self.assertEqual(list(results), list(range(1, 11)))
        self.assertEqual(len(provider.requests), 10)
        self.assertTrue(all(path.is_file() for path in results.values()))
        self.assertTrue(
            all(
                request.reference_paths == self.references.paths()
                for request in provider.requests
            )
        )
        self.assertIn("cinematic realism", provider.requests[0].prompt.lower())
        self.assertIn("9:16 and 16:9", provider.requests[0].prompt)
        self.assertEqual(
            [request.seed for request in provider.requests],
            list(range(1001, 1011)),
        )

    def test_unchanged_scenes_are_reused_and_only_changed_scene_is_generated(self) -> None:
        first_provider = FakeImageProvider()
        self._generate(first_provider)

        self.storyboard["scenes"][4]["image_prompt"] += " Updated framing detail."
        second_provider = FakeImageProvider()
        self._generate(second_provider)

        self.assertEqual(len(first_provider.requests), 10)
        self.assertEqual(len(second_provider.requests), 1)
        self.assertIn("Updated framing detail", second_provider.requests[0].prompt)

    def test_missing_reference_stops_before_provider_calls(self) -> None:
        self.references.almaz.unlink()
        provider = FakeImageProvider()

        with self.assertRaisesRegex(FileNotFoundError, "Almaz reference"):
            self._generate(provider)

        self.assertEqual(provider.requests, [])

    def test_duplicate_scene_numbers_are_rejected_before_provider_calls(self) -> None:
        self.storyboard["scenes"][1]["scene_number"] = 1
        provider = FakeImageProvider()

        with self.assertRaisesRegex(ValueError, "unique"):
            self._generate(provider)

        self.assertEqual(provider.requests, [])

    def test_missing_aspect_ratio_is_rejected_before_provider_calls(self) -> None:
        self.storyboard["aspect_ratios"] = ["9:16"]
        provider = FakeImageProvider()

        with self.assertRaisesRegex(ValueError, "both 9:16 and 16:9"):
            self._generate(provider)

        self.assertEqual(provider.requests, [])


if __name__ == "__main__":
    unittest.main()
