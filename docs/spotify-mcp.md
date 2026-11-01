# Spotify MCP en Limits

Implementación propia y acotada de MCP stdio JSON-RPC 2024-11-05, bajo la licencia
MIT de Limits. Evita instalar un servidor de terceros con acceso arbitrario al
sistema. No incorpora SDK ni dependencias nuevas: usa Python y requests existentes.
El mantenimiento corresponde a este repositorio; no es un servidor oficial de Spotify.

Herramientas: buscar, consultar canciones guardadas (muestra de 10), estado,
dispositivos, reproducir una URI observada y play/pause/next/previous. No modifica
biblioteca ni playlists. No promete recomendaciones personalizadas ni acceso a
funciones que Spotify no permita a la aplicación/cuenta.

## Conectar

1. Crear una aplicación en Spotify Developer y registrar exactamente
   `http://127.0.0.1:8898/callback` como redirect URI.
2. Configurar `SPOTIFY_CLIENT_ID` en `.env`. No hace falta Client Secret: usa PKCE.
3. Desde la sesión gráfica ejecutar `./bin/limits-spotify-login` y autorizar Spotify.
4. Configurar `SPOTIFY_MCP_ENABLED=true` y reiniciar Limits.

El usuario indicó que todavía no tiene Client ID: la integración queda preparada
y desactivada. No se ha abierto una autorización ni probado la cuenta real.
El token se guarda en `~/.limits/spotify/token.json` (0600, carpeta 0700), se renueva
bajo bloqueo entre procesos y nunca se devuelve por MCP. `config.py` centraliza
configuración. El callback abre solo loopback durante un máximo de tres minutos,
con state aleatorio y verificador PKCE. No registrar tokens, códigos ni URLs OAuth.

## Comportamiento y límites

Qwen invoca únicamente el servidor local incluido: `python -m modules.spotify_mcp`.
El cliente inicializa el protocolo y limita herramientas, parámetros, tamaño y tiempo;
cancelar termina el grupo de procesos. No admite comandos, URLs API ni servidores
arbitrarios propuestos por el modelo. Los resultados son datos, nunca permisos.

Las URI de reproducción y dispositivos deben proceder de consultas del turno.
La respuesta a una mutación se contrasta con el estado actual. Una petición aceptada
sin coincidencia observada queda sin verificar. No se reintenta una mutación ante
429, timeout o cancelación, ni se repite next/previous cambiando de MCP a MPRIS.
La comprobación inmediata puede preceder a la actualización de Spotify: se informa
sin verificar antes que afirmar éxito; no garantiza que la API publique el efecto
instantáneamente.

MPRIS sigue disponible para controles locales compatibles, aunque MCP esté apagado.
Para búsqueda/reproducción específica, la vía antigua puede enviar una búsqueda,
pero eso no demuestra que esté sonando el contenido solicitado. No sustituye el
acceso OAuth a la biblioteca. Si MCP está habilitado y falla, Qwen puede consultar
el estado local; no debe repetir efectos inciertos a través del otro transporte.

Spotify Web API puede exigir Premium y permisos/cuotas particulares; los 401/403,
404 sin dispositivo y 429 se comunican sin exponer cuerpos HTTP. No se eluden
restricciones de la cuenta ni se usan cookies del navegador.

## Fuentes del contrato

- [MCP stdio](https://modelcontextprotocol.io/specification/2024-11-05/basic/transports).
- [Spotify PKCE](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow).
- [Redirect URI](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri).
- [Reproducción](https://developer.spotify.com/documentation/web-api/reference/start-a-users-playback).
- [Dispositivos](https://developer.spotify.com/documentation/web-api/reference/get-a-users-available-devices).

Preparación revisada por lectura y sintaxis; conexión, interoperabilidad MCP y
comportamiento real pendientes. No se ejecutaron pruebas por instrucción del usuario.
