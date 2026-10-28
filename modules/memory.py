"""Memoria persistente de Limits (P0-3): hechos, notas y episodios.

SQLite en `~/.limits/memory.db` (WAL + FTS5). Una sola conexión por proceso;
el CLI y el servicio pueden coexistir gracias a WAL.

Regla de oro: la memoria NUNCA puede tumbar al asistente. Cualquier fallo de
disco/SQLite deja el store `enabled=False` y Limits funciona como antes.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
DEFAULT_MAX_BYTES = 600

# ── Redacción en escritura: secretos que jamás deben quedar en disco ────────
_REDACTIONS = (
    (re.compile(r"\bgsk_[A-Za-z0-9]{8,}\b"), "[redactado]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "[redactado]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[redactado]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), "[redactado]"),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "[redactado]"),
)

_ARTICULOS = ("mi ", "mis ", "el ", "la ", "los ", "las ", "un ", "una ")

# Palabras que no aportan a una búsqueda por FTS («qué sabes de mi proyecto»).
_STOPWORDS = {"mi", "mis", "el", "la", "los", "las", "de", "del", "sobre",
              "que", "y", "o", "un", "una", "unos", "unas", "lo", "al"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id           INTEGER PRIMARY KEY,
    key          TEXT NOT NULL UNIQUE,
    value        TEXT NOT NULL,
    tags         TEXT DEFAULT '',
    source       TEXT DEFAULT 'user',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    last_used_at TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    key, value, tags,
    content='facts', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, key, value, tags)
    VALUES (new.id, new.key, new.value, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, key, value, tags)
    VALUES ('delete', old.id, old.key, old.value, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, key, value, tags)
    VALUES ('delete', old.id, old.key, old.value, old.tags);
    INSERT INTO facts_fts(rowid, key, value, tags)
    VALUES (new.id, new.key, new.value, new.tags);
END;

CREATE TABLE IF NOT EXISTS episodes (
    id     INTEGER PRIMARY KEY,
    ts     TEXT NOT NULL,
    role   TEXT NOT NULL,
    text   TEXT NOT NULL,
    intent TEXT,
    ok     INTEGER,
    meta   TEXT
);
CREATE INDEX IF NOT EXISTS episodes_ts ON episodes(ts);

CREATE TABLE IF NOT EXISTS fact_history (
    id        INTEGER PRIMARY KEY,
    fact_id   INTEGER REFERENCES facts(id),
    old_value TEXT,
    new_value TEXT,
    ts        TEXT NOT NULL
);
"""


def _plain(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).casefold()


def redact(text: str) -> str:
    """Sustituye tokens con pinta de secreto por `[redactado]`."""
    out = str(text)
    for pattern, repl in _REDACTIONS:
        out = pattern.sub(repl, out)
    return out


