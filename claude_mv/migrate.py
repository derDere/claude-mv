"""Move logic: rename storage, patch ~/.claude.json, patch history.jsonl,
scan JSONL content, move the actual folder."""

import json
import os
import shutil
from pathlib import Path

from . import paths, safety, ui


def _detect_old_key(projects_obj: dict, old_path: str) -> str | None:
    for variant in paths.path_variants(old_path):
        if variant in projects_obj:
            return variant
    return None


def patch_claude_json(
    old_path: str, new_path: str, dry_run: bool
) -> tuple[bool, str]:
    p = paths.claude_json_path()
    if not p.exists():
        return False, f"no ~/.claude.json at {p}"

    mt0 = safety.mtime_ns(p)
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return False, f"could not parse ~/.claude.json: {e}"

    projects = data.get("projects")
    if not isinstance(projects, dict):
        return False, "no 'projects' object in ~/.claude.json"

    matched = _detect_old_key(projects, old_path)
    if matched is None:
        return False, f"no entry for OLD in projects map"

    new_key = paths.match_slash_style(matched, new_path)
    if new_key != matched and new_key in projects:
        return False, f"new key {new_key!r} already exists in projects map"

    if dry_run:
        return True, f"would rekey projects[{matched!r}] -> [{new_key!r}]"

    new_projects = {}
    for k, v in projects.items():
        new_projects[new_key if k == matched else k] = v
    data["projects"] = new_projects

    if safety.mtime_ns(p) != mt0:
        return False, "~/.claude.json changed during run — aborting write"

    safety.atomic_write_text(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return True, f"rekeyed projects[{matched!r}] -> [{new_key!r}]"


def _count_lines(p: Path) -> int:
    n = 0
    with open(p, "rb") as f:
        for _ in f:
            n += 1
    return n


def patch_history_jsonl(
    old_path: str, new_path: str, dry_run: bool
) -> tuple[int, int, str]:
    """Returns (matches, total_lines, message). JSON-aware: parses each line
    as JSON and rewrites only the 'project' field."""
    p = paths.history_jsonl_path()
    if not p.exists():
        return 0, 0, f"no history.jsonl at {p}"

    total = _count_lines(p)
    if total == 0:
        return 0, 0, "history.jsonl is empty"

    mt0 = safety.mtime_ns(p)
    old_variants = set(paths.path_variants(old_path))

    if dry_run:
        matches = 0
        bar = ui.Bar(total)
        with open(p, "r", encoding="utf-8") as fin:
            for line in fin:
                bar.tick()
                stripped = line.rstrip("\r\n")
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if obj.get("project") in old_variants:
                    matches += 1
        bar.close()
        return matches, total, f"would patch {matches}/{total} lines"

    tmp = p.with_name(p.name + ".claude-mv.tmp")
    matches = 0
    bar = ui.Bar(total)
    with open(p, "r", encoding="utf-8") as fin, open(
        tmp, "w", encoding="utf-8", newline="\n"
    ) as fout:
        for line in fin:
            bar.tick()
            stripped = line.rstrip("\r\n")
            if not stripped:
                fout.write(line)
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                fout.write(line)
                continue
            current = obj.get("project")
            if current in old_variants:
                obj["project"] = paths.match_slash_style(current, new_path)
                matches += 1
                fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            else:
                fout.write(line if line.endswith("\n") else line + "\n")
    bar.close()

    if safety.mtime_ns(p) != mt0:
        tmp.unlink(missing_ok=True)
        return 0, total, "history.jsonl changed during run — aborting write"

    os.replace(tmp, p)
    return matches, total, f"patched {matches}/{total} lines"


def scan_jsonl_for_old_path(storage_dir: Path, old_path: str) -> dict[str, int]:
    """Read-only scan of all *.jsonl under storage_dir for OLD-path mentions
    in the conversation content. Returns {relative_path: count}."""
    if not storage_dir.exists():
        return {}
    needles = [
        old_path,
        old_path.replace("\\", "/"),
        old_path.replace("\\", "\\\\"),  # JSON-escaped backslashes
    ]
    results: dict[str, int] = {}
    for jsonl in storage_dir.rglob("*.jsonl"):
        count = 0
        try:
            with open(jsonl, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if any(n in line for n in needles):
                        count += 1
        except OSError:
            continue
        if count:
            results[str(jsonl.relative_to(storage_dir))] = count
    return results


def run(
    old_raw: str,
    new_raw: str,
    fix_only: bool,
    dry_run: bool,
    move_anyway: bool,
    verbose: bool,
) -> int:
    """Main entry point. Returns shell exit code."""
    old_path = paths.normalize_input_path(old_raw)
    new_path = paths.normalize_input_path(new_raw)

    if old_path == new_path:
        ui.error("OLD and NEW resolve to the same path")
        return 2

    old_dir = Path(old_path)
    new_dir = Path(new_path)

    if not fix_only:
        if not old_dir.exists():
            ui.error(f"OLD does not exist: {old_path}")
            return 2
        if new_dir.exists():
            ui.error(f"NEW already exists: {new_path}")
            return 2

    enc_old = paths.encode_path(old_path)
    enc_new = paths.encode_path(new_path)
    if enc_old == enc_new:
        ui.error(
            f"OLD and NEW encode to the same folder name ({enc_old!r}). "
            "Only chars like _ . / \\ differ. Pick a NEW with a different name."
        )
        return 2

    storage_old = paths.projects_dir() / enc_old
    storage_new = paths.projects_dir() / enc_new

    if storage_new.exists():
        ui.error(f"target storage folder already exists: {storage_new}")
        return 2

    has_storage = storage_old.exists()

    # --- process check (skipped on dry-run with a warning) ---
    running, sample = safety.claude_process_running()
    if running:
        if dry_run:
            ui.warn(f"Claude Code seems to be running ({sample[:80]}); continuing because --dry-run.")
        else:
            ui.error(
                "Claude Code appears to be running:\n"
                f"  {sample}\n"
                "Please close it before running claude-mv."
            )
            return 1

    # --- missing-storage edge case ---
    if not has_storage:
        if fix_only:
            ui.error(f"no Claude storage at {storage_old} — nothing to fix")
            return 1
        if not move_anyway and not dry_run:
            ui.warn(f"no Claude storage at {storage_old}")
            try:
                ans = input("Move the folder anyway (no Claude data to migrate)? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                ui.info("\nAborted.")
                return 0
            if ans.strip().lower() not in ("y", "yes"):
                ui.info("Aborted.")
                return 0

    # --- plan summary ---
    ui.info()
    ui.heading(f"claude-mv{' (DRY RUN)' if dry_run else ''}")
    ui.info(f"  OLD: {old_path}")
    ui.info(f"  NEW: {new_path}")
    ui.info(f"  encoded OLD: {enc_old}")
    ui.info(f"  encoded NEW: {enc_new}")
    ui.info(f"  mode: {'fix (storage only)' if fix_only else 'move + patch'}")
    ui.info(f"  storage: {'found' if has_storage else 'MISSING'}")
    ui.info()

    total_stages = 6 if fix_only else 7
    stage = ui.Stage(total_stages)

    # 1) Backup
    stage.begin("Backup ~/.claude.json + history.jsonl")
    if dry_run:
        stage.skip("dry-run")
    else:
        cj_bak = safety.backup_file(paths.claude_json_path())
        hj_bak = safety.backup_file(paths.history_jsonl_path())
        names = [b.name for b in (cj_bak, hj_bak) if b]
        stage.end(", ".join(names) if names else "nothing to back up")

    # 2) Rename storage folder
    stage.begin(f"Rename projects/{enc_old} -> projects/{enc_new}")
    if not has_storage:
        stage.skip("no storage")
    elif dry_run:
        stage.skip("dry-run")
    else:
        try:
            os.rename(storage_old, storage_new)
            stage.end()
        except OSError as e:
            ui.error(f"rename failed: {e}")
            return 1

    # 3) Patch ~/.claude.json
    stage.begin("Patch ~/.claude.json")
    changed, msg = patch_claude_json(old_path, new_path, dry_run)
    if changed:
        stage.end(msg)
    else:
        stage.skip(msg)

    # 4) Patch history.jsonl
    stage.begin("Patch ~/.claude/history.jsonl")
    stage.multiline()
    n, total, msg = patch_history_jsonl(old_path, new_path, dry_run)
    stage.end(msg)

    # 5) Scan JSONL content (read-only)
    stage.begin("Scan JSONL content for historical OLD references")
    scan_target = storage_new if (has_storage and not dry_run) else storage_old
    if not scan_target.exists():
        stage.skip("no storage")
    else:
        hits = scan_jsonl_for_old_path(scan_target, old_path)
        if hits:
            total_hits = sum(hits.values())
            stage.end(
                f"{total_hits} hits across {len(hits)} files "
                f"(historical tool-calls, not patched)",
                color=ui.YELLOW,
            )
            if verbose:
                for f, c in sorted(hits.items()):
                    ui.dim(f"        {c:6d}  {f}")
        else:
            stage.end("no historical references")

    # 6) Move folder (skipped in fix mode)
    if not fix_only:
        stage.begin(f"Move folder {old_path} -> {new_path}")
        if dry_run:
            stage.skip("dry-run")
        else:
            try:
                shutil.move(str(old_dir), str(new_dir))
                stage.end()
            except OSError as e:
                ui.error(f"move failed: {e}")
                return 1

    # 7) Verify (or 6 in fix mode)
    stage.begin("Verify")
    if dry_run:
        stage.skip("dry-run")
    else:
        problems = []
        if has_storage and not storage_new.exists():
            problems.append("new storage folder missing")
        if not fix_only and not new_dir.exists():
            problems.append("new project folder missing")
        if problems:
            stage.end("; ".join(problems), color=ui.RED)
            return 1
        stage.end("all checks passed")

    ui.info()
    ui.ok("Done." if not dry_run else "Dry run complete.")
    return 0
