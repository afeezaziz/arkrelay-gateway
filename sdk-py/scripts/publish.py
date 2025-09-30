#!/usr/bin/env python3
"""
Publish ArkRelay Python SDK to PyPI

Usage:
    python scripts/publish.py --test    # Publish to Test PyPI
    python scripts/publish.py           # Publish to PyPI
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n🔄 {description}")
    print(f"Running: {cmd}")

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ Error: {result.stderr}")
        print(f"❌ Command failed: {cmd}")
        sys.exit(1)
    else:
        print(f"✅ {description} completed successfully")
        if result.stdout:
            print(f"Output: {result.stdout}")


def main():
    parser = argparse.ArgumentParser(description="Publish ArkRelay Python SDK")
    parser.add_argument("--test", action="store_true", help="Publish to Test PyPI")
    parser.add_argument("--version", help="Version to publish (overrides current version)")
    args = parser.parse_args()

    # Validate we're in the right directory
    if not Path("pyproject.toml").exists():
        print("❌ Error: pyproject.toml not found. Run from sdk-py directory.")
        sys.exit(1)

    # Update version if specified
    if args.version:
        run_command(
            f"sed -i.bak 's/version = .*/version = \"{args.version}\"/' pyproject.toml",
            f"Updating version to {args.version}"
        )
        run_command("rm -f pyproject.toml.bak", "Cleaning up backup")

    # Clean previous builds
    run_command("rm -rf dist/ build/ *.egg-info", "Cleaning previous builds")

    # Install build dependencies
    run_command(
        "python -m pip install --upgrade build twine",
        "Installing build dependencies"
    )

    # Build the package
    run_command("python -m build", "Building package")

    # Check the package
    run_command("twine check dist/*", "Checking package")

    # Publish to appropriate repository
    if args.test:
        run_command(
            "twine upload --repository testpypi dist/*",
            "Publishing to Test PyPI"
        )
        print("\n🎉 Published to Test PyPI!")
        print("Install with: pip install --index-url https://test.pypi.org/simple/ arkrelay")
    else:
        run_command(
            "twine upload dist/*",
            "Publishing to PyPI"
        )
        print("\n🎉 Published to PyPI!")
        print("Install with: pip install arkrelay")


if __name__ == "__main__":
    main()