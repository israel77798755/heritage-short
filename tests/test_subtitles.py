"""Tests for draft English subtitle generation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.subtitles import (
    build_english_srt,
    format_srt_timestamp,
    write_english_srt,
)
from validate_storyboard import SCHEMA_PATH, STORYBOARD_PATH, StoryboardValidationError


class TestSubtitleGeneration(unittest.TestCase):
    def setUp(self) -> None:
        self.storyboard = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))

    def test_formats_srt_timestamps(self) -> None:
        self.assertEqual(format_srt_timestamp(0), "00:00:00,000")
        self.assertEqual(format_srt_timestamp(75_123), "00:01:15,123")
        self.assertEqual(format_srt_timestamp(3_600_000), "01:00:00,000")

    def test_rejects_negative_or_non_integer_timestamps(self) -> None:
        with self.assertRaises(ValueError):
            format_srt_timestamp(-1)
        with self.assertRaises(TypeError):
            format_srt_timestamp(1.5)

    def test_builds_one_ordered_cue_per_shot(self) -> None:
        srt = build_english_srt(self.storyboard)
        cues = srt.strip().split("\n\n")

        self.assertEqual(len(cues), 10)
        self.assertTrue(cues[0].startswith("1\n00:00:00,000 --> 00:00:07,000"))
        self.assertIn("Before sunrise", cues[0])
        self.assertTrue(cues[-1].startswith("10\n00:01:08,000 --> 00:01:15,000"))

    def test_validates_before_writing_subtitles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            storyboard_path = root / "storyboard.json"
            output_path = root / "subtitles" / "en.srt"
            invalid = json.loads(json.dumps(self.storyboard))
            invalid["scenes"][0]["subtitle_en"] = ""
            storyboard_path.write_text(
                json.dumps(invalid, ensure_ascii=False), encoding="utf-8"
            )

            with self.assertRaises(StoryboardValidationError):
                write_english_srt(
                    output_path,
                    storyboard_path=storyboard_path,
                    schema_path=SCHEMA_PATH,
                )

            self.assertFalse(output_path.exists())

    def test_writes_validated_srt_to_requested_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "subtitles" / "en.srt"
            result = write_english_srt(output_path)

            self.assertEqual(result, output_path)
            self.assertIn("00:01:15,000", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
