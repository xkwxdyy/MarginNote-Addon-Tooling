"""Read-only checks. Archives are never extracted and scripts are never run."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


def stream_sha256(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def sha256(path):
    with path.open("rb") as stream:
        return stream_sha256(stream)


def safe_name(name):
    parts = name.rstrip("/").split("/")
    if not name or "\\" in name or name.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise ValueError(f"unsafe archive path: {name!r}")
    if re.match(r"[A-Za-z]:", parts[0]):
        raise ValueError(f"unsafe archive path: {name!r}")
    return str(PurePosixPath(*parts))


def verify_package(archive_path, source=None, expect_addon_id=None, expect_version=None,
                   expect_sha256=None, compare_files=(), required_files=()):
    archive_path = Path(archive_path).expanduser().resolve()
    if not archive_path.is_file():
        raise ValueError(f"archive does not exist: {archive_path}")
    if compare_files and source is None:
        raise ValueError("--compare-file requires --source")
    digest = sha256(archive_path)
    if expect_sha256:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expect_sha256):
            raise ValueError("expected SHA-256 must contain 64 hexadecimal characters")
        if digest != expect_sha256.lower():
            raise ValueError("archive SHA-256 mismatch")
    with zipfile.ZipFile(archive_path) as archive:
        files = {}
        seen = set()
        for info in archive.infolist():
            name = safe_name(info.filename)
            if name in seen:
                raise ValueError(f"duplicate archive path: {name}")
            seen.add(name)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"archive symlink is not allowed: {name}")
            if info.flag_bits & 1:
                raise ValueError(f"encrypted archive entry: {name}")
            if not info.is_dir():
                files[name] = info
        bad_file = archive.testzip()
        if bad_file:
            raise ValueError(f"archive integrity check failed: {bad_file}")
        for name in ("mnaddon.json", "main.js", *required_files):
            name = safe_name(name)
            if name not in files:
                raise ValueError(f"required archive file missing: {name}")
        if files["mnaddon.json"].file_size > 1024 * 1024:
            raise ValueError("mnaddon.json exceeds 1 MiB")
        manifest = json.loads(archive.read("mnaddon.json").decode("utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("mnaddon.json must be an object")
        for field in ("addonid", "version"):
            if not isinstance(manifest.get(field), str) or not manifest[field].strip():
                raise ValueError(f"mnaddon.json {field} must be a nonempty string")
        if expect_addon_id and manifest["addonid"] != expect_addon_id:
            raise ValueError("manifest addonid mismatch")
        if expect_version and manifest["version"] != expect_version:
            raise ValueError("manifest version mismatch")
        checked = []
        if source is not None:
            source = Path(source).expanduser().resolve()
            if not source.is_dir():
                raise ValueError(f"source directory does not exist: {source}")
            for name in sorted(set(compare_files) if compare_files else files):
                name = safe_name(name)
                if name not in files:
                    raise ValueError(f"comparison file missing from archive: {name}")
                local = (source / name).resolve()
                if not local.is_relative_to(source) or not local.is_file():
                    raise ValueError(f"comparison source file missing or outside source: {name}")
                with archive.open(files[name]) as stream:
                    packaged_digest = stream_sha256(stream)
                if sha256(local) != packaged_digest:
                    raise ValueError(f"source/package mismatch: {name}")
                checked.append(name)
    return {
        "archive": str(archive_path), "sha256": digest,
        "addonid": manifest["addonid"], "version": manifest["version"],
        "file_count": len(files), "source_root": str(source) if source else None,
        "compared_files": checked,
    }
