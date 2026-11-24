"""Provider-injected generation of fictional character and style references."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipeline.cached_generation import run_cached_generation_call
from pipeline.keyframes import KeyframeReferences
from pipeline.providers import GenerationRequest, ImageGenerationProvider

_REFERENCE_ASSETS = (
    ("almaz", "almaz.png", 9001),
    ("dawit", "dawit.png", 9002),
    ("visual_style", "visual-style.png", 9003),
)


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{} must be a non-empty string.".format(label))
    return value.strip()


def _reference_prompts(storyboard: Mapping[str, Any]) -> dict[str, str]:
    characters = storyboard.get("characters")
    style = storyboard.get("visual_style")
    if not isinstance(characters, Mapping) or not isinstance(style, Mapping):
        raise ValueError("Storyboard must define characters and visual_style.")

    mother = characters.get("mother")
    child = characters.get("child")
    if not isinstance(mother, Mapping) or not isinstance(child, Mapping):
        raise ValueError("Storyboard must define mother and child characters.")
    if mother.get("fictional") is not True or child.get("fictional") is not True:
        raise ValueError("Reference generation is restricted to fictional characters.")

    visual_style = "\n\n".join(
        [
            _required_text(style.get("style_block"), "visual_style.style_block"),
            "Palette: {}".format(
                _required_text(style.get("palette"), "visual_style.palette")
            ),
            "Lighting: {}".format(
                _required_text(style.get("lighting"), "visual_style.lighting")
            ),
            "Framing: {}".format(
                _required_text(style.get("framing_note"), "visual_style.framing_note")
            ),
        ]
    )
    almaz_description = _required_text(mother.get("description"), "mother.description")
    dawit_description = _required_text(child.get("description"), "child.description")
    return {
        "almaz": (
            "Create a single fictional character reference portrait of Almaz. "
            "Use the following character description consistently; show no "
            "other people and include no text.\n\n{}\n\n{}".format(
                almaz_description, visual_style
            )
        ),
        "dawit": (
            "Create a single fictional character reference portrait of Dawit. "
            "Use the following character description consistently; show no "
            "other people and include no text.\n\n{}\n\n{}".format(
                dawit_description, visual_style
            )
        ),
        "visual_style": (
            "Create a visual style reference without text for a fictional "
            "Ethiopian highland family film. Show the color, lighting, material, "
            "and cinematic framing direction only; do not depict named "
            "characters.\n\n{}".format(visual_style)
        ),
    }


def generate_reference_images(
    storyboard: Mapping[str, Any],
    provider: ImageGenerationProvider,
    *,
    provider_name: str,
    model: str,
    outputs_dir: Path,
    log_path: Path,
    max_attempts: int = 3,
) -> KeyframeReferences:
    """Create or reuse reference portraits and a visual-style image.

    The operation is provider-injected and makes no network call unless
    explicitly invoked with an image provider. Only fictional characters from
    the storyboard are used as portrait subjects.
    """
    prompts = _reference_prompts(storyboard)
    generate_image = getattr(provider, "generate_image", None)
    if not callable(generate_image):
        raise TypeError("Image provider must implement generate_image().")

    output_root = Path(outputs_dir) / "assets" / "references"
    results: dict[str, Path] = {}
    for label, filename, seed in _REFERENCE_ASSETS:
        request = GenerationRequest(
            prompt=prompts[label],
            output_path=output_root / filename,
            seed=seed,
        )
        result = run_cached_generation_call(
            generate_image,
            request,
            provider=provider_name,
            model=model,
            stage="references",
            outputs_dir=Path(outputs_dir),
            log_path=Path(log_path),
            shot_id="reference-{}".format(label),
            max_attempts=max_attempts,
        )
        results[label] = result.result.output_path

    return KeyframeReferences(
        almaz=results["almaz"],
        dawit=results["dawit"],
        visual_style=results["visual_style"],
    )
