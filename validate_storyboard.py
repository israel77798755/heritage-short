"""Validate storyboard.json against the JSON Schema and film rules."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional fallback when jsonschema is absent
    Draft202012Validator = None


ROOT_DIR = Path(__file__).resolve().parent
STORYBOARD_PATH = ROOT_DIR / "storyboard.json"
SCHEMA_PATH = ROOT_DIR / "schema" / "storyboard.schema.json"

MIN_FILM_DURATION_SECONDS = 60
MAX_FILM_DURATION_SECONDS = 90
MIN_SCENE_COUNT = 8
MAX_SCENE_COUNT = 12
REQUIRED_ASPECT_RATIOS = ("9:16", "16:9")
REQUIRED_LESSON_IDS = (
    "trust_god",
    "respect_others",
    "never_give_up",
    "remain_hopeful",
)
REQUIRED_SCENE_TEXT_FIELDS = (
    "title",
    "purpose",
    "shot_size",
    "camera_movement",
    "visual",
    "image_prompt",
    "motion_prompt",
    "narration",
    "subtitle_en",
    "audio",
    "music_cue",
)
ETHIOPIC_PATTERN = re.compile(r"[\u1200-\u137F]")


class StoryboardValidationError(ValueError):
    """Raised when storyboard.json fails schema or semantic validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        message = "Storyboard validation failed:\n" + "\n".join(
            f"- {err}" for err in errors
        )
        super().__init__(message)


