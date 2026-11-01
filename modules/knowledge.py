"""Recuerdos versionados en SQLite y Markdown editable con sincronización reversible."""

import fcntl
import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path

from modules.memory import MemoryStore, redact

log = logging.getLogger("limits.conocimiento")
CARPETAS = (
    "Preferencias",
    "Entorno",
    "Decisiones",
    "Sesiones",
    "Aprendizajes",
    "Pendientes-de-validar",
)
ESQUEMA = """
CREATE TABLE IF NOT EXISTS knowledge_meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
INSERT OR IGNORE INTO knowledge_meta VALUES('epoch',0);
CREATE TABLE IF NOT EXISTS knowledge (
 id TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
 status TEXT NOT NULL, source TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 updated REAL NOT NULL, expires REAL, deleted INTEGER NOT NULL DEFAULT 0,
 dirty INTEGER NOT NULL DEFAULT 1, exported_hash TEXT, conflict INTEGER NOT NULL DEFAULT 0,
 fact_key TEXT UNIQUE);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(title, body, content='knowledge', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
 INSERT INTO knowledge_fts(rowid,title,body) VALUES(new.rowid,new.title,new.body); END;
CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge BEGIN
 INSERT INTO knowledge_fts(knowledge_fts,rowid,title,body) VALUES('delete',old.rowid,old.title,old.body);
 INSERT INTO knowledge_fts(rowid,title,body) VALUES(new.rowid,new.title,new.body); END;
CREATE TRIGGER IF NOT EXISTS facts_knowledge_insert AFTER INSERT ON facts BEGIN
 INSERT INTO knowledge(id,category,title,body,status,source,updated,fact_key)
 VALUES('fact-'||lower(hex(randomblob(16))),'Preferencias',new.key,new.value,'confirmado','usuario_explicito',unixepoch(),new.key)
 ON CONFLICT(fact_key) DO UPDATE SET title=new.key,body=new.value,exported_hash=CASE WHEN deleted=1 THEN NULL ELSE exported_hash END,deleted=0,dirty=1,conflict=0,revision=revision+1,updated=unixepoch(); END;
DROP TRIGGER IF EXISTS facts_knowledge_update;
CREATE TRIGGER IF NOT EXISTS facts_knowledge_update AFTER UPDATE OF value ON facts BEGIN
 UPDATE knowledge_meta SET value=value+1 WHERE key='epoch';
 UPDATE knowledge SET body=new.value,dirty=1,exported_hash=CASE WHEN conflict=1 THEN NULL ELSE exported_hash END,conflict=0,revision=revision+1,updated=unixepoch() WHERE fact_key=new.key; END;
DROP TRIGGER IF EXISTS facts_knowledge_delete;
CREATE TRIGGER IF NOT EXISTS facts_knowledge_delete AFTER DELETE ON facts BEGIN
 UPDATE knowledge_meta SET value=value+1 WHERE key='epoch';
 DELETE FROM fact_history WHERE fact_id=old.id;
 UPDATE episodes SET ok=0 WHERE instr(text,old.value)>0 OR instr(lower(text),replace(old.key,'_',' '))>0;
 UPDATE knowledge SET deleted=1,dirty=1,body='',title='',revision=revision+1,updated=unixepoch() WHERE fact_key=old.key;
 UPDATE knowledge SET deleted=1,dirty=1,body='',title='' WHERE category IN ('Aprendizajes','Sesiones','Pendientes-de-validar') AND (instr(body,old.value)>0 OR instr(lower(title),replace(old.key,'_',' '))>0 OR instr(lower(body),replace(old.key,'_',' '))>0); END;
"""


def huella(texto):
    return hashlib.sha256(texto.encode()).hexdigest()


