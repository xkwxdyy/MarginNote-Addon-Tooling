import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from addon_tools.workspace import find_workspace, load_workspace, resolve_project


CLI = Path(__file__).resolve().parents[1] / "bin/addon-workspace.py"


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="addon workspace ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "Projects/example addon"
        (self.project / "plugin").mkdir(parents=True)
        self.config = {"version": 1, "projects": {
            "example-addon": {"path": "Projects/example addon", "payload": "plugin"}
        }}
        self.write_config()
        self.env = dict(os.environ)
        self.env.pop("ADDON_WORKSPACE_ROOT", None)

    def write_config(self, name="addon-workspace.local.json"):
        (self.root / name).write_text(json.dumps(self.config), encoding="utf-8")

    def test_explicit_workspace_with_spaces(self):
        result = resolve_project("example-addon", self.root)
        self.assertEqual(result["workspace_root"], str(self.root))
        self.assertEqual(result["project_root"], str(self.project))
        self.assertEqual(result["payload_root"], str(self.project / "plugin"))
        self.assertEqual(Path(result["tooling_root"]), CLI.parent.parent)

    def test_manifest_fallback_and_local_precedence(self):
        (self.root / "addon-workspace.local.json").unlink()
        self.write_config("addon-workspace.example.json")
        self.assertEqual(find_workspace(self.root), self.root)
        self.write_config("addon-workspace.json")
        (self.root / "addon-workspace.local.json").write_text("invalid")
        with self.assertRaisesRegex(ValueError, "invalid workspace manifest"):
            load_workspace(self.root)

    def test_discovery_prefers_real_workspace_over_tool_example(self):
        tooling = self.root / "Tooling/public"
        tooling.mkdir(parents=True)
        (tooling / "addon-workspace.example.json").write_text("{}")
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(tooling)
        with patch.dict(os.environ, self.env, clear=True), patch("addon_tools.workspace.TOOLING_ROOT", tooling):
            self.assertEqual(find_workspace(), self.root)

    def test_default_payload(self):
        self.config["projects"]["example-addon"].pop("payload")
        self.write_config()
        self.assertEqual(resolve_project("example-addon", self.root)["payload_root"], str(self.project))

    def test_unknown_or_missing_project_fails(self):
        with self.assertRaisesRegex(ValueError, "unknown project"):
            resolve_project("missing", self.root)
        self.config["projects"]["missing"] = {"path": "Projects/missing"}
        self.write_config()
        self.assertIn("missing", load_workspace(self.root)[1])
        with self.assertRaisesRegex(ValueError, "project_root does not exist"):
            resolve_project("missing", self.root)

    def test_missing_payload_fails(self):
        self.config["projects"]["example-addon"]["payload"] = "missing"
        self.write_config()
        with self.assertRaisesRegex(ValueError, "payload_root does not exist"):
            resolve_project("example-addon", self.root)

    def test_absolute_and_parent_escape_fail(self):
        for field, value in (("path", str(self.project)), ("path", "../outside"), ("payload", "../../outside")):
            with self.subTest(field=field, value=value):
                config = self.config["projects"]["example-addon"]
                saved = config[field]
                config[field] = value
                self.write_config()
                with self.assertRaises(ValueError):
                    load_workspace(self.root)
                config[field] = saved

    def test_symlink_escape_fails(self):
        outside = self.root / "other-project"
        outside.mkdir()
        (self.project / "escape").symlink_to(outside, target_is_directory=True)
        self.config["projects"]["example-addon"]["payload"] = "escape"
        self.write_config()
        with self.assertRaisesRegex(ValueError, "escapes"):
            load_workspace(self.root)

    def test_invalid_version_or_project_entry_fails(self):
        for config in ({"version": True, "projects": {}}, {"version": 1, "projects": []},
                       {"version": 1, "projects": {"../bad": {"path": "Projects/bad"}}}):
            self.config = config
            self.write_config()
            with self.assertRaises(ValueError):
                load_workspace(self.root)

    def test_cli_from_unrelated_cwd_and_environment_precedence(self):
        env = dict(self.env, ADDON_WORKSPACE_ROOT=str(self.root / "missing"))
        result = subprocess.run([
            sys.executable, str(CLI), "--workspace", str(self.root),
            "resolve", "example-addon", "--field", "payload_root"
        ], cwd=self.root.parent, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.project / "plugin"))

    def test_cli_failure_has_no_partial_json(self):
        result = subprocess.run([
            sys.executable, str(CLI), "--workspace", str(self.root), "resolve", "unknown"
        ], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("unknown project", result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node is unavailable")
    def test_node_can_consume_cli_json(self):
        script = """const {execFileSync}=require('node:child_process');
const [python,tool,workspace]=process.argv.slice(1);
const result=JSON.parse(execFileSync(python,[tool,'--workspace',workspace,'resolve','example-addon'],{encoding:'utf8'}));
process.stdout.write(result.payload_root);"""
        result = subprocess.run([
            "node", "-e", script, sys.executable, str(CLI), str(self.root)
        ], cwd=self.root.parent, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(self.project / "plugin"))
