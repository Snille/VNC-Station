import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.tools import import_config_bundle


class ImportConfigBundleTests(unittest.TestCase):
    def test_import_config_bundle_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root_dir = base / "repo"
            root_dir.mkdir()
            zip_path = base / "bundle.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("vnc-view/../../escape.json", "{}")

            with patch("app.tools.ROOT_DIR", root_dir):
                with self.assertRaises(ValueError):
                    import_config_bundle(zip_path)

    def test_import_config_bundle_imports_allowed_paths_inside_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root_dir = base / "repo"
            root_dir.mkdir()
            zip_path = base / "bundle.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("vnc-view/sample.json", '{"x":"1"}')
                zf.writestr("default.json", '{"station_name":"Station 01"}')

            with patch("app.tools.ROOT_DIR", root_dir):
                applied = import_config_bundle(zip_path)

            self.assertEqual(len(applied), 2)
            self.assertTrue((root_dir / "vnc-view" / "sample.json").exists())
            self.assertTrue((root_dir / "default.json").exists())


if __name__ == "__main__":
    unittest.main()
