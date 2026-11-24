"""Shared configuration, paths, and environment helpers for the pipeline.

This module is the single place where every pipeline stage finds:
- Project directory paths (storyboard, schema, outputs, logs).
- A safe way to read API keys from a local .env file.

Usage in any pipeline stage script::

    from pipeline.config import STORYBOARD_PATH, OUTPUTS_DIR, get_env

    api_key = get_env("GEMINI_API_KEY")   # raises if missing
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project layout
# ---------------------------------------------------------------------------
# config.py sits inside  heritage-short/pipeline/config.py
# so the project root is one level up from this file's parent directory.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

STORYBOARD_PATH: Path = PROJECT_ROOT / "storyboard.json"
SCHEMA_PATH: Path = PROJECT_ROOT / "schema" / "storyboard.schema.json"
OUTPUTS_DIR: Path = PROJECT_ROOT / "outputs"
RUNS_JSONL_PATH: Path = PROJECT_ROOT / "runs.jsonl"
ENV_PATH: Path = PROJECT_ROOT / ".env"

# ---------------------------------------------------------------------------
# Load .env (safe even if .env does not exist yet)
# ---------------------------------------------------------------------------
load_dotenv(dotenv_path=ENV_PATH)

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


class MissingEnvVarError(EnvironmentError):
    """Raised when a required environment variable is not set."""

    def __init__(self, name: str) -> None:
        super().__init__(
            f"Required environment variable '{name}' is not set. "
            f"Copy .env.example to .env and fill in your keys."
        )


def get_env(name: str, *, required: bool = True) -> str | None:
    """Return the value of an environment variable.

    Parameters
    ----------
    name:
        The variable name (e.g. ``"GEMINI_API_KEY"``).
    required:
        When *True* (the default), raise ``MissingEnvVarError`` if the
        variable is empty or absent.  When *False*, return ``None``
        instead.

    Returns
    -------
    The variable's value, or ``None`` when *required* is ``False``
    and the variable is missing.

    Notes
    -----
    This helper never prints or logs the value, so API keys stay safe.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        if required:
            raise MissingEnvVarError(name)
        return None
    return value


def ensure_outputs_dir() -> Path:
    """Create the outputs/ directory if it does not exist and return its path."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUTS_DIR
