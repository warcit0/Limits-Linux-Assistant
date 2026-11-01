# P0-2 · Arranque automático

**Estado:** propuesto · Depende de: nada · Esfuerzo: 30 min (+ 1 reinicio de prueba)
**Habilita:** que Limits exista sin que tú lo arranques. Es el requisito más
barato y el más vergonzoso de incumplir.

## Problema

```text
$ systemctl --user is-active limits.service   → active
$ systemctl --user is-enabled limits.service  → disabled
```

El servicio funciona hoy porque alguien lo arrancó a mano. Tras reiniciar el PC
no hay gateway, no hay micrófono y el móvil no conecta. Además, con `linger`
desactivado, el servicio solo existe **después de iniciar sesión**.

## Diseño

Tres capas, cada una con su fallo posible:

| Capa | Qué resuelve | Comando |
|---|---|---|
| `enable` | arranca al iniciar sesión | `systemctl --user enable limits.service` |
| `linger` | arranca **sin** iniciar sesión | `loginctl enable-linger $USER` |
| orden de arranque | el micrófono existe cuando Limits lo pide | `After=pipewire.service wireplumber.service` |

```text
boot ─► user@1000.service (linger) ─► pipewire / wireplumber
                                            │
                                     limits.service
                                            │
                              ┌─────────────┴─────────────┐
                              │ STT listo?                │
                              │ no → reintento (10 s)     │
                              │ sí → gateway + wake word  │
                              └───────────────────────────┘
```

## Cambios por archivo

| Archivo | Cambio |
|---|---|
| `~/.config/systemd/user/limits.service` | `After=pipewire.service wireplumber.service`, `Restart=always`, `RestartSec=10`, `StartLimitBurst=0` |
| `setup-service.sh` | `enable` + `loginctl enable-linger` + comprobación final |
| `bin/limits-health` **(nuevo)** | Comprueba servicio, puerto 8765, handshake WS y micrófono; código de salida 0/1 |
| `INICIO.md` / `README.md` | Sección «arranque automático» (activar, desactivar, comprobar) |
| `commands/system.py` | (opcional) `get_system_info(type=health)` para preguntarlo por voz |

## Por qué `Restart=always` y no `on-failure`

Hoy: `Restart=on-failure`, `StartLimitBurst=3`. Si el micrófono no está listo al
arrancar, el proceso muere 3 veces en 15 s y systemd **se rinde**. Con
`Restart=always` y sin límite de burst, Limits reintenta hasta que PipeWire
publique el dispositivo. El coste es un log cada 10 s hasta que arranca.

## Tareas

- [x] Verificar por qué quedó `disabled` (¿lo desactivó `limits-service stop`?)
      y dejarlo documentado
      → **Resuelto:** `bin/limits-service` nunca hace `disable`; se desactivó a
      mano en algún momento. Documentado en `INICIO.md` (stop ≠ disable).
- [x] `systemctl --user enable limits.service`
- [x] `loginctl enable-linger "$USER"` + verificar con `loginctl show-user $USER -p Linger`
- [x] Editar la unit: `After`, `Restart=always`, `RestartSec=10`, sin `StartLimit*`
      (`StartLimitIntervalSec=0` en `[Unit]`, que es donde vive la clave)
- [x] `setup-service.sh` idempotente: escribe la unit, `daemon-reload`, `enable`, `linger`
- [x] `bin/limits-health` (servicio + puerto + WS + micrófono)
- [x] Documentar en `INICIO.md` cómo desactivarlo (`disable` + `disable-linger`)
- [ ] **Prueba real:** reiniciar el PC, no abrir terminal, comprobar salud y móvil
      (pendiente: requiere que el usuario acepte reiniciar)

## Criterios de aceptación

1. Tras `reboot`, sin abrir terminal: `systemctl --user is-active limits` →
   `active` y `is-enabled` → `enabled`.
2. `bin/limits-health` devuelve 0 y reporta micrófono disponible.
3. El móvil conecta sin tocar nada (mismo QR/token).
4. Si se arranca el servicio con PipeWire caído, se recupera solo en ≤ 30 s.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Con `linger`, el servicio arranca antes de que exista sesión gráfica y el micrófono falla | `Restart=always` + reintento; si el audio sigue sin aparecer, dejar `linger` fuera y depender del login |
| `DISPLAY=:0` / `WAYLAND_DISPLAY=wayland-1` hardcodeados: si cambia el TTY o el compositor, falla | Documentar; a futuro leerlas del entorno de la sesión |
| Doble instancia (servicio + `limits --text`) | Ya cubierto: `--takeover` y el check del puerto 8765 |

## No-objetivos

- Arrancar con el PC apagado (wake-on-LAN) → fuera de alcance.
- systemd del sistema (`--system`) → debe ser usuario para tener PipeWire y sesión.
