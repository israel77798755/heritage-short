"""Validation-gated orchestration for reference and keyframe generation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pipeline.keyframes import KeyframeReferences, generate_keyframes
from pipeline.orchestrator import PipelineStage, execute_pipeline
from pipeline.providers import ImageGenerationProvider
from pipeline.references import generate_reference_images


def run_visual_workflow(
    provider: ImageGenerationProvider,
    *,
    provider_name: str,
    model: str,
    storyboard_path: Path,
    schema_path: Path,
    outputs_dir: Path,
    log_path: Path,
) -> dict[str, Any]:
    """Validate the storyboard, then generate/reuse references and keyframes.

    The provider is supplied by the caller; this workflow does not select a
    service, create an API client, or make a call until explicitly invoked.
    """

    def reference_stage(
        storyboard: Mapping[str, Any],
        _prior_outputs: Mapping[str, Any],
    ) -> KeyframeReferences:
        return generate_reference_images(
            storyboard,
            provider,
            provider_name=provider_name,
            model=model,
            outputs_dir=outputs_dir,
            log_path=log_path,
        )

    def keyframe_stage(
        storyboard: Mapping[str, Any],
        prior_outputs: Mapping[str, Any],
    ) -> dict[int, Path]:
        references = prior_outputs.get("references")
        if not isinstance(references, KeyframeReferences):
            raise TypeError(
                "The reference stage must return KeyframeReferences before keyframes."
            )
        return generate_keyframes(
            storyboard,
            provider,
            provider_name=provider_name,
            model=model,
            references=references,
            outputs_dir=outputs_dir,
            log_path=log_path,
        )

    return execute_pipeline(
        [
            PipelineStage("references", reference_stage),
            PipelineStage("keyframes", keyframe_stage),
        ],
        storyboard_path=Path(storyboard_path),
        schema_path=Path(schema_path),
    )
