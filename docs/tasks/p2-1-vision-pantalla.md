# P2-1 · Visión de pantalla

**Estado:** propuesto · Esfuerzo: 2-3 días · Depende de: P1 (grounding)
**Criterio:** Limits lee lo que hay en pantalla sin inventar, en ≤ 2,5 s p50 con
OCR; describir/preguntar con VLM local en ≤ 6 s p50; ninguna captura sobrevive al
turno.

Plan completo en [plan-p2-pantalla-workspaces-sesion.md](../plan-p2-pantalla-workspaces-sesion.md).

## Contexto medido

- `grim` captura 1920×1080 en **57 ms** (PNG 246 KB).
- `tesseract --psm 6` tarda **1,8 s** en esa imagen.
- Solo hay idiomas `afr`, `eng`, `osd`: **falta `spa`**.
- VRAM: 1.330 MiB libres con el router cargado → un VLM de 3B no cabe junto a él.
- OpenCode cloud: **429** (gratis) y **401** (pago) → la nube no es requisito.

## Checklist

### 1. OCR determinista (T0)
- [ ] Instalar `tesseract-data-spa` y verificar `tesseract --list-langs`.
- [ ] `modules/screen.py`:
  - [ ] `capture(region="active")` con `grim -g "$(hyprctl activewindow -j)"`.
  - [ ] `capture(region="full")` con `grim`.
  - [ ] Directorio `/dev/shm/limits-screen` (700) + borrado en `finally`.
  - [ ] `ocr(path, lang="spa+eng")` con fallback a `eng` y aviso único.
  - [ ] `clean_text()` + recorte a N caracteres para narración.
  - [ ] `screen_text()` con caché de 2 s (evita capturar dos veces el mismo turno).
- [ ] `commands/screen.py`:
  - [ ] `screen_read(region)` narra el OCR literal (máx ~60 s de voz).
  - [ ] `screen_find(text, region)` → sí/no + contexto (línea anterior y siguiente).
  - [ ] `screen_windows()` → inventario por workspace (`hyprctl clients -j`).
- [ ] `modules/screen_router.py` (determinista): «lee la pantalla», «qué dice»,
      «qué tengo en pantalla», «busca X en pantalla», «qué tengo abierto».
- [ ] `action_map` + `ACTION_HINTS` (grounding): `pantalla|pantalla|lee|dice`.

### 2. VLM local (T1)
- [ ] `ollama pull moondream:1.8b` (1,8 GB) y medir VRAM/latencia reales.
- [ ] `modules/screen.py::describe(path, question=None)` contra `VISION_MODEL`.
  - [ ] Resize a 1280 px con `magick` antes de enviar.
  - [ ] `num_ctx=4096`, `keep_alive=0` (no robar VRAM al router).
  - [ ] Si el modelo no está instalado: mensaje claro, nunca silencio.
- [ ] `screen_describe` y `screen_ask` en `action_map` + few-shot corto.
- [ ] Probar `qwen2.5vl:3b` como alternativa y **documentar** por qué se elige
      uno (calidad vs expulsión del router).

### 3. Escalado OpenCode (T2, opt-in)
- [ ] `VISION_CLOUD=false` por defecto en `.env.example` y `config.py`.
- [ ] `modules/screen.py::escalate(path, question)` con
      `opencode run --standalone -m $VISION_CLOUD_MODEL -f <png>`, timeout 90 s.
- [ ] Fail-loud con la causa (429/401/timeout) y sin reintentos en bucle.
- [ ] Confirmación por voz la primera vez de la sesión si `VISION_CLOUD=1`.
- [ ] Validar credenciales/modelo con visión antes de encender la bandera.

### 4. Privacidad
- [ ] Ningún PNG fuera de tmpfs; test que comprueba el directorio tras el turno.
- [ ] Texto OCR solo a DEBUG y pasado por `redact()`.
- [ ] Nada de pantalla en `episodes` salvo «recuerda lo que dice la pantalla».
- [ ] Sin envío a red si `VISION_CLOUD=false` (test con `requests` mockeado).

### 5. Tests
- [ ] `tests/test_screen.py` con PNG sintético (texto conocido): OCR no vacío,
      `clean_text`, `find` con acierto y fallo.
- [ ] `tests/test_screen_router.py`: frases mecánicas y no secuestros
      («abre la pantalla de música» no es `screen_read`).
- [ ] `tests/test_executor_guard.py`: acciones nuevas sin evidencia se bloquean.
- [ ] Presupuesto de prompt ≤ 8.400 B con el few-shot nuevo.

### 6. Verificación
- [ ] `unittest` en verde (≥ 263 + nuevos).
- [ ] `bin/measure-router` ≥ 0,90 (el corpus no debe caer).
- [ ] 10 lecturas reales: texto narrado = OCR (revisión manual, 0 invenciones).
- [ ] p50 de `screen_read` ≤ 2,5 s y de `screen_describe` ≤ 6 s.

## Pendiente / decisiones abiertas

- **«Dictar»**: este plan asume narrar en voz alta. Escribir texto en la app
  enfocada queda fuera (requiere `ydotool`/`wtype`, no instalados).
- ¿La captura por defecto debe ser la **ventana activa** o el **monitor
  completo**? Propuesta: ventana activa; «toda la pantalla» explícito.
