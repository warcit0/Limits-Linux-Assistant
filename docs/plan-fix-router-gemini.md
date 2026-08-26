# Plan de corrección: router de palabras clave Gemini no rutea

> Estado: **PENDIENTE (mañana)** — causa raíz ya reproducida y aislada.
> Síntoma real del usuario: *"Limits, investigáme cuál fue el último CPU que
> salió"* → fue a qwen/system_info en vez de saltar a Gemini.

## Causa raíz (demostrada)

`match_gemini_route()` hace matching por SUBSTRING sensible a acentos:

```
"investigáme".find("investiga") → -1   # la 'á' rompe el prefijo
```

Whisper transcribe imperativos con enclíticos TILDEADOS (*investigáme*,
*dímelo*, *repíteme*) y variantes sin tilde indistintamente. El router actual
solo acierta si la palabra clave aparece EXACTA.

Reproducción verificada (2026-08-25):
- ✅ "investiga qué pasó con X" → research
- ❌ "investigáme cuál fue el último cpu que salió." → None (BUG)

## Correcciones a aplicar (en orden)

### 1. Matching insensible a diacríticos (fix principal)
Normalizar texto y keywords con NFD + filtrar categoría `Mn` ANTES del
substring, en `modules/gemini.py`:

```python
import unicodedata
def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower())
                   if unicodedata.category(c) != "Mn")
```
Aplicar a `low` y pre-normalizar las tuplas de keywords una sola vez a nivel
de módulo. ~10 líneas.

### 2. Ampliar keywords conservadoramente
Añadir formas verbales y coloquiales frecuentes de voz:
- `investigar`, `investígamen`, `búsquemen`, `buscárame` (normalización ya
  cubre tildes; faltan terminaciones)
- `quiero saber sobre`, `qué pasó con`, `cuál fue el último`, `cuáles son los
  últimos`, `el más nuevo`, `últimas noticias`
⚠️ NO añadir: `cuál es mi`, `cuánto/a` (conflictos con info local/comandos).

### 3. Endurecer regla 6 del prompt (misruta de qwen)
Hoy qwen 1.5b mandó "último CPU que salió" a `get_system_info`. Añadir al
prompt un par CONTRASTANTE explícito:

```
"¿cuánta RAM uso?"            → get_system_info (MI sistema)
"cuál fue el último CPU del mercado" → gemini_research (mundo exterior)
```
Y reformular regla 6: "preguntas sobre TU sistema/hardware local → acciones
normales; preguntas sobre el mundo/noticias/lanzamientos → gemini_research".

### 4. Visibilidad de arranque (anti "instancia vieja")
- Banner: mostrar estado del cerebro (`Gemini: ON/OFF/binario ausente`)
- Si `GEMINI_ENABLED=true` y `available()==False` → WARNING destacado, no solo
  línea dim.
Motivo: el usuario probó con instancia previa al commit y costó descartarlo.

### 5. Tests de regresión con frases reales de voz
En `tests/test_gemini.py` añadir (normalización activa):
- "investigáme cuál fue el último cpu que salió." → research  ← EL CASO
- "infórmate del clima" / "INFORMAME YA" → research
- "Búsca en internet…" (tilde mal puesta) → research
- No-ruteo intacto: "busca el archivo", "cuánta RAM tengo"

## Verificación final (checklist manual)

1. `py_compile` + suite completa en verde
2. Relanzar `limits`; banner debe decir `Gemini: ON`
3. Voz: *"Limits, investigáme cuál fue el último CPU que salió"* →
   consola muestra `turno gemini (research)` + respuesta hablada (ElevenLabs,
   larga)
4. Control: *"Limits, abre firefox"* sigue yendo a qwen (~1.5s)
5. Control negativo: *"Limits, busca el archivo main.py"* → búsqueda local

## Notas

- El bug upstream de gemdev (chat sin -t crashea) sigue anotado; nuestro puente
  inmune.
- Si tras esto qwen aún confunde "mundo exterior vs mi PC" en frases SIN
  palabras clave, considerar subir ese par de ejemplos al inicio de EJEMPLOS
  (los primeros pesan más) antes que engordar reglas.
