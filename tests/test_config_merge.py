import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import load_session_settings


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
            session_path.write_text(json.dumps({"x": "99", "label_text": "Custom"}), encoding="utf-8")

            with patch("app.config.DEFAULT_CONFIG_PATH", default_path):
                merged = load_session_settings(session_path)

            self.assertEqual(merged.x, 99)
            self.assertEqual(merged.y, 20)
            self.assertEqual(merged.label_text, "Custom")
            self.assertEqual(merged.station_name, "Station 01")


if __name__ == "__main__":
    unittest.main()

