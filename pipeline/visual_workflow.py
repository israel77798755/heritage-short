"""Validation-gated orchestration for reference and keyframe generation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pipeline.keyframes import KeyframeReferences, generate_keyframes
from pipeline.orchestrator import PipelineStage, execute_pipeline
from pipeline.providers import ImageGenerationProvider
from pipeline.references import generate_reference_images


class ReferenceApprovalRequiredError(RuntimeError):
    """Raised when human review does not approve the candidate references."""


def run_visual_workflow(
    provider: ImageGenerationProvider,
    *,
    provider_name: str,
    model: str,
    storyboard_path: Path,
    schema_path: Path,
    outputs_dir: Path,
    log_path: Path,
    approve_references: Callable[[KeyframeReferences], bool],
) -> dict[str, Any]:
    """Validate, then require approved references before generating keyframes.

    The provider is supplied by the caller; this workflow does not select a
    service, create an API client, or make a call until explicitly invoked.
    The approval callback must explicitly return ``True`` before keyframes run.
    """
    if not callable(approve_references):
        raise TypeError("approve_references must be callable.")

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

    def approval_stage(
        _storyboard: Mapping[str, Any],
        prior_outputs: Mapping[str, Any],
    ) -> KeyframeReferences:
        references = prior_outputs.get("references")
        if not isinstance(references, KeyframeReferences):
            raise TypeError(
                "The reference stage must return KeyframeReferences before approval."
            )
        if approve_references(references) is not True:
            raise ReferenceApprovalRequiredError(
                "Candidate references were not approved; keyframe generation stopped."
            )
        return references

    def keyframe_stage(
        storyboard: Mapping[str, Any],
        prior_outputs: Mapping[str, Any],
    ) -> dict[int, Path]:
        references = prior_outputs.get("approved_references")
        if not isinstance(references, KeyframeReferences):
            raise TypeError(
                "Approved KeyframeReferences are required before keyframes."
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
            PipelineStage("approved_references", approval_stage),
            PipelineStage("keyframes", keyframe_stage),
        ],
        storyboard_path=Path(storyboard_path),
        schema_path=Path(schema_path),
    )
