"""`--list` command: show all projects tracked in ~/.claude.json with status."""

import json
from pathlib import Path

from . import paths, ui


def list_projects() -> int:
    cj = paths.claude_json_path()
    if not cj.exists():
        ui.warn(f"~/.claude.json not found at {cj}")
        return 1

    try:
        data = json.loads(cj.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        ui.error(f"could not parse ~/.claude.json: {e}")
        return 1

    projects = data.get("projects", {})
    if not isinstance(projects, dict) or not projects:
        ui.info("(no projects tracked)")
        return 0

    rows = []
    for key in projects:
        folder_ok = Path(key).is_dir()
        storage_ok = paths.project_storage_dir(key).exists()
        flags = []
        if not folder_ok:
            flags.append("MISSING DIR")
        if not storage_ok:
            flags.append("MISSING STORAGE")
        if not flags:
            flags.append("OK")
        rows.append((key, ", ".join(flags)))

    rows.sort(key=lambda r: r[0].lower())
    width = max(len(k) for k, _ in rows)
    for key, status in rows:
        color = ui.GREEN if status == "OK" else ui.YELLOW
        ui.info(f"  {key:<{width}}  {color}[{status}]{ui.RESET}")

    ui.info()
    ok_count = sum(1 for _, s in rows if s == "OK")
    ui.info(f"{len(rows)} project(s), {ok_count} OK, {len(rows) - ok_count} with issues")
    return 0
