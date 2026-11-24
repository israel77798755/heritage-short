"""Tests for logged provider execution using local fake operations."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.provider_runner import run_generation_call
from pipeline.providers import (
    GenerationRequest,
    GenerationResult,
    ProviderRateLimitError,
)


class TestProviderRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.output_path = self.root / "generated.png"
        self.log_path = self.root / "runs.jsonl"
        self.request = GenerationRequest(
            prompt="A fictional scene",
            output_path=self.output_path,
            seed=19,
            parameters={"aspect_ratio": "9:16"},
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _read_log(self) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
        ]

    def test_success_writes_output_and_logs_safe_metadata(self) -> None:
        def generate(request: GenerationRequest) -> GenerationResult:
            request.output_path.write_bytes(b"image")
            return GenerationResult(
                provider="fake-provider",
                model="fake-image-model",
                output_path=request.output_path,
                seed=request.seed,
                cost=0.0,
                currency="USD",
                cost_basis="test fixture",
            )

        result = run_generation_call(
            generate,
            self.request,
            provider="fake-provider",
            model="fake-image-model",
            stage="keyframes",
            shot_id="shot-01",
            log_path=self.log_path,
        )

        self.assertEqual(result.output_path, self.output_path)
        record = self._read_log()[0]
        self.assertEqual(record["status"], "succeeded")
        self.assertEqual(record["attempt"], 1)
        self.assertEqual(record["seed"], 19)
        self.assertEqual(record["cost"], 0.0)
        parameters = record["parameters"]
        self.assertIsInstance(parameters, dict)
        self.assertIn("prompt_sha256", parameters)
        self.assertNotIn("A fictional scene", self.log_path.read_text(encoding="utf-8"))

    def test_transient_failure_is_logged_for_each_attempt(self) -> None:
        calls = 0

        def generate(request: GenerationRequest) -> GenerationResult:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ProviderRateLimitError("temporary quota response")
            request.output_path.write_bytes(b"image")
            return GenerationResult(
                provider="fake-provider",
                model="fake-image-model",
                output_path=request.output_path,
                seed=request.seed,
            )

        run_generation_call(
            generate,
            self.request,
            provider="fake-provider",
            model="fake-image-model",
            stage="keyframes",
            log_path=self.log_path,
            max_attempts=2,
            sleep=lambda _delay: None,
        )

        records = self._read_log()
        self.assertEqual([record["status"] for record in records], ["rate_limited", "succeeded"])
        self.assertEqual([record["attempt"] for record in records], [1, 2])
        self.assertEqual(records[0]["run_id"], records[1]["run_id"])

    def test_missing_output_is_logged_as_failure(self) -> None:
        def generate(request: GenerationRequest) -> GenerationResult:
            return GenerationResult(
                provider="fake-provider",
                model="fake-image-model",
                output_path=request.output_path,
                seed=request.seed,
            )

        with self.assertRaises(FileNotFoundError):
            run_generation_call(
                generate,
                self.request,
                provider="fake-provider",
                model="fake-image-model",
                stage="keyframes",
                log_path=self.log_path,
            )

        record = self._read_log()[0]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["error_type"], "FileNotFoundError")


if __name__ == "__main__":
    unittest.main()
