# `claude-mv` Tool — Spezifikation

> Anforderungen aus dem Anforderungs-Formular vom 2026-05-28 + offene Punkte geklärt.
> Recherche-Grundlagen siehe **`claude-storage-research.md`** (nicht hier duplizieren).

---

## 1. Zweck

Ein CLI-Tool das einen Projekt-Ordner verschiebt **und gleichzeitig alle Claude-Code-Chats/-Metadaten mitzieht**, damit `--continue`/`--resume` weiter funktioniert.

---

## 2. Stack & Distribution

- **Sprache**: Python 3.x, **stdlib-only** (keine Drittabhängigkeiten — auch kein `rich`, `click`, `psutil`).
- **Struktur**: plain `.py`-Dateien, modular aufgeteilt. **Keine** große Single-File-Lösung, aber auch kein komplexes Package-Layout.
  ```
  claude_mv/
  ├── main.py             ← Entry-Point (argparse, dispatch)
  ├── paths.py            ← Path-Encoding (claude_mv → C--Users-...-claude-mv), Pfad-Helper
  ├── migrate.py          ← Kernlogik: mv, fix
  ├── inventory.py        ← list-Command, Discovery
  ├── safety.py           ← Prozess-Check, Mtime-Snapshot, Backup, atomic-Write
  ├── ui.py               ← Fortschrittsbalken, Print-Helfer (stdlib only)
  └── pyproject.toml      ← nur damit `uvx` läuft, keine Install-Routine
  ```
- **Kein Install/Uninstall.** Aufruf direkt via `python -m claude_mv …` oder `uvx --from <repo> claude-mv …`.
- **`pyproject.toml`** minimal — Entry-Point auf `main.py:main`, damit `uvx` funktioniert.

---

## 3. Plattform

- **Windows zuerst** (Dev-Plattform).
- **Linux mitdenken** — d.h. Pfad-Encoding muss beide Stile beherrschen (Windows hat Drive-Letter+`:`, Linux nicht). Live-Test auf Linux erfolgt später.
- macOS nicht explizit gefordert (sollte aber als Linux-Variante mitlaufen).

---

## 4. CLI-Stil

- `argparse`, Subcommands.
- **Vollautomatisch** — keine y/N-Prompts. Destruktives geht über Flags, nicht über Dialoge.
- **Fortschrittsbalken** für `history.jsonl`-Patch (3000+ Zeilen) — ohne Drittlib, einfach `\r` mit Counter.
- Ausgaben: knapp, klar, farbig falls TTY (ANSI-Codes stdlib-only — kein `colorama` als Lib, einfach Strings).

### Aufruf-Form — keine Subcommands

Tool heißt eh `claude-mv` — kein extra `mv`-Subcommand. **Default-Aktion = move**. Spezialfälle über Mode-Flags:

| Aufruf | Verhalten |
|---|---|
| `claude-mv OLD NEW` | **Default**: Verschiebt Ordner OLD → NEW **und** patcht Claude-Storage. |
| `claude-mv OLD NEW --dry-run` | Zeigt alle geplanten Schritte, schreibt nichts. |
| `claude-mv --fix OLD NEW` | Patcht **nur** Claude-Storage (Fall: Ordner wurde schon manuell verschoben). Verschiebt **nichts** auf der Festplatte. |
| `claude-mv --list` | Listet getrackte Projekte + Status. Ignoriert Pfad-Args. |

Flags:
- `--dry-run` — keine Writes
- `--fix` — Mode-Flag (Storage-only)
- `--list` — Mode-Flag (Inventory)
- `--move-anyway` — auch verschieben wenn kein Claude-Storage zu OLD existiert (sonst Abbruch mit Y/n-Prompt — die einzige Ausnahme von der "no prompts"-Regel)
- `-v` / `--verbose` — mehr Detail

argparse-Setup: mutually exclusive group für `--fix` / `--list`. Bei `--list` werden POSITIONAL-Args ignoriert (oder als Filter genutzt, optional).

---

## 5. Was wird tatsächlich angefasst (aus Research §1)

Nur **3 Stellen**:

1. **`~/.claude/projects/<encoded(OLD)>/`** → umbenennen zu `<encoded(NEW)>/`
2. **`~/.claude.json` → `obj["projects"]`** → Sub-Key von OLD auf NEW umbenennen.
   - **WICHTIG**: nur diesen einen Dictionary-Key anpacken. Alle anderen Top-Level-Felder (`oauthAccount`, `subscriptionNoticeCount`, `cachedStatsigGates`, ~80 weitere) bleiben byte-identisch.
   - Slash-Stil des Keys (`/` vs `\\`) so übernehmen wie er war.
