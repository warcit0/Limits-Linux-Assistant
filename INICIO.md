# 🎙️ Limits — Guía de Inicio Rápido

Esta guía explica cómo iniciar el asistente de voz **Limits** en sus tres modos de operación.

---

## ✅ Requisitos Previos

Antes de iniciar por primera vez, asegúrate de tener el entorno listo:

```bash
cd ~/Proyectos/Limits

# Crear entorno virtual (solo la primera vez)
python3 -m venv limits-env

# Instalar dependencias (solo la primera vez)
./limits-env/bin/pip install -r requirements.txt
```

Asegúrate también de tener tu archivo `.env` configurado con tu `GROQ_API_KEY` y tu `WAKE_WORD`.

---

## 🗣️ Modo 1 — Voz (Normal)

Es el modo principal. Limits escucha por el micrófono, espera que digas su nombre (la *wake word*) y ejecuta tu comando.

```bash
cd ~/Proyectos/Limits
limits
```

**Flujo de uso:**
1. Espera a ver `✓ Limits listo.` en la consola.
2. Di tu wake word: **"Limits"**
3. Di tu comando: *"Limits, abre Spotify"*, *"Limits, busca en YouTube..."*
4. Para apagar, di **"Limits, salir"** o presiona `Ctrl + C`.

---

## ⌨️ Modo 2 — Texto (Sin Micrófono)

Útil para probar comandos sin hablar, depurar o si no tienes micrófono disponible.

```bash
cd ~/Proyectos/Limits
limits --text
```

**Flujo de uso:**
1. Aparecerá el prompt `[Tú]:` en la consola.
2. Escribe tu comando directamente (sin necesidad de decir "Limits").
3. Para salir, escribe `salir` o presiona `Ctrl + C`.

---

## 🚀 Modo 3 — Inicio Automático con el Sistema (Systemd)

Configura Limits para que inicie automáticamente en segundo plano cada vez que inicias sesión en tu CachyOS/Hyprland.

### Instalar el servicio (solo una vez)

```bash
cd ~/Proyectos/Limits
chmod +x setup-service.sh
./setup-service.sh
```

Esto crea e inicia un servicio de usuario de systemd llamado `limits.service`,
lo deja **habilitado** y activa `linger` para que arranque aunque no inicies
sesión gráfica (útil tras un reinicio). Es idempotente: puedes ejecutarlo
siempre que quieras.

### Comprobar que está sano

```bash
./bin/limits-health    # servicio + puerto + auth del móvil + micrófono
```

Sale 0 si el servicio y el gateway responden; avisa (sin fallar) si el
micrófono no está disponible en esa sesión.

### Interrumpirlo (barge-in)

Mientras habla puedes decir **«para»**, «cállate», «basta» o «stop»: corta al
instante. Si dices otra cosa, la corta y la atiende como siguiente turno. Desde
la app del móvil, el mensaje `stop` hace lo mismo (el botón «Para» aún no está
en la app).

### Comandos de gestión del servicio

| Acción | Comando |
|---|---|
| Ver estado | `systemctl --user status limits.service` |
| Ver logs en vivo | `journalctl --user -u limits.service -f` |
| Detener | `systemctl --user stop limits.service` |
| Reiniciar | `systemctl --user restart limits.service` |
| Deshabilitar autostart | `systemctl --user disable limits.service` |
| Desactivar arranque sin sesión | `loginctl disable-linger "$USER"` |

> [!NOTE]
> `limits-service stop` **no** deshabilita el arranque automático: solo para el
> proceso. Para que no vuelva tras un reinicio usa `disable` (y
> `disable-linger` si no quieres el servicio sin sesión abierta).

> [!IMPORTANT]
> Tras cualquier cambio en el código o el archivo `.env`, reinicia el servicio para que tome efecto:
> ```bash
> systemctl --user restart limits.service
> ```

---

## 🧠 Memoria

Limits recuerda lo que le pidas explícitamente, aunque reinicies el PC:

```text
«recuerda que mi proyecto principal es Limits»
«apunta que el wifi se cae los martes»
«¿qué sabes de mí?»
«olvida mi proyecto principal»
```

Todo vive en `~/.limits/memory.db` (SQLite local, permiso 600). Nunca sale de tu
máquina y los tokens con pinta de secreto se guardan como `[redactado]`. Para
empezar de cero: detén el servicio y borra ese archivo (se recrea vacío). Para
desactivarla sin borrar nada: `MEMORY_ENABLED=false` en `.env`.

---

## 🔄 Actualizaciones desde GitHub

Para bajar la última versión del código:

```bash
cd ~/Proyectos/Limits
git pull
systemctl --user restart limits.service   # Si el servicio está activo
```
