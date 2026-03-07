import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import load_session_settings, resolve_ks_target


class ConfigMergeTests(unittest.TestCase):
    def test_load_session_settings_merges_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            default_path = base / "default.json"
            session_path = base / "sample.json"

            default_path.write_text(
                json.dumps(
                    {
                        "x": "10",
                        "y": "20",
                        "width": "1000",
                        "height": "700",
                        "label_text": "Default",
                        "label_x": "1",
                        "label_y": "2",
                        "label_bg": "white",
                        "label_width": "100",
                        "label_height": "40",
                        "label_font": "18",
                        "label_font_color": "black",
                        "label_border_size": "2",
                        "label_border_color": "green",
                        "station_name": "Station 01",
                    }
                ),
                encoding="utf-8",
            )
            session_path.write_text(
                json.dumps(
                    {
                        "x": "99",
                        "label_text": "Custom",
                        "position_name": "Position 01",
                        "linked_session": "Target B|control",
                        "ks": r"G:\Path\to\file.xlsx",
                        "ks_button_text": "Manual",
                        "ha_sensors": ["sensor.temp_a", "sensor.temp_b"],
                    }
                ),
                encoding="utf-8",
            )

            with patch("app.config.DEFAULT_CONFIG_PATH", default_path):
                merged = load_session_settings(session_path)

            self.assertEqual(merged.x, 99)
            self.assertEqual(merged.y, 20)
            self.assertEqual(merged.label_text, "Custom")
            self.assertEqual(merged.station_name, "Station 01")
            self.assertEqual(merged.position_name, "Position 01")
            self.assertEqual(merged.linked_session, "Target B|control")
            self.assertEqual(merged.ks, r"G:\Path\to\file.xlsx")
            self.assertEqual(merged.ks_button_text, "Manual")
            self.assertEqual(merged.ha_sensors, ["sensor.temp_a", "sensor.temp_b"])

    def test_resolve_ks_target_uses_latest_file_in_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            older = base / "older.txt"
            newer = base / "newer.txt"
            older.write_text("a", encoding="utf-8")
            newer.write_text("b", encoding="utf-8")
            os.utime(older, (1000, 1000))
            os.utime(newer, (2000, 2000))

            target, error = resolve_ks_target(str(base))

            self.assertEqual(target, newer)
            self.assertEqual(error, "")

    def test_resolve_ks_target_accepts_direct_file_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "doc.txt"
            file_path.write_text("x", encoding="utf-8")

            target, error = resolve_ks_target(str(file_path))

            self.assertEqual(target, file_path)
            self.assertEqual(error, "")

    def test_resolve_ks_target_reports_empty_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target, error = resolve_ks_target(temp_dir)

            self.assertIsNone(target)
            self.assertIn("No files found in Active Folder", error)


if __name__ == "__main__":
    unittest.main()
