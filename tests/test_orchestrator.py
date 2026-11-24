"""Tests for validation-before-execution and ordered pipeline stages."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from pipeline.orchestrator import PipelineStage, execute_pipeline
from validate_storyboard import SCHEMA_PATH, STORYBOARD_PATH, StoryboardValidationError


class TestPipelineOrchestrator(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.storyboard_path = Path(self.temporary_directory.name) / "storyboard.json"
        self.storyboard = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
        self.storyboard_path.write_text(
            json.dumps(self.storyboard, ensure_ascii=False), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_runs_stages_in_order_and_passes_prior_outputs(self) -> None:
        calls: list[str] = []

        def first(storyboard: dict[str, Any], prior: dict[str, Any]) -> str:
            calls.append("keyframes")
            self.assertEqual(storyboard["target_duration_seconds"], 75)
            self.assertEqual(prior, {})
            return "reference-assets"

        def second(storyboard: dict[str, Any], prior: dict[str, Any]) -> str:
            calls.append("shots")
            self.assertEqual(prior["keyframes"], "reference-assets")
            return "shot-assets"

        results = execute_pipeline(
            [
                PipelineStage("keyframes", first),
                PipelineStage("shots", second),
            ],
            storyboard_path=self.storyboard_path,
            schema_path=SCHEMA_PATH,
        )

        self.assertEqual(calls, ["keyframes", "shots"])
        self.assertEqual(results, {
            "keyframes": "reference-assets",
            "shots": "shot-assets",
        })

    def test_invalid_storyboard_prevents_every_stage_from_running(self) -> None:
        invalid_storyboard = copy.deepcopy(self.storyboard)
        invalid_storyboard["scenes"][0]["subtitle_en"] = ""
        self.storyboard_path.write_text(
            json.dumps(invalid_storyboard, ensure_ascii=False), encoding="utf-8"
        )
        stage_calls: list[bool] = []

        def should_not_run(storyboard, prior_outputs):
            stage_calls.append(True)

        with self.assertRaises(StoryboardValidationError):
            execute_pipeline(
                [PipelineStage("keyframes", should_not_run)],
                storyboard_path=self.storyboard_path,
                schema_path=SCHEMA_PATH,
            )

        self.assertEqual(stage_calls, [])

    def test_stage_failure_stops_later_stages(self) -> None:
        later_stage_calls: list[bool] = []

        def fail(storyboard, prior_outputs):
            raise RuntimeError("stage failed")

        def later_stage(storyboard, prior_outputs):
            later_stage_calls.append(True)

        with self.assertRaisesRegex(RuntimeError, "stage failed"):
            execute_pipeline(
                [
                    PipelineStage("keyframes", fail),
                    PipelineStage("shots", later_stage),
                ],
                storyboard_path=self.storyboard_path,
                schema_path=SCHEMA_PATH,
            )

        self.assertEqual(later_stage_calls, [])

    def test_rejects_empty_or_duplicate_stage_configuration(self) -> None:
        with self.assertRaises(ValueError):
            execute_pipeline(
                [],
                storyboard_path=self.storyboard_path,
                schema_path=SCHEMA_PATH,
            )

        stage = PipelineStage("keyframes", lambda storyboard, prior: None)
        with self.assertRaises(ValueError):
            execute_pipeline(
                [stage, stage],
                storyboard_path=self.storyboard_path,
                schema_path=SCHEMA_PATH,
            )


if __name__ == "__main__":
    unittest.main()
