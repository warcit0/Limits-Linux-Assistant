# Limits Jarvis — cliente Android

App de una sola pantalla (estética HUD) que envía comandos de voz al gateway de
Limits en tu PC. Protocolo y diseño: `docs/plan-control-remoto-android.md`.

## Requisitos del PC

```bash
# En .env de Limits:
GATEWAY_ENABLED=true
systemctl --user restart limits.service
```

El token de emparejamiento está en `~/.limits/gateway_token` — cópialo al
teléfono la primera vez (campo ⚙ → Token). Ambos dispositivos deben estar en el
mismo WiFi.

## Compilar (dos caminos)

### A) Sin Android Studio (CLI, recomendado)

1. JDK 17+ (`pacman -S jdk21-openjdk`).
2. Gradle: `sudo pacman -S gradle` (solo para generar el wrapper una vez).
3. SDK de Android por línea de comandos:

```bash
mkdir -p ~/Android/Sdk/cmdline-tools && cd ~/Android/Sdk/cmdline-tools
unzip ~/Descargas/commandlinetools-linux-*-latest.zip   # de developer.android.com/studio#command-line-tools-only
mv cmdline-tools latest

yes | ~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager --licenses
~/Android/Sdk/cmdline-tools/latest/bin/sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"

echo "sdk.dir=$HOME/Android/Sdk" > clients/android/local.properties
cd clients/android && gradle wrapper --gradle-version 8.9
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

4. Instalar en el teléfono:
   - Opción adb: activa "Depuración USB" y `adb install -r app-debug.apk`
   - Sin cables: copia el APK al teléfono (Nextcloud/Telegram/USB) e instálalo
     permitiendo "orígenes desconocidos".

### B) Con Android Studio

`File > Open` sobre `clients/android/`, espera el sync y pulsa Run con el móvil
conectado por USB.

## En el teléfono

1. Activa **Opciones de desarrollador** (7 toques en "Número de compilación") si
   usarás adb.
2. Abre la app → ⚙ → pega el token → Guardar.
3. El estado debe pasar a `● Conectado — <IP-del-PC>`; pulsa **Hablar** y dicta
   el comando ("abre spotify", "qué RAM estoy usando"…).

## Notas

- **Batería (F4)**: cuando exista Foreground Service, MIUI/Samsung pedirán
  excluir la app del ahorro de batería; se documentará aquí.
- Reconexión automática ante caídas de WiFi (backoff 1→15 s).
- El reconocimiento de voz usa el motor de Google del teléfono; solo se envía
  TEXTO al PC, nunca audio.
