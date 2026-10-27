# Track aparte: redactar / tipar en aplicaciones

**Estado: APLAZADO.** No forma parte del lane de órdenes de archivos ni de
aflojar el router LLM.

## Por qué no va en el catálogo actual

“Escríbeme un mensaje en Discord” o “redacta en Obsidian” no se resuelve con
más intents JSON. Requiere automatización de UI:

- Inyectar texto en la ventana enfocada (`wtype` / `ydotool` en Wayland)
- O adapters por app (API/CLI de Obsidian, atajos Discord, etc.)
- Foco correcto vía Hyprland antes de tipar

Aflojar Qwen para que “analice” no escribe en la app correcta; un fallo pega
texto en el chat equivocado.

## Piloto futuro (cuando se retome)

1. Elegir 1–2 apps (p.ej. Obsidian + ventana enfocada genérica).
2. Handler tipado `type_text {text, target?}` con allowlist de targets.
3. Confirmación si el target no está enfocado o el texto > N caracteres.
4. Few-shot mínimo; **no** mezclar con `desktop_task` de archivos.

Hasta entonces: el usuario abre la app con Limits y escribe a mano, o usa
clipboard manualmente.
