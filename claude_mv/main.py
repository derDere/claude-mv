"""claude-mv CLI entry point. Default action = move. --fix / --list switch modes."""

import argparse
import sys

from . import inventory, migrate


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="claude-mv",
        description=(
            "Move a project folder and migrate its Claude Code session "
            "storage (or just patch storage in-place). Default: move OLD to "
            "NEW and patch all path references."
        ),
        epilog=(
            "Examples:\n"
            "  claude-mv C:\\old\\project C:\\new\\project\n"
            "  claude-mv --dry-run C:\\old\\project C:\\new\\project\n"
            "  claude-mv --fix C:\\old\\project C:\\new\\project   "
            "# folder already moved\n"
            "  claude-mv --list"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--fix",
        action="store_true",
        help="Patch storage only; do not move the folder (use after manual mv).",
    )
    mode.add_argument(
        "--list",
        dest="list_mode",
        action="store_true",
        help="List all projects tracked in ~/.claude.json with status.",
    )

    p.add_argument("OLD", nargs="?", help="Old absolute path (required unless --list).")
    p.add_argument("NEW", nargs="?", help="New absolute path (required unless --list).")

    p.add_argument(
        "--dry-run", action="store_true", help="Show what would happen; write nothing."
    )
    p.add_argument(
        "--move-anyway",
        action="store_true",
        help="If no Claude storage exists for OLD, move the folder without prompting.",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true", help="More detailed output."
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_mode:
        return inventory.list_projects()

    if not args.OLD or not args.NEW:
        parser.error("OLD and NEW are required (unless --list is given)")

    return migrate.run(
        old_raw=args.OLD,
        new_raw=args.NEW,
        fix_only=args.fix,
        dry_run=args.dry_run,
        move_anyway=args.move_anyway,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
