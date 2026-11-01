"""Comandos de control del sistema operativo."""

import json
import subprocess
import re
import time
import psutil
from rich.console import Console
from commands.apps import AppCommands
from commands.media import pick_player

console = Console()


class SystemCommands:
    """
    SEGURIDAD: Todos los comandos usan listas de argumentos (NO shell=True con f-strings)
    para prevenir inyección de comandos si el LLM genera parámetros maliciosos.
    """

    def set_volume(self, level: int, mode: str = "absolute") -> str:
        """Ajusta el volumen y compara el valor real con el solicitado."""
        from modules.command_result import ResultadoComando
        level = int(level)
        actual = self._volumen_real() if mode == "relative" else None
        if mode == "relative" and actual is None:
            return ResultadoComando("No pude consultar el volumen inicial; no he enviado el ajuste relativo.", ok=False)
        esperado = max(0, min(100, actual+level if actual is not None else level))
        argumento = f"{level:+d}%" if mode == "relative" else f"{esperado}%"
        subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", argumento],
                       check=True, capture_output=True, timeout=3)
        observado = self._volumen_real()
        if observado is None or abs(observado-esperado)>1:
            return ResultadoComando("Envié el ajuste de volumen, pero no he comprobado el valor solicitado.", ok=None)
        return ResultadoComando(f"Volumen al {observado} %; comprobado.", ok=True, verificado=True)

    @staticmethod
    def _volumen_real():
        r = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                           capture_output=True, text=True, check=True, timeout=3)
        m = re.search(r"Volume:\s*([0-9.]+)", r.stdout)
        return round(float(m[1])*100) if m else None

    def get_volume(self) -> str:
        """Obtiene el volumen real del sistema."""
        observado = self._volumen_real()
        return f"Volumen: {observado} %." if observado is not None else "No pude consultar el volumen."

    def set_brightness(self, level: int) -> str:
        """Ajusta el brillo y compara el valor real con el solicitado."""
        from modules.command_result import ResultadoComando
        level = max(0, min(100, int(level)))
        subprocess.run(["brightnessctl", "set", f"{level}%"], check=True, capture_output=True, timeout=3)
        r = subprocess.run(["brightnessctl", "-m"], check=True, capture_output=True, text=True, timeout=3)
        campos = r.stdout.strip().split(',')
        if len(campos)>3 and campos[3].strip('%').isdigit() and abs(int(campos[3].strip('%'))-level)<=1:
            return ResultadoComando(f"Brillo al {level} %; comprobado.", ok=True, verificado=True)
        return ResultadoComando("Envié el ajuste de brillo, pero no he comprobado el valor solicitado.", ok=None)

    def lock_screen(self) -> None:
        """Bloquea la pantalla con hyprlock."""
        subprocess.Popen(["hyprlock"], start_new_session=True)

    def screenshot(self) -> None:
        """Captura de pantalla con flameshot."""
        subprocess.Popen(
            ["flameshot", "gui"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def media_control(self, action: str = "play-pause",
                      player: str | None = None, verify: bool = False) -> str:
        """Controla la reproducción multimedia vía playerctl.

        `player` fija el reproductor ("spotify", "firefox"…). Sin él se elige
        el que esté sonando y, si ninguno, Spotify: nunca "el primero", que
        puede ser una pestaña del navegador.

        Devuelve un recibo del envío y su observación; nunca repite un efecto incierto.
        """
        return self._control_multimedia(action,player,verify)

    def _control_multimedia(self, action, player=None, verify=False, *, cancelar=None):
        """Espera capacidades, envía UN efecto y observa su resultado, sin reintentos."""
        from modules.command_result import ResultadoComando
        valido = {'play','pause','play-pause','next','previous','stop'}
        if action not in valido:
            return ResultadoComando('La operación multimedia no es válida; no envié ninguna orden.',ok=False)
        def detenido():
            return cancelar is not None and cancelar.is_set()
        def esperar():
            cancelar.wait(.15) if cancelar is not None else time.sleep(.15)
        def leer(target, comando):
            try:
                r = subprocess.run(['playerctl','--player',target,*comando],capture_output=True,text=True,timeout=1)
                return r.stdout.strip() if r.returncode == 0 else ''
            except (OSError,subprocess.SubprocessError):
                return ''
        def observar(target):
            return {'estado':leer(target,['status']),
                    'pista':leer(target,['metadata','--format','{{mpris:trackid}}|{{xesam:url}}|{{title}}']).strip('| ')}
        def capacidad(target):
            propiedad = {'play':'CanPlay','pause':'CanPause','next':'CanGoNext','previous':'CanGoPrevious'}.get(action,'CanControl')
            try:
                r = subprocess.run(['gdbus','call','--session','--dest','org.mpris.MediaPlayer2.'+target,
                    '--object-path','/org/mpris/MediaPlayer2','--method','org.freedesktop.DBus.Properties.Get',
                    'org.mpris.MediaPlayer2.Player',propiedad],capture_output=True,text=True,timeout=1)
                if r.returncode == 0:
                    return 'true' in r.stdout.lower()
            except (OSError,subprocess.SubprocessError):
                pass
            return None  # No se cambia de transporte ni de reproductor por falta de observación.
        fin = time.monotonic()+4
        target, antes = None, {}
        while not detenido():
            target = pick_player(player)
            if target:
                antes = observar(target)
                if antes['estado'] and capacidad(target) is not False:
                    break
            if time.monotonic() >= fin:
                texto = 'El reproductor no tiene disponible esa operación o aún está cargando. No envié la orden.' if target else 'No encuentro el reproductor solicitado disponible. No envié la orden.'
                return ResultadoComando(texto,ok=False)
            esperar()
        if detenido():
            return ResultadoComando('Operación cancelada antes de enviar la orden multimedia.',ok=False)
        try:
            # Único envío: una respuesta incierta nunca repite next/play por otro transporte.
            r = subprocess.run(['playerctl','--player',target,action],capture_output=True,text=True,timeout=5)
        except (OSError,subprocess.SubprocessError):
            return ResultadoComando('No pude confirmar la entrega de la orden multimedia; no la repetiré automáticamente.',ok=True)
        if r.returncode != 0:
            return ResultadoComando('El reproductor no pudo aceptar la orden multimedia; no he confirmado su efecto.',ok=False)
        if not verify:
            return ResultadoComando('Solicitud multimedia enviada a '+target+'.',ok=True)
        esperado = {'play':'Playing','pause':'Paused','stop':'Stopped'}.get(action)
        if action == 'play-pause':
            esperado = 'Paused' if antes.get('estado') == 'Playing' else 'Playing'
        fin = time.monotonic()+2
        while not detenido():
            despues = observar(target)
            comprobado = despues['estado'] == esperado if esperado else bool(antes.get('pista') and despues['pista'] and despues['pista'] != antes['pista'])
            if comprobado:
                texto = 'La canción cambió; he comprobado el nuevo contenido.' if action in {'next','previous'} else 'Estado de reproducción comprobado: '+{'Playing':'reproduciendo','Paused':'en pausa','Stopped':'detenido'}[esperado]+'.'
                return ResultadoComando(texto,ok=True,verificado=True)
            if time.monotonic() >= fin:
                break
            esperar()
        return ResultadoComando('Solicitud multimedia enviada a '+target+'; todavía no he comprobado su efecto.',ok=True)

    def hyprland_control(self, action: str) -> None:
        """Controles directos del gestor de ventanas Hyprland."""
        if action == "killactive":
            subprocess.run(["hyprctl", "dispatch", "killactive"], check=False)
        elif action == "fullscreen":
            subprocess.run(["hyprctl", "dispatch", "fullscreen"], check=False)

    # Mapa de nombres de voz a clases reales de ventana en Hyprland
    WINDOW_CLASS_MAP = {
        "spotify":      "Spotify",
        "discord":      "discord",
        "chromium":     "chromium",
        "github":       "chrome-mjoklplbddabcmpepnokjaffbmgbkkgg-Default",
        "firefox":      "firefox",
        "code":         "code",
        "vscode":       "code",
        "antigravity":  "antigravity",
        "ghostty":      "com.mitchellh.ghostty",
        "terminal":     "com.mitchellh.ghostty",
        "steam":        "steam",
        "obs":          "com.obsproject.Studio",
        "obsidian":     "obsidian",
        "thunar":       "thunar",
    }

    @classmethod
    def coincide_clase(cls, app, cliente):
        """Reconoce clases exactas de las variantes conocidas de una aplicación."""
        clase = cls.WINDOW_CLASS_MAP.get(app.lower(), app).casefold()
        clases = {clase}
        if clase == "code":
            clases.update({"code-oss", "vscodium"})
        observadas = {str(cliente.get(k, "")).casefold() for k in ("class", "initialClass")}
        observadas |= {c.rsplit('.',1)[-1] for c in observadas}
        return bool(clases & observadas)

    def focus_window(self, app: str) -> str:
        """Enfoca una ventana observada y comprueba su dirección activa."""
        from modules.command_result import ResultadoComando
        try:
            r = subprocess.run(["hyprctl", "-j", "clients"], capture_output=True,
                               text=True, timeout=3, check=True)
            cliente = next((c for c in json.loads(r.stdout)
                            if self.coincide_clase(app, c) and c.get("mapped", True)), None)
            if cliente is None:
                return AppCommands().open_app(app)
            direccion = cliente.get("address", "")
            if not re.fullmatch(r"0x[0-9a-fA-F]+", direccion):
                raise ValueError("La ventana no tiene una dirección válida.")
            r = subprocess.run(["hyprctl", "dispatch", "focuswindow", "address:"+direccion],
                               capture_output=True, text=True, timeout=3, check=True)
            if r.stdout.strip() != "ok":
                raise ValueError("Hyprland rechazó el foco.")
            for _ in range(10):
                r = subprocess.run(["hyprctl", "-j", "activewindow"], capture_output=True,
                                   text=True, timeout=1, check=True)
                if json.loads(r.stdout).get("address") == direccion:
                    return ResultadoComando(f"{app} está al frente; foco comprobado.", ok=True, verificado=True)
                time.sleep(.05)
            raise ValueError("No pude comprobar el foco de la ventana.")
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
            return ResultadoComando(f"No pude enfocar {app}: {e}", ok=False)

    @staticmethod
    def _window_exists(window_class: str) -> bool:
        """Consulta las ventanas activas de Hyprland y busca la clase (case-insensitive)."""
        try:
            result = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True, text=True, timeout=3, check=False
            )
            clients = json.loads(result.stdout) if result.returncode == 0 else []
            return any(
                str(c.get("class", "")).lower() == window_class.lower()
                for c in clients if isinstance(c, dict)
            )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return False

    def get_info(self, type: str = "all") -> str:
        """Retorna información del sistema en texto para sintetizar."""
        if type == "memory":
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            return f"Usas {used_gb:.1f} GB de {total_gb:.1f} GB, al {mem.percent} por ciento."
        elif type == "cpu":
            cpu = psutil.cpu_percent(interval=1)
            return f"CPU al {cpu} por ciento."
        elif type == "disk":
            disk = psutil.disk_usage("/")
            free_gb = disk.free / (1024 ** 3)
            return f"Tienes {free_gb:.1f} gigabytes libres en disco."
        else:
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.5)
            return f"CPU al {cpu} por ciento. RAM al {mem.percent} por ciento."

    def get_time(self, detail: str = "all") -> str:
        """Hora/fecha locales (P0-1). Determinista, sin LLM."""
        from modules.clock import date_line, time_line, weekday_line

        if detail == "time":
            return time_line()
        if detail == "date":
            return date_line()
        if detail == "weekday":
            return weekday_line()
        return f"{date_line()} {time_line()}"

    def shutdown(self) -> None:
        """Apaga el sistema. Solo ejecutar tras confirmación."""
        subprocess.run(["shutdown", "now"])

    def reboot(self) -> None:
        """Reinicia el sistema. Solo ejecutar tras confirmación."""
        subprocess.run(["reboot"])
