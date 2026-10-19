import hashlib
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile

from addon_tools.package import verify_package


CLI = Path(__file__).resolve().parents[1] / "bin/addon-workspace.py"


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="addon package ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        self.archive = self.root / "example.mnaddon"
        self.files = {
            "mnaddon.json": json.dumps({"addonid": "example.extension.addon", "version": "1.0.0"}).encode(),
            "main.js": b"console.log('offline');\n",
            "assets/icon.txt": b"example asset\n",
        }
        for name, content in self.files.items():
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.write_package()

    def write_package(self, extra=()):
        with warnings.catch_warnings(), zipfile.ZipFile(self.archive, "w") as archive:
            warnings.simplefilter("ignore", UserWarning)
            for name, content in self.files.items():
                archive.writestr(name, content)
            for name, content in extra:
                archive.writestr(name, content)

    def test_integrity_manifest_digest_and_full_source_parity(self):
        result = verify_package(self.archive, self.source, "example.extension.addon", "1.0.0")
        self.assertEqual(result["file_count"], 3)
        self.assertEqual(result["compared_files"], sorted(self.files))
        self.assertEqual(result["sha256"], hashlib.sha256(self.archive.read_bytes()).hexdigest())
        verify_package(self.archive, expect_sha256=result["sha256"].upper())

    def test_expected_identity_version_and_digest_fail_closed(self):
        for kwargs in ({"expect_addon_id": "other"}, {"expect_version": "2.0"},
                       {"expect_sha256": "0" * 64}, {"expect_sha256": "not-a-digest"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                verify_package(self.archive, **kwargs)

    def test_missing_or_invalid_manifest_and_entry(self):
        original = dict(self.files)
        for name, content in (("mnaddon.json", None), ("main.js", None),
                              ("mnaddon.json", b"invalid"), ("mnaddon.json", b"[]"),
                              ("mnaddon.json", b'{"addonid":"example","version":1}')):
            self.files = dict(original)
            if content is None:
                self.files.pop(name)
            else:
                self.files[name] = content
            self.write_package()
            with self.subTest(name=name, content=content), self.assertRaises(ValueError):
                verify_package(self.archive)

    def test_source_mismatch_and_selected_file_comparison(self):
        (self.source / "assets/icon.txt").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "source/package mismatch"):
            verify_package(self.archive, self.source)
        result = verify_package(self.archive, self.source, compare_files=["main.js"])
        self.assertEqual(result["compared_files"], ["main.js"])
        with self.assertRaisesRegex(ValueError, "requires --source"):
            verify_package(self.archive, compare_files=["main.js"])

    def test_required_files_and_missing_source(self):
        with self.assertRaisesRegex(ValueError, "required archive file missing"):
            verify_package(self.archive, required_files=["missing.js"])
        (self.source / "main.js").unlink()
        with self.assertRaisesRegex(ValueError, "source file missing"):
            verify_package(self.archive, self.source)

    def test_unsafe_duplicate_and_symlink_paths(self):
        for name in ("../escape", "/absolute", "assets/../escape", "assets\\escape", "C:/escape", "assets//icon.txt", "main.js"):
            self.write_package([(name, b"bad")])
            with self.subTest(name=name), self.assertRaises(ValueError):
                verify_package(self.archive)
        link = zipfile.ZipInfo("link.js")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.write_package([(link, b"main.js")])
        with self.assertRaisesRegex(ValueError, "symlink"):
            verify_package(self.archive)

    def test_source_symlink_escape_is_rejected(self):
        outside = self.root / "outside.js"
        outside.write_bytes(self.files["main.js"])
        (self.source / "main.js").unlink()
        (self.source / "main.js").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "outside source"):
            verify_package(self.archive, self.source)

    def test_crc_corruption_fails(self):
        with zipfile.ZipFile(self.archive) as archive:
            info = archive.getinfo("main.js")
        data = bytearray(self.archive.read_bytes())
        name_length, extra_length = struct.unpack_from("<HH", data, info.header_offset + 26)
        start = info.header_offset + 30 + name_length + extra_length
        data[start] ^= 1
        self.archive.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "integrity check failed"):
            verify_package(self.archive)

    def test_cli_reports_digest_without_a_workspace(self):
        result = subprocess.run([
            sys.executable, str(CLI), "verify-package", str(self.archive), "--source", str(self.source)
        ], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["addonid"], "example.extension.addon")

    def test_non_zip_failure_is_reported_without_traceback(self):
        self.archive.write_text("not a zip")
        result = subprocess.run([
            sys.executable, str(CLI), "verify-package", str(self.archive)
        ], text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)