class Conocimiento:
    @contextmanager
    def _bloqueo_archivo(self):
        fd = os.open(
            self.carpeta / ".limits-sync.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    @staticmethod
    def _render(r):
        meta = {k: r[k] for k in ("id", "revision", "status", "source", "updated")}
        return (
            "---\nlimits: "
            + json.dumps(meta, ensure_ascii=False)
            + "\n---\n# "
            + r["title"]
            + "\n\n"
            + r["body"]
            + "\n"
        )

    def __init__(self, sqlite_path, carpeta):
        self.path = str(Path(sqlite_path).expanduser())
        self.carpeta = Path(carpeta).expanduser()
        self.lock = threading.RLock()
        self.conn = None
        self.enabled = False
        try:
            if self.carpeta.is_symlink():
                raise ValueError("La bóveda no puede ser un enlace.")
            # Inicializar el mismo esquema de hechos: no crear una segunda fuente.
            inicial = MemoryStore(self.path)
            if not inicial.enabled:
                raise ValueError("SQLite no está disponible.")
            inicial.close()
            self.conn = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.conn.executescript("BEGIN IMMEDIATE;\n"+ESQUEMA+"\nCOMMIT;")
            for fila in self.conn.execute('SELECT key,value FROM facts').fetchall():
                limpio = redact(fila['value'])
                if limpio != fila['value']:
                    self.conn.execute('UPDATE facts SET value=? WHERE key=?',(limpio,fila['key']))
            self.conn.execute("""INSERT OR IGNORE INTO knowledge
                (id,category,title,body,status,source,updated,fact_key)
                SELECT 'fact-'||lower(hex(randomblob(16))),'Preferencias',key,value,'confirmado','usuario_explicito',unixepoch(),key FROM facts""")
            self.conn.commit()
            self.carpeta.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.carpeta, 0o700)
            for nombre in CARPETAS:
                p = self.carpeta / nombre
                if p.is_symlink():
                    raise ValueError("Una carpeta de la bóveda es un enlace.")
                p.mkdir(exist_ok=True, mode=0o700)
            indice = self.carpeta / "Inicio.md"
            if not indice.exists():
                self._escribir(
                    indice,
                    "# Memoria de Limits\n\n"
                    + "\n".join(f"- [[{n}/]]" for n in CARPETAS)
                    + "\n\nPuedes editar notas. Elimina una nota para olvidarla. Los conflictos y las inferencias quedan pendientes, nunca como hechos.\nLas notas aportan contexto; no conceden permisos para ejecutar acciones. No guardes secretos.\n",
                )
            self.enabled = True
            self.sincronizar()
        except (OSError, ValueError, sqlite3.Error):
            log.warning(
                "Memoria compartida no disponible; el asistente sigue funcionando."
            )
            if self.conn:
                self.conn.close()
            self.conn = None

    def close(self):
        with self.lock:
            if self.conn:
                self.conn.close()
                self.conn = None
            self.enabled = False

    @staticmethod
    def _escribir(path, texto):
        if path.is_symlink():
            raise ValueError("No se escribe a través de enlaces.")
        temporal = path.with_suffix(".limits-tmp")
        fd = os.open(
            temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "w") as f:
            f.write(texto)
        temporal.replace(path)

    def _ruta(self, r):
        if r["category"] not in CARPETAS or not re.fullmatch(r"[\w-]{1,100}", r["id"]):
            raise ValueError("Nota fuera del catálogo de memoria.")
        path = self.carpeta / r["category"] / (r["id"] + ".md")
        if path.parent.is_symlink() or path.is_symlink():
            raise ValueError("Nota enlazada no permitida.")
        return path

    def guardar(
        self,
        categoria,
        titulo,
        contenido,
        *,
        estado="confirmado",
        origen="observacion",
        id_=None,
        vence=None,
    ):
        if not self.enabled:
            return None
        if categoria not in CARPETAS or estado not in {"confirmado", "pendiente"}:
            raise ValueError("Categoría o estado inválidos.")
        titulo, contenido = redact(titulo)[:300], redact(contenido)[:8000]
        id_ = id_ or uuid.uuid4().hex
        with self.lock:
            transaccion = self.conn.in_transaction
            try:
                self.conn.execute(
                    """INSERT INTO knowledge(id,category,title,body,status,source,updated,expires)
                  VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,
                  title=excluded.title,updated=excluded.updated,expires=excluded.expires,dirty=1,revision=revision+1
                  WHERE deleted=0 AND (body!=excluded.body OR title!=excluded.title)""",
                    (id_, categoria, titulo, contenido, estado, origen, time.time(), vence),
                )
                if not transaccion:
                    self.conn.commit()
            except sqlite3.Error:
                if transaccion:
                    raise
                self.conn.rollback()
                log.warning("No se pudo guardar el recuerdo; SQLite conserva el estado anterior.")
                return None
        return id_

    def epoca(self):
        if not self.enabled:
            return 0
        with self.lock:
            try:
                return self.conn.execute(
                    "SELECT value FROM knowledge_meta WHERE key='epoch'"
                ).fetchone()[0]
            except sqlite3.Error:
                log.warning("No se pudo consultar la revisión de memoria.")
                return 0

    def _borrar(self, r):
        self.conn.execute("UPDATE knowledge SET deleted=1,dirty=1,body='',title='' WHERE source=?",("conflicto_edicion:"+r["id"],))
        self.conn.execute("UPDATE knowledge_meta SET value=value+1 WHERE key='epoch'")
        self.conn.execute(
            "UPDATE knowledge SET deleted=1,dirty=1,body='',title='',revision=revision+1 WHERE id=?",
            (r["id"],),
        )
        if r["fact_key"]:
            self.conn.execute("DELETE FROM facts WHERE key=?", (r["fact_key"],))

    def sincronizar(self):
        try:
            self._sincronizar()
        except (OSError, ValueError, sqlite3.Error):
            log.warning(
                "No se pudo sincronizar la bóveda; SQLite conserva los cambios."
            )

    def _sincronizar(self):
        """La marca dirty es una cola transaccional persistente; un fallo se reintenta."""
        if not self.enabled:
            return
        with self.lock, self._bloqueo_archivo():
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                filas = self.conn.execute("SELECT * FROM knowledge").fetchall()
                conocidos = set()
                for r in filas:
                    path = self._ruta(r)
                    conocidos.add(path)
                    if r["deleted"]:
                        if path.exists():
                            path.unlink()
                        self.conn.execute(
                            "UPDATE knowledge SET dirty=0 WHERE id=?", (r["id"],)
                        )
                        continue
                    if path.exists():
                        if path.stat().st_size > 32000:
                            continue
                        texto = path.read_text()
                        if r["exported_hash"] and huella(texto) != r["exported_hash"]:
                            if r["dirty"] and texto == self._render(r):
                                self.conn.execute(
                                    "UPDATE knowledge SET dirty=0,exported_hash=? WHERE id=?",
                                    (huella(texto), r["id"]),
                                )
                            else:
                                self._importar(path, texto, r)
                    elif r["exported_hash"]:
                        self._borrar(r)
                # Notas nuevas escritas por el usuario: solo carpetas dedicadas, sin enlaces.
                for categoria in CARPETAS:
                    carpeta = self.carpeta / categoria
                    if carpeta.is_symlink():
                        raise ValueError("Carpeta enlazada.")
                    for path in list(carpeta.glob("*.md"))[:250]:
                        if (
                            path in conocidos
                            or path.is_symlink()
                            or path.stat().st_size > 32000
                        ):
                            continue
                        id_ = "nota-" + huella(str(path.relative_to(self.carpeta)))[:32]
                        contenido = path.read_text()
                        if contenido.startswith("---\nlimits: "):
                            try:
                                meta = json.loads(
                                    contenido.split("\n---\n", 1)[0].removeprefix(
                                        "---\nlimits: "
                                    )
                                )
                                viejo = self.conn.execute(
                                    "SELECT deleted FROM knowledge WHERE id=?",
                                    (meta.get("id"),),
                                ).fetchone()
                                if viejo:
                                    # Una copia con id gestionado es un respaldo del usuario, no un nuevo recuerdo.
                                    continue
                            except (ValueError, TypeError):
                                continue
                        contenido = redact(contenido)
                        self.guardar(
                            categoria,
                            path.stem,
                            contenido,
                            origen="edicion_usuario",
                            id_=id_,
                            estado="pendiente"
                            if categoria == "Pendientes-de-validar"
                            else "confirmado",
                        )
                        # Se conserva el archivo humano; se registra como alias de importación.
                        self.conn.execute(
                            "UPDATE knowledge SET source=? WHERE id=?",
                            (
                                "edicion_usuario:"
                                + str(path.relative_to(self.carpeta)),
                                id_,
                            ),
                        )
                        # Formato canónico evita ambigüedad de identificador y edición futura.
                        canon = self.carpeta / categoria / (id_ + ".md")
                        if canon != path and not canon.exists():
                            path.rename(canon)
                for r in self.conn.execute(
                    "SELECT * FROM knowledge WHERE dirty=1 AND conflict=0"
                ).fetchall():
                    path = self._ruta(r)
                    if r["deleted"]:
                        if path.exists():
                            path.unlink()
                        self.conn.execute(
                            "UPDATE knowledge SET dirty=0 WHERE id=?", (r["id"],)
                        )
                        continue
                    texto = self._render(r)
                    self._escribir(path, texto)
                    self.conn.execute(
                        "UPDATE knowledge SET dirty=0,exported_hash=? WHERE id=?",
                        (huella(texto), r["id"]),
                    )
                self.conn.commit()
                self._indice()
            except (OSError, ValueError, sqlite3.Error, UnicodeError):
                # Nunca descartar la cola por un fallo del archivo; los registros siguen en SQL.
                self.conn.rollback()
                log.warning("Sincronización de memoria pendiente; se reintentará.")

    def _indice(self):
        filas = self.conn.execute('SELECT * FROM knowledge WHERE deleted=0 ORDER BY category,title').fetchall()
        partes = []
        for categoria in CARPETAS:
            notas = [r for r in filas if r['category']==categoria]
            if not notas:continue
            partes.append('## '+categoria)
            for r in notas:
                titulo = r['title'].replace('_',' ') if r['fact_key'] else r['title']
                titulo = re.sub(r'[\[\]|\n]',' ',titulo)
                estado = ' · pendiente' if r['status']!='confirmado' or r['conflict'] else ''
                partes.append(f"- [[{categoria}/{r['id']}|{titulo}]]{estado}")
        inicio, fin = '<!-- limits:indice:inicio -->', '<!-- limits:indice:fin -->'
        bloque = inicio+'\n'+('\n'.join(partes) or 'Todavía no hay recuerdos guardados.')+'\n'+fin
        path = self.carpeta/'Inicio.md'
        actual = path.read_text() if path.exists() and not path.is_symlink() else '# Memoria de Limits\n'
        if inicio in actual and fin in actual:
            antes, resto = actual.split(inicio,1)
            _, despues = resto.split(fin,1)
            nuevo = antes+bloque+despues
        else:
            for categoria in CARPETAS:
                actual = actual.replace('- [['+categoria+'/]]\n','')
            nuevo = actual.rstrip()+'\n\n'+bloque+'\n'
        if nuevo != actual:self._escribir(path,nuevo)

    def _importar(self, path, texto, r):
        try:
            cabecera, resto = texto.split("\n---\n", 1)
            meta = json.loads(cabecera.removeprefix("---\nlimits: "))
            titulo, cuerpo = resto.split("\n", 1)
            if meta.get("id") != r["id"]:
                raise ValueError("Identificador distinto.")
            if (r["dirty"] or meta.get("revision") != r["revision"]) and not (r["conflict"] and meta.get("resolver_revision")==r["revision"]):
                id_ = "conflicto-" + huella(r["id"] + texto)[:32]
                self.guardar(
                    "Pendientes-de-validar",
                    "Conflicto: " + r["title"],
                    "Nota original: "+r["id"]+"\nRevisión SQLite: "+str(r["revision"])+"\nValor SQLite: "+r["body"]+"\nEdición humana:\n"+resto+"\nPara resolver, edita la nota original y añade resolver_revision con la revisión SQLite al objeto limits de su cabecera.",
                    estado="pendiente",
                    origen="conflicto_edicion:"+r["id"],
                    id_=id_,
                )
                if not r["conflict"]:
                    self.conn.execute("UPDATE knowledge_meta SET value=value+1 WHERE key='epoch'")
                self.conn.execute(
                    "UPDATE knowledge SET conflict=1 WHERE id=?", (r["id"],)
                )
                return
            if meta.get("status") not in {"confirmado", "pendiente"}:
                raise ValueError("Estado inválido.")
            titulo, cuerpo = redact(titulo.removeprefix("# ")), redact(cuerpo.strip())
            self.conn.execute("UPDATE knowledge_meta SET value=value+1 WHERE key='epoch'")
            self.conn.execute(
                """UPDATE knowledge SET title=?,body=?,status=?,source='edicion_usuario',
              revision=revision+1,updated=?,dirty=1,conflict=0 WHERE id=?""",
                (titulo, cuerpo, meta["status"], time.time(), r["id"]),
            )
            if r["fact_key"]:
                self.conn.execute(
                    "UPDATE facts SET value=?,updated_at=datetime('now') WHERE key=?",
                    (cuerpo, r["fact_key"]),
                )
        except (ValueError, KeyError, TypeError):
            self.conn.execute("UPDATE knowledge SET conflict=1 WHERE id=?", (r["id"],))

    def recuperar(self, consulta, limite=4):
        if not self.enabled:
            return []
        self.sincronizar()
        tokens = [t for t in re.findall(r"\w+", consulta.casefold()) if len(t)>2 and "".join(c for c in unicodedata.normalize("NFD",t) if not unicodedata.combining(c)) not in {"que","dime","quiero","necesito","favor","puedes","ahora","primero","hoy","del","los","para","las","con","por","como"}][:20]
        if not tokens:
            return []
        match = " OR ".join('"' + t + '"' for t in tokens)
        with self.lock:
            try:
                filas = self.conn.execute(
                    """SELECT k.id,k.category,k.title,k.body,k.source,k.updated FROM knowledge k
                   JOIN knowledge_fts f ON k.rowid=f.rowid WHERE knowledge_fts MATCH ?
                   AND k.deleted=0 AND k.conflict=0 AND k.status='confirmado' AND k.source NOT LIKE 'conflicto_edicion%'
                   AND (k.expires IS NULL OR k.expires>?) ORDER BY bm25(knowledge_fts) LIMIT ?""",
                    (match, time.time(), min(6, limite)),
                ).fetchall()
                resultado = []
                usados = 0
                for r in filas:
                    item = dict(r)
                    item["body"] = item["body"][:1000]
                    usados += len(json.dumps(item, ensure_ascii=False))
                    if usados > 3500:
                        break
                    resultado.append(item)
                return resultado
            except sqlite3.Error:
                log.warning("No se pudo recuperar memoria relevante.")
                return []

    def olvidar(self, id_):
        if not self.enabled:
            return False
        with self.lock, self.conn:
            r = self.conn.execute(
                "SELECT * FROM knowledge WHERE id=?", (id_,)
            ).fetchone()
            if not r:
                return False
            self._borrar(r)
        self.sincronizar()
        return True

    def registrar_resultado(self, entrada, acciones, *, completado=False):
        if not self.enabled:
            return
        # Solo procedimientos con efectos comprobados, nunca texto libre del asistente.
        validas = [a["accion"] for a in acciones if a.get("ok") and a.get("verificado")]
        if validas and completado:
            texto = "Registro histórico, no estado actual.\nPetición: "+redact(entrada)+"\nPasos comprobados: "+", ".join(validas)
            detalles = [redact(a.get("observacion", ""))[:500] for a in acciones if a.get("ok") and a.get("verificado") and a.get("observacion")]
            if detalles:
                texto += "\nObservación al ejecutar: "+"; ".join(detalles)
            self.guardar(
                "Aprendizajes",
                "Procedimiento comprobado",
                texto,
                origen="herramientas_verificadas",
                id_="procedimiento-" + huella(texto)[:32],
            )
        if acciones:
            dia = time.strftime("%Y-%m-%d")
            id_sesion = "sesion-" + dia
            with self.lock:
                anterior = self.conn.execute(
                    "SELECT body FROM knowledge WHERE id=?", (id_sesion,)
                ).fetchone()
            lineas = anterior["body"].splitlines() if anterior else []
            resumen = ", ".join(
                a.get("accion", "")
                + (
                    ": comprobado"
                    if a.get("ok") and a.get("verificado") is True
                    else ": pendiente o fallido"
                )
                for a in acciones
            )
            linea = time.strftime("%H:%M:%S") + (" · completo · " if completado else " · incompleto · ") + resumen
            self.guardar(
                "Sesiones",
                "Actividad " + dia,
                "\n".join((lineas + [linea])[-40:]),
                origen="recibos_herramientas",
                id_=id_sesion,
            )
        self.sincronizar()
