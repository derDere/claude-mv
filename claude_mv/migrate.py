"""Move logic: rename storage, patch ~/.claude.json, patch history.jsonl,
scan JSONL content, move the actual folder.

The tool is idempotent: if a previous run already migrated some pieces
(e.g. the storage folder is already renamed but the project folder was
not moved due to a permission error), a retry will detect the partial
state and finish what's left instead of bailing out.
"""

import hashlib
import json
import os
import shutil
from pathlib import Path

from . import paths, safety, ui


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _hash_file(path: Path, chunk: int = 1 << 16) -> str:
    """SHA-256 of a file's content, streamed."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _detect_key(projects_obj: dict, p: str) -> str | None:
    for variant in paths.path_variants(p):
        if variant in projects_obj:
            return variant
    return None


def _count_lines(p: Path) -> int:
    n = 0
    with open(p, "rb") as f:
        for _ in f:
            n += 1
    return n


# ---------------------------------------------------------------------------
# robust per-file folder move (used when NEW already exists or fast rename fails)
# ---------------------------------------------------------------------------


def robust_move_folder(
    old_dir: Path, new_dir: Path, merge: bool, dry_run: bool
) -> tuple[dict, list[str]]:
    """Move every file from old_dir to new_dir, tolerant of partial failures.

    Behaviour:
    - If new_dir does not exist: try fast `os.rename` first. If that fails
      (permission, cross-volume, locked file), fall back to per-file move.
    - If new_dir exists and merge=True: per-file merge. SHA-256-identical
      files are skipped (and removed from old); different files are
      overwritten; new files are moved over.
    - If new_dir exists and merge=False: returns an error in the list.
    - Every per-file op is wrapped in try/except, so one bad file does not
      abort the rest.

    Returns ({moved, identical, overwritten, failed}, errors_list).
    """
    stats = {"moved": 0, "identical": 0, "overwritten": 0, "failed": 0}
    errors: list[str] = []

    if not old_dir.exists():
        return stats, [f"source folder does not exist: {old_dir}"]

    # Fast path: NEW does not exist → simple rename
    if not new_dir.exists():
        files = [p for p in old_dir.rglob("*") if p.is_file()]
        if dry_run:
            stats["moved"] = len(files)
            return stats, errors
        try:
            os.rename(old_dir, new_dir)
            stats["moved"] = len(files)
            return stats, errors
        except OSError as e:
            errors.append(f"fast rename failed ({e}); per-file fallback")
            # fall through

    # Slow path
    if new_dir.exists() and not merge and not errors:
        return stats, [
            f"target {new_dir} already exists and merge was not requested"
        ]

    if not dry_run:
        new_dir.mkdir(parents=True, exist_ok=True)

    files = [p for p in old_dir.rglob("*") if p.is_file()]
    for src in files:
        rel = src.relative_to(old_dir)
        dst = new_dir / rel
        try:
            if dst.exists() and dst.is_file():
                if _hash_file(src) == _hash_file(dst):
                    if not dry_run:
                        src.unlink()
                    stats["identical"] += 1
                    continue
                if not dry_run:
                    dst.unlink()
                    shutil.move(str(src), str(dst))
                stats["overwritten"] += 1
            else:
                if not dry_run:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dst))
                stats["moved"] += 1
        except OSError as e:
            errors.append(f"{rel}: {e}")
            stats["failed"] += 1

    # Best-effort cleanup of empty source dirs
    if not dry_run:
        for d in sorted(
            (p for p in old_dir.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            try:
                d.rmdir()
            except OSError:
                pass
        try:
            old_dir.rmdir()
        except OSError as e:
            if stats["failed"] > 0:
                errors.append(
                    f"source folder not empty (some files failed): {e}"
                )
            else:
                errors.append(f"could not remove source folder: {e}")

    return stats, errors


# ---------------------------------------------------------------------------
# state patches — each returns (status, message)
# status in: "changed" | "already" | "missing" | "error"
# ---------------------------------------------------------------------------


def patch_claude_json(
    old_path: str, new_path: str, dry_run: bool
) -> tuple[str, str]:
    p = paths.claude_json_path()
    if not p.exists():
        return "missing", f"no ~/.claude.json at {p}"

    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return "error", f"could not parse ~/.claude.json: {e}"

    projects = data.get("projects")
    if not isinstance(projects, dict):
        return "error", "no 'projects' object in ~/.claude.json"

    matched_old = _detect_key(projects, old_path)
    matched_new = _detect_key(projects, new_path)

    if matched_old is None:
        if matched_new is not None:
            return "already", f"projects map already keyed by NEW ({matched_new!r})"
        return "missing", "no entry for OLD or NEW in projects map"

    if matched_new is not None and matched_new != matched_old:
        return (
            "error",
            f"both OLD ({matched_old!r}) and NEW ({matched_new!r}) keys exist — "
            "manual cleanup of ~/.claude.json needed",
        )

    new_key = paths.match_slash_style(matched_old, new_path)
    if dry_run:
        return "changed", f"would rekey projects[{matched_old!r}] -> [{new_key!r}]"

    mt0 = safety.mtime_ns(p)
    new_projects = {}
    for k, v in projects.items():
        new_projects[new_key if k == matched_old else k] = v
    data["projects"] = new_projects

    if safety.mtime_ns(p) != mt0:
        return "error", "~/.claude.json changed during run — aborting write"

    safety.atomic_write_text(
        p, json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    )
    return "changed", f"rekeyed projects[{matched_old!r}] -> [{new_key!r}]"


def patch_history_jsonl(
    old_path: str, new_path: str, dry_run: bool
) -> tuple[str, str, int, int]:
    """Returns (status, message, matches, total_lines)."""
    p = paths.history_jsonl_path()
    if not p.exists():
        return "missing", f"no history.jsonl at {p}", 0, 0

    total = _count_lines(p)
    if total == 0:
        return "already", "history.jsonl is empty", 0, 0

    mt0 = safety.mtime_ns(p)
    old_variants = set(paths.path_variants(old_path))

    # Pre-scan: anything to do?
    pre_matches = 0
    with open(p, "r", encoding="utf-8") as fin:
        for line in fin:
            line = line.rstrip("\r\n")
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("project") in old_variants:
                pre_matches += 1

    if pre_matches == 0:
        return "already", f"no OLD entries in history.jsonl (already migrated?)", 0, total

    if dry_run:
        return "changed", f"would patch {pre_matches}/{total} lines", pre_matches, total

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
        return "error", "history.jsonl changed during run — aborting write", 0, total

    os.replace(tmp, p)
    return "changed", f"patched {matches}/{total} lines", matches, total


def scan_jsonl_for_old_path(storage_dir: Path, old_path: str) -> dict[str, int]:
    if not storage_dir.exists():
        return {}
    needles = [
        old_path,
        old_path.replace("\\", "/"),
        old_path.replace("\\", "\\\\"),
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


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------


def _report_status(stage: ui.Stage, status: str, msg: str) -> bool:
    """Render the patch-status to the user. Returns False if status indicates
    a hard error that should abort."""
    if status == "changed":
        stage.end(msg)
    elif status == "already":
        stage.end(f"already done — {msg}", color=ui.DIM)
    elif status == "missing":
        stage.skip(msg)
    else:  # "error"
        stage.end(msg, color=ui.RED)
        return False
    return True


def run(
    old_raw: str,
    new_raw: str,
    fix_only: bool,
    dry_run: bool,
    move_anyway: bool,
    merge: bool,
    verbose: bool,
) -> int:
    old_path = paths.normalize_input_path(old_raw)
    new_path = paths.normalize_input_path(new_raw)

    if old_path == new_path:
        ui.error("OLD and NEW resolve to the same path")
        return 2

    old_dir = Path(old_path)
    new_dir = Path(new_path)
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

    has_old_dir = old_dir.exists()
    has_new_dir = new_dir.exists()
    has_old_storage = storage_old.exists()
    has_new_storage = storage_new.exists()

    if has_old_storage and has_new_storage:
        ui.error(
            f"both old and new storage folders exist — ambiguous:\n"
            f"  {storage_old}\n  {storage_new}\n"
            "Manually decide which one to keep, then re-run."
        )
        return 2

    # --- validate: OLD must exist (unless --fix and only the storage check matters)
    if not fix_only and not has_old_dir and not has_new_dir:
        ui.error(f"neither OLD nor NEW directory exists: {old_path} / {new_path}")
        return 2

    if not fix_only and not has_old_dir and has_new_dir and not has_old_storage:
        # everything looks already migrated on disk and in storage
        if not has_new_storage:
            ui.warn("OLD does not exist and no storage found — nothing to do.")
            return 0
        # fall through: state patches may still need to run (idempotent)
        ui.info("Note: OLD already moved; will verify state patches are in sync.")

    # --- detect NEW-exists situation and handle merge prompt ---
    need_folder_move = not fix_only
    if need_folder_move and has_new_dir and has_old_dir:
        # both exist — this is the recovery case
        if not merge:
            if dry_run:
                ui.warn(f"NEW already exists ({new_path}); would prompt for merge.")
                merge = True  # for dry-run, assume yes for planning
            else:
                ui.warn(f"NEW already exists: {new_path}")
                try:
                    ans = input(
                        "Merge OLD into existing NEW (per-file SHA-256 compare, "
                        "identical files skipped, different ones overwritten)? [y/N] "
                    )
                except (EOFError, KeyboardInterrupt):
                    ui.info("\nAborted.")
                    return 0
                if ans.strip().lower() not in ("y", "yes"):
                    ui.info("Aborted.")
                    return 0
                merge = True

    # --- process check ---
    running, sample = safety.claude_process_running()
    if running:
        if dry_run:
            ui.warn(
                f"Claude Code seems to be running ({sample[:80]}); "
                "continuing because --dry-run."
            )
        else:
            ui.error(
                "Claude Code appears to be running:\n"
                f"  {sample}\n"
                "Please close it before running claude-mv."
            )
            return 1

    # --- missing-storage edge case (only when OLD-dir exists but no storage) ---
    if (
        not fix_only
        and has_old_dir
        and not has_old_storage
        and not has_new_storage
        and not dry_run
    ):
        if not move_anyway:
            ui.warn(f"no Claude storage found for OLD ({storage_old})")
            try:
                ans = input(
                    "Move the folder anyway (no Claude data to migrate)? [y/N] "
                )
            except (EOFError, KeyboardInterrupt):
                ui.info("\nAborted.")
                return 0
            if ans.strip().lower() not in ("y", "yes"):
                ui.info("Aborted.")
                return 0

    # --- plan ---
    ui.info()
    ui.heading(f"claude-mv{' (DRY RUN)' if dry_run else ''}")
    ui.info(f"  OLD: {old_path}")
    ui.info(f"  NEW: {new_path}")
    ui.info(f"  encoded OLD: {enc_old}")
    ui.info(f"  encoded NEW: {enc_new}")
    mode_parts = []
    if fix_only:
        mode_parts.append("fix (storage only)")
    else:
        mode_parts.append("move + patch")
    if merge:
        mode_parts.append("MERGE")
    ui.info(f"  mode: {', '.join(mode_parts)}")
    ui.info(
        f"  state: old_dir={'Y' if has_old_dir else 'N'} "
        f"new_dir={'Y' if has_new_dir else 'N'} "
        f"old_storage={'Y' if has_old_storage else 'N'} "
        f"new_storage={'Y' if has_new_storage else 'N'}"
    )
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

    # 2) Storage folder
    stage.begin(f"Storage folder ({enc_old} -> {enc_new})")
    if has_old_storage and has_new_storage:
        stage.end("BOTH exist (impossible, validated earlier)", color=ui.RED)
        return 1
    elif has_old_storage:
        if dry_run:
            stage.skip("dry-run")
        else:
            try:
                os.rename(storage_old, storage_new)
                stage.end()
            except OSError as e:
                stage.end(f"rename failed: {e}", color=ui.RED)
                return 1
    elif has_new_storage:
        stage.end("already renamed", color=ui.DIM)
    else:
        stage.skip("no storage to rename")

    # 3) Patch ~/.claude.json
    stage.begin("Patch ~/.claude.json")
    status, msg = patch_claude_json(old_path, new_path, dry_run)
    if not _report_status(stage, status, msg):
        return 1

    # 4) Patch history.jsonl
    stage.begin("Patch ~/.claude/history.jsonl")
    stage.multiline()
    status, msg, n, total = patch_history_jsonl(old_path, new_path, dry_run)
    if not _report_status(stage, status, msg):
        return 1

    # 5) Scan JSONL content
    stage.begin("Scan JSONL content for historical OLD references")
    scan_target = storage_new if storage_new.exists() else storage_old
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
        if not has_old_dir and has_new_dir:
            stage.end("already moved", color=ui.DIM)
        elif not has_old_dir:
            stage.skip("OLD does not exist")
        elif dry_run:
            stage.skip("dry-run")
        else:
            stage.multiline()
            stats, errors = robust_move_folder(
                old_dir=old_dir, new_dir=new_dir, merge=merge, dry_run=False
            )
            for line in errors:
                ui.warn(line)
            summary = (
                f"moved={stats['moved']} identical={stats['identical']} "
                f"overwritten={stats['overwritten']} failed={stats['failed']}"
            )
            if stats["failed"] > 0:
                stage.end(summary + " — some files could not be moved", color=ui.YELLOW)
            else:
                stage.end(summary)

    # 7) Verify
    stage.begin("Verify")
    if dry_run:
        stage.skip("dry-run")
    else:
        problems = []
        if (has_old_storage or has_new_storage) and not storage_new.exists():
            problems.append("new storage folder missing")
        if not fix_only and not new_dir.exists():
            problems.append("new project folder missing")
        if not fix_only and old_dir.exists():
            # leftover source files — soft warning, not hard error
            problems.append(
                f"OLD still has content (likely files that could not be moved)"
            )
        if problems:
            stage.end("; ".join(problems), color=ui.YELLOW)
        else:
            stage.end("all checks passed")

    ui.info()
    if dry_run:
        ui.ok("Dry run complete.")
    else:
        ui.ok("Done.")
    return 0
