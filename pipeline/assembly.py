"""Build and run FFmpeg commands for the radio cut and both film exports."""

from __future__ import annotations

import math
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pipeline.media_preflight import (
    ASPECT_RATIOS,
    AssemblyPreflight,
    MediaInfo,
    MediaPreflightError,
    probe_media,
)


_FPS = 30
_PRESET = "medium"
_CRF = 20
_COMMAND_TIMEOUT_SECONDS = 3600


class AssemblyError(RuntimeError):
    """Raised when an export cannot be built or fails output validation."""


class AssemblyOutputExistsError(AssemblyError):
    """Raised rather than overwriting an existing generated file."""


@dataclass(frozen=True)
class ExportCommands:
    aspect_ratio: str
    segment_commands: tuple[tuple[str, ...], ...]
    segment_paths: tuple[Path, ...]
    concat_manifest_path: Path
    end_card_text_path: Path
    final_command: tuple[str, ...]
    output_path: Path


def build_shot_command(
    plan: AssemblyPreflight,
    scene_number: int,
    aspect_ratio: str,
) -> tuple[tuple[str, ...], Path]:
    """Create a normalized MP4 command; stills receive a slow pan/zoom."""
    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError("Unsupported aspect ratio: {}".format(aspect_ratio))
    shot = next(
        (item for item in plan.shot_inputs if item.scene_number == scene_number),
        None,
    )
    if shot is None:
        raise ValueError("No preflighted asset for scene {}.".format(scene_number))
    width, height = ASPECT_RATIOS[aspect_ratio]
    output_path = (
        plan.output_directories[aspect_ratio]
        / "shot-{:02}.mp4".format(scene_number)
    )
    _require_new_output(output_path)
    duration = _seconds(shot.duration_seconds)
    filters = [
        "scale={}:{}:force_original_aspect_ratio=increase".format(width, height),
        "crop={}:{}".format(width, height),
    ]
    if shot.is_still:
        frames = max(1, shot.duration_seconds * _FPS)
        if scene_number % 2:
            x_position = "(iw-iw/zoom)*on/{}".format(frames)
        else:
            x_position = "(iw-iw/zoom)*(1-on/{})".format(frames)
        filters.append(
            "zoompan=z='min(1+0.08*on/{},1.08)':x='{}':"
            "y='(ih-ih/zoom)/2':d=1:s={}x{}:fps={}".format(
                frames, x_position, width, height, _FPS
            )
        )
    else:
        filters.append("fps={}".format(_FPS))
        filters.append(
            "tpad=stop_mode=clone:stop_duration={}".format(duration)
        )
    filters.extend(
        (
            "trim=duration={}".format(duration),
            "setpts=PTS-STARTPTS",
            "setsar=1",
            "format=yuv420p",
        )
    )
    command = [str(plan.ffmpeg_path), "-n"]
    if shot.is_still:
        command.extend(("-loop", "1", "-framerate", str(_FPS), "-t", duration))
    command.extend(("-i", str(shot.path)))
    command.extend(
        (
            "-vf",
            ",".join(filters),
            "-an",
            "-sn",
            "-dn",
            "-c:v",
            "libx264",
            "-preset",
            _PRESET,
            "-crf",
            str(_CRF),
            "-r",
            str(_FPS),
            "-pix_fmt",
            "yuv420p",
            "-t",
            duration,
            "-movflags",
            "+faststart",
            str(output_path),
        )
    )
    return tuple(command), output_path


def build_export_commands(
    plan: AssemblyPreflight,
    aspect_ratio: str,
) -> ExportCommands:
    """Prepare segment and final-mux commands for one target format."""
    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError("Unsupported aspect ratio: {}".format(aspect_ratio))
    segment_results = tuple(
        build_shot_command(plan, shot.scene_number, aspect_ratio)
        for shot in plan.shot_inputs
    )
    segment_commands = tuple(command for command, _ in segment_results)
    segment_paths = tuple(path for _, path in segment_results)
    manifest_path = plan.output_directories[aspect_ratio] / "segments.ffconcat"
    text_path = plan.final_output_paths[aspect_ratio].parent / "end-card.txt"
    output_path = plan.final_output_paths[aspect_ratio]
    _require_new_output(manifest_path)
    _require_new_output(text_path)
    _require_new_output(output_path)

    final_command = _build_final_command(
        plan,
        aspect_ratio,
        manifest_path,
        text_path,
        output_path,
    )
    return ExportCommands(
        aspect_ratio=aspect_ratio,
        segment_commands=segment_commands,
        segment_paths=segment_paths,
        concat_manifest_path=manifest_path,
        end_card_text_path=text_path,
        final_command=final_command,
        output_path=output_path,
    )


