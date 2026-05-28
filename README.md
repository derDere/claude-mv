# claude-mv

> Move a Claude Code project directory **and take all the chat history with it.**

Claude Code stores chat sessions, history and per-project settings under
paths derived from your project's absolute filesystem path. When you rename
or move the project folder, those references break and your chats become
orphaned — `claude --resume` won't find them anymore.

`claude-mv` fixes that. One command moves the folder **and** migrates all
of Claude Code's references in lockstep.

- Pure Python stdlib — **zero dependencies**
- Works on Windows, macOS and Linux
- Atomic writes + automatic backups
- Refuses to run while Claude Code is open (avoids races)
- Dry-run mode so you can see exactly what would happen

---

## Quick start

You need [`uv`](https://github.com/astral-sh/uv) installed (it ships
`uvx`). The tool itself has no other dependencies — `uvx` pulls and runs
it straight from GitHub.

The simplest invocation:

```bash
uvx --from git+https://github.com/derDere/claude-mv.git claude-mv \
    "C:\old\project\path" "C:\new\project\path"
```

For something shorter, see **[Installing as a global `claude-mv` command](#installing-as-a-global-claude-mv-command)** below.

You can also clone and run locally:

```bash
git clone https://github.com/derDere/claude-mv.git
cd claude-mv
python -m claude_mv "C:\old\project\path" "C:\new\project\path"
```

**Close all Claude Code instances first.** The tool will refuse to run
otherwise — you don't want Claude to modify its state files while we're
mid-migration.

---

## Installing as a global `claude-mv` command

Typing `uvx --from git+https://github.com/derDere/claude-mv.git claude-mv …`
every time is no fun. The repo ships three tiny wrapper scripts that
forward all arguments to `uvx`. Pick the one for your shell, drop it
somewhere on your `PATH`, and you can just say `claude-mv …`.

The wrappers live in the repo root: [`claude-mv.sh`](claude-mv.sh)
(bash / zsh), [`claude-mv.ps1`](claude-mv.ps1) (PowerShell),
[`claude-mv.bat`](claude-mv.bat) (cmd.exe). Each one is two lines and
just calls `uvx`.

### Windows (PowerShell)

1. Download [`claude-mv.ps1`](claude-mv.ps1) (or the whole repo).
2. Put it in any folder that's on your `PATH` — for example
   `C:\Users\<you>\bin\` after adding that folder to your user `PATH`.
3. PowerShell may refuse to run unsigned scripts. If so, allow local
   scripts once:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```
4. Now you can call it from anywhere:
   ```powershell
   claude-mv "C:\old\project" "C:\new\project"
   ```

### Windows (cmd.exe)

1. Download [`claude-mv.bat`](claude-mv.bat).
2. Drop it into a `PATH` folder.
3. Use it from `cmd`:
   ```cmd
   claude-mv "C:\old\project" "C:\new\project"
   ```

### Linux / macOS (bash / zsh)

1. Download [`claude-mv.sh`](claude-mv.sh).
2. Put it in a `PATH` folder under the name `claude-mv` (no extension).
   `~/.local/bin/` is a good choice on Linux; `/usr/local/bin/` works on
   both:
   ```bash
   sudo curl -L -o /usr/local/bin/claude-mv \
       https://raw.githubusercontent.com/derDere/claude-mv/main/claude-mv.sh
   sudo chmod +x /usr/local/bin/claude-mv
   ```
3. Or, if you already cloned the repo, symlink it:
   ```bash
   chmod +x ./claude-mv.sh
   ln -s "$(pwd)/claude-mv.sh" ~/.local/bin/claude-mv
   ```
4. Use it from anywhere:
   ```bash
   claude-mv ~/projects/old-name ~/projects/new-name
   ```

### Linux / macOS — alias (no file needed)

If you'd rather not put a file on disk, a shell alias does the same job.
Add this line to your `~/.bashrc` or `~/.zshrc`:

```bash
alias claude-mv='uvx --from git+https://github.com/derDere/claude-mv.git claude-mv'
```

Then `source` the file (or open a new terminal) and `claude-mv` is
available globally.

> Note: aliases only work in interactive shells — scripts won't see them.
> Use the wrapper file approach if you need that.

---

## Usage

```text
claude-mv [OLD] [NEW] [options]
```

| Command | What it does |
|---|---|
| `claude-mv OLD NEW` | Move the folder OLD → NEW and patch every Claude reference. **The main use case.** |
| `claude-mv --dry-run OLD NEW` | Show exactly what would change. No files touched. **Try this first.** |
| `claude-mv --fix OLD NEW` | Patch Claude state only. Use this when you've already moved the folder by hand (Explorer, `git mv`, etc.) and Claude lost track. |
| `claude-mv --list` | List every project Claude knows about, with status (folder still there? storage still there?). Useful for cleanups. |

Other flags:

- `--move-anyway` — proceed even if no Claude storage was found for OLD
  (the tool will otherwise ask you for confirmation in that case)
- `-v` / `--verbose` — show extra detail (e.g. per-file scan hits)

### Examples

The examples below use the short `claude-mv` form (wrapper script or
alias installed — see the previous section). Without a wrapper, prefix
every command with `uvx --from git+https://github.com/derDere/claude-mv.git`.

Move a Windows project:

```powershell
claude-mv "C:\Users\me\src\old-name" "C:\Users\me\src\new-name"
```

Preview the changes first:

```bash
claude-mv --dry-run ~/projects/foo ~/projects/foo-renamed
```

You already moved the folder manually and want Claude to find it again:

```bash
claude-mv --fix ~/projects/foo ~/projects/foo-renamed
```

See what Claude is currently tracking:

```bash
claude-mv --list
```

---

## What gets touched

Claude Code references the project path in exactly three places. `claude-mv`
updates all three:

1. **`~/.claude/projects/<encoded-path>/`** — the per-project storage folder
   (containing `*.jsonl` session transcripts). The folder is renamed via
   `os.rename`.
2. **`~/.claude.json` → `projects` map** — the global registry of known
   projects. The matching key is rekeyed; every other field stays
   byte-identical.
3. **`~/.claude/history.jsonl`** — every prompt you ever typed, with its
   project path. Each line is parsed as JSON, the `project` field gets
   rewritten, and the line is serialized back. No string substitution — that
   would risk corruption if OLD is a substring of NEW.

Everything else — `file-history/`, `session-env/`, `tasks/`, `shell-snapshots/`,
plugin state — is keyed by *session UUID* rather than project path, so it
stays valid automatically.

For the full technical write-up see [`claude-storage-research.md`](claude-storage-research.md).

### Path encoding

Claude Code encodes the absolute path into a folder name by replacing these
five characters with `-`:

| Input character | Why |
|---|---|
| `\` | Windows path separator |
| `/` | Unix path separator |
| `:` | drive-letter colon |
| `_` | (yes, really — Claude encodes underscores) |
| `.` | (yes, really — Claude encodes dots) |

So `C:\Users\me\my_project.v2` becomes `C--Users-me-my-project-v2`.
This means certain different paths collide (`foo_bar`, `foo-bar`, `foo.bar`
all encode to `foo-bar`). `claude-mv` checks for this collision before
doing anything destructive and aborts cleanly.

---

## Safety

`claude-mv` will not blindly trample your data:

- **Process check.** Refuses to run if any `claude.exe` / `claude code`
  process is alive. (You can still use `--dry-run` to preview.)
- **Backups.** Before any write, `~/.claude.json` and `~/.claude/history.jsonl`
  are copied to `*.claude-mv.bak` siblings. If something goes wrong, you can
  restore them with a regular file copy — no special tooling needed.
- **Atomic writes.** Every patched file is written to a `*.tmp` first and
  then `os.replace`'d into place. No half-written files.
- **mtime guard.** The tool snapshots each file's modification time before
  reading and re-checks it before writing. If Claude (or anything else)
  modified the file in between, the write aborts.
- **Collision check.** Refuses to overwrite an existing destination folder
  or storage folder.

The actual project folder is renamed with `os.rename` / `shutil.move`, so
rolling back is a simple manual `mv` in the worst case.

---

## What's *not* handled (yet)

- **UNC paths** (`\\server\share\…`) — rejected with a clear error.
- **Recursive sub-projects.** If you move `C:\foo` and there are also
  Claude-tracked projects under `C:\foo\bar`, those sub-projects are
  *not* migrated automatically. You'd run `claude-mv` again for each.
- **JSONL content (historical tool calls).** The transcripts still contain
  the old path inside historical `Read({path: ...})` calls etc. The tool
  *scans and reports* these but doesn't rewrite them, since they're history,
  not state. Claude will not try to re-execute old paths.

---

## How does it compare to alternatives?

There's no official Anthropic tool for this. The closest community options
are:

- [`claudepath`](https://github.com/Mahiler1909/claudepath) — Python, well-tested
  on macOS/Linux. Its encoder doesn't handle Windows backslashes/drive
  letters and it doesn't patch `~/.claude.json` at all.
- [`claude-move-project (clamp)`](https://github.com/wsagency/claude-move-project)
  and [`claude-code-project-mover`](https://github.com/skydiver/claude-code-project-mover) —
  both Bash, so Windows-native users would need WSL.

`claude-mv` is a slim alternative that:
- handles Windows paths correctly (all five encoding chars),
- patches `~/.claude.json` (which the others miss),
- has zero runtime dependencies, and
- runs the same way on every OS.

For the analysis of `claudepath`'s code that informed this design, see
[`claudepath-analysis.md`](claudepath-analysis.md).

---

## Project documents

- [`tool-spec.md`](tool-spec.md) — design spec for this tool
- [`claude-storage-research.md`](claude-storage-research.md) — research into
  Claude Code's storage layout
- [`claudepath-analysis.md`](claudepath-analysis.md) — analysis of the
  `claudepath` reference implementation

---

## License

No license declared yet — treat the code as all-rights-reserved by the
author until one is added.
