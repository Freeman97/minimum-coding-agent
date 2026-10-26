"""Tests that the quality gate configuration catches documentation violations.

The project requires a green ``make check``. These tests lock the gate itself:
if the ruff ``D`` rules or the pydoclint configuration stop catching missing
docstrings, the tests fail instead of silently weakening the gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ruff_detects_missing_public_docstring(tmp_path: Path) -> None:
    rust_ruff = Path(sys.executable).with_name("ruff")
    assert rust_ruff.exists(), "ruff is expected in the project virtual environment"
    sample = tmp_path / "sample.py"
    sample.write_text("def undocumented():\n    return 1\n", encoding="utf-8")

    result = subprocess.run(
        [
            str(rust_ruff),
            "check",
            "--config",
            str(REPO_ROOT / "pyproject.toml"),
            str(sample),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "D103" in result.stdout
    assert "sample.py:1" in result.stdout


def test_pydoclint_detects_missing_argument_section(tmp_path: Path) -> None:
    pydoclint = Path(sys.executable).with_name("pydoclint")
    assert pydoclint.exists(), "pydoclint is expected in the project virtual environment"
    sample = tmp_path / "sample.py"
    sample.write_text(
        'def count_lines(path: str) -> int:\n    """Count lines in a file."""\n    return 1\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(pydoclint),
            "--config",
            str(REPO_ROOT / "pyproject.toml"),
            str(sample),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "DOC101" in result.stdout + result.stderr


def test_live_marker_is_excluded_by_default(tmp_path: Path) -> None:
    marked = tmp_path / "test_marked_live.py"
    marked.write_text(
        "import pytest\n\n\n@pytest.mark.live\ndef test_live_only() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    base_command = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(REPO_ROOT / "pyproject.toml"),
        str(marked),
        "-q",
    ]

    default_run = subprocess.run(
        base_command, cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    assert default_run.returncode == 5
    assert "deselected" in default_run.stdout

    live_run = subprocess.run(
        [*base_command, "-m", "live"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    assert live_run.returncode == 0
    assert "1 passed" in live_run.stdout
