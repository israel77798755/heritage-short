"""Tests for safe, append-only model call logging."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.runlog import append_model_call


class TestRunLog(unittest.TestCase):
    def call(self, log_path: Path, **overrides):
        values = {
            "provider": "example-provider",
            "model": "example-model",
            "stage": "keyframes",
            "parameters": {"width": 512, "quality": "draft"},
            "seed": 42,
            "latency_ms": 1250,
            "cost": None,
            "currency": None,
            "cost_basis": None,
            "status": "succeeded",
        }
        values.update(overrides)
        return append_model_call(log_path, **values)

    def test_records_required_call_metadata_and_nullable_cost(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "runs.jsonl"
            self.call(log_path)

            record = json.loads(log_path.read_text(encoding="utf-8"))

        self.assertEqual(record["model"], "example-model")
        self.assertEqual(record["seed"], 42)
        self.assertEqual(record["latency_ms"], 1250)
        self.assertIsNone(record["cost"])
        self.assertIsNone(record["cost_basis"])
        self.assertEqual(record["status"], "succeeded")

    def test_redacts_sensitive_fields_and_common_secret_strings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "runs.jsonl"
            self.call(
                log_path,
                parameters={
                    "width": 512,
                    "GEMINI_API_KEY": "not-a-real-key-123456789",
                    "note": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
                    "nested": {"access_token": "another-secret-value"},
                },
            )

            raw_log = log_path.read_text(encoding="utf-8")
            record = json.loads(raw_log)

        self.assertNotIn("not-a-real-key-123456789", raw_log)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", raw_log)
        self.assertNotIn("another-secret-value", raw_log)
        self.assertEqual(record["parameters"]["GEMINI_API_KEY"], "[REDACTED]")
        self.assertEqual(record["parameters"]["nested"]["access_token"], "[REDACTED]")
        self.assertIn("[REDACTED]", record["parameters"]["note"])

    def test_appends_one_json_record_per_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "runs.jsonl"
            self.call(log_path, status="succeeded")
            self.call(log_path, status="failed", attempt=2, error_type="TimeoutError")

            records = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]["attempt"], 2)
        self.assertEqual(records[1]["error_type"], "TimeoutError")

    def test_records_missing_seed_and_cost_as_null(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "runs.jsonl"
            self.call(log_path, seed=None, cost=None)

            record = json.loads(log_path.read_text(encoding="utf-8"))

        self.assertIsNone(record["seed"])
        self.assertIsNone(record["cost"])

    def test_redacts_credential_patterns_in_top_level_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "runs.jsonl"
            self.call(
                log_path,
                provider="provider api_key=not-a-real-secret-value",
                error_type="Bearer abcdefghijklmnopqrstuvwxyz",
            )

            raw_log = log_path.read_text(encoding="utf-8")
            record = json.loads(raw_log)

        self.assertNotIn("not-a-real-secret-value", raw_log)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", raw_log)
        self.assertIn("[REDACTED]", record["provider"])
        self.assertEqual(record["error_type"], "[REDACTED]")

    def test_invalid_call_does_not_create_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "runs.jsonl"
            with self.assertRaises(ValueError):
                self.call(log_path, latency_ms=-1)

        self.assertFalse(log_path.exists())

    def test_rejects_non_json_parameter_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "runs.jsonl"
            with self.assertRaises(TypeError):
                self.call(log_path, parameters={"unsupported": object()})

        self.assertFalse(log_path.exists())


if __name__ == "__main__":
    unittest.main()
