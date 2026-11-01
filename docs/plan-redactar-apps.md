# Plan 5 — Redactar / tipar en aplicaciones (track aparte)

**Estado:** aplazado (no bloquear planes 1–4)  
**Relacionado:** [`track-redactar-apps.md`](track-redactar-apps.md)

## Problema

“Escríbeme un mensaje en Discord / pega esto en Obsidian” no es un intent más del catálogo de archivos: es automatización de UI en Wayland.

## Enfoque (cuando se retome)

### Piloto A — Ventana enfocada genérica

- `type_text {text}` vía `wtype` o `ydotool` en la ventana que ya tiene foco.
- Confirmación si `len(text) > N` o si no hay ventana enfocada conocida.
- **No** elegir app por voz en v1.

### Piloto B — Una app con adapter

- Elegir **una**: Obsidian (URI/CLI) o pegar vía clipboard (`wl-copy`) + atajo.
- Handler tipado + 1 few-shot; allowlist de targets.

## Reglas duras

- No mezclar con `desktop_task` de archivos.
- No shell libre ni “escribe lo que quieras en cualquier sitio” sin confirmación.
- Router de intents sigue strict; tipar es action atómica, no agent libre.

## Criterio de hecho (piloto)

- Una frase “escribe Hola en la ventana actual” → texto visible en la app enfocada (smoke manual).
- Cero tipado accidental en terminal/Limits sin confirmación cuando el texto es largo.

## Orden (futuro)

1. Decidir wtype vs ydotool en CachyOS/Hyprland  
2. Piloto A  
3. Evaluar Piloto B  
4. Documentar límites de seguridad en AGENTS.md  
