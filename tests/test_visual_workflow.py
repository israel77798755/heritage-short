"""Tests for validation-gated orchestration of visual generation stages."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from pipeline.keyframes import KeyframeReferences
from pipeline.providers import GenerationRequest, GenerationResult
from pipeline.visual_workflow import run_visual_workflow
from validate_storyboard import SCHEMA_PATH, STORYBOARD_PATH, StoryboardValidationError


class FakeImageProvider:
    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def generate_image(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        request.output_path.write_bytes(b"fake image")
        return GenerationResult(
            provider="fake-image-provider",
            model="fake-image-model",
            output_path=request.output_path,
            seed=request.seed,
        )


class TestVisualWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.storyboard_path = self.root / "storyboard.json"
        self.storyboard = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
        self._write_storyboard()
        self.outputs_dir = self.root / "outputs"
        self.log_path = self.root / "runs.jsonl"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write_storyboard(self) -> None:
        self.storyboard_path.write_text(
            json.dumps(self.storyboard, ensure_ascii=False),
            encoding="utf-8",
        )

    def _run(self, provider: FakeImageProvider) -> dict[str, Any]:
        return run_visual_workflow(
            provider,
            provider_name="fake-image-provider",
            model="fake-image-model",
            storyboard_path=self.storyboard_path,
            schema_path=SCHEMA_PATH,
            outputs_dir=self.outputs_dir,
            log_path=self.log_path,
        )

    def test_runs_reference_stage_before_all_keyframes(self) -> None:
        provider = FakeImageProvider()

        results = self._run(provider)

        self.assertEqual(list(results), ["references", "keyframes"])
        self.assertIsInstance(results["references"], KeyframeReferences)
        self.assertEqual(list(results["keyframes"]), list(range(1, 11)))
        self.assertEqual(len(provider.requests), 13)
        self.assertEqual(
            [request.seed for request in provider.requests[:3]],
            [9001, 9002, 9003],
        )
        self.assertEqual(
            [request.seed for request in provider.requests[3:]],
            list(range(1001, 1011)),
        )

    def test_invalid_storyboard_prevents_every_provider_call(self) -> None:
        self.storyboard["scenes"][0]["subtitle_en"] = ""
        self._write_storyboard()
        provider = FakeImageProvider()

        with self.assertRaises(StoryboardValidationError):
            self._run(provider)

        self.assertEqual(provider.requests, [])
        self.assertFalse(self.log_path.exists())

    def test_only_changed_shot_is_regenerated_on_rerun(self) -> None:
        first_provider = FakeImageProvider()
        self._run(first_provider)

        self.storyboard["scenes"][0]["image_prompt"] += " New close framing."
        self._write_storyboard()
        second_provider = FakeImageProvider()
        self._run(second_provider)

        self.assertEqual(len(first_provider.requests), 13)
        self.assertEqual(len(second_provider.requests), 1)
        self.assertIn("New close framing", second_provider.requests[0].prompt)


if __name__ == "__main__":
    unittest.main()
