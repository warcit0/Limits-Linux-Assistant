package dev.limits.jarvis.net

import android.net.Uri

/**
 * Payload de emparejamiento que imprime el PC (`limits-qr`):
 *
 *     limits://pair?v=1&h=192.168.1.101&p=8765&t=<token 64 hex>
 *
 * Escanearlo desde la app (botón «Escanear QR») o con la cámara del móvil
 * evita teclear el token a mano.
 *
 * El parser es deliberadamente tolerante: algunos lectores devuelven el QR con
 * mayúsculas, sin `//`, o con un salto de línea. Lo que NO se acepta es texto
 * sin `h` y `t` (p. ej. el QR del servidor de descarga).
 */
object Pairing {

    data class Endpoint(val host: String, val port: Int, val token: String)

    const val MIN_TOKEN = 16

    fun parse(raw: String?): Endpoint? {
        val text = raw?.trim().orEmpty()
        if (text.isEmpty()) return null

        // 1) Forma canónica: limits://pair?...
        canonical(text)?.let { return it }

        // 2) Cualquier texto con query que traiga h y t (tolerancia a lectores
        //    que alteran el esquema o recortan las barras).
        val query = text.substringAfter('?', "")
        if (query.isNotEmpty()) return fromQuery(query)

        return null
    }

    private fun canonical(text: String): Endpoint? {
        val uri = runCatching { Uri.parse(text) }.getOrNull() ?: return null
        if (!uri.scheme.equals("limits", ignoreCase = true)) return null
        val hostOk = uri.host.equals("pair", ignoreCase = true) ||
                (uri.host.isNullOrEmpty() &&
                        uri.path.orEmpty().trim('/').equals("pair", ignoreCase = true))
        if (!hostOk) return null
        return fromQuery(uri.encodedQuery.orEmpty())
    }

    private fun fromQuery(query: String): Endpoint? {
        if (query.isEmpty()) return null
        val uri = Uri.parse("limits://pair?$query")
        val host = uri.getQueryParameter("h")?.trim().orEmpty()
        val token = uri.getQueryParameter("t")?.trim().orEmpty()
        val port = uri.getQueryParameter("p")?.trim()?.toIntOrNull() ?: 8765

        if (host.isEmpty()) return null
        if (token.length < MIN_TOKEN) return null
        if (port !in 1..65535) return null
        return Endpoint(host, port, token)
    }
}
