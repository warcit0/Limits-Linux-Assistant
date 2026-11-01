# P2-2 · Workspaces por voz

**Estado:** parcialmente implementado por Mejora 2 · Esfuerzo: 1 día · Depende de: P1 (grounding)
**Criterio:** 12 frases típicas cambian de workspace (o mueven la ventana) como
se espera, en < 150 ms y sin crear workspaces por accidente.

Plan completo en [plan-p2-pantalla-workspaces-sesion.md](../plan-p2-pantalla-workspaces-sesion.md).

Implementados: cambio entre existentes, vuelta al anterior, movimiento explícito
con comprobación de address y listado por ventanas. Se comprobaron cambio y
restauración reales. No se declara cerrada esta tarea: especiales, creación y
aceptación completa de las 12 frases siguen pendientes.

## Contexto medido (previo a Mejora 2)

- Hoy: 4 workspaces numéricos + `special:music` (Spotify) y
  `special:communication` (Discord), un solo monitor 1920×1080.
- `hyprland_control` solo hace `killactive` y `fullscreen`: no hay nada de
  workspaces en `action_map`.

## Checklist

### 1. Comandos
- [ ] `commands/workspaces.py`:
  - [ ] `switch(target, monitor=None)` → `hyprctl dispatch workspace <id|name>`.
  - [ ] `move_window(target)` → `hyprctl dispatch movetoworkspace <id|name>`.
  - [ ] `back()` → workspace anterior (historial de proceso).
  - [ ] `list_open()` → ventanas agrupadas por workspace, resumen hablado.
  - [ ] `_exists(target)` contra `hyprctl workspaces -j` (id y nombre).
  - [ ] Especiales por nombre (`music`, `communication`) vía
        `workspace special:<nombre>` **solo si ya existe** (no usar
        `togglespecialworkspace` para «ve al especial»: los toglearía).
  - [ ] Nunca crear un workspace nuevo salvo frase explícita («crea el 9»).

### 2. Router determinista
- [ ] `modules/workspace_router.py`:
  - [ ] «workspace N», «escritorio N», «ve al N», «pásate al N».
  - [ ] Números en palabra (uno…diez) y ordinales («el tercero»).
  - [ ] «siguiente», «anterior», «vuelve al anterior», «vuelve».
  - [ ] «el especial de música / de comunicación / de <nombre>».
  - [ ] «manda/mueve/envía esto al N» → `workspace_move`.
  - [ ] «qué tengo abierto» → `workspace_list`.
  - [ ] No secuestros: «abre el workspace» sin número, «pon el volumen 3».

### 3. Integración
- [ ] `action_map` + `ACTION_HINTS` (grounding):
      `workspace_switch` ← `workspace|escritorio`, `workspace_move` ← además
      `manda|mueve|envia`.
- [ ] Ejecutar el router **antes** del LLM en `main.run_pipeline`.
- [ ] Few-shot único en el prompt (las frases raras) sin pasarse de 8.400 B.
- [ ] `workspace_list` responde resumido (máx 3 workspaces + especiales).

### 4. Tests
- [ ] `tests/test_workspaces.py`: switch numérico, por nombre, especial,
      movimiento y listado (con `hyprctl` simulado).
- [ ] `tests/test_workspace_router.py`: 12 frases válidas + 6 no secuestros.
- [ ] Test de «target inexistente» → no ejecuta y pide aclaración.

### 5. Verificación E2E
- [ ] Con el servicio real: «ve al 3» → `hyprctl activeworkspace` = 3.
- [ ] «manda esto al 2» → la ventana activa aparece en el workspace 2.
- [ ] «vuelve al anterior» → vuelve al workspace de partida.
- [ ] «qué tengo abierto» enumera las ventanas actuales sin inventar.
- [ ] Latencia < 150 ms (medida en el log del turno).

## Riesgos

- `hyprctl` exige sesión Wayland activa; bajo el servicio ya se exporta
  `WAYLAND_DISPLAY`. Si falla, frase honesta (no «hecho»).
- Multi-monitor: se deja `monitor` opcional; en esta máquina hay uno.
