"""Unit tests for validate_storyboard.py and schema/storyboard.schema.json."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validate_storyboard import (
    SCHEMA_PATH,
    STORYBOARD_PATH,
    StoryboardValidationError,
    main,
    require_valid_storyboard,
    validate_storyboard,
)


class TestValidateStoryboard(unittest.TestCase):
    """Verify schema and semantic validation rules for storyboard.json."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.valid_storyboard = json.loads(
            STORYBOARD_PATH.read_text(encoding="utf-8")
        )
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def fresh_storyboard(self) -> dict:
        """Return a deep copy of the valid storyboard for isolated mutation."""
        return copy.deepcopy(self.valid_storyboard)

    def test_repository_storyboard_is_valid(self) -> None:
        errors = validate_storyboard(self.valid_storyboard, schema=self.schema)
        self.assertEqual(errors, [])

    def test_require_valid_storyboard_returns_data(self) -> None:
        data = require_valid_storyboard(STORYBOARD_PATH, SCHEMA_PATH)
        self.assertEqual(len(data["scenes"]), 10)

    def test_rejects_fewer_than_eight_scenes(self) -> None:
        sb = self.fresh_storyboard()
        sb["scenes"] = sb["scenes"][:7]
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("8-12" in err or "minItems" in err for err in errors))

    def test_rejects_more_than_twelve_scenes(self) -> None:
        sb = self.fresh_storyboard()
        while len(sb["scenes"]) < 13:
            extra = copy.deepcopy(sb["scenes"][-1])
            extra["scene_number"] = len(sb["scenes"]) + 1
            sb["scenes"].append(extra)
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("8-12" in err or "maxItems" in err for err in errors))

    def test_rejects_duration_outside_60_to_90_range(self) -> None:
        sb = self.fresh_storyboard()
        sb["target_duration_seconds"] = 50
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("60" in err and "90" in err for err in errors))

    def test_rejects_total_with_end_card_over_90_seconds(self) -> None:
        sb = self.fresh_storyboard()
        sb["target_duration_seconds"] = 88
        sb["scenes"][0]["duration_seconds"] += 13
        sb["end_card"]["duration_seconds"] = 3
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("exceeds 90 seconds" in err for err in errors))

    def test_rejects_mismatched_target_duration_sum(self) -> None:
        sb = self.fresh_storyboard()
        sb["scenes"][0]["duration_seconds"] += 1
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("total 76 seconds" in err for err in errors))

    def test_rejects_non_sequential_scene_numbers(self) -> None:
        sb = self.fresh_storyboard()
        sb["scenes"][1]["scene_number"] = 99
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("sequential" in err for err in errors))

    def test_rejects_non_amharic_narration(self) -> None:
        sb = self.fresh_storyboard()
        sb["scenes"][0]["narration"] = "This is English only."
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("Amharic" in err or "pattern" in err for err in errors))

    def test_rejects_empty_english_subtitle(self) -> None:
        sb = self.fresh_storyboard()
        sb["scenes"][0]["subtitle_en"] = "   "
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("subtitle_en" in err for err in errors))

    def test_rejects_missing_lesson_coverage(self) -> None:
        sb = self.fresh_storyboard()
        for scene in sb["scenes"]:
            if scene["lesson"] == "never_give_up":
                scene["lesson"] = "closing"
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("never_give_up" in err for err in errors))

    def test_rejects_missing_aspect_ratio(self) -> None:
        sb = self.fresh_storyboard()
        sb["aspect_ratios"] = ["16:9"]
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("9:16" in err or "minItems" in err for err in errors))

    def test_rejects_non_fictional_character(self) -> None:
        sb = self.fresh_storyboard()
        sb["characters"]["mother"]["fictional"] = False
        errors = validate_storyboard(sb, schema=self.schema)
        self.assertTrue(any("fictional" in err for err in errors))

    def test_require_valid_storyboard_raises_before_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_path = Path(tmp_dir) / "bad_storyboard.json"
            sb = self.fresh_storyboard()
            sb["scenes"][0]["subtitle_en"] = ""
            bad_path.write_text(json.dumps(sb), encoding="utf-8")
            with self.assertRaises(StoryboardValidationError):
                require_valid_storyboard(bad_path, SCHEMA_PATH)

    def test_cli_exit_codes(self) -> None:
        self.assertEqual(main([]), 0)
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_path = Path(tmp_dir) / "missing.json"
            self.assertEqual(main(["--storyboard", str(bad_path)]), 1)


if __name__ == "__main__":
    unittest.main()
