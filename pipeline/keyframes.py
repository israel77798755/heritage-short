"""Storyboard-driven keyframe generation with shared identity references."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.cached_generation import run_cached_generation_call
from pipeline.providers import ImageGenerationProvider, GenerationRequest


@dataclass(frozen=True)
class KeyframeReferences:
    """Approved image references used to keep characters and style consistent."""

    almaz: Path
    dawit: Path
    visual_style: Path

    def paths(self) -> tuple[Path, ...]:
        return (self.almaz, self.dawit, self.visual_style)


def _validate_keyframe_inputs(
    storyboard: Mapping[str, Any],
    references: KeyframeReferences,
) -> list[Mapping[str, Any]]:
    scenes = storyboard.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Storyboard must contain a non-empty scenes list.")

    seen_numbers: set[int] = set()
    for scene in scenes:
        if not isinstance(scene, Mapping):
            raise ValueError("Every storyboard scene must be an object.")
        number = scene.get("scene_number")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError("Scene numbers must be positive whole numbers.")
        if number in seen_numbers:
            raise ValueError("Scene numbers must be unique.")
        seen_numbers.add(number)
        if not isinstance(scene.get("image_prompt"), str) or not scene["image_prompt"].strip():
            raise ValueError(
                "Scene {} must have a non-empty image_prompt.".format(number)
            )
        seed = scene.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError("Scene {} must have a non-negative seed.".format(number))

    for label, path in (
        ("Almaz", references.almaz),
        ("Dawit", references.dawit),
        ("visual style", references.visual_style),
    ):
        reference = Path(path)
        if not reference.is_file():
            raise FileNotFoundError(
                "{} reference image does not exist: {}".format(label, reference)
            )
        if reference.stat().st_size == 0:
            raise OSError("{} reference image is empty: {}".format(label, reference))

    return scenes


def _build_keyframe_prompt(
    storyboard: Mapping[str, Any],
    scene: Mapping[str, Any],
) -> str:
    style = storyboard.get("visual_style")
    aspect_ratios = storyboard.get("aspect_ratios")
    if not isinstance(style, Mapping):
        raise ValueError("Storyboard must define visual_style.")
    if not isinstance(aspect_ratios, list) or not all(
        isinstance(ratio, str) for ratio in aspect_ratios
    ):
        raise ValueError("Storyboard must list its requested aspect_ratios.")
    if len(aspect_ratios) != 2 or set(aspect_ratios) != {"9:16", "16:9"}:
        raise ValueError("Keyframes must support both 9:16 and 16:9 aspect ratios.")
    style_parts = (
        style.get("style_block"),
        "Palette: {}".format(style.get("palette", "")),
        "Lighting: {}".format(style.get("lighting", "")),
        "Framing: {}".format(style.get("framing_note", "")),
    )
    return "\n\n".join(
        [
            "Create one cinematic storyboard keyframe. The provided references "
            "define Almaz, Dawit, and the visual style. Preserve their identity "
            "when they appear; do not add characters absent from the shot "
            "description. Keep the composition compatible with {} and include "
            "no text.".format(" and ".join(aspect_ratios)),
            *[part for part in style_parts if isinstance(part, str) and part.strip()],
            "Shot: {}".format(scene["image_prompt"]),
        ]
    )


def generate_keyframes(
    storyboard: Mapping[str, Any],
    provider: ImageGenerationProvider,
    *,
    provider_name: str,
    model: str,
    references: KeyframeReferences,
    outputs_dir: Path,
    log_path: Path,
    max_attempts: int = 3,
) -> dict[int, Path]:
    """Generate or reuse one cached keyframe per storyboard scene.

    This function is provider-injected: it performs no provider selection and
    is safe to exercise with a local fake provider in tests.
    """
    scenes = _validate_keyframe_inputs(storyboard, references)
    generate_image = getattr(provider, "generate_image", None)
    if not callable(generate_image):
        raise TypeError("Image provider must implement generate_image().")

    reference_paths = references.paths()
    results: dict[int, Path] = {}
    for scene in scenes:
        scene_number = scene["scene_number"]
        request = GenerationRequest(
            prompt=_build_keyframe_prompt(storyboard, scene),
            output_path=(
                Path(outputs_dir)
                / "assets"
                / "keyframes"
                / "shot-{:02}.png".format(scene_number)
            ),
            reference_paths=reference_paths,
            seed=scene["seed"],
        )
        result = run_cached_generation_call(
            generate_image,
            request,
            provider=provider_name,
            model=model,
            stage="keyframes",
            outputs_dir=Path(outputs_dir),
            log_path=Path(log_path),
            shot_id="shot-{:02}".format(scene_number),
            max_attempts=max_attempts,
        )
        results[scene_number] = result.result.output_path
    return results
