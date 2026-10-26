"""Smoke tests for the installable package and its module entry point."""

from __future__ import annotations

import re
import subprocess
import sys

from minimum_coding_agent import __version__


def test_version_is_exported() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_module_entry_point_prints_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "minimum_coding_agent", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert f"mca {__version__}" in result.stdout