3. **`~/.claude/history.jsonl`** → in allen Zeilen `"project"`-Feld von OLD auf NEW patchen.
   - **JSON-aware** patchen: jede Zeile parsen, `project`-Feld vergleichen, ersetzen, serialisieren. **Niemals** als String-Ersetzung im rohen Text (OLD kann Substring von NEW sein → Doppel-Ersetzung).

UUID-keyed Daten (`file-history/`, `session-env/`, `tasks/`, `shell-snapshots/`) werden **nicht** angefasst.

### Zusätzlich: JSONL-Content-Scan (read-only, nur Warnung)

In `~/.claude/projects/<encoded(NEW)>/**/*.jsonl` (inkl. `subagents/<uuid>/*.jsonl`) **nach** der Umbenennung des Storage-Ordners ein `rglob`-Scan nach OLD-Pfad-Treffern. **Nicht patchen** — nur Anzahl Treffer pro Datei melden, damit der User weiß dass historische Tool-Calls noch den alten Pfad referenzieren (z.B. `Read({path: "C:\\old\\file.ts"})`). Das ist Verlauf, kein Bug.

Bei `mv` zusätzlich: **Ordner-Move** OLD → NEW.

### 5.1 Path-Encoder (kritisch — die Achillesferse von claudepath)

Algorithmus: jedes Zeichen aus dieser Klasse durch `-` ersetzen:

| Eingabe-Zeichen | Beispiel-Input | Encoded-Output |
|---|---|---|
| `\` (Backslash) | `C:\Users\foo` | `C--Users-foo` |
| `/` (Forward-Slash) | `/home/user/foo` | `-home-user-foo` |
| `:` (Doppelpunkt nach Drive-Letter) | `C:` | `C-` |
| `_` (Underscore) | `claude_mv` | `claude-mv` |
| `.` (Punkt) | `com.example.foo` | `com-example-foo` |

Plus:
- **Drive-Letter-Case** so übernehmen wie geliefert. PowerShell liefert üblicherweise groß (`C:`). Wenn User Tool aus einer Shell mit klein (`c:`) aufruft → entstehen separate Encoded-Folder. Tool macht hier **nichts magisches** — verlässt sich auf das was rein kommt.
- **Kollisions-Check** vorab: existiert `~/.claude/projects/<encoded(NEW)>/` schon? → Abbruch.
- **Reverse-Decode brauchen wir NICHT.** OLD wird vom User als Argument geliefert, wir encoden nur in eine Richtung. (claudepath hat DFS-Backtracking dafür — komplexer Code für ein Problem das wir gar nicht haben.)

---

## 6. Safety-Layer (alle stdlib, ~30 Zeilen total)

### 6.1 Prozess-Check
- Vor jeder Mutation: ist Claude Code gerade aktiv?
- **Windows**: `subprocess.run(["tasklist", "/FO", "CSV"], …)`, parsen nach `claude.exe` oder Node-Prozess mit `claude` in der CommandLine.
- **Linux/macOS**: `subprocess.run(["ps", "-eo", "command="], …)`, analog.
- **Plattform-Switch via `sys.platform`** — nicht versuchen `pgrep` überall zu nutzen (genau dieser Fehler bei claudepath: silently kaputt auf Windows).
- Wenn weder `tasklist` noch `ps` verfügbar (exotische Plattform): **explizite Warnung**, kein Silent-Fail. User muss bewusst `--force` setzen.
- Treffer → Abbruch mit klarer Meldung. `--force` überspringt.

### 6.2 Mtime-Snapshot
- Vor Read von `~/.claude.json` und `history.jsonl`: `os.stat(f).st_mtime_ns` cachen.
- Vor Write: nochmal vergleichen. Wenn jemand zwischendurch geschrieben hat → Abbruch.

### 6.3 Atomic Write
- Niemals direkt in Ziel-Datei schreiben.
- Pattern: `tmp = path + ".tmp"`, write tmp, `os.replace(tmp, path)`.

### 6.4 Backup — minimal
- **Nur zwei Kopien**, direkt daneben:
  - `~/.claude.json` → `~/.claude.json.claude-mv.bak`
  - `~/.claude/history.jsonl` → `~/.claude/history.jsonl.claude-mv.bak`
- **Kein** Backup des `projects/<encoded>/`-Ordners (der wird per `os.rename` umbenannt, nicht zerstört — rollback ist `os.rename` zurück).
- **Kein** Timestamped-Verzeichnis, **kein** `manifest.txt`, **kein** `restore`-Command.
- Begründung (User-Aussage): "Änderungen sind nicht so kompliziert dass man sie nicht von Hand wieder fixen kann — es sind nur ein paar Pfade."
- Bei jedem neuen Lauf wird die `.bak` überschrieben (nur letzter Stand wird vorgehalten).
- `--no-backup` Flag entfällt — Backups sind so billig dass sie immer laufen.

---

## 7. Algorithmus für `mv OLD NEW`

```
0. Validate
   - OLD existiert, ist Dir, ist absolut
   - NEW existiert nicht (oder ist leeres Dir)
   - encoded(OLD) ≠ encoded(NEW)
   - ~/.claude/projects/<encoded(NEW)>/ existiert noch NICHT
