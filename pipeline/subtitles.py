"""Create a draft English SRT from validated storyboard shot timings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.config import SCHEMA_PATH, STORYBOARD_PATH
from validate_storyboard import require_valid_storyboard


def format_srt_timestamp(milliseconds: int) -> str:
    """Format non-negative milliseconds as an SRT timestamp."""
    if isinstance(milliseconds, bool) or not isinstance(milliseconds, int):
        raise TypeError("milliseconds must be a whole number.")
    if milliseconds < 0:
        raise ValueError("milliseconds cannot be negative.")

    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return "{:02}:{:02}:{:02},{:03}".format(
        hours, minutes, seconds, milliseconds
    )


def build_english_srt(storyboard: dict[str, Any]) -> str:
    """Build draft SRT cues using cumulative storyboard shot durations."""
    scenes = storyboard["scenes"]
    cues = []
    elapsed_seconds = 0

    for cue_number, scene in enumerate(scenes, start=1):
        duration_seconds = scene["duration_seconds"]
        start_ms = elapsed_seconds * 1_000
        end_ms = (elapsed_seconds + duration_seconds) * 1_000
        subtitle_text = scene["subtitle_en"].strip()
        cues.append(
            "{}\n{} --> {}\n{}".format(
                cue_number,
                format_srt_timestamp(start_ms),
                format_srt_timestamp(end_ms),
                subtitle_text,
            )
        )
        elapsed_seconds += duration_seconds

    return "\n\n".join(cues) + "\n"


def write_english_srt(
    output_path: Path,
    *,
    storyboard_path: Path = STORYBOARD_PATH,
    schema_path: Path = SCHEMA_PATH,
) -> Path:
    """Validate the storyboard, then write storyboard-timed English subtitles.

    These timings follow planned shot durations. Final subtitles must be
    adjusted against the generated narration audio before export.
    """
    storyboard = require_valid_storyboard(
        storyboard_path=Path(storyboard_path),
        schema_path=Path(schema_path),
    )
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        build_english_srt(storyboard),
        encoding="utf-8",
        newline="\n",
    )
    return target
