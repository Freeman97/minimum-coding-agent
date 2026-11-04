"""Execute the tools documentation and demo against the delivered public API."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def test_tools_documentation_python_example(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    document = (root / "docs/tools.md").read_text(encoding="utf-8")
    examples = re.findall(r"```python\n(.*?)\n```", document, flags=re.DOTALL)
    assert len(examples) == 1
    result = subprocess.run(
        [sys.executable, "-c", examples[0]],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "1: hello\n"


def test_tools_demo_from_another_working_directory(tmp_path: Path) -> None:
    demo = Path(__file__).resolve().parents[2] / "scripts/demo_tools.py"
    result = subprocess.run(
        [sys.executable, str(demo)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "tool demo finished: all assertions passed" in result.stdout
    assert '"exit_code": 0' in result.stdout
    assert "PATH_OUTSIDE_WORKSPACE" in result.stdout
    assert "COMMAND_DENIED" in result.stdout
    assert list(tmp_path.iterdir()) == []
