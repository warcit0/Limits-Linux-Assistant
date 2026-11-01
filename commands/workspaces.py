"""Destinos de Hyprland con comprobación posterior del estado."""

import json
import re
import subprocess
import time
from modules.command_result import ResultadoComando


def normalizar_destino(target):
    valor = str(target).strip().casefold()
    nombres = dict(zip("cero uno dos tres cuatro cinco seis siete ocho nueve diez".split(),range(11)))
    valor = str(nombres.get(valor,valor))
    return "10" if valor == "0" else valor


class WorkspaceCommands:
    def __init__(self):
        self.anterior = None

    def _leer(self, comando):
        r = subprocess.run(
            ["hyprctl", "-j", comando],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        return json.loads(r.stdout)

    def _destino(self, target):
        valor = normalizar_destino(target)
        for w in self._leer("workspaces"):
            if valor in {
                str(w["id"]),
                str(w["name"]),
                str(w["name"]).removeprefix("special:"),
            }:
                return w
        # Hyprland materializa los destinos numéricos al entrar en ellos.
        if valor.isdecimal() and 1 <= int(valor) <= 10:
            return {"id": int(valor), "name": str(int(valor))}
        if not valor.isdecimal():
            nombre = valor.removeprefix("special:")
            especiales = set()
            for b in self._leer("binds"):
                arg = str(b.get("arg", ""))
                if b.get("dispatcher") == "togglespecialworkspace":
                    especiales.add(arg)
                elif arg.startswith("special:"):
                    especiales.add(arg.removeprefix("special:"))
            if nombre in especiales and re.fullmatch(r"[\w-]+", nombre):
                return {"id": -1, "name": "special:"+nombre}
        raise ValueError(
            f"No existe el espacio de trabajo {valor}. No he creado ninguno."
        )

    def _dispatch(self, accion, destino):
        r = subprocess.run(
            ["hyprctl", "dispatch", accion, str(destino)],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        if r.stdout.strip() != "ok":
            raise ValueError("Hyprland rechazó la operación.")

    def _comprobar(self, consulta, condicion):
        for _ in range(6):
            if condicion(self._leer(consulta)):
                return
            time.sleep(0.02)
        raise ValueError("Hyprland no confirmó el cambio; no lo daré por realizado.")

    def switch(self, target: str) -> str:
        """Cambia a un destino válido, incluso vacío, y comprueba el estado real."""
        try:
            destino = self._destino(target)
            if destino["id"] < 0:
                nombre = str(destino["name"]).removeprefix("special:")
                if not re.fullmatch(r"[\w-]+", nombre):
                    raise ValueError("Nombre de espacio especial inválido.")
                visible = lambda ms: any(m.get("specialWorkspace", {}).get("name") == "special:"+nombre for m in ms)
                if visible(self._leer("monitors")):
                    return ResultadoComando(f"El espacio especial {nombre} ya está visible; comprobado.",ok=True,verificado=True)
                actual = self._leer("activeworkspace")
                self._dispatch("togglespecialworkspace", nombre)
                self._comprobar("monitors", visible)
                self.anterior = actual["id"]
                return ResultadoComando(f"El espacio especial {nombre} está visible; comprobado.",ok=True,verificado=True)
            actual = self._leer("activeworkspace")
            if actual["id"] == destino["id"]:
                return ResultadoComando(f"Ya estás en el espacio de trabajo {destino['name']}.",ok=True,verificado=True)
            self._dispatch("workspace", destino["id"])
            self._comprobar("activeworkspace", lambda w: w["id"] == destino["id"])
            self.anterior = actual["id"]
            return ResultadoComando(f"Estás en el espacio de trabajo {destino['name']}; he comprobado el cambio.",ok=True,verificado=True)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
            return f"No pude cambiar de espacio de trabajo: {e}"

    def back(self) -> str:
        """Regresa al último espacio cambiado por Limits."""
        if self.anterior is None:
            return "No tengo un espacio anterior registrado en esta sesión."
        return self.switch(str(self.anterior))

    def move_window(self, target: str) -> str:
        """Mueve solo la ventana activa y comprueba su destino."""
        try:
            destino = self._destino(target)
            if destino["id"] < 0:
                return "No he movido la ventana: el destino debe ser un espacio numérico existente."
            ventana = self._leer("activewindow")
            direccion = ventana.get("address")
            if not direccion:
                return "No hay una ventana activa que pueda mover."
            self._dispatch(
                "movetoworkspacesilent", f"{destino['id']},address:{direccion}"
            )
            self._comprobar(
                "clients",
                lambda ws: any(
                    w.get("address") == direccion
                    and w.get("workspace", {}).get("id") == destino["id"]
                    for w in ws
                ),
            )
            return ResultadoComando(f"Ventana movida al espacio de trabajo {destino['name']}; destino comprobado.",ok=True,verificado=True)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
            return f"No pude mover la ventana: {e}"

    def list_open(self) -> str:
        """Enumera espacios existentes y aplicaciones visibles."""
        try:
            espacios = self._leer("workspaces")
            clientes = self._leer("clients")
            return (
                "; ".join(
                    f"{w['name']}: "
                    + (
                        ", ".join(
                            sorted(
                                {
                                    c.get("class", "aplicación")
                                    for c in clientes
                                    if c.get("workspace", {}).get("id") == w["id"]
                                }
                            )
                        )
                        or "sin ventanas"
                    )
                    for w in espacios
                )
                or "No hay espacios de trabajo visibles."
            )
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            return "No pude consultar los espacios de trabajo de Hyprland."
