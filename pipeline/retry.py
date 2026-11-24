"""Small, bounded retry helper for transient provider failures."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import TypeVar


Result = TypeVar("Result")


def retry_call(
    operation: Callable[[], Result],
    *,
    retry_on: tuple[type[Exception], ...],
    max_attempts: int = 3,
    initial_delay_seconds: float = 0.5,
    maximum_delay_seconds: float = 4.0,
    sleep: Callable[[float], None] = time.sleep,
) -> Result:
    """Run an operation, retrying only declared transient exceptions.

    The operation is called at most ``max_attempts`` times. Permanent errors
    and undeclared exception types are raised immediately. Provider wrappers
    should log every actual attempt inside ``operation`` so retries remain
    visible in ``runs.jsonl``.
    """
    if not callable(operation):
        raise TypeError("operation must be callable.")
    if (
        not isinstance(retry_on, tuple)
        or not retry_on
        or any(
            not isinstance(error_type, type)
            or not issubclass(error_type, Exception)
            for error_type in retry_on
        )
    ):
        raise TypeError("retry_on must be a non-empty tuple of Exception types.")
    if (
        isinstance(max_attempts, bool)
        or not isinstance(max_attempts, int)
        or max_attempts < 1
    ):
        raise ValueError("max_attempts must be a positive whole number.")
    if not callable(sleep):
        raise TypeError("sleep must be callable.")
    _validate_delay("initial_delay_seconds", initial_delay_seconds)
    _validate_delay("maximum_delay_seconds", maximum_delay_seconds)
    if maximum_delay_seconds < initial_delay_seconds:
        raise ValueError(
            "maximum_delay_seconds cannot be less than initial_delay_seconds."
        )

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except retry_on:
            if attempt == max_attempts:
                raise
            delay = min(
                initial_delay_seconds * (2 ** (attempt - 1)),
                maximum_delay_seconds,
            )
            sleep(delay)

    raise RuntimeError("Retry loop ended without a result or exception.")


def _validate_delay(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("{} must be a non-negative number.".format(name))
    if not math.isfinite(value) or value < 0:
        raise ValueError("{} must be a finite, non-negative number.".format(name))
