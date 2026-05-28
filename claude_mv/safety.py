"""Safety: process check, mtime tracking, backup, atomic write."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def claude_process_running() -> tuple[bool, str]:
    """Detect a running Claude Code process. Returns (running, sample_line)."""
    if sys.platform == "win32":
        cmd = ["tasklist", "/FO", "CSV", "/NH"]
        needles = ("claude.exe",)
    else:
        cmd = ["ps", "-eo", "command="]
        needles = ("claude code", "claude-code", "@anthropic-ai/claude-code")

    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5, check=False
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        return False, f"(could not check: {e})"

    for line in out.splitlines():
        low = line.lower()
        if "claude-mv" in low:
            continue
        for needle in needles:
            if needle in low:
                return True, line.strip()
    return False, ""


def mtime_ns(path: Path) -> int:
    return path.stat().st_mtime_ns if path.exists() else 0


def backup_file(path: Path) -> Path | None:
    """Copy `path` to `path + '.claude-mv.bak'`. Returns the backup path or
    None if the source doesn't exist. Overwrites previous backup."""
    if not path.exists():
        return None
    bak = path.with_name(path.name + ".claude-mv.bak")
    shutil.copy2(path, bak)
    return bak


def atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".claude-mv.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))
