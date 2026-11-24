"""Verify the asset inventory is clearly a placeholder, not generated media."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from validate_storyboard import STORYBOARD_PATH


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "MEDIA_PLACEHOLDERS.json"


class TestMediaPlaceholders(unittest.TestCase):
    def test_inventory_lists_missing_assets_without_faking_media_files(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        storyboard = json.loads(STORYBOARD_PATH.read_text(encoding="utf-8"))
        assets = manifest["assets"]

        self.assertEqual(manifest["status"], "PLACEHOLDERS_ONLY")
        self.assertFalse(manifest["generated_media"])
        self.assertFalse(manifest["provider_requests_made"])
        self.assertIn("not media", manifest["notice"].lower())
        self.assertTrue(all(asset["is_placeholder"] for asset in assets))
        self.assertEqual(
            len({asset["asset_id"] for asset in assets}),
            len(assets),
        )
        self.assertTrue(
            {
                "reference-almaz",
                "reference-dawit",
                "reference-visual-style",
                "narration-amharic",
                "music-score",
                "english-subtitles",
                "subtitle-end-card-font",
                "radio-cut",
                "final-vertical",
                "final-horizontal",
            }.issubset({asset["asset_id"] for asset in assets})
        )

        scenes = storyboard["scenes"]
        for stage, extension in (("keyframes", "png"), ("moving_shots", "mp4")):
            stage_assets = [asset for asset in assets if asset["stage"] == stage]
            expected_paths = {
                "outputs/assets/{}/shot-{:02}.{}".format(
                    stage, scene["scene_number"], extension
                )
                for scene in scenes
            }
            self.assertEqual(
                {asset["expected_path"] for asset in stage_assets},
                expected_paths,
            )

        for asset in assets:
            expected_path = asset["expected_path"]
            if expected_path and expected_path.startswith("outputs/"):
                self.assertFalse(
                    (PROJECT_ROOT / expected_path).exists(),
                    "A pending placeholder path now has a file; update its status.",
                )


if __name__ == "__main__":
    unittest.main()
