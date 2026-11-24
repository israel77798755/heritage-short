"""Tests for cache-aware generation with local fake provider operations."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Callable

from pipeline.cached_generation import (
    CachedGenerationResult,
    run_cached_generation_call,
)
from pipeline.providers import GenerationRequest, GenerationResult


class TestCachedGeneration(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.outputs_dir = self.root / "outputs"
        self.log_path = self.root / "runs.jsonl"
        self.reference = self.root / "character.png"
        self.reference.write_bytes(b"fictional character reference")
        self.request = GenerationRequest(
            prompt="A fictional scene",
            output_path=self.root / "shot.png",
            reference_paths=(self.reference,),
            seed=19,
            parameters={"aspect_ratio": "9:16", "guidance": 7},
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _read_log(self) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
        ]

    def _run(
        self,
        operation: Callable[[GenerationRequest], GenerationResult],
        request: GenerationRequest | None = None,
        shot_id: str = "shot-01",
    ) -> CachedGenerationResult:
        return run_cached_generation_call(
            operation,
            request or self.request,
            provider="fake-provider",
            model="fake-image-model",
            stage="keyframes",
            outputs_dir=self.outputs_dir,
            log_path=self.log_path,
            shot_id=shot_id,
            sleep=lambda _delay: None,
        )

    def test_cache_miss_writes_to_cache_and_logs_provider_call(self) -> None:
        received_paths: list[Path] = []

        def generate(request: GenerationRequest) -> GenerationResult:
            received_paths.append(request.output_path)
            request.output_path.write_bytes(b"generated image")
            return GenerationResult(
                provider="fake-provider",
                model="fake-image-model",
                output_path=request.output_path,
                seed=request.seed,
                cost=0.0,
                currency="USD",
                cost_basis="test fixture",
            )

        result = self._run(generate)

        self.assertFalse(result.cache_hit)
        self.assertTrue(result.result.output_path.is_file())
        self.assertEqual(received_paths[0].parent, result.result.output_path.parent)
        self.assertNotEqual(received_paths[0], result.result.output_path)
        self.assertFalse(received_paths[0].exists())
        self.assertEqual(len(self._read_log()), 1)

    def test_cache_hit_skips_provider_and_does_not_log_a_model_call(self) -> None:
        def generate(request: GenerationRequest) -> GenerationResult:
            request.output_path.write_bytes(b"generated image")
            return GenerationResult(
                provider="fake-provider",
                model="fake-image-model",
                output_path=request.output_path,
                seed=request.seed,
            )

        first = self._run(generate)
        second = self._run(
            lambda _request: self.fail("Provider should not run on a cache hit.")
        )

        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.cache_key, second.cache_key)
        self.assertEqual(first.result.output_path, second.result.output_path)
        self.assertEqual(len(self._read_log()), 1)

    def test_changed_reference_content_invalidates_the_cache(self) -> None:
        calls = 0

        def generate(request: GenerationRequest) -> GenerationResult:
            nonlocal calls
            calls += 1
            request.output_path.write_bytes(
                "generated image {}".format(calls).encode("ascii")
            )
            return GenerationResult(
                provider="fake-provider",
                model="fake-image-model",
                output_path=request.output_path,
                seed=request.seed,
            )

        first = self._run(generate)
        self.reference.write_bytes(b"updated fictional reference")
        second = self._run(generate)

        self.assertNotEqual(first.cache_key, second.cache_key)
        self.assertEqual(calls, 2)

    def test_shot_identifier_and_parameters_are_part_of_the_cache_key(self) -> None:
        def generate(request: GenerationRequest) -> GenerationResult:
            request.output_path.write_bytes(b"generated image")
            return GenerationResult(
                provider="fake-provider",
                model="fake-image-model",
                output_path=request.output_path,
                seed=request.seed,
            )

        first = self._run(generate)
        other_shot = self._run(generate, shot_id="shot-02")
        changed_request = GenerationRequest(
            prompt=self.request.prompt,
            output_path=self.request.output_path,
            reference_paths=self.request.reference_paths,
            seed=self.request.seed,
            parameters={"aspect_ratio": "9:16", "guidance": 8},
        )
        changed_parameters = self._run(generate, request=changed_request)

        self.assertEqual(
            len(
                {
                    first.cache_key,
                    other_shot.cache_key,
                    changed_parameters.cache_key,
                }
            ),
            3,
        )

    def test_empty_cache_entry_is_an_explicit_error(self) -> None:
        def generate(request: GenerationRequest) -> GenerationResult:
            request.output_path.write_bytes(b"image")
            return GenerationResult(
                provider="fake-provider",
                model="fake-image-model",
                output_path=request.output_path,
                seed=request.seed,
            )

        first = self._run(generate)
        first.result.output_path.write_bytes(b"")

        with self.assertRaisesRegex(OSError, "empty"):
            self._run(lambda _request: self.fail("Corrupt cache must not be used."))

    def test_failed_call_does_not_leave_a_cache_hit_behind(self) -> None:
        def partial_failure(request: GenerationRequest) -> GenerationResult:
            request.output_path.write_bytes(b"partial output")
            raise RuntimeError("provider failed")

        with self.assertRaisesRegex(RuntimeError, "provider failed"):
            self._run(partial_failure)
        self.assertEqual(list((self.outputs_dir / "cache" / "keyframes").iterdir()), [])

        def generate(request: GenerationRequest) -> GenerationResult:
            request.output_path.write_bytes(b"complete output")
            return GenerationResult(
                provider="fake-provider",
                model="fake-image-model",
                output_path=request.output_path,
                seed=request.seed,
            )

        result = self._run(generate)

        self.assertFalse(result.cache_hit)
        self.assertEqual(len(self._read_log()), 2)

    def test_output_path_must_have_a_file_extension(self) -> None:
        request = GenerationRequest(
            prompt=self.request.prompt,
            output_path=self.root / "shot",
            seed=self.request.seed,
        )

        with self.assertRaisesRegex(ValueError, "file extension"):
            self._run(lambda _request: self.fail("Invalid request must not run."), request)


if __name__ == "__main__":
    unittest.main()
