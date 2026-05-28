# claudepath — Was lernen wir, was vermeiden wir

Analyse von [github.com/Mahiler1909/claudepath](https://github.com/Mahiler1909/claudepath) (shallow clone, mit Explore-Agent durchsucht, danach wieder gelöscht). Stand: 2026-05-28.

> **Kontext**: Wir bauen unser eigenes `claude-mv` Tool (Spec siehe `tool-spec.md`). claudepath ist die nächstliegende Vergleichs-Implementierung — Python, stdlib-only, gleicher Use-Case.

## TL;DR

claudepath ist **Unix-zentriert und auf Windows kaputt** in genau dem Punkt der für uns am wichtigsten ist: dem Path-Encoding. Auch das `~/.claude.json`-Patching fehlt komplett. **Wir können nicht einfach abkupfern** — wir müssen den Encoder neu denken. Übernehmen können wir: deren Backup-Layout, das JSON-aware Patching von JSONL, und die Test-Struktur.

---

## ✅ Was wir übernehmen

### 1. JSON-aware Line-Patching für `history.jsonl` (statt String-Replace)
**Quelle**: `src/claudepath/updaters.py:replace_path_values()`

Jede Zeile als JSON parsen, nur das `project`-Feld vergleichen/ersetzen, dann wieder serialisieren. **Nicht** per regex/string-replace, weil OLD ein Substring von NEW sein kann und dann doppelt ersetzt würde. Solide Idee — übernehmen.

### 2. Atomic-Write Pattern
Sie nutzen `tempfile.mkstemp()` + `os.replace()`. Genau das was unsere Spec §6.3 vorgibt. Bestätigt unseren Ansatz.

### 3. Backup-Layout
- Location: `~/.claude/backups/claudepath/{YYYYMMDD_HHMMSS}/`
- Plus `manifest.txt` mit Key=Value-Pairs (`project_dir=…`, `history_path=…`)
- Pro Migration ein eigener Timestamped-Ordner statt `.bak.<ts>` neben der Datei

→ **Besser als unser bisheriger Plan**. Sammelt alle Backups einer Migration zentral, einfacher zum Restoren. **Übernehmen** (mit unserem Tool-Namen statt `claudepath/`).

### 4. Test-Struktur
- Eine Test-Datei pro Modul (`test_encoder.py`, `test_updaters.py`, `test_mover.py`, …)
- pytest mit `tmp_path` Fixture
- In-Memory-Daten statt Fixture-Files

Sauber. Wenn wir Tests schreiben: gleiche Struktur.

### 5. Stdlib-only ist machbar
Sie nutzen exakt 0 Drittabhängigkeiten. ANSI-Color-Codes als Konstanten (`RESET = "\033[0m"` etc.), kein `colorama`. Bestätigt dass unsere stdlib-Anforderung realistisch ist.

---

## ❌ Was wir explizit anders/besser machen

### 1. Path-Encoder — KAPUTT auf Windows
**Quelle**: `src/claudepath/encoder.py`

```python
def encode_path(abs_path: str) -> str:
    return abs_path.replace("/", "-")
```

**Das ist's. Mehr nicht.**

Was claudepath **nicht** behandelt (alles live-verifiziert dass Claude Code es macht):
- Backslashes `\` → bleiben unverändert. `C:\Users\foo` wird zu `C:-Users-foo` statt `C--Users-foo`. **Komplett falsch.**
- Doppelpunkt nach Drive-Letter → bleibt. `C:` wird `C:` statt `C-`.
- Underscores `_` → bleiben. Aber Claude Code macht `claude_mv` → `claude-mv`.
- Punkte `.` → bleiben. Aber Claude Code macht `com.example.foo` → `com-example-foo`.
- Case-Sensitivity: kein Handling (auf diesem Rechner gibt's `C--…` UND `c--…` Ordner für identische Pfade).

→ **Unser Encoder muss alle 5 Klassen abdecken**: `\`, `/`, `:`, `_`, `.`. Plus Drive-Letter-Case übernehmen wie geliefert.

### 2. `~/.claude.json` wird **gar nicht** angefasst
**Quelle**: gesamte Codebase, kein Treffer für `.claude.json`.

claudepath patcht nur Dateien **innerhalb** von `~/.claude/`. Die globale Projekt-Registry in `~/.claude.json` (mit dem `projects`-Sub-Object) bleibt unberührt → **Trust-Dialog, MCP-Server-Config etc. landen wieder im Onboarding** für den umbenannten Pfad.

Das ist ein echter Bug bei denen (oder Vergessen). Unser Tool muss das machen, siehe Spec §5 Punkt 2.

### 3. Process-Check ist Unix-only und still kaputt auf Windows
**Quelle**: `_check_claude_running()` nutzt `pgrep -f` — gibt's auf Windows nicht. Der OSError wird silently gefangen, **keine Warnung**, Tool macht weiter.

→ Unser Tool: `tasklist` auf Windows, `ps -e` auf Linux, mit klarer Fehlermeldung falls weder noch (statt Silent-Fail).

### 4. Custom Arg-Parser statt argparse
**Quelle**: `src/claudepath/cli.py` — komplett manuell, if-elif-Chain.

Reinvented the wheel. Wir nutzen `argparse` aus stdlib, das ist explizit für sowas da. Spart Code und liefert `--help` umsonst.

### 5. Patcht Phantom-Dateien ohne zu meckern
`sessions-index.json` und `usage-data/*` werden patched falls vorhanden, sonst stilles `return 0`. Auf aktuellem Claude Code (2.1.153) existieren die gar nicht — claudepath rödelt sich also durch File-Existence-Checks die immer `False` zurückgeben. Funktioniert, aber:

→ Unser Tool: **diese Dateien gar nicht erst kennen**. Slimmer, klarer, kein toter Code.

### 6. DFS-basiertes Path-Decoding (Quelle: `_decode_encoded_name()`)
Sie versuchen aus dem encoded Ordnernamen den Original-Pfad **rekonstruktiv** abzuleiten — DFS mit Backtracking, Filesystem-Probing. Geht nur weil das Encoding ambig ist (`a-b` kann `a-b` oder `a/b` sein).

→ **Brauchen wir nicht.** Unser Tool kennt den OLD-Pfad immer (User gibt ihn als Argument), wir encoden nur **hin**, nie zurück.

### 7. Hintergrund-Thread für PyPI-Version-Check
Sie pollen im Hintergrund die PyPI nach Updates. Komplexität für nichts.

→ **Anti-Goal in Spec §9 bestätigt.**

---

## 🤔 Was sie haben, was wir auch wollen sollten

### `list`-Command — Discovery von getrackten Projekten
Sie haben `claudepath list`. Wir haben das auch in Spec §4 schon. Bestätigt sinnvoll.

### `--no-backup` Flag
Falls man bewusst keinen Backup will (z.B. Wegwerf-Test). Nicht kritisch, aber günstig zum Mitnehmen.

### Recursive JSONL-Patching via `rglob("*.jsonl")`
Sie laufen rekursiv durch das Projekt-Storage und patchen **alle** JSONL — inklusive `subagents/<uuid>/*.jsonl`. Wir hatten in Research §6 festgestellt dass JSONL kein `cwd` enthält und nicht angefasst werden muss. **Aber**: in den Subagent-JSONL? Nicht verifiziert auf diesem Rechner. Sicherheitshalber: unser Tool **scannt** die JSONLs nach OLD-Pfad-Treffern und meldet sie nur (kein Auto-Patch), damit wir nicht stillschweigend Geschichte umschreiben.

### Duplicate-Session-Handling beim Merge
Falls jemand `claude-mv mv A B` macht und in B existiert schon Claude-Storage: warnen + überspringen statt überschreiben. Kann später, aber gut zu wissen.

---

## Spec-Updates daraus

Konkret in `tool-spec.md` zu ergänzen:

1. **Encoder-Tabelle** (5 Zeichenklassen → `-`) explizit aufschreiben mit Tests.
2. **Backup-Layout** von `.bak.<ts>` neben der Datei auf `~/.claude/backups/claude-mv/{ts}/` mit `manifest.txt` umstellen.
3. **JSONL-Scan-Modus** (read-only) als zusätzlicher Schritt für `mv`: meldet Treffer von OLD im JSONL-Content, ohne zu patchen.
4. **Process-Check**: explizit `tasklist`/`ps`, mit Fallback-Fehlermeldung wenn beides fehlt.
5. `--no-backup` Flag in CLI-Tabelle ergänzen.

---

## Sources

- claudepath GitHub: https://github.com/Mahiler1909/claudepath
- Geklont nach `.temp/claudepath/`, durchsucht via Explore-Subagent, danach gelöscht.
