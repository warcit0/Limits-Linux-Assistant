"""Registra la bóveda propia de Limits sin sustituir las bóvedas existentes."""

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import Config
from modules.knowledge import Conocimiento


def main():
    c = Config()
    registro = Path.home() / ".config/obsidian/obsidian.json"
    # Solo leer el registro local; no abrir ni modificar notas de otras bóvedas.
    datos = json.loads(registro.read_text()) if registro.exists() else {"vaults": {}}
    vaults = datos.setdefault("vaults", {})
    if not isinstance(vaults, dict):
        raise ValueError("Registro de Obsidian inválido.")
    carpeta = Path(c.KNOWLEDGE_VAULT)
    respaldo = Path.home() / ".limits/respaldos"
    respaldo.mkdir(parents=True, exist_ok=True, mode=0o700)
    if registro.exists():
        copia = respaldo / ("obsidian-antes-memoria-" + str(time.time_ns()) + ".json")
        fd = os.open(copia, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        shutil.copyfile(registro, copia)
    memoria = Conocimiento(c.MEMORY_PATH, carpeta)
    if not memoria.enabled:
        raise RuntimeError("No se pudo preparar la memoria compartida.")
    memoria.close()
    obsidian = carpeta / ".obsidian"
    obsidian.mkdir(exist_ok=True)
    id_ = hashlib.sha256(str(carpeta).encode()).hexdigest()[:16]
    if not any(v.get("path") == str(carpeta) for v in vaults.values()):
        vaults[id_] = {"path": str(carpeta), "ts": int(time.time() * 1000)}
        registro.parent.mkdir(parents=True, exist_ok=True)
        temp = registro.with_suffix(".limits-tmp")
        temp.write_text(json.dumps(datos, ensure_ascii=False))
        temp.replace(registro)
    print("Bóveda de memoria registrada:", carpeta)


if __name__ == "__main__":
    main()
