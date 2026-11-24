"""Tests for the assembly CLI without running media tools."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.cli import main, resolve_shot_assets
from pipeline.media_preflight import MediaPreflightError


class TestAssemblyCli(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.storyboard = self.root / "storyboard.json"
        self.storyboard.write_text(
            json.dumps(
                {
                    "scenes": [
                        {"scene_number": 1},
                        {"scene_number": 2},
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.assets = self.root / "assets"
        (self.assets / "keyframes").mkdir(parents=True)
        (self.assets / "moving_shots").mkdir(parents=True)
        for scene_number in (1, 2):
            (
                self.assets
                / "keyframes"
                / "shot-{:02}.png".format(scene_number)
            ).write_bytes(b"fake still")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_asset_resolution_prefers_video_and_falls_back_to_still(self) -> None:
        video = self.assets / "moving_shots" / "shot-01.mp4"
        still_one = self.assets / "keyframes" / "shot-01.png"
        still_two = self.assets / "keyframes" / "shot-02.png"
        for path in (video, still_one, still_two):
            path.write_bytes(b"fake")

        result = resolve_shot_assets(self.storyboard, self.assets)

        self.assertEqual(result, {1: video, 2: still_two})

    def test_missing_scene_media_is_reported(self) -> None:
        for scene_number in (1, 2):
            (
                self.assets
                / "keyframes"
                / "shot-{:02}.png".format(scene_number)
            ).unlink()
        with self.assertRaisesRegex(MediaPreflightError, "No video or still"):
            resolve_shot_assets(self.storyboard, self.assets)

    def test_preflight_command_prints_plan_without_rendering(self) -> None:
        report = SimpleNamespace(
            ffmpeg_path=Path("ffmpeg.exe"),
            ffprobe_path=Path("ffprobe.exe"),
            shot_inputs=[1, 2],
            story_duration_seconds=75,
            total_duration_seconds=78,
            final_output_paths={"9:16": self.root / "vertical.mp4"},
            radio_cut_path=self.root / "radio.wav",
        )
        arguments = [
            "preflight",
            "--storyboard",
            str(self.storyboard),
            "--assets-dir",
            str(self.assets),
            "--font",
            str(self.root / "font.ttf"),
        ]
        with (
            patch("pipeline.cli.preflight_assembly", return_value=report) as preflight,
            patch("pipeline.cli.render_all_exports") as render,
        ):
            result = main(arguments)

        self.assertEqual(result, 0)
        preflight.assert_called_once()
        render.assert_not_called()

    def test_render_command_passes_preflight_plan_to_renderer(self) -> None:
        report = object()
        arguments = [
            "render",
            "--storyboard",
            str(self.storyboard),
            "--assets-dir",
            str(self.assets),
            "--font",
            str(self.root / "font.ttf"),
        ]
        with (
            patch("pipeline.cli.preflight_assembly", return_value=report),
            patch("pipeline.cli.render_all_exports", return_value=(self.root / "out.mp4",)) as render,
            patch("builtins.print"),
        ):
            result = main(arguments)

        self.assertEqual(result, 0)
        render.assert_called_once_with(report)


if __name__ == "__main__":
    unittest.main()
