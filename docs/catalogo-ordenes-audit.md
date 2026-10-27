# Auditoría: catálogo de órdenes vs frases reales

Fecha: 2026-10-27. Base: `action_map` + `prompts/system_prompt.txt`.

## Cubierto (atómico)

| Frase típica | Action |
|---|---|
| abre/cierra Spotify, Discord… | open/close_application |
| tráeme Discord | focus_window |
| volumen / brillo / lock / apaga | set_volume, …, shutdown |
| pon X en Spotify/YouTube | spotify_play / youtube_play |
| busca gatos en Google | web_search |
| abre el proyecto Limits en code | open_project |
| git status / docker | git_status / docker_status |
| pásalo a la tele | tv_cast |

## Gaps prioritarios (archivos / escritorio)

| Frase | Antes | Después (plan) |
|---|---|---|
| busca el archivo config.py | search_file débil / confunde con web | search_file con rutas + few-shot |
| busca X y ábrelo / muéstralo | no existe | search_and_open |
| ábrelo en el explorador / muéstralo en Thunar | no existe | reveal_file |
| copia A a B / mueve / renombra | no existe | copy_file / move_file / rename_file |
| busca X en Descargas y cópialo al escritorio | multi-paso | desktop_task (lane compuesto) |
| pega esto en Discord / escribe un correo | UI typing | **aplazado** — ver `docs/track-redactar-apps.md` |

## Confusiones del router (prompt)

- Few-shot solo de `"busca … en google"` → `web_search`; cero ejemplos de archivo local.
- `search_file` devolvía “N resultados” sin rutas → el siguiente turno no puede hacer `open_file`.
- No hay intent compuesto; el clasificador no puede encadenar tools.

## Criterio de ampliación

Cada action nueva: handler tipado + `action_map` + ≥1 few-shot. Sin shell libre. Move/rename → confirmación verbal.
