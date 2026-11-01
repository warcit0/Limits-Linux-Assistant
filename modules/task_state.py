"""Estado local de tareas; separado de los recuerdos personales."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid


class RespuestaTurno(str):
    """Mantiene el contrato de texto y transporta su origen y artefactos."""

    def __new__(cls, texto, *, fuente="system", completo=None, artefactos=()):
        obj = super().__new__(cls, texto)
        obj.source = fuente
        obj.completo = completo if completo is not None else texto
        obj.artefactos = tuple(artefactos)
        return obj


@dataclass
class Tarea:
    sesion: str
    objetivo: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    rol: str = "cotidiano"
    modo: str = "leer"
    estado: str = "trabajando"
    revision: int = 1
    actualizado: float = field(default_factory=time.time)
    historial: list = field(default_factory=list)
    raices: list = field(default_factory=list)
    observadas: list = field(default_factory=list)
    artefactos: list = field(default_factory=list)
    recibos: dict = field(default_factory=dict)
    pruebas: dict = field(default_factory=dict)
    pendiente: dict | None = None
    respuesta: str = ""
    respuesta_archivo: str | None = None
    sesiones_modelos: dict = field(default_factory=dict)
    pregunta_abierta: str = ""
    epoca_memoria: int = 0
    seleccion_herramientas: list = field(default_factory=list)
    capacidades: list = field(default_factory=list)
    plan_resultados: list = field(default_factory=list)
    coherente: bool = False
    semantica: bool = False
    autorizaciones_semanticas: dict = field(default_factory=dict)
    limitacion_rechazada: bool = False
    reinterpretar: bool = False
    requiere_sintesis: bool = False
    cobertura_completa: bool = False
    pendientes_objetivo: list = field(default_factory=list)
    requiere_observacion: bool = False
    objetivos: list = field(default_factory=list)
    dialogo: list = field(default_factory=list)
    memorias: list = field(default_factory=list)
    entidades: dict = field(default_factory=dict)
    errores_plan: list = field(default_factory=list)
    escalado: bool = False
    reclasificado: bool = False
    plan_operativo: list = field(default_factory=list)
    referente: dict = field(default_factory=dict)

    def contexto(self, limite: int) -> dict:
        """Prioriza objetivo y observaciones recientes sin truncar un JSON."""
        base = {"objetivo": self.objetivo[:min(4000, limite // 3)], "rol": self.rol, "modo": self.modo, "estado": self.estado,
                "raices": list(self.raices), "observadas": self.observadas[-80:],
                "artefactos": self.artefactos[-8:], "historial": [], "pregunta_abierta": self.pregunta_abierta}
        for campo in ("observadas", "artefactos", "raices"):
            while len(json.dumps(base, ensure_ascii=False)) > limite and base[campo]:
                base[campo].pop(0)
        for turno in reversed(self.historial[-10:]):
            candidato = [turno] + base["historial"]
            if len(json.dumps({**base, "historial": candidato}, ensure_ascii=False)) > limite:
                break
            base["historial"] = candidato
        return base


class AlmacenTareas:
    """JSON atómico por sesión, nombres opacos y permisos privados."""

    def __init__(self, directorio):
        self.directorio = Path(directorio).expanduser()
        self._lock = threading.RLock()
        self._cache: dict[str, Tarea] = {}

    def _ruta(self, sesion):
        nombre = hashlib.sha256(sesion.encode()).hexdigest()
        return self.directorio / "estado" / (nombre + ".json")

    def cargar(self, sesion: str) -> Tarea | None:
        with self._lock:
            if sesion in self._cache:
                return self._cache[sesion]
            ruta = self._ruta(sesion)
            if not ruta.exists():
                return None
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            tarea = Tarea(**datos)
            if tarea.sesion != sesion:
                raise ValueError("La sesión guardada no coincide")
            # Tras reiniciar no se recuperan autorizaciones ni trabajos activos.
            if tarea.estado in {"trabajando", "aprobacion"}:
                tarea.estado = "interrumpida"
                tarea.pendiente = None
            self._cache[sesion] = tarea
            return tarea

    def guardar(self, tarea: Tarea):
        with self._lock:
            self.directorio.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.directorio, 0o700)
            ruta = self._ruta(tarea.sesion)
            ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(ruta.parent, 0o700)
            temporal = ruta.with_suffix("." + uuid.uuid4().hex + ".tmp")
            tarea.actualizado = time.time()
            try:
                with os.fdopen(os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                      0o600), "w", encoding="utf-8") as f:
                    json.dump(asdict(tarea), f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temporal, ruta)
            finally:
                temporal.unlink(missing_ok=True)
            self._cache[tarea.sesion] = tarea

    def carpeta(self, tarea: Tarea) -> Path:
        self.directorio.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directorio, 0o700)
        ruta = self.directorio / "trabajos" / tarea.id
        ruta.mkdir(parents=True, exist_ok=True, mode=0o700)
        return ruta