def normalize_key(key: str) -> str:
    """'mi Proyecto principal' → 'proyecto_principal'."""
    text = _plain(key).strip(" .,;:!?¡¿'\"")
    for art in _ARTICULOS:
        if text.startswith(art):
            text = text[len(art):]
            break
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def _ts() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class MemoryStore:
    def __init__(self, path: str | Path = "~/.limits/memory.db",
                 enabled: bool = True):
        self.path = str(Path(path).expanduser())
        self.enabled = False
        self._conn: sqlite3.Connection | None = None
        if not enabled:
            return
        conn = None
        try:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=5)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            conn.commit()
            if self.path != ":memory:":
                os.chmod(self.path, 0o600)
            self._conn = conn
            self.enabled = True
        except Exception:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            self._conn = None
            self.enabled = False

    # ── Hechos ───────────────────────────────────────────────────────────────
    def remember(self, key: str, value: str, tags: str = "") -> str:
        """Upsert de un hecho. Sin clave → nota libre (`nota:<hash>`)."""
        value = redact(str(value)).strip()
        if not value:
            return "No he guardado nada: estaba vacío."
        given_key = normalize_key(key) if key else ""
        is_note = not given_key
        norm = given_key or f"nota_{hashlib.sha1(value.encode('utf-8')).hexdigest()[:8]}"
        tags = redact(str(tags)).strip()
        now = _ts()
        if not self.enabled or self._conn is None:
            return "No puedo guardar: la memoria está desactivada."
        try:
            row = self._conn.execute(
                "SELECT id, value FROM facts WHERE key = ?", (norm,)).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO facts (key, value, tags, source, created_at, updated_at)"
                    " VALUES (?, ?, ?, 'user', ?, ?)",
                    (norm, value, tags, now, now))
            else:
                if row["value"] != value:
                    self._conn.execute(
                        "INSERT INTO fact_history (fact_id, old_value, new_value, ts)"
                        " VALUES (?, ?, ?, ?)", (row["id"], row["value"], value, now))
                self._conn.execute(
                    "UPDATE facts SET value = ?, tags = ?, updated_at = ? WHERE id = ?",
                    (value, tags, now, row["id"]))
            self._conn.commit()
        except Exception:
            return "No he podido guardarlo ahora mismo."
        if is_note:
            return "Anotado: lo tendré en cuenta."
        legible = norm.replace("_", " ")
        return f"Anotado: {legible} es {value}."

    def forget(self, key: str) -> bool:
        """Borra un hecho por clave exacta o, si no hay, por parecido."""
        if not self.enabled or self._conn is None:
            return False
        norm = normalize_key(key)
        try:
            cur = self._conn.execute("DELETE FROM facts WHERE key = ?", (norm,))
            if cur.rowcount == 0 and len(norm) >= 3:
                cur = self._conn.execute(
                    "DELETE FROM facts WHERE key LIKE ?", (f"%{norm}%",))
            self._conn.commit()
            return cur.rowcount > 0
        except Exception:
            return False

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Búsqueda FTS5 (sin acentos); fallback a LIKE si FTS no está."""
        if not self.enabled or self._conn is None or not str(query).strip():
            return []
        tokens = [t for t in re.findall(r"\w+", _plain(query))
                  if t not in _STOPWORDS and len(t) > 1]
        if not tokens:
            tokens = re.findall(r"\w+", _plain(query))
        rows = []
        if tokens:
            match = " AND ".join(f'"{t}"*' for t in tokens)
            try:
                rows = self._conn.execute(
                    "SELECT key, value, tags FROM facts"
                    " WHERE id IN (SELECT rowid FROM facts_fts WHERE facts_fts MATCH ?)"
                    " ORDER BY COALESCE(last_used_at, updated_at) DESC LIMIT ?",
                    (match, limit)).fetchall()
            except Exception:
                rows = []
        if not rows:
            like = f"%{tokens[0]}%" if tokens else f"%{query}%"
            try:
                rows = self._conn.execute(
                    "SELECT key, value, tags FROM facts"
                    " WHERE key LIKE ? OR value LIKE ?"
                    " ORDER BY COALESCE(last_used_at, updated_at) DESC LIMIT ?",
                    (like, like, limit)).fetchall()
            except Exception:
                return []
        return [dict(r) for r in rows]

    def facts_block(self, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
        """Bloque para `{memory}`: recencia primero, nunca corta una palabra."""
        if not self.enabled or self._conn is None:
            return ""
        try:
            rows = self._conn.execute(
                "SELECT id, key, value FROM facts"
                " ORDER BY COALESCE(last_used_at, updated_at) DESC, id DESC"
            ).fetchall()
        except Exception:
            return ""
        lines, used, ids = [], 0, []
        for row in rows:
            label = ("nota" if row["key"].startswith("nota_")
                     else row["key"].replace("_", " "))
            line = f"- {label}: {row['value']}"
            size = len(line.encode("utf-8")) + 1
            if used + size > max_bytes:
                break
            lines.append(line)
            used += size
            ids.append((_ts(), row["id"]))
        if ids:
            try:
                self._conn.executemany(
                    "UPDATE facts SET last_used_at = ? WHERE id = ?", ids)
                self._conn.commit()
            except Exception:
                pass
        return "\n".join(lines)

    def list_facts(self, limit: int = 20) -> list[dict]:
        if not self.enabled or self._conn is None:
            return []
        try:
            rows = self._conn.execute(
                "SELECT key, value, updated_at FROM facts"
                " ORDER BY COALESCE(last_used_at, updated_at) DESC LIMIT ?",
                (limit,)).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    # ── Episodios ────────────────────────────────────────────────────────────
    def log_turn(self, role: str, text: str, intent: str | None = None,
                 ok: bool | None = None, meta: dict | None = None) -> None:
        if not self.enabled or self._conn is None or not text:
            return
        import json

        try:
            self._conn.execute(
                "INSERT INTO episodes (ts, role, text, intent, ok, meta)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (_ts(), role, redact(str(text)), intent,
                 None if ok is None else int(bool(ok)),
                 json.dumps(meta, ensure_ascii=False) if meta else None))
            # Retención acotada: el historial de voz no es un archivo eterno.
            self._conn.execute(
                "DELETE FROM episodes WHERE id <= (SELECT MAX(id) - 5000 FROM episodes)")
            self._conn.commit()
        except Exception:
            pass

    def recent_turns(self, n: int = 6) -> list[dict]:
        if not self.enabled or self._conn is None:
            return []
        try:
            rows = self._conn.execute(
                "SELECT role, text FROM episodes WHERE role IN ('user', 'assistant')"
                " ORDER BY id DESC LIMIT ?", (n,)).fetchall()
            return [dict(r) for r in reversed(rows)]
        except Exception:
            return []

    def stats(self) -> dict:
        if not self.enabled or self._conn is None:
            return {"enabled": False, "facts": 0, "episodes": 0}
        try:
            facts = self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            episodes = self._conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            return {"enabled": True, "facts": facts, "episodes": episodes,
                    "path": self.path}
        except Exception:
            return {"enabled": False, "facts": 0, "episodes": 0}

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


# ── Singleton perezoso (no toca disco al importar ni al construir Limits) ───
_default_store: MemoryStore | None = None


def get_store() -> MemoryStore:
    global _default_store
    if _default_store is None:
        try:
            from config import Config
            cfg = Config()
            _default_store = MemoryStore(cfg.MEMORY_PATH,
                                         enabled=cfg.MEMORY_ENABLED)
        except Exception:
            _default_store = MemoryStore(enabled=False)
    return _default_store


def set_store(store: MemoryStore | None) -> None:
    """Reemplaza el singleton (tests o arranque explícito)."""
    global _default_store
    _default_store = store


def _close_default_store() -> None:
    if _default_store is not None:
        _default_store.close()


atexit.register(_close_default_store)
