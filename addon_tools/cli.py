import argparse
import json
import sys
import zipfile

from .package import verify_package
from .workspace import load_workspace, resolve_project


def main(argv=None):
    parser = argparse.ArgumentParser(description="Resolve add-on workspaces and verify packages offline.")
    parser.add_argument("--workspace", help="Workspace directory containing an addon-workspace JSON manifest")
    commands = parser.add_subparsers(dest="command", required=True)
    locate = commands.add_parser("resolve", help="Print a project's absolute locations")
    locate.add_argument("project_id")
    locate.add_argument("--field", choices=("project_id", "workspace_root", "tooling_root", "project_root", "payload_root"))
    commands.add_parser("list", help="Print the configured project IDs as JSON")
    check = commands.add_parser("verify-package", help="Verify a ZIP package without extracting or running it")
    check.add_argument("archive")
    check.add_argument("--source", help="Payload or staging tree to compare against the archive")
    check.add_argument("--expect-addon-id")
    check.add_argument("--expect-version")
    check.add_argument("--expect-sha256")
    check.add_argument("--compare-file", action="append", default=[])
    check.add_argument("--required-file", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "resolve":
            result = resolve_project(args.project_id, args.workspace)
            if args.field:
                print(result[args.field])
                return 0
        elif args.command == "list":
            _, projects = load_workspace(args.workspace)
            result = sorted(projects)
        else:
            result = verify_package(
                args.archive, source=args.source, expect_addon_id=args.expect_addon_id,
                expect_version=args.expect_version, expect_sha256=args.expect_sha256,
                compare_files=args.compare_file, required_files=args.required_file,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
