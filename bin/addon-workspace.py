#!/usr/bin/env python3
"""Dependency-free entry point; callable from shell, Python, or Node."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from addon_tools.cli import main


if __name__ == "__main__":
    sys.exit(main())
