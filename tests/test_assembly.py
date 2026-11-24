"""Tests for FFmpeg command preparation using temporary, fake media files."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.assembly import (
    AssemblyError,
    AssemblyOutputExistsError,
    build_export_commands,
    build_radio_cut_command,
    build_shot_command,
    render_all_exports,
    run_media_command,
    validate_final_export,
)
from pipeline.media_preflight import (
    ASPECT_RATIOS,
    AssemblyPreflight,
    MediaInfo,
    MediaPreflightError,
    ShotInput,
)


class TestAssembly(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.ffmpeg = self.root / "ffmpeg.exe"
        self.ffprobe = self.root / "ffprobe.exe"
        self.ffmpeg.write_bytes(b"fake")
        self.ffprobe.write_bytes(b"fake")
        self.narration = self.root / "narration.wav"
        self.music = self.root / "music.wav"
        self.subtitles = self.root / "subtitles.srt"
        self.font = self.root / "licensed.ttf"
        for path in (self.narration, self.music, self.subtitles, self.font):
            path.write_bytes(b"fake")

        self.segment_directories = {}
        self.final_paths = {}
        for ratio, (width, height) in ASPECT_RATIOS.items():
            ratio_name = ratio.replace(":", "x")
            segment_dir = self.root / "outputs" / "segments" / ratio_name
            final_path = (
                self.root
                / "outputs"
                / "final"
                / ratio_name
                / "wisdom-of-our-mothers-{}x{}.mp4".format(width, height)
            )
            segment_dir.mkdir(parents=True)
            final_path.parent.mkdir(parents=True)
            self.segment_directories[ratio] = segment_dir
            self.final_paths[ratio] = final_path

        self.shots = []
        for scene_number in range(1, 11):
            is_still = scene_number != 2
            asset = self.root / (
                "shot-{:02}.{}".format(scene_number, "png" if is_still else "mp4")
            )
            asset.write_bytes(b"fake media")
            self.shots.append(
                ShotInput(
                    scene_number=scene_number,
                    duration_seconds=7 if scene_number in (1, 3, 5, 7, 10) else 8,
                    path=asset,
                    is_still=is_still,
                )
            )

        self.plan = AssemblyPreflight(
            ffmpeg_path=self.ffmpeg,
            ffprobe_path=self.ffprobe,
            shot_inputs=tuple(self.shots),
            narration_path=self.narration,
            music_path=self.music,
            subtitle_path=self.subtitles,
            font_path=self.font,
            output_directories=self.segment_directories,
            final_output_paths=self.final_paths,
            radio_cut_path=self.root / "outputs" / "final" / "radio" / "radio.wav",
            end_card_text="English title\nAmharic title\n\nEnglish disclosure\nAmharic disclosure",
            story_duration_seconds=75,
            total_duration_seconds=78,
        )
        self.plan.radio_cut_path.parent.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_still_shot_uses_pan_zoom_and_video_shot_is_normalized(self) -> None:
        still_command, still_output = build_shot_command(self.plan, 1, "9:16")
        video_command, video_output = build_shot_command(self.plan, 2, "16:9")

        self.assertIn("-loop", still_command)
        self.assertIn("zoompan=", " ".join(still_command))
        self.assertIn("1080x1920", " ".join(still_command))
        self.assertNotIn("zoompan=", " ".join(video_command))
        self.assertIn("tpad=stop_mode=clone", " ".join(video_command))
        self.assertIn("1920:1080", " ".join(video_command))
        self.assertEqual(still_output.suffix, ".mp4")
        self.assertEqual(video_output.suffix, ".mp4")

    def test_final_command_includes_audio_mix_normalization_and_subtitles(self) -> None:
        commands = build_export_commands(self.plan, "9:16")
        final_command = " ".join(commands.final_command)

        self.assertEqual(len(commands.segment_commands), 10)
        self.assertIn("sidechaincompress", final_command)
        self.assertIn("loudnorm=I=-14:TP=-1:LRA=11", final_command)
        self.assertIn("drawtext=", final_command)
        self.assertIn("mov_text", final_command)
        self.assertIn("-map 4:0", final_command)
        self.assertIn("1080x1920", final_command)
        self.assertIn("78.000", final_command)

    def test_radio_cut_contains_only_narration_and_is_normalized(self) -> None:
        command = build_radio_cut_command(self.plan)

        self.assertIn(str(self.narration), command)
        self.assertNotIn(str(self.music), command)
        self.assertIn("loudnorm=I=-16:TP=-1:LRA=11", " ".join(command))
        self.assertIn(str(self.plan.radio_cut_path), command)

    def test_concat_manifest_requires_nonempty_segments_and_never_overwrites(self) -> None:
        from pipeline.assembly import write_concat_manifest

        segment = self.root / "clip's.mp4"
        segment.write_bytes(b"fake video")
        manifest = self.root / "segments.ffconcat"
        write_concat_manifest((segment,), manifest)
        text = manifest.read_text(encoding="utf-8")
        self.assertIn("ffconcat version 1.0", text)
        self.assertIn("'\\''", text)

        with self.assertRaises(AssemblyOutputExistsError):
            write_concat_manifest((segment,), manifest)
        with self.assertRaises(MediaPreflightError):
            write_concat_manifest((self.root / "missing.mp4",), self.root / "missing.ffconcat")

    def test_render_runs_radio_cut_and_both_formats_without_real_ffmpeg(self) -> None:
        def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            output = Path(command[-1])
            output.write_bytes(b"fake rendered media")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        def fake_probe(path: Path, _ffprobe_path: Path) -> MediaInfo:
            if path == self.plan.radio_cut_path:
                return MediaInfo(75.0, False, True, False, None, None)
            ratio = "9:16" if "1080x1920" in path.name else "16:9"
            width, height = ASPECT_RATIOS[ratio]
            return MediaInfo(78.0, True, True, True, width, height)

        with (
            patch("pipeline.assembly.subprocess.run", side_effect=fake_run) as run,
            patch("pipeline.assembly.probe_media", side_effect=fake_probe),
        ):
            outputs = render_all_exports(self.plan)

        self.assertEqual(
            outputs,
            (
                self.plan.radio_cut_path,
                self.final_paths["9:16"],
                self.final_paths["16:9"],
            ),
        )
        self.assertTrue(all(path.is_file() for path in outputs))
        self.assertEqual(run.call_count, 23)

    def test_existing_final_output_stops_before_running_commands(self) -> None:
        self.final_paths["9:16"].write_bytes(b"preserve existing file")

        with patch("pipeline.assembly.run_media_command") as run:
            with self.assertRaises(AssemblyOutputExistsError):
                render_all_exports(self.plan)
        run.assert_not_called()
        self.assertEqual(
            self.final_paths["9:16"].read_bytes(), b"preserve existing file"
        )

    def test_media_command_failure_is_reported(self) -> None:
        completed = subprocess.CompletedProcess(
            ["ffmpeg"], 1, stdout="", stderr="simulated encode failure"
        )
        with patch("pipeline.assembly.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(AssemblyError, "simulated encode failure"):
                run_media_command(("ffmpeg", "-version"))

    def test_export_validation_rejects_wrong_dimensions(self) -> None:
        wrong_size = MediaInfo(78.0, True, True, True, 1280, 720)
        with patch("pipeline.assembly.probe_media", return_value=wrong_size):
            with self.assertRaisesRegex(AssemblyError, "incorrect video dimensions"):
                validate_final_export(
                    self.final_paths["9:16"],
                    self.ffprobe,
                    "9:16",
                    78,
                )


if __name__ == "__main__":
    unittest.main()
