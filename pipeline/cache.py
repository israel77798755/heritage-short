"""Content-based cache helpers for generated per-shot assets."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


_STAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def _file_sha256(path: Path) -> str:
    """Return a file's SHA-256 digest without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_cache_key(
    stage: str,
    inputs: Mapping[str, Any],
    reference_files: Mapping[str, Path] | None = None,
) -> str:
    """Build a stable key from stage inputs and the contents of reference files.

    Callers should include every generation-affecting value in ``inputs``,
    such as the shot ID, prompt, provider, model, parameters, and seed. File
    names alone are not sufficient for references, so their contents are
    hashed too.
    """
    if not isinstance(stage, str) or not _STAGE_PATTERN.fullmatch(stage):
        raise ValueError("stage must contain only lowercase letters, digits, '_' or '-'.")
    if not isinstance(inputs, Mapping):
        raise TypeError("inputs must be a mapping of generation inputs.")

    reference_hashes: dict[str, str] = {}
    for label, file_path in sorted((reference_files or {}).items()):
        if not isinstance(label, str) or not label.strip():
            raise ValueError("Reference file labels must be non-empty strings.")
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError("Reference file does not exist: {}".format(path))
        reference_hashes[label] = _file_sha256(path)

    payload = {
        "stage": stage,
        "inputs": inputs,
        "reference_sha256": reference_hashes,
    }
    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def cache_output_path(
    outputs_dir: Path,
    stage: str,
    cache_key: str,
    file_extension: str,
) -> Path:
    """Return the deterministic path for one cached output asset."""
    if not isinstance(stage, str) or not _STAGE_PATTERN.fullmatch(stage):
        raise ValueError("stage must contain only lowercase letters, digits, '_' or '-'.")
    if not isinstance(cache_key, str) or not _SHA256_PATTERN.fullmatch(cache_key):
        raise ValueError("cache_key must be a lowercase SHA-256 hex digest.")
    if (
        not isinstance(file_extension, str)
        or not file_extension.startswith(".")
        or len(file_extension) < 2
        or "/" in file_extension
        or "\\" in file_extension
    ):
        raise ValueError("file_extension must be a file suffix such as '.png'.")

    return Path(outputs_dir) / "cache" / stage / (cache_key + file_extension)


def find_cached_asset(path: Path) -> Path | None:
    """Return an existing non-empty cached file, or None for a cache miss.

    An empty file is treated as a corrupt cache entry and reported rather
    than silently accepted as a successful generated asset.
    """
    path = Path(path)
    if not path.exists():
        return None
    if not path.is_file():
        raise OSError("Cached asset path is not a file: {}".format(path))
    if path.stat().st_size == 0:
        raise OSError("Cached asset is empty and may be incomplete: {}".format(path))
    return path
