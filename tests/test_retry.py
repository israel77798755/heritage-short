"""Tests for bounded retries on explicitly transient exceptions."""

from __future__ import annotations

import unittest

from pipeline.retry import retry_call


class TemporaryProviderError(Exception):
    """Represents a retryable network or rate-limit error in tests."""


class PermanentProviderError(Exception):
    """Represents a non-retryable provider error in tests."""


class TestRetryCall(unittest.TestCase):
    def test_retries_transient_errors_then_returns_result(self) -> None:
        attempts = []
        delays = []

        def operation():
            attempts.append(len(attempts) + 1)
            if len(attempts) < 3:
                raise TemporaryProviderError("temporary")
            return "complete"

        result = retry_call(
            operation,
            retry_on=(TemporaryProviderError,),
            max_attempts=3,
            initial_delay_seconds=0.25,
            maximum_delay_seconds=1.0,
            sleep=delays.append,
        )

        self.assertEqual(result, "complete")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(delays, [0.25, 0.5])

    def test_does_not_retry_permanent_errors(self) -> None:
        attempts = []
        delays = []

        def operation():
            attempts.append(True)
            raise PermanentProviderError("invalid request")

        with self.assertRaises(PermanentProviderError):
            retry_call(
                operation,
                retry_on=(TemporaryProviderError,),
                sleep=delays.append,
            )

        self.assertEqual(len(attempts), 1)
        self.assertEqual(delays, [])

    def test_raises_after_maximum_attempts(self) -> None:
        attempts = []

        def operation():
            attempts.append(True)
            raise TemporaryProviderError("still unavailable")

        with self.assertRaisesRegex(TemporaryProviderError, "still unavailable"):
            retry_call(
                operation,
                retry_on=(TemporaryProviderError,),
                max_attempts=2,
                sleep=lambda delay: None,
            )

        self.assertEqual(len(attempts), 2)

    def test_invalid_retry_configuration_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            retry_call(lambda: None, retry_on=(TemporaryProviderError,), max_attempts=0)

        with self.assertRaises(TypeError):
            retry_call(lambda: None, retry_on=(BaseException,))

        with self.assertRaises(ValueError):
            retry_call(
                lambda: None,
                retry_on=(TemporaryProviderError,),
                initial_delay_seconds=2.0,
                maximum_delay_seconds=1.0,
            )


if __name__ == "__main__":
    unittest.main()
