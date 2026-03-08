import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import (
    clear_runtime_caches,
    load_session_settings,
    resolve_ks_target,
    save_json,
    scan_positions,
    set_json_warning_reporter,
)


class ConfigMergeTests(unittest.TestCase):
    def setUp(self):
        clear_runtime_caches()
        set_json_warning_reporter(None)

    def tearDown(self):
        clear_runtime_caches()
        set_json_warning_reporter(None)

    def test_load_session_settings_merges_defaults(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            base = Path(temp_dir)
            default_path = base / "default.json"
            local_path = base / "default.local.json"
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

            with patch("app.config.DEFAULT_CONFIG_PATH", default_path), patch(
                "app.config.DEFAULT_LOCAL_CONFIG_PATH", local_path
            ):
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

    def test_invalid_json_warning_is_deduplicated_until_file_changes(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            base = Path(temp_dir)
            bad_path = base / "broken.json"
            warnings = []
            set_json_warning_reporter(warnings.append)

            bad_path.write_text("{invalid", encoding="utf-8")
            self.assertEqual(load_session_settings(bad_path).x, 1)
            self.assertEqual(load_session_settings(bad_path).x, 1)
            self.assertEqual(len(warnings), 1)

            bad_path.write_text("{still invalid", encoding="utf-8")
            clear_runtime_caches()
            set_json_warning_reporter(warnings.append)
            self.assertEqual(load_session_settings(bad_path).x, 1)
            self.assertEqual(len(warnings), 2)

    def test_scan_positions_cache_invalidates_after_save(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            base = Path(temp_dir)
            positions_dir = base / "vnc-positions"
            positions_dir.mkdir()
            first = positions_dir / "pos-a.json"
            second = positions_dir / "pos-b.json"

            save_json(first, {"name": "Pos A", "x": "10", "y": "20", "width": "100", "height": "200"})
            with patch("app.config.VNC_POSITIONS_DIR", positions_dir):
                names = [preset.name for preset in scan_positions()]
                self.assertEqual(names, ["Pos A"])

                save_json(
                    second,
                    {"name": "Pos B", "x": "30", "y": "40", "width": "300", "height": "400"},
                )
                names = [preset.name for preset in scan_positions()]
                self.assertEqual(names, ["Pos A", "Pos B"])


if __name__ == "__main__":
    unittest.main()
