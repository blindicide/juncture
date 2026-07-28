"""Run provenance capture."""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


def git_commit(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def collect_provenance(root: Path) -> dict[str, str | None]:
    return {
        "git_commit": git_commit(root),
        "python_version": sys.version,
        "platform": platform.platform(),
    }
