"""Cuarentena reversible de episodios sintéticos inequívocos."""

import os
import sqlite3
from datetime import datetime
from pathlib import Path


def limpiar_episodios(ruta, aplicar=False):
    """Nunca toca hechos; conserva originales en respaldo y tabla de cuarentena."""
    ruta = Path(ruta).expanduser()
    if not ruta.is_file():
        raise ValueError("No existe la base de memoria que se quiere revisar.")
    conn = sqlite3.connect(ruta)
    try:
        filas = conn.execute(
            "SELECT id,role,text,intent,ok FROM episodes ORDER BY id"
        ).fetchall()
        ids = set()
        for i, (id_, rol, texto, intent, ok) in enumerate(filas):
            sintetico = intent == "test" or (
                rol == "assistant"
                and texto == "respuesta simulada"
                and i > 0
                and filas[i - 1][1] == "user"
                and filas[i - 1][2] in {"gemini hola", "investiga las estrellas"}
            )
            if sintetico:
                ids.add(id_)
                if (
                    rol == "assistant"
                    and i
                    and filas[i - 1][1] == "user"
                    and filas[i - 1][0] == id_ - 1
                ):
                    ids.add(filas[i - 1][0])
        falsas = {
            "Estoy viendo una pantalla con un usuario que está trabajando en el sistema. Se observa la información del sistema, detalles sobre la canción sonando y las aplicaciones corrientes.",
            "No he realizado cambios. El objetivo se ha alcanzado. Te encuentras ya en el espacio de trabajo 2.",
            "Ya estoy en el World Space 1.",
        }
        excluir = [
            r[0] for r in filas if r[1] == "assistant" and r[2] in falsas and r[4] != 0
        ]
        informe = {
            "sinteticos": len(ids),
            "afirmaciones_no_verificadas": len(excluir),
            "aplicado": False,
        }
        if not aplicar or not (ids or excluir):
            return informe
        carpeta = ruta.parent / "respaldos"
        carpeta.mkdir(mode=0o700, exist_ok=True)
        backup = (
            carpeta
            / f"memoria-antes-cuarentena-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db"
        )
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        copia = sqlite3.connect(backup)
        try:
            conn.backup(copia)
        finally:
            copia.close()
        with conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS episodes_quarantine AS SELECT * FROM episodes WHERE 0"
            )
            for id_ in sorted(ids):
                conn.execute(
                    "INSERT INTO episodes_quarantine SELECT * FROM episodes WHERE id=?",
                    (id_,),
                )
                conn.execute("DELETE FROM episodes WHERE id=?", (id_,))
            conn.executemany(
                "UPDATE episodes SET ok=0 WHERE id=?", [(i,) for i in excluir]
            )
        informe.update(aplicado=True, respaldo=str(backup))
        return informe
    finally:
        conn.close()
