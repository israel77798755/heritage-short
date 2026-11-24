"""Tests for deterministic content-based asset cache helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline.cache import build_cache_key, cache_output_path, find_cached_asset


class TestAssetCache(unittest.TestCase):
    def test_same_inputs_and_references_produce_the_same_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            reference = Path(temporary_directory) / "character.png"
            reference.write_bytes(b"reference-image")

            first = build_cache_key(
                "keyframes",
                {"shot": 1, "prompt": "warm light", "seed": 12},
                {"character": reference},
            )
            second = build_cache_key(
                "keyframes",
                {"seed": 12, "prompt": "warm light", "shot": 1},
                {"character": reference},
            )

        self.assertEqual(first, second)

    def test_changed_generation_input_changes_the_key(self) -> None:
        first = build_cache_key("shots", {"shot": 3, "motion": "slow push-in"})
        second = build_cache_key("shots", {"shot": 3, "motion": "static camera"})

        self.assertNotEqual(first, second)

    def test_changed_reference_contents_change_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            reference = Path(temporary_directory) / "character.png"
            reference.write_bytes(b"first-reference")
            first = build_cache_key("keyframes", {"shot": 1}, {"character": reference})

            reference.write_bytes(b"updated-reference")
            second = build_cache_key("keyframes", {"shot": 1}, {"character": reference})

        self.assertNotEqual(first, second)

    def test_missing_reference_is_an_explicit_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = Path(temporary_directory) / "missing.png"
            with self.assertRaises(FileNotFoundError):
                build_cache_key("keyframes", {}, {"character": missing})

    def test_output_path_and_cache_hit(self) -> None:
        key = build_cache_key("keyframes", {"shot": 1})
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = cache_output_path(
                Path(temporary_directory), "keyframes", key, ".png"
            )
            self.assertIsNone(find_cached_asset(output_path))

            output_path.parent.mkdir(parents=True)
            output_path.write_bytes(b"generated-image")
            self.assertEqual(find_cached_asset(output_path), output_path)

    def test_empty_cached_file_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            empty_file = Path(temporary_directory) / "empty.png"
            empty_file.touch()
            with self.assertRaisesRegex(OSError, "empty"):
                find_cached_asset(empty_file)

    def test_rejects_unsafe_stage_and_extension(self) -> None:
        with self.assertRaises(ValueError):
            build_cache_key("../outside", {})

        key = build_cache_key("keyframes", {})
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(ValueError):
                cache_output_path(Path(temporary_directory), "keyframes", key, "../file")


if __name__ == "__main__":
    unittest.main()
