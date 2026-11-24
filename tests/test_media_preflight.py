"""Tests for assembly preflight without requiring FFmpeg or media assets."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.media_preflight import (
    ASPECT_RATIOS,
    MediaPreflightError,
    MediaToolUnavailableError,
    preflight_assembly,
    resolve_media_tool,
    validate_srt,
)
from pipeline.subtitles import build_english_srt
from pipeline.config import SCHEMA_PATH, STORYBOARD_PATH


class TestMediaPreflight(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.ffmpeg = self.root / "ffmpeg.exe"
        self.ffprobe = self.root / "ffprobe.exe"
        self.ffmpeg.write_bytes(b"fake executable")
        self.ffprobe.write_bytes(b"fake executable")

        with STORYBOARD_PATH.open("r", encoding="utf-8") as file:
            storyboard = json.load(file)
        self.shots: dict[int, Path] = {}
        for scene in storyboard["scenes"]:
            number = scene["scene_number"]
            shot = self.root / "shot-{:02}.png".format(number)
            shot.write_bytes(b"fake image")
            self.shots[number] = shot

        self.narration = self.root / "narration.wav"
        self.music = self.root / "music.wav"
        self.narration.write_bytes(b"fake audio")
        self.music.write_bytes(b"fake audio")
        self.subtitles = self.root / "subtitles.srt"
        self.subtitles.write_text(
            build_english_srt(storyboard), encoding="utf-8", newline="\n"
        )
        self.font = self.root / "licensed-font.ttf"
        self.font.write_bytes(b"font placeholder")
        self.output_dir = self.root / "outputs"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_resolves_explicit_tool_path(self) -> None:
        self.assertEqual(
            resolve_media_tool("ffmpeg", self.ffmpeg),
            self.ffmpeg.resolve(),
        )

    def test_missing_tool_has_actionable_error(self) -> None:
        with self.assertRaises(MediaToolUnavailableError):
            resolve_media_tool("ffmpeg", search_path="")

    def test_valid_srt_is_accepted_and_malformed_srt_is_rejected(self) -> None:
        self.assertEqual(validate_srt(self.subtitles), 75_000)
        invalid = self.root / "invalid.srt"
        invalid.write_text("1\n00:00:02,000 --> 00:00:01,000\nBad cue\n", encoding="utf-8")

        with self.assertRaises(MediaPreflightError):
            validate_srt(invalid)

    def test_subtitles_may_not_overlap_the_end_card(self) -> None:
        late_subtitles = self.root / "late-subtitles.srt"
        late_subtitles.write_text(
            "1\n00:01:14,000 --> 00:01:16,000\nLate cue\n",
            encoding="utf-8",
        )

        def fake_probe(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            asset = Path(command[-1])
            if asset.suffix == ".png":
                streams = [{"codec_type": "video", "width": 1024, "height": 1024}]
                duration = None
            else:
                streams = [{"codec_type": "audio"}]
                duration = "75.0"
            output = {"streams": streams, "format": {"duration": duration}}
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps(output), stderr=""
            )

        with patch("pipeline.media_preflight.subprocess.run", side_effect=fake_probe):
            with self.assertRaisesRegex(MediaPreflightError, "past the story"):
                preflight_assembly(
                    storyboard_path=STORYBOARD_PATH,
                    schema_path=SCHEMA_PATH,
                    shot_assets=self.shots,
                    narration_path=self.narration,
                    music_path=self.music,
                    subtitle_path=late_subtitles,
                    font_path=self.font,
                    output_dir=self.output_dir,
                    ffmpeg_path=self.ffmpeg,
                    ffprobe_path=self.ffprobe,
                )

    def test_preflight_validates_inputs_and_prepares_both_ratios(self) -> None:
        def fake_probe(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            asset = Path(command[-1])
            if asset.suffix == ".png":
                streams = [{"codec_type": "video", "width": 1024, "height": 1024}]
                duration = None
            else:
                streams = [{"codec_type": "audio"}]
                duration = "75.0"
            output = {"streams": streams, "format": {"duration": duration}}
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps(output), stderr=""
            )

        with patch("pipeline.media_preflight.subprocess.run", side_effect=fake_probe):
            plan = preflight_assembly(
                storyboard_path=STORYBOARD_PATH,
                schema_path=SCHEMA_PATH,
                shot_assets=self.shots,
                narration_path=self.narration,
                music_path=self.music,
                subtitle_path=self.subtitles,
                font_path=self.font,
                output_dir=self.output_dir,
                ffmpeg_path=self.ffmpeg,
                ffprobe_path=self.ffprobe,
            )

        self.assertEqual(len(plan.shot_inputs), 10)
        self.assertTrue(all(shot.is_still for shot in plan.shot_inputs))
        self.assertEqual(plan.story_duration_seconds, 75)
        self.assertEqual(plan.total_duration_seconds, 78)
        self.assertEqual(set(plan.final_output_paths), set(ASPECT_RATIOS))
        for output_directory in (
            *plan.output_directories.values(),
            *(path.parent for path in plan.final_output_paths.values()),
        ):
            self.assertTrue(output_directory.is_dir())

    def test_missing_shot_asset_fails_before_probing_media(self) -> None:
        incomplete = dict(self.shots)
        incomplete.pop(10)

        with patch("pipeline.media_preflight.subprocess.run") as run:
            with self.assertRaises(MediaPreflightError):
                preflight_assembly(
                    storyboard_path=STORYBOARD_PATH,
                    schema_path=SCHEMA_PATH,
                    shot_assets=incomplete,
                    narration_path=self.narration,
                    music_path=self.music,
                    subtitle_path=self.subtitles,
                    font_path=self.font,
                    output_dir=self.output_dir,
                    ffmpeg_path=self.ffmpeg,
                    ffprobe_path=self.ffprobe,
                )
        run.assert_not_called()

    def test_audio_asset_without_audio_stream_is_rejected(self) -> None:
        def fake_probe(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            asset = Path(command[-1])
            if asset.suffix == ".png":
                streams = [{"codec_type": "video", "width": 1024, "height": 1024}]
                duration = None
            else:
                streams = [{"codec_type": "video", "width": 10, "height": 10}]
                duration = "10.0"
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": streams, "format": {"duration": duration}}),
                stderr="",
            )

        with patch("pipeline.media_preflight.subprocess.run", side_effect=fake_probe):
            with self.assertRaisesRegex(MediaPreflightError, "audio stream"):
                preflight_assembly(
                    storyboard_path=STORYBOARD_PATH,
                    schema_path=SCHEMA_PATH,
                    shot_assets=self.shots,
                    narration_path=self.narration,
                    music_path=self.music,
                    subtitle_path=self.subtitles,
                    font_path=self.font,
                    output_dir=self.output_dir,
                    ffmpeg_path=self.ffmpeg,
                    ffprobe_path=self.ffprobe,
                )


if __name__ == "__main__":
    unittest.main()
