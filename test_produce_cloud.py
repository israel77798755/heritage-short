"""Unit tests for cloud image provider error handling, timeouts, resume, and caching."""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import types
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

if "edge_tts" not in sys.modules:
    edge_tts_stub = types.ModuleType("edge_tts")
    edge_tts_stub.Communicate = object  # type: ignore[attr-defined]
    sys.modules["edge_tts"] = edge_tts_stub

from scripts import produce_cloud


def _sample_png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (64, 64), color=(180, 120, 60)).save(buf, format="PNG")
    return buf.getvalue()


class TestProduceCloudAuthAndErrors(unittest.TestCase):
    """Verify auth failures fail fast, timeouts/resume work, and no fake images are created."""

    def test_http_401_fails_immediately_without_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            out_path = tmp / "shot-01.png"
            runs_path = tmp / "runs.jsonl"
            err_401 = urllib.error.HTTPError(
                url="https://aihorde.net/api/v2/generate/async",
                code=401,
                msg="Unauthorized",
                hdrs=None,
                fp=None,
            )

            with (
                patch.object(produce_cloud, "RUNS_JSONL_PATH", runs_path),
                patch.object(produce_cloud, "_http_json", side_effect=err_401) as mock_http,
                patch.object(produce_cloud.time, "sleep") as mock_sleep,
            ):
                with self.assertRaises(produce_cloud.ProviderAuthError) as ctx:
                    produce_cloud._fetch_aihorde_image(
                        "test prompt", seed=1001, out_path=out_path, label="shot-01"
                    )

            self.assertEqual(mock_http.call_count, 1)
            mock_sleep.assert_not_called()
            self.assertIn("HTTP 401", str(ctx.exception))
            self.assertIn("aborting without retrying", str(ctx.exception))
            self.assertFalse(out_path.exists())
            log_entry = json.loads(runs_path.read_text(encoding="utf-8").strip())
            self.assertEqual(log_entry["status"], "error")
            self.assertEqual(log_entry["http_status"], 401)

    def test_http_403_fails_immediately_without_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            out_path = tmp / "shot-02.png"
            runs_path = tmp / "runs.jsonl"
            err_403 = urllib.error.HTTPError(
                url="https://aihorde.net/api/v2/generate/async",
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=None,
            )

            with (
                patch.object(produce_cloud, "RUNS_JSONL_PATH", runs_path),
                patch.object(produce_cloud, "_http_json", side_effect=err_403) as mock_http,
                patch.object(produce_cloud.time, "sleep") as mock_sleep,
            ):
                with self.assertRaises(produce_cloud.ProviderAuthError):
                    produce_cloud._fetch_aihorde_image(
                        "test prompt", seed=1002, out_path=out_path, label="shot-02"
                    )

            self.assertEqual(mock_http.call_count, 1)
            mock_sleep.assert_not_called()
            self.assertFalse(out_path.exists())

    def test_http_429_rate_limit_retries_and_reports_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            out_path = tmp / "shot-03.png"
            runs_path = tmp / "runs.jsonl"
            err_429 = urllib.error.HTTPError(
                url="https://aihorde.net/api/v2/generate/async",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "12"},
                fp=None,
            )

            with (
                patch.object(produce_cloud, "RUNS_JSONL_PATH", runs_path),
                patch.object(produce_cloud, "_http_json", side_effect=err_429) as mock_http,
                patch.object(produce_cloud.time, "sleep") as mock_sleep,
            ):
                with self.assertRaises(produce_cloud.ProviderError) as ctx:
                    produce_cloud._fetch_aihorde_image(
                        "test prompt",
                        seed=1003,
                        out_path=out_path,
                        label="shot-03",
                        max_submit_attempts=2,
                    )

            self.assertEqual(mock_http.call_count, 2)
            mock_sleep.assert_called_once_with(12.0)
            self.assertIn("HTTP 429", str(ctx.exception))
            self.assertFalse(out_path.exists())

    def test_http_503_retries_and_raises_provider_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            out_path = tmp / "shot-03b.png"
            runs_path = tmp / "runs.jsonl"
            err_503 = urllib.error.HTTPError(
                url="https://aihorde.net/api/v2/generate/async",
                code=503,
                msg="Service Unavailable",
                hdrs=None,
                fp=None,
            )

            with (
                patch.object(produce_cloud, "RUNS_JSONL_PATH", runs_path),
                patch.object(produce_cloud, "_http_json", side_effect=err_503) as mock_http,
                patch.object(produce_cloud.time, "sleep"),
            ):
                with self.assertRaises(produce_cloud.ProviderError) as ctx:
                    produce_cloud._fetch_aihorde_image(
                        "test prompt",
                        seed=1003,
                        out_path=out_path,
                        label="shot-03b",
                        max_submit_attempts=3,
                    )

            self.assertEqual(mock_http.call_count, 3)
            self.assertIn("HTTP 503", str(ctx.exception))
            self.assertFalse(out_path.exists())

    def test_faulted_job_fails_without_fake_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            out_path = tmp / "shot-fault.png"
            runs_path = tmp / "runs.jsonl"
            responses = [
                {"id": "job-fault"},
                {"done": False, "faulted": True, "is_possible": True},
            ]

            with (
                patch.object(produce_cloud, "RUNS_JSONL_PATH", runs_path),
                patch.object(produce_cloud, "_http_json", side_effect=responses),
            ):
                with self.assertRaises(produce_cloud.ProviderError) as ctx:
                    produce_cloud._fetch_aihorde_image(
                        "test prompt", seed=1004, out_path=out_path, label="shot-fault"
                    )

            self.assertIn("faulted", str(ctx.exception))
            self.assertFalse(out_path.exists())

    def test_overall_timeout_reports_completed_and_remaining_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            out_path = tmp / "shot-timeout.png"
            runs_path = tmp / "runs.jsonl"

            with (
                patch.object(produce_cloud, "RUNS_JSONL_PATH", runs_path),
                patch.object(produce_cloud.time, "monotonic", return_value=1000.0),
                patch.object(produce_cloud, "_http_json") as mock_http,
            ):
                with self.assertRaises(produce_cloud.ProviderError) as ctx:
                    produce_cloud._fetch_aihorde_image(
                        "test prompt",
                        seed=1005,
                        out_path=out_path,
                        label="shot-timeout",
                        overall_deadline=999.0,
                        completed_count=5,
                        total_count=12,
                    )

            mock_http.assert_not_called()
            msg = str(ctx.exception)
            self.assertIn("5 of 12 images completed", msg)
            self.assertIn("7 remaining", msg)
            self.assertFalse(out_path.exists())

    def test_timeout_configuration_reads_env_and_cli(self) -> None:
        with patch.dict(os.environ, {"VISUAL_OVERALL_TIMEOUT_SECONDS": "420"}):
            self.assertEqual(produce_cloud.resolve_overall_visual_timeout(), 420.0)
            self.assertEqual(produce_cloud.resolve_overall_visual_timeout(180.0), 180.0)

    def test_aihorde_async_success_saves_png_and_logs_model_and_zero_cost(self) -> None:
        png_b64 = base64.b64encode(_sample_png_bytes()).decode("ascii")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            out_path = tmp / "shot-04.png"
            runs_path = tmp / "runs.jsonl"

            responses = [
                {"id": "job-123"},
                {"done": True, "faulted": False, "is_possible": True},
                {
                    "generations": [
                        {
                            "img": png_b64,
                            "model": "Deliberate",
                            "worker_name": "VolunteerGPU-1",
                        }
                    ]
                },
            ]

            with (
                patch.object(produce_cloud, "RUNS_JSONL_PATH", runs_path),
                patch.object(produce_cloud, "_http_json", side_effect=responses),
            ):
                was_generated = produce_cloud._fetch_aihorde_image(
                    "test prompt", seed=1004, out_path=out_path, label="shot-04"
                )

            self.assertTrue(was_generated)
            self.assertTrue(out_path.is_file())
            with Image.open(out_path) as saved:
                self.assertEqual(saved.format, "PNG")
            log_entry = json.loads(runs_path.read_text(encoding="utf-8").strip())
            self.assertEqual(log_entry["status"], "ok")
            self.assertEqual(log_entry["provider"], "aihorde.net")
            self.assertEqual(log_entry["model"], "Deliberate")
            self.assertEqual(log_entry["cost_usd"], 0.0)
            self.assertEqual(log_entry["seed"], 1004)

    def test_cached_image_skips_network_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            out_path = tmp / "shot-05.png"
            out_path.write_bytes(b"x" * 12_000)

            with patch.object(produce_cloud, "_http_json") as mock_http:
                was_generated = produce_cloud._fetch_aihorde_image(
                    "test prompt", seed=1005, out_path=out_path, label="shot-05"
                )

            self.assertFalse(was_generated)
            mock_http.assert_not_called()

    def test_resume_skips_cached_images_and_generates_remaining(self) -> None:
        png_b64 = base64.b64encode(_sample_png_bytes()).decode("ascii")
        storyboard = {
            "visual_style": {"style_block": "warm cinematic realism"},
            "characters": {
                "mother": {"description": "Almaz"},
                "child": {"description": "Dawit"},
            },
            "scenes": [
                {"scene_number": 1, "image_prompt": "Scene 1", "seed": 1001},
                {"scene_number": 2, "image_prompt": "Scene 2", "seed": 1002},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            refs_dir = tmp / "assets" / "references"
            keyframes_dir = tmp / "assets" / "keyframes"
            refs_dir.mkdir(parents=True)
            keyframes_dir.mkdir(parents=True)
            # Pre-populate 3 cached files; only shot-02 should be generated on resume.
            (refs_dir / "mother_almaz.png").write_bytes(b"x" * 12_000)
            (refs_dir / "child_dawit.png").write_bytes(b"x" * 12_000)
            (keyframes_dir / "shot-01.png").write_bytes(b"x" * 12_000)

            responses = [
                {"id": "job-resume"},
                {"done": True, "faulted": False, "is_possible": True},
                {"generations": [{"img": png_b64, "model": "Deliberate"}]},
            ]

            with (
                patch.object(produce_cloud, "OUTPUTS_DIR", tmp),
                patch.object(produce_cloud, "RUNS_JSONL_PATH", tmp / "runs.jsonl"),
                patch.object(produce_cloud, "_http_json", side_effect=responses) as mock_http,
            ):
                summary = produce_cloud.generate_visuals(storyboard)

            self.assertEqual(summary, {"total": 4, "completed": 4, "generated": 1, "cached": 3})
            self.assertEqual(mock_http.call_count, 3)
            self.assertTrue((keyframes_dir / "shot-02.png").is_file())

    def test_character_references_generate_before_scenes(self) -> None:
        storyboard = {
            "visual_style": {"style_block": "warm cinematic realism"},
            "characters": {
                "mother": {"description": "Almaz"},
                "child": {"description": "Dawit"},
            },
            "scenes": [
                {"scene_number": 1, "image_prompt": "Scene 1", "seed": 1001},
                {"scene_number": 2, "image_prompt": "Scene 2", "seed": 1002},
            ],
        }
        seen_labels: list[str] = []

        def fake_fetch(**kwargs):
            seen_labels.append(kwargs["label"])
            return True

        with patch.object(produce_cloud, "_fetch_aihorde_image", side_effect=fake_fetch):
            produce_cloud.generate_visuals(storyboard)

        self.assertEqual(
            seen_labels,
            ["ref-mother-almaz", "ref-child-dawit", "shot-01", "shot-02"],
        )


if __name__ == "__main__":
    unittest.main()
