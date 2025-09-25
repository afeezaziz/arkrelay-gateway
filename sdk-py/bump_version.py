#!/usr/bin/env python3
"""
Simple version bump helper for sdk-py/pyproject.toml and git tag creation.

Usage:
  python bump_version.py 0.1.1

This will:
- Update version in sdk-py/pyproject.toml
- Print the git tag to create: sdk-py-v0.1.1

It will NOT commit or tag automatically (to avoid accidental pushes).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python bump_version.py X.Y.Z", file=sys.stderr)
        return 1
    version = sys.argv[1]
    text = PYPROJECT.read_text()
    new_text, n = re.subn(r'^version\s*=\s*"[^"]+"', f'version = "{version}"', text, count=1, flags=re.M)
    if n != 1:
        print("Could not find version field to replace.", file=sys.stderr)
        return 2
    PYPROJECT.write_text(new_text)
    print(f"Bumped sdk version to {version} in {PYPROJECT}")
    print(f"Next: git commit -am 'sdk(py): bump to {version}' && git tag sdk-py-v{version} && git push origin main sdk-py-v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
