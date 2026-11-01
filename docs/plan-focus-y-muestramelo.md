# Plan 1 — Foco Hyprland + “muéstramelo” + búsqueda útil

**Estado:** implementado (2026-10-27)  
**Objetivo:** que abrir/mostrar un archivo ponga la ventana **delante en el workspace actual**, y que follow-ups (“muéstramelo”, “ábrelo”, “el primero”) usen el último resultado sin re-buscar todo el home.

## Problema actual

- `open_file` / `reveal_file` solo hacen `xdg-open` / `thunar` → en Hyprland la ventana puede nacer detrás u en otro workspace.
- `search_*` con `path=~` devuelve venvs/`node_modules`/pip antes que el proyecto del usuario.
- “muéstramelo” no tiene memoria de turno: el router no sabe *cuál* archivo.

## Alcance

### 1.1 Memoria de último match (`modules/executor.py` o `commands/files.py`)

- Tras `search_file` / `search_and_open` / `reveal_file` (con matches), guardar:
  - `last_matches: list[str]` (rutas absolutas, máx 5)
  - `last_opened: str | None`
- Exponer actions/follow-ups:
  - `open_last` / reusar `open_file` con path vacío → usa `last_matches[0]` si hay uno, o pide índice
  - `reveal_last` igual para explorador
- Few-shots: “muéstramelo”, “ábrelo”, “el segundo”, “ábrelo en el explorador”.

### 1.2 Focus post-apertura (Hyprland)

- Tras `xdg-open`/`thunar`, esperar breve (p.ej. 300–800 ms) y:
  - `hyprctl clients -j` → emparejar por clase típica (thunar, code, firefox, …) o por título/path si aparece
  - `hyprctl dispatch focuswindow …` y si hace falta `movetoworkspace` al workspace activo
- Fallback: si no hay match en N ms, hablar “lo abrí; si no lo ves, mira el otro escritorio” (sin mentir que está enfocado).

### 1.3 Búsqueda con defaults sensatos

- Default `path` configurable (`FILE_SEARCH_ROOT`, p.ej. `~/Proyectos:~Desktop:~Downloads` o lista).
- Con `fd`: `--exclude` venvs, `.git`, `node_modules`, `__pycache__`, `limits-env`, `site-packages`.
- Few-shot: “busca main.py en Proyectos/Limits”.

## Fuera de alcance

- Tipar en apps; agent compuesto multi-paso (plan 2).

## Criterio de hecho

- Corpus: “busca X en Limits y ábrelo” → 1 match → ventana enfocada en workspace actual (smoke manual Hyprland).
- “muéstramelo” justo después de una búsqueda con 1 match → `reveal`/`open` del mismo path sin segunda búsqueda amplia.
- Tests unitarios de memoria last_matches (sin hyprctl real); focus con mock de `hyprctl clients -j`.

## Orden de implementación

1. last_matches + follow-ups + few-shots  
2. excludes / FILE_SEARCH_ROOT  
3. focus hyprctl + smoke manual  
