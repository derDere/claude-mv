"""Path encoding and filesystem helpers for claude-mv."""

import os
from pathlib import Path

_ENCODE_CHARS = frozenset({"\\", "/", ":", "_", "."})


def encode_path(abs_path: str) -> str:
    """Encode an absolute path to Claude Code's storage-folder name.

    Replaces each of \\ / : _ . with -. Live-verified on Claude Code 2.1.x
    (Windows). All other chars (spaces, parens, unicode, hyphens) pass through.
    """
    return "".join("-" if c in _ENCODE_CHARS else c for c in abs_path)


def normalize_input_path(p: str) -> str:
    """Turn a user-typed path into a lexically-absolute string.

    Expands ~, expands env vars, makes absolute, strips trailing separators.
    Does NOT resolve symlinks (we want the path conceptually, not physically).
    """
    p = os.path.expandvars(os.path.expanduser(p))
    return os.path.abspath(p).rstrip("\\/")


def claude_home() -> Path:
    return Path.home() / ".claude"


def claude_json_path() -> Path:
    return Path.home() / ".claude.json"


def history_jsonl_path() -> Path:
    return claude_home() / "history.jsonl"


def projects_dir() -> Path:
    return claude_home() / "projects"


def project_storage_dir(abs_path: str) -> Path:
    return projects_dir() / encode_path(abs_path)


def path_variants(p: str) -> list[str]:
    """All slash-style variants we might find a path stored as."""
    return list(dict.fromkeys([p, p.replace("\\", "/"), p.replace("/", "\\")]))


def match_slash_style(reference: str, target: str) -> str:
    """Return `target` rewritten to use the same slash style as `reference`."""
    has_only_forward = "/" in reference and "\\" not in reference
    if has_only_forward:
        return target.replace("\\", "/")
    return target