def is_integer(value: Any) -> bool:
    """Return True for integers, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_non_empty_str(value: Any) -> bool:
    """Return True when value is a non-empty string after stripping."""
    return isinstance(value, str) and bool(value.strip())


def _format_schema_path(path_parts: Any) -> str:
    """Format a jsonschema error path as a readable dotted path."""
    parts = [str(part) for part in path_parts]
    return ".".join(parts) if parts else "<root>"


def _validate_with_jsonschema(
    storyboard: Any, schema: dict[str, Any]
) -> list[str]:
    """Validate storyboard against the JSON Schema using Draft202012Validator."""
    if Draft202012Validator is None:
        return []

    validator = Draft202012Validator(schema)
    schema_errors = sorted(
        validator.iter_errors(storyboard), key=lambda err: list(err.path)
    )
    return [
        f"Schema error at {_format_schema_path(err.path)}: {err.message}"
        for err in schema_errors
    ]


def _validate_structure_fallback(
    storyboard: dict[str, Any], schema: dict[str, Any]
) -> list[str]:
    """Check core schema keys when the jsonschema package is not installed."""
    errors: list[str] = []
    required_root = schema.get("required", [])
    allowed_root = set(schema.get("properties", {}).keys())

    for key in required_root:
        if key not in storyboard:
            errors.append(f"Missing required root field '{key}'.")

    if schema.get("additionalProperties") is False:
        extra_keys = sorted(set(storyboard.keys()) - allowed_root)
        for key in extra_keys:
            errors.append(f"Unexpected root field '{key}'.")

    return errors


def _validate_durations(storyboard: dict[str, Any]) -> tuple[list[str], int]:
    """Validate top-level and total film duration bounds (60-90 seconds)."""
    errors: list[str] = []
    minimum = storyboard.get("minimum_duration_seconds")
    maximum = storyboard.get("maximum_duration_seconds")
    target = storyboard.get("target_duration_seconds")

    if not is_integer(minimum) or not (
        MIN_FILM_DURATION_SECONDS <= minimum <= MAX_FILM_DURATION_SECONDS
    ):
        errors.append(
            "minimum_duration_seconds must be a whole number between "
            f"{MIN_FILM_DURATION_SECONDS} and {MAX_FILM_DURATION_SECONDS}."
        )
    if not is_integer(maximum) or not (
        MIN_FILM_DURATION_SECONDS <= maximum <= MAX_FILM_DURATION_SECONDS
    ):
        errors.append(
            "maximum_duration_seconds must be a whole number between "
            f"{MIN_FILM_DURATION_SECONDS} and {MAX_FILM_DURATION_SECONDS}."
        )
    if is_integer(minimum) and is_integer(maximum) and minimum > maximum:
        errors.append("minimum_duration_seconds cannot exceed maximum_duration_seconds.")

    if not is_integer(target) or not (
        MIN_FILM_DURATION_SECONDS <= target <= MAX_FILM_DURATION_SECONDS
    ):
        errors.append(
            "target_duration_seconds must be a whole number between "
            f"{MIN_FILM_DURATION_SECONDS} and {MAX_FILM_DURATION_SECONDS}."
        )
    elif is_integer(minimum) and is_integer(maximum) and not (minimum <= target <= maximum):
        errors.append("target_duration_seconds must lie within minimum and maximum.")

    scenes = storyboard.get("scenes")
    total_story_seconds = 0
    if isinstance(scenes, list):
        for scene in scenes:
            if isinstance(scene, dict) and is_integer(scene.get("duration_seconds")):
                total_story_seconds += scene["duration_seconds"]

    if is_integer(target) and isinstance(scenes, list) and total_story_seconds != target:
        errors.append(
            f"Scene durations total {total_story_seconds} seconds, "
            f"but target_duration_seconds is {target} seconds."
        )

    if isinstance(scenes, list) and not (
        MIN_FILM_DURATION_SECONDS <= total_story_seconds <= MAX_FILM_DURATION_SECONDS
    ):
        errors.append(
            f"Scene durations total {total_story_seconds} seconds, outside the "
            f"{MIN_FILM_DURATION_SECONDS}-{MAX_FILM_DURATION_SECONDS} second limit."
        )

    end_card = storyboard.get("end_card")
    if isinstance(end_card, dict):
        end_duration = end_card.get("duration_seconds")
        if not is_integer(end_duration) or end_duration <= 0:
            errors.append("end_card.duration_seconds must be a positive whole number.")
        elif total_story_seconds + end_duration > MAX_FILM_DURATION_SECONDS:
            errors.append(
                f"Total runtime with end card ({total_story_seconds + end_duration}s) "
                f"exceeds {MAX_FILM_DURATION_SECONDS} seconds."
            )

    return errors, total_story_seconds


def _validate_metadata_sections(storyboard: dict[str, Any]) -> list[str]:
    """Validate language, aspect ratios, characters, music, and AI end card."""
    errors: list[str] = []

    if not _is_non_empty_str(storyboard.get("title")):
        errors.append("The storyboard needs a non-empty title.")
    if not _is_non_empty_str(storyboard.get("title_am")) or not ETHIOPIC_PATTERN.search(
        storyboard["title_am"]
    ):
        errors.append("title_am must contain Amharic Ge'ez text.")

    if storyboard.get("language") != "am":
        errors.append("language must be 'am' for Amharic narration.")
    if storyboard.get("subtitle_language") != "en":
        errors.append("subtitle_language must be 'en' for English subtitles.")

    aspect_ratios = storyboard.get("aspect_ratios")
    if not isinstance(aspect_ratios, list) or not all(
        ratio in aspect_ratios for ratio in REQUIRED_ASPECT_RATIOS
    ):
        errors.append("aspect_ratios must include both '9:16' and '16:9'.")

    characters = storyboard.get("characters")
    if not isinstance(characters, dict):
        errors.append("characters must be an object describing mother and child.")
    else:
        for role in ("mother", "child"):
            char = characters.get(role)
            if not isinstance(char, dict):
                errors.append(f"characters.{role} must be an object.")
                continue
            if char.get("fictional") is not True:
                errors.append(f"characters.{role}.fictional must be true.")
            if not _is_non_empty_str(char.get("description")):
                errors.append(f"characters.{role} needs a non-empty description.")

    end_card = storyboard.get("end_card")
    if not isinstance(end_card, dict):
        errors.append("end_card must be an object with AI disclosure details.")
    else:
        if not _is_non_empty_str(end_card.get("disclosure_en")):
            errors.append("end_card.disclosure_en must be non-empty.")
        if not _is_non_empty_str(end_card.get("disclosure_am")) or not ETHIOPIC_PATTERN.search(
            end_card["disclosure_am"]
        ):
            errors.append("end_card.disclosure_am must contain Amharic text.")

    return errors


def _validate_scenes_and_lessons(storyboard: dict[str, Any]) -> list[str]:
    """Validate scene count, numbering, prompts, narration, subtitles, and 4 lessons."""
    errors: list[str] = []
    scenes = storyboard.get("scenes")

    if not isinstance(scenes, list) or not scenes:
        return ["scenes must be a non-empty list."]

    if not (MIN_SCENE_COUNT <= len(scenes) <= MAX_SCENE_COUNT):
        errors.append(
            f"scenes has {len(scenes)} shots; expected {MIN_SCENE_COUNT}-{MAX_SCENE_COUNT}."
        )

    scene_by_number: dict[int, dict[str, Any]] = {}
    scene_lessons: set[str] = set()

    for position, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            errors.append(f"Scene {position} must be a JSON object.")
            continue

        scene_number = scene.get("scene_number")
        if not is_integer(scene_number) or scene_number <= 0:
            errors.append(f"Scene {position} needs a positive whole-number scene_number.")
        elif scene_number in scene_by_number:
            errors.append(f"Scene number {scene_number} is used more than once.")
        else:
            scene_by_number[scene_number] = scene
            if scene_number != position:
                errors.append(
                    f"Scene at position {position} has scene_number {scene_number}; "
                    "scene numbers must be sequential starting at 1."
                )

        duration = scene.get("duration_seconds")
        if not is_integer(duration) or duration <= 0:
            errors.append(
                f"Scene {position} needs a positive whole-number duration_seconds."
            )

        for field in REQUIRED_SCENE_TEXT_FIELDS:
            if not _is_non_empty_str(scene.get(field)):
                errors.append(f"Scene {position} needs a non-empty '{field}'.")

        narration = scene.get("narration")
        if _is_non_empty_str(narration) and not ETHIOPIC_PATTERN.search(narration):
            errors.append(
                f"Scene {position} narration must contain Amharic Ge'ez characters."
            )

        seed = scene.get("seed")
        if not is_integer(seed) or seed < 0:
            errors.append(f"Scene {position} needs a non-negative integer 'seed'.")

        lesson_tag = scene.get("lesson")
        if isinstance(lesson_tag, str):
            scene_lessons.add(lesson_tag)

    lessons = storyboard.get("lessons")
    if not isinstance(lessons, list):
        errors.append("lessons must be a list of the four core lessons.")
    else:
        defined_ids: list[str] = []
        for entry in lessons:
            if not isinstance(entry, dict):
                errors.append("Each entry in lessons must be an object.")
                continue
            lesson_id = entry.get("id")
            if isinstance(lesson_id, str):
                defined_ids.append(lesson_id)
            if not _is_non_empty_str(entry.get("lesson_en")):
                errors.append(f"Lesson '{lesson_id}' needs a non-empty lesson_en.")
            if not _is_non_empty_str(entry.get("lesson_am")) or not ETHIOPIC_PATTERN.search(
                entry["lesson_am"]
            ):
                errors.append(f"Lesson '{lesson_id}' needs Amharic text in lesson_am.")
            mapped_scenes = entry.get("scene_numbers")
            if not isinstance(mapped_scenes, list) or not mapped_scenes:
                errors.append(f"Lesson '{lesson_id}' must map to at least one scene.")
            else:
                for num in mapped_scenes:
                    if num not in scene_by_number:
                        errors.append(
                            f"Lesson '{lesson_id}' references unknown scene_number {num}."
                        )
                    elif scene_by_number[num].get("lesson") != lesson_id:
                        errors.append(
                            f"Scene {num} has lesson '{scene_by_number[num].get('lesson')}', "
                            f"expected '{lesson_id}'."
                        )

        for required_id in REQUIRED_LESSON_IDS:
            if required_id not in defined_ids:
                errors.append(f"Missing required lesson '{required_id}' in lessons.")
            if required_id not in scene_lessons:
                errors.append(
                    f"No scene in scenes covers required lesson '{required_id}'."
                )

    return errors


def validate_storyboard(
    storyboard: Any, schema: dict[str, Any] | None = None
) -> list[str]:
    """Return a list of schema and semantic problems found in the storyboard."""
    if not isinstance(storyboard, dict):
        return ["The storyboard must be a JSON object."]

    errors: list[str] = []
    if schema is not None:
        if Draft202012Validator is not None:
            errors.extend(_validate_with_jsonschema(storyboard, schema))
        else:
            errors.extend(_validate_structure_fallback(storyboard, schema))

    duration_errors, _ = _validate_durations(storyboard)
    errors.extend(duration_errors)
    errors.extend(_validate_metadata_sections(storyboard))
    errors.extend(_validate_scenes_and_lessons(storyboard))
    return errors


def _load_json(path: Path, label: str) -> tuple[Any | None, str | None]:
    """Read and parse a JSON file, returning (data, error_message)."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as error:
        return None, f"Could not read {label} ({path}): {error}"

    try:
        return json.loads(raw_text), None
    except json.JSONDecodeError as error:
        return (
            None,
            f"Could not parse {label} ({path}): {error.msg} "
            f"(line {error.lineno}, column {error.colno}).",
        )


