"""Validate media inputs and local tools before film assembly."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from validate_storyboard import require_valid_storyboard


ASPECT_RATIOS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
_SRT_TIMESTAMP = re.compile(
    r"^(\d{2}):([0-5]\d):([0-5]\d),(\d{3}) --> "
    r"(\d{2}):([0-5]\d):([0-5]\d),(\d{3})$"
)


class MediaPreflightError(RuntimeError):
    """Raised when inputs or tools are not ready for assembly."""


class MediaToolUnavailableError(MediaPreflightError):
    """Raised when FFmpeg or ffprobe cannot be found."""


@dataclass(frozen=True)
class ShotInput:
    scene_number: int
    duration_seconds: int
    path: Path
    is_still: bool


@dataclass(frozen=True)
class MediaInfo:
    duration_seconds: float | None
    has_video: bool
    has_audio: bool
    width: int | None
    height: int | None


@dataclass(frozen=True)
class AssemblyPreflight:
    ffmpeg_path: Path
    ffprobe_path: Path
    shot_inputs: tuple[ShotInput, ...]
    narration_path: Path
    music_path: Path
    subtitle_path: Path
    font_path: Path
    output_directories: Mapping[str, Path]
    final_output_paths: Mapping[str, Path]
    story_duration_seconds: int
    total_duration_seconds: int


def resolve_media_tool(
    name: str,
    explicit_path: Path | None = None,
    *,
    search_path: str | None = None,
) -> Path:
    """Resolve an executable path or raise a clear, actionable error."""
    if name not in ("ffmpeg", "ffprobe"):
        raise ValueError("Only ffmpeg and ffprobe are supported media tools.")
    if explicit_path is not None:
        candidate = Path(explicit_path).expanduser()
        if not candidate.is_file():
            raise MediaToolUnavailableError(
                "{} was not found at the configured path: {}".format(name, candidate)
            )
        return candidate.resolve()

    located = shutil.which(name, path=search_path)
    if located is None:
        raise MediaToolUnavailableError(
            "{} is not available on PATH. Install it or pass its executable path."
            .format(name)
        )
    return Path(located).resolve()


def probe_media(path: Path, ffprobe_path: Path) -> MediaInfo:
    """Read stream types, dimensions, and duration using ffprobe JSON output."""
    source = _require_nonempty_file(path, "media input")
    command = [
        str(ffprobe_path),
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height",
        "-of",
        "json",
        str(source),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaPreflightError(
            "Could not run ffprobe on {}: {}".format(source, error)
        ) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "ffprobe returned a non-zero exit code"
        raise MediaPreflightError(
            "ffprobe could not inspect {}: {}".format(source, detail)
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise MediaPreflightError(
            "ffprobe returned invalid JSON for {}.".format(source)
        ) from error
    if not isinstance(result, dict):
        raise MediaPreflightError(
            "ffprobe returned an unexpected result for {}.".format(source)
        )

    streams = result.get("streams")
    if not isinstance(streams, list):
        raise MediaPreflightError(
            "ffprobe did not report streams for {}.".format(source)
        )
    video_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "video"
    ]
    has_audio = any(
        isinstance(stream, dict) and stream.get("codec_type") == "audio"
        for stream in streams
    )
    format_data = result.get("format")
    duration_value = (
        format_data.get("duration") if isinstance(format_data, dict) else None
    )
    duration = _positive_float(duration_value)
    width = _positive_integer(video_streams[0].get("width")) if video_streams else None
    height = (
        _positive_integer(video_streams[0].get("height")) if video_streams else None
    )
    return MediaInfo(
        duration_seconds=duration,
        has_video=bool(video_streams),
        has_audio=has_audio,
        width=width,
        height=height,
    )


def validate_srt(path: Path) -> None:
    """Reject empty, malformed, or non-monotonic SRT cue files."""
    subtitle_path = _require_nonempty_file(path, "subtitle file")
    text = subtitle_path.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise MediaPreflightError("Subtitle file is empty: {}".format(subtitle_path))
    cues = re.split(r"\r?\n\s*\r?\n", text)
    previous_end_ms = -1
    for expected_index, cue in enumerate(cues, start=1):
        lines = cue.splitlines()
        if len(lines) < 3 or lines[0].strip() != str(expected_index):
            raise MediaPreflightError(
                "Subtitle cue {} has an invalid sequence number or is incomplete."
                .format(expected_index)
            )
        match = _SRT_TIMESTAMP.fullmatch(lines[1].strip())
        if match is None:
            raise MediaPreflightError(
                "Subtitle cue {} has an invalid timestamp.".format(expected_index)
            )
        values = [int(value) for value in match.groups()]
        start_ms = _timestamp_milliseconds(values[:4])
        end_ms = _timestamp_milliseconds(values[4:])
        if start_ms < previous_end_ms or end_ms <= start_ms:
            raise MediaPreflightError(
                "Subtitle cue {} overlaps or has a non-positive duration."
                .format(expected_index)
            )
        if not any(line.strip() for line in lines[2:]):
            raise MediaPreflightError(
                "Subtitle cue {} has no text.".format(expected_index)
            )
        previous_end_ms = end_ms


def preflight_assembly(
    *,
    storyboard_path: Path,
    schema_path: Path,
    shot_assets: Mapping[int, Path],
    narration_path: Path,
    music_path: Path,
    subtitle_path: Path,
    font_path: Path,
    output_dir: Path,
    ffmpeg_path: Path | None = None,
    ffprobe_path: Path | None = None,
) -> AssemblyPreflight:
    """Validate all inputs and create writable per-ratio output directories."""
    storyboard = require_valid_storyboard(
        storyboard_path=Path(storyboard_path),
        schema_path=Path(schema_path),
    )
    resolved_ffmpeg = resolve_media_tool("ffmpeg", ffmpeg_path)
    resolved_ffprobe = resolve_media_tool("ffprobe", ffprobe_path)

    scenes = storyboard["scenes"]
    expected_numbers = {scene["scene_number"] for scene in scenes}
    if not isinstance(shot_assets, Mapping):
        raise TypeError("shot_assets must map scene numbers to asset paths.")
    for scene_number in shot_assets:
        if isinstance(scene_number, bool) or not isinstance(scene_number, int):
            raise TypeError("Shot asset keys must be whole scene numbers.")
    actual_numbers = set(shot_assets)
    if actual_numbers != expected_numbers:
        missing = sorted(expected_numbers - actual_numbers)
        unexpected = sorted(actual_numbers - expected_numbers)
        raise MediaPreflightError(
            "Shot assets must match the storyboard exactly; missing={}, unexpected={}"
            .format(missing, unexpected)
        )

    shot_inputs = []
    for scene in scenes:
        scene_number = scene["scene_number"]
        path = _require_nonempty_file(
            shot_assets[scene_number], "shot {}".format(scene_number)
        )
        suffix = path.suffix.lower()
        if suffix not in _IMAGE_EXTENSIONS | _VIDEO_EXTENSIONS:
            raise MediaPreflightError(
                "Unsupported shot asset type for {}: {}".format(path, suffix)
            )
        info = probe_media(path, resolved_ffprobe)
        if not info.has_video or not info.width or not info.height:
            raise MediaPreflightError(
                "Shot asset must contain a video stream with valid dimensions: {}"
                .format(path)
            )
        is_still = suffix in _IMAGE_EXTENSIONS
        if not is_still and (info.duration_seconds is None or info.duration_seconds <= 0):
            raise MediaPreflightError(
                "Shot video must have a positive duration: {}".format(path)
            )
        shot_inputs.append(
            ShotInput(
                scene_number=scene_number,
                duration_seconds=scene["duration_seconds"],
                path=path,
                is_still=is_still,
            )
        )

    _require_audio(narration_path, resolved_ffprobe, "narration")
    _require_audio(music_path, resolved_ffprobe, "music")
    validate_srt(Path(subtitle_path))

    font = _require_nonempty_file(font_path, "subtitle and end-card font")
    if font.suffix.lower() not in _FONT_EXTENSIONS:
        raise MediaPreflightError(
            "Font must be a .ttf, .otf, or .ttc file: {}".format(font)
        )

    output_root = Path(output_dir)
    output_directories: dict[str, Path] = {}
    final_output_paths: dict[str, Path] = {}
    for ratio, (width, height) in ASPECT_RATIOS.items():
        ratio_name = "{}x{}".format(ratio.split(":")[0], ratio.split(":")[1])
        segment_dir = output_root / "segments" / ratio_name
        final_dir = output_root / "final" / ratio_name
        _ensure_writable_directory(segment_dir)
        _ensure_writable_directory(final_dir)
        output_directories[ratio] = segment_dir
        final_output_paths[ratio] = final_dir / (
            "wisdom-of-our-mothers-{}x{}.mp4".format(width, height)
        )

    story_duration = storyboard["target_duration_seconds"]
    total_duration = story_duration + storyboard["end_card"]["duration_seconds"]
    return AssemblyPreflight(
        ffmpeg_path=resolved_ffmpeg,
        ffprobe_path=resolved_ffprobe,
        shot_inputs=tuple(shot_inputs),
        narration_path=Path(narration_path).resolve(),
        music_path=Path(music_path).resolve(),
        subtitle_path=Path(subtitle_path).resolve(),
        font_path=font,
        output_directories=output_directories,
        final_output_paths=final_output_paths,
        story_duration_seconds=story_duration,
        total_duration_seconds=total_duration,
    )


def _require_audio(path: Path, ffprobe_path: Path, label: str) -> MediaInfo:
    source = _require_nonempty_file(path, label)
    info = probe_media(source, ffprobe_path)
    if not info.has_audio or info.duration_seconds is None:
        raise MediaPreflightError(
            "{} must contain an audio stream with a known duration: {}"
            .format(label.capitalize(), source)
        )
    return info


def _require_nonempty_file(path: Path, label: str) -> Path:
    source = Path(path).expanduser()
    if not source.is_file():
        raise MediaPreflightError(
            "{} does not exist or is not a file: {}".format(label.capitalize(), source)
        )
    if source.stat().st_size == 0:
        raise MediaPreflightError("{} is empty: {}".format(label.capitalize(), source))
    return source.resolve()


def _ensure_writable_directory(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=str(path)):
            pass
    except OSError as error:
        raise MediaPreflightError(
            "Output directory is not writable: {} ({})".format(path, error)
        ) from error


def _positive_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _positive_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _timestamp_milliseconds(parts: list[int]) -> int:
    hours, minutes, seconds, milliseconds = parts
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + milliseconds