def write_concat_manifest(segment_paths: Sequence[Path], manifest_path: Path) -> Path:
    """Write a concat-demuxer list after verifying every segment is ready."""
    if not segment_paths:
        raise ValueError("At least one rendered segment is required.")
    manifest = Path(manifest_path)
    _require_new_output(manifest)
    lines = ["ffconcat version 1.0"]
    for path in segment_paths:
        segment = Path(path)
        if not segment.is_file() or segment.stat().st_size == 0:
            raise MediaPreflightError(
                "Rendered segment is missing or empty: {}".format(segment)
            )
        escaped = segment.resolve().as_posix().replace("'", "'\\''")
        lines.append("file '{}'".format(escaped))
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("x", encoding="utf-8", newline="\n") as file:
        file.write("\n".join(lines) + "\n")
    return manifest


def write_end_card_text(plan: AssemblyPreflight, output_path: Path) -> Path:
    """Write the storyboard's end-card copy without replacing existing work."""
    target = Path(output_path)
    _require_new_output(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as file:
        file.write(plan.end_card_text + "\n")
    return target


def build_radio_cut_command(plan: AssemblyPreflight) -> tuple[str, ...]:
    """Build a narration-only, normalized WAV cut; music is intentionally absent."""
    _require_new_output(plan.radio_cut_path)
    return (
        str(plan.ffmpeg_path),
        "-n",
        "-i",
        str(plan.narration_path),
        "-vn",
        "-af",
        "aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,"
        "apad=whole_dur={duration},atrim=duration={duration},"
        "loudnorm=I=-16:TP=-1:LRA=11".format(
            duration=_seconds(plan.story_duration_seconds)
        ),
        "-t",
        _seconds(plan.story_duration_seconds),
        "-c:a",
        "pcm_s16le",
        str(plan.radio_cut_path),
    )


def render_all_exports(plan: AssemblyPreflight) -> tuple[Path, ...]:
    """Render the radio cut and both aspect ratios, stopping on any failure."""
    radio_command = build_radio_cut_command(plan)
    export_specs = tuple(
        build_export_commands(plan, aspect_ratio)
        for aspect_ratio in ASPECT_RATIOS
    )
    run_media_command(radio_command)
    validate_radio_cut(
        plan.radio_cut_path,
        plan.ffprobe_path,
        plan.story_duration_seconds,
    )

    outputs = [plan.radio_cut_path]
    for commands in export_specs:
        for segment_command in commands.segment_commands:
            run_media_command(segment_command)
        write_concat_manifest(
            commands.segment_paths,
            commands.concat_manifest_path,
        )
        write_end_card_text(plan, commands.end_card_text_path)
        run_media_command(commands.final_command)
        validate_final_export(
            commands.output_path,
            plan.ffprobe_path,
            commands.aspect_ratio,
            plan.total_duration_seconds,
        )
        outputs.append(commands.output_path)
    return tuple(outputs)


def run_media_command(
    command: Sequence[str],
    *,
    timeout_seconds: int = _COMMAND_TIMEOUT_SECONDS,
) -> None:
    """Run one FFmpeg process without a shell and surface useful failures."""
    if not command or not isinstance(command[0], str):
        raise ValueError("command must contain an executable path.")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
        raise TypeError("timeout_seconds must be a positive whole number.")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a positive whole number.")
    try:
        completed = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AssemblyError("Could not run media command: {}".format(error)) from error
    if completed.returncode != 0:
        detail = completed.stderr.strip()[-4000:] or "media tool returned a non-zero exit code"
        raise AssemblyError(
            "Media command failed with exit code {}: {}".format(
                completed.returncode, detail
            )
        )


def validate_final_export(
    path: Path,
    ffprobe_path: Path,
    aspect_ratio: str,
    expected_duration_seconds: int,
    *,
    duration_tolerance_seconds: float = 0.15,
) -> MediaInfo:
    """Verify final video dimensions, streams, subtitles, and runtime."""
    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError("Unsupported aspect ratio: {}".format(aspect_ratio))
    info = probe_media(path, ffprobe_path)
    expected_width, expected_height = ASPECT_RATIOS[aspect_ratio]
    if not info.has_video or (info.width, info.height) != (
        expected_width,
        expected_height,
    ):
        raise AssemblyError(
            "Final export has incorrect video dimensions for {}.".format(aspect_ratio)
        )
    if not info.has_audio:
        raise AssemblyError("Final export has no audio stream.")
    if not info.has_subtitles:
        raise AssemblyError("Final export has no English subtitle stream.")
    _validate_duration(
        info,
        expected_duration_seconds,
        duration_tolerance_seconds,
        "Final export",
    )
    return info


def validate_radio_cut(
    path: Path,
    ffprobe_path: Path,
    expected_duration_seconds: int,
    *,
    duration_tolerance_seconds: float = 0.15,
) -> MediaInfo:
    """Verify the radio cut is audio-only and has the expected runtime."""
    info = probe_media(path, ffprobe_path)
    if not info.has_audio or info.has_video:
        raise AssemblyError("Radio cut must contain audio only.")
    _validate_duration(
        info,
        expected_duration_seconds,
        duration_tolerance_seconds,
        "Radio cut",
    )
    return info


def _build_final_command(
    plan: AssemblyPreflight,
    aspect_ratio: str,
    manifest_path: Path,
    end_card_text_path: Path,
    output_path: Path,
) -> tuple[str, ...]:
    width, height = ASPECT_RATIOS[aspect_ratio]
    end_card_duration = plan.total_duration_seconds - plan.story_duration_seconds
    font_size = max(24, min(width, height) // 30)
    audio_duration = _seconds(plan.total_duration_seconds)
    font_path = _filter_path(plan.font_path)
    text_path = _filter_path(end_card_text_path)
    video_filter = (
        "[0:v]setpts=PTS-STARTPTS,format=yuv420p[story];"
        "[1:v]drawtext=fontfile='{}':textfile='{}':expansion=none:"
        "fontcolor=0xF5E9D1:fontsize={}:line_spacing=12:"
        "x=(w-text_w)/2:y=(h-text_h)/2:box=1:"
        "boxcolor=0x1B160F@0.45:boxborderw=36:text_shaping=1,"
        "format=yuv420p,setpts=PTS-STARTPTS[card];"
        "[story][card]concat=n=2:v=1:a=0[vout]"
    ).format(font_path, text_path, font_size)
    audio_filter = (
        "[2:a]aresample=48000,aformat=channel_layouts=stereo,"
        "apad=whole_dur={duration},atrim=duration={duration},"
        "asetpts=PTS-STARTPTS[narr];"
        "[3:a]volume=-12dB,aresample=48000,aformat=channel_layouts=stereo,"
        "apad=whole_dur={duration},atrim=duration={duration},"
        "asetpts=PTS-STARTPTS[music];"
        "[music][narr]sidechaincompress=threshold=0.02:ratio=8:"
        "attack=20:release=500[ducked];"
        "[narr][ducked]amix=inputs=2:duration=longest:dropout_transition=2,"
        "atrim=duration={duration},"
        "afade=t=out:st={fade_start}:d=1,"
        "loudnorm=I=-14:TP=-1:LRA=11[aout]"
    ).format(
        duration=audio_duration,
        fade_start=_seconds(max(0, plan.total_duration_seconds - 1)),
    )
    return (
        str(plan.ffmpeg_path),
        "-n",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(manifest_path),
        "-f",
        "lavfi",
        "-i",
        "color=c=0x1B160F:s={}x{}:r={}:d={}".format(
            width, height, _FPS, end_card_duration
        ),
        "-i",
        str(plan.narration_path),
        "-i",
        str(plan.music_path),
        "-sub_charenc",
        "UTF-8",
        "-i",
        str(plan.subtitle_path),
        "-filter_complex",
        video_filter + ";" + audio_filter,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-map",
        "4:0",
        "-t",
        _seconds(plan.total_duration_seconds),
        "-c:v",
        "libx264",
        "-preset",
        _PRESET,
        "-crf",
        str(_CRF),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=eng",
        "-disposition:s:0",
        "default",
        "-movflags",
        "+faststart",
        str(output_path),
    )


def _filter_path(path: Path) -> str:
    value = Path(path).resolve().as_posix()
    value = value.replace("\\", "\\\\").replace(":", "\\:")
    return value.replace("'", "\\'")


def _require_new_output(path: Path) -> None:
    if Path(path).exists():
        raise AssemblyOutputExistsError(
            "Refusing to overwrite existing output: {}".format(path)
        )


def _seconds(value: int) -> str:
    return "{:.3f}".format(float(value))


def _validate_duration(
    info: MediaInfo,
    expected_duration_seconds: int,
    tolerance_seconds: float,
    label: str,
) -> None:
    if (
        isinstance(expected_duration_seconds, bool)
        or not isinstance(expected_duration_seconds, int)
        or expected_duration_seconds <= 0
    ):
        raise ValueError("expected_duration_seconds must be a positive whole number.")
    if (
        isinstance(tolerance_seconds, bool)
        or not isinstance(tolerance_seconds, (int, float))
        or not math.isfinite(tolerance_seconds)
        or tolerance_seconds < 0
    ):
        raise ValueError("duration tolerance must be a non-negative number.")
    if (
        info.duration_seconds is None
        or abs(info.duration_seconds - expected_duration_seconds) > tolerance_seconds
    ):
        raise AssemblyError(
            "{} duration must be {} seconds (observed {}).".format(
                label,
                expected_duration_seconds,
                info.duration_seconds,
            )
        )
