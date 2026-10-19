"""Resolve project locations without using a Git root or the caller's cwd."""

import json
import os
from pathlib import Path
import re


MANIFEST_NAMES = ("addon-workspace.local.json", "addon-workspace.json", "addon-workspace.example.json")
TOOLING_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ID = re.compile(r"[A-Za-z][A-Za-z0-9._-]*\Z")


def contained_path(root, value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty relative path")
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"{label} must be relative")
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"{label} escapes its root")
    return target


def find_workspace(explicit=None):
    selected = explicit or os.environ.get("ADDON_WORKSPACE_ROOT")
    if selected:
        root = Path(selected).expanduser().resolve()
        if not any((root / name).is_file() for name in MANIFEST_NAMES):
            raise ValueError(f"workspace manifest not found in: {root}")
        return root
    # The installed tool's ancestors also work when invoked from an unrelated cwd.
    roots = []
    for start in (Path.cwd().resolve(), TOOLING_ROOT):
        for root in (start, *start.parents):
            if root not in roots:
                roots.append(root)
    # A real workspace configuration takes precedence over the tool's example.
    for name in MANIFEST_NAMES:
        for root in roots:
            if (root / name).is_file():
                return root
    raise ValueError("cannot find a workspace manifest; pass --workspace or ADDON_WORKSPACE_ROOT")


def load_workspace(explicit=None):
    root = find_workspace(explicit)
    manifest = next(root / name for name in MANIFEST_NAMES if (root / name).is_file())
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid workspace manifest: {error}") from error
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("workspace manifest version must be 1")
    projects = data.get("projects")
    if not isinstance(projects, dict):
        raise ValueError("workspace manifest projects must be an object")
    for project_id, config in projects.items():
        if not PROJECT_ID.fullmatch(project_id) or not isinstance(config, dict):
            raise ValueError(f"invalid project entry: {project_id}")
        project = contained_path(root, config.get("path"), f"{project_id}.path")
        contained_path(project, config.get("payload", "."), f"{project_id}.payload")
    return root, projects


def resolve_project(project_id, explicit=None):
    root, projects = load_workspace(explicit)
    if project_id not in projects:
        raise ValueError(f"unknown project: {project_id}")
    config = projects[project_id]
    project = contained_path(root, config["path"], f"{project_id}.path")
    payload = contained_path(project, config.get("payload", "."), f"{project_id}.payload")
    for label, directory in (("project_root", project), ("payload_root", payload)):
        if not directory.is_dir():
            raise ValueError(f"{label} does not exist: {directory}")
    return {
        "project_id": project_id,
        "workspace_root": str(root),
        "tooling_root": str(TOOLING_ROOT),
        "project_root": str(project),
        "payload_root": str(payload),
    }
