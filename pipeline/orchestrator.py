"""Validation-gated orchestration for storyboard-driven production stages."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from validate_storyboard import require_valid_storyboard


_STAGE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
StageFunction = Callable[[Mapping[str, Any], Mapping[str, Any]], Any]


@dataclass(frozen=True)
class PipelineStage:
    """A named stage that consumes the storyboard and prior stage outputs."""

    name: str
    run: StageFunction


def _validate_stages(stages: Sequence[PipelineStage]) -> None:
    if not stages:
        raise ValueError("At least one pipeline stage must be configured.")

    seen_names: set[str] = set()
    for stage in stages:
        if not isinstance(stage, PipelineStage):
            raise TypeError("Each configured stage must be a PipelineStage.")
        if not isinstance(stage.name, str) or not _STAGE_NAME_PATTERN.fullmatch(
            stage.name
        ):
            raise ValueError(
                "Stage names must start with a lowercase letter and contain only "
                "lowercase letters, digits, '_' or '-'."
            )
        if stage.name in seen_names:
            raise ValueError("Pipeline stage names must be unique.")
        if not callable(stage.run):
            raise TypeError("Stage '{}' must have a callable run function.".format(stage.name))
        seen_names.add(stage.name)


def execute_pipeline(
    stages: Sequence[PipelineStage],
    *,
    storyboard_path: Path,
    schema_path: Path,
) -> dict[str, Any]:
    """Validate first, then execute each configured stage in order.

    A validation error prevents every stage from running. A stage failure is
    allowed to propagate and stops later stages; callers must report or log
    the failure rather than continue with incomplete outputs.
    """
    _validate_stages(stages)
    storyboard = require_valid_storyboard(
        storyboard_path=Path(storyboard_path),
        schema_path=Path(schema_path),
    )

    results: dict[str, Any] = {}
    for stage in stages:
        results[stage.name] = stage.run(storyboard, dict(results))
    return results