def validate_storyboard_file(
    storyboard_path: Path = STORYBOARD_PATH,
    schema_path: Path = SCHEMA_PATH,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Load and validate storyboard.json and its schema; return (data, errors)."""
    storyboard, sb_error = _load_json(storyboard_path, "storyboard")
    if sb_error:
        return None, [sb_error]

    schema, schema_error = _load_json(schema_path, "schema")
    if schema_error:
        return None, [schema_error]

    if not isinstance(schema, dict):
        return None, [f"Schema ({schema_path}) must be a JSON object."]

    errors = validate_storyboard(storyboard, schema=schema)
    return storyboard if not errors else None, errors


def require_valid_storyboard(
    storyboard_path: Path = STORYBOARD_PATH,
    schema_path: Path = SCHEMA_PATH,
) -> dict[str, Any]:
    """Pre-generation gate: return validated storyboard or raise StoryboardValidationError."""
    storyboard, errors = validate_storyboard_file(
        storyboard_path=storyboard_path,
        schema_path=schema_path,
    )
    if errors or storyboard is None:
        raise StoryboardValidationError(errors)
    return storyboard


def main(argv: list[str] | None = None) -> int:
    """Run storyboard validation from the command line."""
    parser = argparse.ArgumentParser(
        description="Validate storyboard.json against schema and production rules."
    )
    parser.add_argument(
        "--storyboard",
        type=Path,
        default=STORYBOARD_PATH,
        help="Path to storyboard.json (default: repository storyboard.json).",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_PATH,
        help="Path to storyboard JSON Schema (default: schema/storyboard.schema.json).",
    )
    args = parser.parse_args(argv)

    storyboard, errors = validate_storyboard_file(
        storyboard_path=args.storyboard,
        schema_path=args.schema,
    )
    if errors or storyboard is None:
        print("Storyboard validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    story_duration = sum(scene["duration_seconds"] for scene in storyboard["scenes"])
    end_duration = storyboard["end_card"]["duration_seconds"]
    schema_mode = "jsonschema" if Draft202012Validator is not None else "built-in fallback"
    print(
        f"Storyboard is valid ({schema_mode}): '{storyboard['title']}' has "
        f"{len(storyboard['scenes'])} scenes, {story_duration}s story + "
        f"{end_duration}s end card ({story_duration + end_duration}s total)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
