# Claude Code Storage — Recherche für `claude-mv` Tool

> Ziel: Tool das einen Projekt-Ordner verschiebt **und alle Claude-Chats/-Metadaten mitnimmt**.
> Diese Datei dokumentiert **nur** wo überall der absolute Projekt-Pfad gespeichert ist und was beim Verschieben angefasst werden muss.

Plattform-Hinweis: Pfade hier mit `%USERPROFILE%` bzw. `~` = User-Home (`C:\Users\<user>` auf Windows, `~` auf macOS/Linux). Verifiziert wurde live auf Windows 11 mit Claude Code 2.1.x.

---

## 0. Existierende Tools — Stand Mai 2026

**Offiziell von Anthropic: NICHTS.** Mehrere offene GitHub-Issues fordern ein eingebautes Move/Rename-Kommando, alle ohne Fix:
- [#1516](https://github.com/anthropics/claude-code/issues/1516), [#27473](https://github.com/anthropics/claude-code/issues/27473), [#33634](https://github.com/anthropics/claude-code/issues/33634), [#41344](https://github.com/anthropics/claude-code/issues/41344), [#52494](https://github.com/anthropics/claude-code/issues/52494).

Die offiziellen Docs erwähnen nur, dass beim Restoren einer Session der `cwd` matchen muss — kein Tool, keine Lösung.

### Community-Tools

| Tool | Sprache | Plattform | Patcht | Befehle | Bewertung für uns |
|---|---|---|---|---|---|
| **[claudepath](https://github.com/Mahiler1909/claudepath)** ([PyPI](https://pypi.org/project/claudepath/)) | Python | Cross-platform (Windows-Support nicht explizit dokumentiert, aber Python — sollte gehen) | `projects/<encoded>/` (rename), `history.jsonl`, *(behauptet auch JSONL-`cwd`, `sessions-index.json`, `usage-data/*` — siehe Hinweis unten)* | `mv`, `remap`, `list`, `restore`, `--dry-run` | **Bester Kandidat zum Testen.** Macht im Prinzip genau das was wir wollen. |
| **[claude-move-project (clamp)](https://github.com/wsagency/claude-move-project)** | Bash | macOS/Linux only — Windows nur via WSL/Git Bash | `projects/<encoded>/`, `history.jsonl` | `--move`, `--here`, `--fix`, `--list`, `--verify`, `--prune`, `--pack`, `--unpack` | **Nicht nativ Windows-tauglich.** Funktional am umfangreichsten, aber Shell-only. |
| **[claude-code-project-mover](https://github.com/skydiver/claude-code-project-mover)** | Bash | Unix-like | (dito) | Skript | Nicht nativ Windows. |
| Gists [gwpl](https://gist.github.com/gwpl/e0b78a711b4a6b2fc4b594c9b9fa2c4c), [maleta](https://gist.github.com/maleta/a71b54c121c262221f7e32ff45db32c1) | Bash | Unix | analog | — | Manuell. |
| MCP-Marketplace-Skills "[Project Directory Migration](https://mcpmarket.com/tools/skills/project-directory-migration)", "[Claude Migrate Session](https://mcpmarket.com/tools/skills/claude-migrate-session)" | — | — | analog | Skill-Aufruf | Closed-source Skills. |

### Empfehlung

1. **Erst `claudepath` testen** (`pipx install claudepath`, dann `claudepath mv --dry-run OLD NEW`). Falls's funktioniert: fertig, kein eigenes Tool nötig.
2. **Falls Windows-Probleme:** eigenes Tool in PowerShell/Python bauen. Der Migrations-Algorithmus aus §9 unten ist klein und überschaubar — die Live-Verifikation hier hat gezeigt dass die JSONL-Inhalte gar **nicht** angefasst werden müssen (siehe §6), was die Sache deutlich vereinfacht gegenüber dem was claudepath laut Doku tut.

### Wichtiger Hinweis zu claudepath's Feature-Liste

claudepath behauptet u.a. `sessions-index.json` und `usage-data/session-meta/*.json` zu patchen sowie das `cwd`-Feld in JSONL-Zeilen. **Diese Dateien/Felder existieren in Claude Code 2.1.153 auf diesem Windows-Rechner nicht** (live verifiziert — siehe §11). Das Tool macht in der Praxis wahrscheinlich No-Ops für diese Pfade, was ungefährlich ist. Aber: Es ist möglich dass claudepath für eine andere/ältere Claude-Code-Version entwickelt wurde und das Verhalten heute leicht anders ist als die Doku suggeriert.

---

## 1. TL;DR — Die 3 Stellen die migriert werden müssen

Wenn ein Projekt von `OLD` → `NEW` verschoben wird, müssen genau diese drei Dinge angefasst werden:

| # | Wo | Was | Format |
|---|----|-----|--------|
| 1 | `~/.claude/projects/<encoded(OLD)>/` | **Ordner umbenennen** zu `<encoded(NEW)>/` | Encoding siehe §3 |
| 2 | `~/.claude.json` → `projects` Map | **Key umbenennen** von `OLD` zu `NEW` | siehe §4 |
| 3 | `~/.claude/history.jsonl` | In allen Zeilen `"project"`-Feld von `OLD` auf `NEW` patchen | siehe §5 |

Optional: zusätzlich den Projekt-Ordner selbst von `OLD` → `NEW` verschieben (das ist ja das eigentliche Ziel).

**Alles andere (Sessions JSONL-Inhalt, file-history, session-env, tasks, shell-snapshots, …) ist UUID-keyed und braucht KEINE Änderung.**

---

## 2. Globale Ordnerstruktur unter `~/.claude/`

Live verifiziert auf diesem Rechner:

```
~/.claude/
├── CLAUDE.md                user-globale Instruktionen
├── settings.json            globale Settings
├── config.json              CLI-Config
├── history.jsonl            (!) GLOBAL: jede Eingabe + Projekt-Pfad + Session-ID
├── .credentials.json
├── stats-cache.json, policy-limits.json, statusline.py, …
│
├── projects/                (!) Per-Projekt-Storage — Ordner-Name = encoded(absoluter Pfad)
│   └── C--Users-me-source-local-claude-mv/
│       ├── <session-uuid>.jsonl                   ← Chat-Transcript (JSON Lines)
│       └── <session-uuid>/                        ← Session-Begleitdaten
│           ├── subagents/                          (Sub-Agent-Transcripts)
│           └── tool-results/                       (ausgelagerte große Tool-Outputs)
│
├── sessions/                kleine "Welche Session läuft auf Port X" Registry (Port→UUID)
├── tasks/<session-uuid>/    Todos pro Session
├── session-env/<session-uuid>/   env-Snapshots pro Session
├── file-history/<session-uuid>/  Pre-Edit-Snapshots (Versionen `<pfad-hash>@vN`)
├── shell-snapshots/         keyed by timestamp+nonce, NICHT pro Projekt
├── debug/, plans/, ide/, paste-cache/, downloads/, backups/, cache/, teams/, plugins/
│
└── ~/.claude.json           (liegt NEBEN ~/.claude/, nicht drin)
                             GLOBALE Config inkl. `projects` Map (Pfad → Config)
```

### Was steckt im Projekt-Ordner-Namen?

Beispiel live auf diesem Rechner:

| Original-Pfad | Encoded Ordnername unter `projects/` |
|---|---|
| `C:\Users\me\source\local\claude_mv` | `C--Users-me-source-local-claude-mv` |
| `C:\Users\me\Documents\Repos\com.example.project.private` | `C--Users-me-Documents-Repos-com-example-project-private` |
| `C:\Users\me\source\local\foo-bar` | `C--Users-me-source-local-foo-bar` |

---

## 3. Encoding-Schema des Ordnernamens (KRITISCH)

Algorithmus den Claude Code anwendet, um aus dem absoluten Pfad einen Ordnernamen unter `projects/` zu machen:

```
Ersetze JEDES dieser Zeichen durch  -  :
  :   (Doppelpunkt nach dem Drive-Letter)
  \   (Windows Pfad-Trenner)
  /   (Unix Pfad-Trenner)
  _   (Underscore!)  ← live-verifiziert auf diesem Rechner
  .   (Punkt!)       ← live-verifiziert: "com.example.project.private" → "com-example-project-private"
```

Praktische Konsequenz: Pfad → Ordnername ist **nicht eindeutig umkehrbar**. Mehrere Original-Pfade kollidieren auf denselben Ordnernamen:

```
C:\Users\me\source\local\claude_mv   ┐
C:\Users\me\source\local\claude-mv   ├─►  C--Users-me-source-local-claude-mv
C:\Users\me\source\local\claude.mv   ┘
```

→ Bekanntes Problem upstream (GitHub Issue [#7009](https://github.com/anthropics/claude-code/issues/7009)).

**Für unser Tool**: Wir müssen den encoded Folder-Namen nicht aus dem Original-Pfad raten. Wir können:
- Aus `~/.claude.json` → `projects` Map den exakten Key (= echter alter Pfad) holen
- Encoded Folder-Namen für OLD und NEW beide nach dem oben genannten Schema bauen
- Falls Ziel-Ordner schon existiert (Kollision) → abbrechen und warnen

### Bonus-Beobachtung: Case-Sensitivität

Auf diesem Rechner liegen sowohl `C--…` als auch `c--…` Ordner für teilweise identische Pfade (Drive-Letter mal groß, mal klein). Windows-Dateisystem ist zwar case-insensitive — aber Claude Code matcht streng. Das Tool sollte den Drive-Letter so übernehmen wie er im aktuellen `cwd` ankommt (PowerShell liefert ihn üblicherweise groß).

---

## 4. `~/.claude.json` — die globale Projekt-Registry

**Format**: Ein einziges großes JSON-File (live: ~160 KB, 77 Projekt-Einträge).

**Migrations-relevanter Teil**: `obj.projects` ist eine Map `{ "<absoluter-pfad>": { …config… } }`.

Beispiel-Einträge (live):
```json
"projects": {
  "C:/Users/me/source/local/claude_mv": {           ← Forward-Slash-Variante (neuere CC-Versionen)
    "allowedTools": [],
    "mcpContextUris": [],
    "mcpServers": {},
    "enabledMcpjsonServers": [],
    "disabledMcpjsonServers": [],
    "hasTrustDialogAccepted": true,
    "projectOnboardingSeenCount": 0,
    "hasClaudeMdExternalIncludesApproved": false,
    "hasClaudeMdExternalIncludesWarningShown": false,
    "lastGracefulShutdown": false,
    "lastVersionBase": "2.1.153"
  },
  "C:\\Users\\me\\source\\repos\\some-other-project": { … }   ← Backslash-Variante (ältere Einträge)
}
```

### ⚠ Gemischte Pfad-Formate

Live auf diesem Rechner: von 77 Keys nutzen **68 Forward-Slashes** (`C:/Users/…`) und **9 Backslashes** (`C:\Users\…`). Das Tool muss **beide Varianten** des alten Pfads suchen und genau die finden, die existiert.

### Tool-Action für `~/.claude.json`

1. Datei einlesen als JSON.
2. In `projects` nachschauen ob OLD existiert — sowohl mit `/` als auch mit `\`.
3. Den Eintrag unter neuem Key (NEW im selben Slash-Stil) einhängen, alten Key löschen.
4. **Backup vorher!** (Diese Datei enthält OAuth-Account, Subscription-State, Cache — die wollen wir nicht verlieren.)
5. JSON wieder schreiben (Pretty-Print beibehalten falls möglich, ist aber semantisch egal).

---

## 5. `~/.claude/history.jsonl` — globaler Prompt-Verlauf

Format: JSON Lines (eine JSON-Zeile = ein eingegebener Prompt, projektübergreifend).

Live-Beispiel:
```json
{"display":"…example prompt text…","pastedContents":{},"timestamp":1700000000000,"project":"C:\\Users\\me\\source\\repos\\some-project","sessionId":"00000000-0000-0000-0000-000000000000"}
```

Felder pro Zeile:
- `display` — der eingegebene Prompt-Text
- `pastedContents` — Paste-Buffer
- `timestamp` — Unix ms
- `project` — **absoluter Projekt-Pfad** (Backslash-Format)
- `sessionId` — UUID

**Live auf diesem Rechner: 3633 Zeilen.**

### Tool-Action für `history.jsonl`

1. Backup anlegen.
2. Datei zeilenweise lesen (nie als Ganzes — die Datei wird groß).
3. Jede Zeile parsen, falls `project === OLD` → durch `NEW` ersetzen, sonst unverändert weiterreichen.
4. Beide Format-Varianten von OLD prüfen (`\\` und `/`).
5. In Tempfile schreiben, dann atomar umbenennen.

---

## 6. Session-Transcript JSONL — KEIN `cwd` drin

**Wichtige live-Verifikation**: In `~/.claude/projects/<encoded>/<uuid>.jsonl` gibt es **kein** `cwd`- oder `workingDirectory`-Feld pro Zeile.

Die Verknüpfung Session ↔ Projekt-Pfad läuft **ausschließlich über den Ordnernamen** unter `projects/`. Das ist eine erfreuliche Vereinfachung: Wenn wir den Ordner umbenennen, sind alle Sessions automatisch dem neuen Pfad zugeordnet — **wir müssen die JSONL-Inhalte nicht anfassen**.

(Tool-Inputs wie `Read({path: "C:\\…\\alt\\datei.ts"})` stecken zwar als historische Tool-Calls im Transcript — die werden aber nicht beim Resume als CWD interpretiert, sondern sind nur Verlauf. Nicht migrationsrelevant.)

---

## 7. UUID-keyed Daten — kein Handlungsbedarf

Diese Ordner sind **per Session-UUID** organisiert, nicht per Projekt-Pfad. Da die JSONL-Datei beim Umbenennen des Projekt-Ordners ihre UUID behält, bleiben alle Verweise gültig — **nichts zu tun**:

- `~/.claude/file-history/<session-uuid>/` — Pre-Edit-Snapshots. Dateinamen sind `<file-path-hash>@v<N>` (Hash, kein Klartextpfad).
- `~/.claude/session-env/<session-uuid>/`
- `~/.claude/tasks/<session-uuid>/` — Todos (TaskCreate)
- `~/.claude/shell-snapshots/snapshot-bash-<timestamp>-<nonce>.sh` — gar nicht an Session/Projekt gebunden
- `~/.claude/debug/`, `plans/`, `ide/`, `paste-cache/` — analog, keine Projekt-Pfad-Bindung

Es ist okay wenn die file-history irgendwann verwaiste UUIDs enthält (= Sessions die gelöscht wurden); Claude Code räumt das selbst auf (siehe `.last-cleanup` neben `~/.claude/`).

---

## 8. Innerhalb des Projekt-Ordners SELBST: `.claude/`

Falls das Projekt einen eigenen `.claude/`-Ordner hat (z.B. dieses Repo hat einen), enthält der ggf. projekt-spezifische Settings (`settings.json`, `settings.local.json`, `agents/`, `skills/`, …). 

**Das verschieben wir mit, wenn wir den Projekt-Ordner verschieben — dafür ist das Tool ja da.** Aber: Wenn in `.claude/settings.json` oder Hooks absolute Pfade stehen, müssen die ggf. auch gepatcht werden. Das ist projekt-individuell und nicht generell vorhersagbar — Empfehlung: das Tool macht eine **Warnung+Grep** über `.claude/**` nach dem alten Pfad und meldet Treffer, ohne automatisch zu ändern.

---

## 9. Migrations-Algorithmus (vorgeschlagen)

```
Input: OLD_PATH (z.B. "C:\Users\me\source\local\claude_mv")
       NEW_PATH (z.B. "C:\Users\me\source\local\claude_mv_new")

PHASE 0 — Validate
  • OLD_PATH existiert, ist Verzeichnis, ist absolut
  • NEW_PATH existiert noch NICHT (oder ist leer)
  • encoded(OLD) ≠ encoded(NEW)  (sonst macht das Tool nichts brauchbares)
  • ~/.claude/projects/<encoded(NEW)>/ existiert noch NICHT (Kollisionsschutz)
  • ~/.claude.json existiert, ist parsebar

PHASE 1 — Backup
  • Kopiere ~/.claude.json nach ~/.claude.json.bak.<timestamp>
  • Kopiere ~/.claude/history.jsonl nach ~/.claude/history.jsonl.bak.<timestamp>
  • (Optional) Snapshot ~/.claude/projects/<encoded(OLD)>/ in ein Backup-Verzeichnis

PHASE 2 — Rename Projekt-Storage
  • Move-Item ~/.claude/projects/<encoded(OLD)>  →  ~/.claude/projects/<encoded(NEW)>

PHASE 3 — Patch ~/.claude.json
  • JSON laden
  • Im obj.projects Sub-Objekt: sowohl OLD-mit-\ als auch OLD-mit-/ suchen
  • Treffer: Eintrag-Wert übernehmen, alten Key löschen, unter NEW (gleicher Slash-Stil wie Original) wieder einfügen
  • JSON zurückschreiben

PHASE 4 — Patch ~/.claude/history.jsonl
  • Streaming line-by-line (Datei kann mehrere MB sein)
  • Jede Zeile parsen; wenn .project ∈ {OLD-\\-form, OLD-/-form}: durch NEW (gleicher Stil) ersetzen
  • In Tempfile schreiben, dann atomar umbenennen

PHASE 5 — Move des eigentlichen Projekt-Ordners
  • Move-Item OLD_PATH  →  NEW_PATH

PHASE 6 — Optional: Scan im Projekt nach Hardcoded Paths
  • grep -ri "OLD_PATH" im NEW_PATH (insbes. .claude/, .vscode/, package.json scripts, …)
  • Treffer dem User REPORTEN (nicht automatisch ändern)

PHASE 7 — Verify
  • ~/.claude/projects/<encoded(NEW)>/ enthält JSONL-Dateien
  • In ~/.claude.json existiert NEW als Key, OLD nicht mehr
  • In history.jsonl gibt es 0 Treffer für OLD (sofern überhaupt vorher welche da waren)
  • NEW_PATH existiert als Ordner
```

### Dry-Run

Tool sollte einen `--dry-run` Modus haben, der alle Phasen simuliert und ausgibt was geändert würde, ohne wirklich zu schreiben.

### Rollback

Bei Fehler in Phase 3/4/5: vorhandene Backup-Dateien zurückkopieren und projects/ wieder umbenennen.

---

## 10. Edge Cases / Footguns

1. **Underscore/Punkt im Pfad** — `claude_mv` → encoded `claude-mv`. Wenn das Ziel `claude-mv` heißt: Kollision (gleicher encoded folder). Tool muss das vorher erkennen.

2. **Forward- vs. Backslash-Inkonsistenz in `~/.claude.json`** — Tool muss beide Varianten suchen.

3. **Laufende Claude-Session blockiert Dateien** — Tool sollte erkennen wenn `~/.claude.json` gerade in Benutzung ist, oder den User zwingen erst zu beenden.

4. **Sub-Pfade**: Wenn jemand `C:\foo` umzieht, gibt es ggf. auch Storage für `C:\foo\bar` (Sub-Projekt). Soll das Tool **alle** Projekt-Einträge mit Prefix `OLD_PATH` mit-migrieren? **Empfehlung: ja**, aber als explizite Option `--recursive` (Default off), und mit Liste in der Dry-Run-Ausgabe.

5. **Symlinks/Junctions auf Windows** — wenn der Original-Pfad über einen Junction läuft, könnte Claude den realen Pfad gespeichert haben statt des Junction-Pfads. Tool sollte Realpath-Auflösung anbieten oder den encoded Folder-Namen direkt suchen.

6. **`.claude.json` ist heilig** — enthält OAuth-Token (`oauthAccount`), Subscription-State, Statsig-Cache. Auf KEINEN Fall ohne Backup überschreiben. Bei JSON-Parse-Fehler abbrechen, niemals "best effort" speichern.

7. **history.jsonl ist append-only** — wenn Claude Code parallel läuft, könnte zwischen Read und Write der Datei neue Zeilen angehängt werden. Idealerweise: User soll Claude vorher beenden. Andernfalls: Sicherheitscheck (Dateigröße vor/nach vergleichen).

8. **UNC-Pfade (`\\server\share\…`)** — nicht getestet, laut Community-Bugs (Issues #54069, #29935) instabil. Tool sollte UNC-Pfade explizit zurückweisen oder mit Warnung versehen.

---

## 11. Tabelle: Vollständige Pfad-Referenzen (Verifiziert + Quellen)

| Ort | Pfad-Referenz | Format | Migrationsbedarf | Verifikation |
|---|---|---|---|---|
| `~/.claude/projects/<encoded>/` | im **Ordnernamen** | encoded (siehe §3) | **JA** — rename | live ✔ |
| `~/.claude.json` `projects` Map | als **Key** | `\` oder `/`, gemischt | **JA** — rekey | live ✔ |
| `~/.claude/history.jsonl` | `"project"` Feld | `\\` (escaped) | **JA** — patch jeder Zeile | live ✔ |
| `<uuid>.jsonl` Inhalt | — | (kein `cwd`) | nein | live ✔ |
| `~/.claude/file-history/<uuid>/` | — | nur Hashes | nein | live ✔ |
| `~/.claude/session-env/<uuid>/` | — | per UUID | nein | live ✔ |
| `~/.claude/tasks/<uuid>/` | — | per UUID | nein | live ✔ |
| `~/.claude/shell-snapshots/` | ggf. in env-Vars eingebettet | reiner Shell-Snapshot | praktisch egal | live ✔ |
| `~/.claude/sessions/<port>.json` | port→uuid lookup | keine Pfade | nein | live ✔ |
| `<projekt>/.claude/**` (im Projekt selbst) | ggf. Hooks/Settings | projektspezifisch | scan+report | nicht generalisierbar |

---

## 12. Quellen

**Live verifiziert** auf Windows 11, Claude Code 2.1.153, am 2026-05-28.

**Externe Quellen** (vom Claude-Code-Guide-Agent recherchiert):
- Offizielle Docs: `code.claude.com/docs/en/claude-directory.md`, `…/memory.md`
- Community-Tool: [github.com/Mahiler1909/claudepath](https://github.com/Mahiler1909/claudepath) — vergleichbares Migrations-Tool
- Community-Skript: [curiouslychase.com claude-mv](https://curiouslychase.com/posts/rescuing-your-claude-conversations-when-you-rename-projects/)
- JSONL-Format-Analyse: [databunny.medium.com session-file-format](https://databunny.medium.com/inside-claude-code-the-session-file-format-and-how-to-inspect-it-b9998e66d56b)
- GitHub-Issues: [#7009 path collision](https://github.com/anthropics/claude-code/issues/7009), [#33634 sessions lost on move](https://github.com/anthropics/claude-code/issues/33634), [#54791 decouple sessions from path](https://github.com/anthropics/claude-code/issues/54791)

**Hinweis**: Die externen Recherche-Quellen erwähnen teilweise zusätzliche Dateien (`sessions-index.json`, `~/.claude/projects/<…>/memory/MEMORY.md`, `~/.claude/todos/`) die in dieser Claude-Code-Version (2.1.153 Windows) **nicht existieren**. Die obige Live-Verifikation ist maßgeblich für unser Tool.
