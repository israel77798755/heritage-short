"""Tests for provider-neutral generation capability contracts."""

from __future__ import annotations

import unittest
from pathlib import Path

from pipeline.providers import (
    GenerationRequest,
    GenerationResult,
    ImageGenerationProvider,
    MusicGenerationProvider,
    NarrationGenerationProvider,
    TextGenerationProvider,
    VideoGenerationProvider,
)


class FakeImageProvider:
    def generate_image(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            provider="test",
            model="fake-image",
            output_path=request.output_path,
            seed=request.seed,
            parameters=request.parameters,
            latency_ms=12,
        )


class FakeMusicProvider:
    def generate_music(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            provider="test",
            model="fake-music",
            output_path=request.output_path,
            seed=request.seed,
            parameters=request.parameters,
            latency_ms=15,
        )


class TestProviderContracts(unittest.TestCase):
    def test_request_carries_references_seed_and_generation_parameters(self) -> None:
        request = GenerationRequest(
            prompt="A fictional mother and child at dawn",
            output_path=Path("outputs/keyframes/shot-01.png"),
            reference_paths=(Path("references/almaz.png"),),
            seed=23,
            parameters={"aspect_ratio": "9:16"},
        )
        provider = FakeImageProvider()

        self.assertIsInstance(provider, ImageGenerationProvider)
        result = provider.generate_image(request)

        self.assertEqual(result.output_path, request.output_path)
        self.assertEqual(result.seed, request.seed)
        self.assertEqual(result.parameters, request.parameters)
        self.assertIsNone(result.cost)
        self.assertIsNone(result.currency)

    def test_provider_is_not_assumed_to_support_other_media_types(self) -> None:
        provider = FakeMusicProvider()

        self.assertIsInstance(provider, MusicGenerationProvider)
        self.assertNotIsInstance(provider, ImageGenerationProvider)
        self.assertNotIsInstance(provider, VideoGenerationProvider)
        self.assertNotIsInstance(provider, NarrationGenerationProvider)
        self.assertNotIsInstance(provider, TextGenerationProvider)


if __name__ == "__main__":
    unittest.main()
