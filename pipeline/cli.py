"""Command-line entry point for assembly preflight and FFmpeg exports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from pipeline.assembly import AssemblyError, render_all_exports
from pipeline.config import OUTPUTS_DIR, SCHEMA_PATH, STORYBOARD_PATH
from pipeline.media_preflight import AssemblyPreflight, MediaPreflightError, preflight_assembly


_ASSETS_DIR = OUTPUTS_DIR / "assets"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate assembly inputs or render the prepared film exports."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command_name in ("preflight", "render"):
        command = commands.add_parser(
            command_name,
            help=(
                "check tools and assets without rendering"
                if command_name == "preflight"
                else "render the radio cut and both aspect ratios"
            ),
        )
        command.add_argument("--storyboard", type=Path, default=STORYBOARD_PATH)
        command.add_argument("--schema", type=Path, default=SCHEMA_PATH)
        command.add_argument("--assets-dir", type=Path, default=_ASSETS_DIR)
        command.add_argument(
            "--narration",
            type=Path,
            default=OUTPUTS_DIR / "audio" / "narration.wav",
        )
        command.add_argument(
            "--music",
            type=Path,
            default=OUTPUTS_DIR / "audio" / "music.wav",
        )
        command.add_argument(
            "--subtitles",
            type=Path,
            default=OUTPUTS_DIR / "subtitles" / "en.srt",
        )
        command.add_argument("--font", type=Path, required=True)
        command.add_argument(
            "--output-dir",
            type=Path,
            default=OUTPUTS_DIR / "production",
        )
        command.add_argument("--ffmpeg", type=Path)
        command.add_argument("--ffprobe", type=Path)
    return parser


def resolve_shot_assets(
    storyboard_path: Path,
    assets_dir: Path,
) -> dict[int, Path]:
    """Prefer a generated clip, otherwise use its still-image fallback."""
    storyboard_file = Path(storyboard_path)
    try:
        with storyboard_file.open("r", encoding="utf-8") as file:
            storyboard = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise MediaPreflightError(
            "Could not read storyboard {}: {}".format(storyboard_file, error)
        ) from error
    scenes = storyboard.get("scenes") if isinstance(storyboard, dict) else None
    if not isinstance(scenes, list) or not scenes:
        raise MediaPreflightError("Storyboard has no scene list.")

    root = Path(assets_dir)
    videos_dir = root / "moving_shots"
    stills_dir = root / "keyframes"
    result: dict[int, Path] = {}
    for scene in scenes:
        if not isinstance(scene, dict):
            raise MediaPreflightError("Storyboard scenes must be objects.")
        number = scene.get("scene_number")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise MediaPreflightError(
                "Storyboard scene numbers must be positive whole numbers."
            )
        video_path = videos_dir / "shot-{:02}.mp4".format(number)
        still_path = stills_dir / "shot-{:02}.png".format(number)
        if video_path.is_file():
            result[number] = video_path
        elif still_path.is_file():
            result[number] = still_path
        else:
            raise MediaPreflightError(
                "No video or still found for scene {}. Expected {} or {}."
                .format(number, video_path, still_path)
            )
    return result


def _preflight_from_args(args: argparse.Namespace) -> AssemblyPreflight:
    shot_assets = resolve_shot_assets(args.storyboard, args.assets_dir)
    return preflight_assembly(
        storyboard_path=args.storyboard,
        schema_path=args.schema,
        shot_assets=shot_assets,
        narration_path=args.narration,
        music_path=args.music,
        subtitle_path=args.subtitles,
        font_path=args.font,
        output_dir=args.output_dir,
        ffmpeg_path=args.ffmpeg,
        ffprobe_path=args.ffprobe,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run an explicit preflight or render command; never calls AI providers."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        plan = _preflight_from_args(args)
        if args.command == "preflight":
            print("Assembly inputs and output directories are ready.")
            print("FFmpeg: {}".format(plan.ffmpeg_path))
            print("ffprobe: {}".format(plan.ffprobe_path))
            print(
                "Shots: {}; story: {}s; total: {}s.".format(
                    len(plan.shot_inputs),
                    plan.story_duration_seconds,
                    plan.total_duration_seconds,
                )
            )
            for ratio, path in plan.final_output_paths.items():
                print("{} output: {}".format(ratio, path))
            print("Radio cut: {}".format(plan.radio_cut_path))
            return 0

        outputs = render_all_exports(plan)
        for path in outputs:
            print("Created: {}".format(path))
        return 0
    except (AssemblyError, MediaPreflightError, OSError) as error:
        print("Assembly {} failed: {}".format(args.command, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