1. Safety
   - Prozess-Check (außer --force)
   - mtime-Snapshot von .claude.json und history.jsonl
2. Backups
   - cp .claude.json → .claude.json.bak.<ts>
   - cp history.jsonl → history.jsonl.bak.<ts>
3. Rename projects-Ordner
   - os.rename projects/<encoded(OLD)> → projects/<encoded(NEW)>
4. Patch .claude.json (atomic)
   - load → mtime recheck → rekey projects[OLD]→projects[NEW] → write .tmp → replace
5. Patch history.jsonl (atomic, mit Fortschrittsbalken, JSON-aware pro Zeile)
   - line-by-line read + parse + transform `project`-Feld + serialize + write .tmp → replace
6. JSONL-Content-Scan (read-only)
   - rglob projects/<encoded(NEW)>/**/*.jsonl, OLD-Pfad-Treffer zählen, Anzahl melden — nicht patchen.
7. Move Projekt-Ordner
   - shutil.move OLD → NEW
8. Verify
   - encoded(NEW)-Ordner da, .claude.json hat NEW als Key, history.jsonl hat 0 OLD-Treffer im `project`-Feld
```

Für `--dry-run`: Schritte 2-7 nur loggen, nicht ausführen.
Für `fix OLD NEW`: Schritt 7 weglassen (Ordner ist schon woanders).

---

## 8. Edge Cases (aus Research §10, hier gelistet, Lösung optional/später)

| Edge Case | Behandlung |
|---|---|
| Encoded-Folder-Kollision (`_` → `-`) | Vorab-Check, Abbruch mit klarer Meldung. |
| `.claude.json` mit `/` vs `\\` als Key | Beide Varianten von OLD suchen, Slash-Stil beim Schreiben übernehmen. |
| Recursive Sub-Projekte | **v1: nicht unterstützt.** Falls relevant: später als `--recursive` Flag nachrüsten. |
| UNC-Pfade `\\server\share\…` | **v1: nicht unterstützt**, mit klarer Fehlermeldung abweisen. |
| Symlinks / Junctions | **v1: nicht prüfen** — User Responsibility. |
| Claude-Storage komplett fehlt für OLD | Default: **Abbrechen mit Y/n-Prompt** ("kein Storage gefunden, trotzdem Ordner verschieben?"). Mit `--move-anyway` Flag: direkt durchziehen ohne Prompt. (Einzige Stelle wo das Tool fragt.) |
| `.claude.json`-Eintrag existiert, aber `projects/<encoded>/`-Ordner nicht (oder umgekehrt) | Tool warnt, migriert das was da ist. |

---

## 9. Anti-Goals

- **Keine** Drittabhängigkeiten (`rich`, `click`, `colorama`, `psutil`, `tqdm`, …) — auch nicht „nur eine kleine".
- **Kein** install/uninstall-Schritt.
- **Keine** y/N-Prompts.
- **Kein** automatisches Backup-Cleanup.
- **Keine** Modifikation der JSONL-Inhalte (es gibt eh keinen `cwd` drin — siehe Research §6).
- **Kein** großes Package-Layout (kein `src/`, kein `tests/` zwingend, kein `setup.py`).

---

## 10. Offener Punkt vor Coding-Start

User-Frage am Ende der Klärung: **Erst claudepath clonen + 10-min-Vergleich**, oder **direkt loslegen**? → wartet auf Entscheidung.
