package dev.limits.jarvis.data

import android.content.Context

/** Ajustes persistentes simples (SharedPreferences): endpoint manual + token. */
object SettingsStore {

    private const val FILE = "limits_jarvis"
    private const val K_AUTO = "auto_discover"
    private const val K_HOST = "manual_host"
    private const val K_PORT = "manual_port"
    private const val K_TOKEN = "token"

    data class Settings(
        val autoDiscover: Boolean,
        val host: String?,
        val port: Int?,
        val token: String,
    )

    fun load(ctx: Context): Settings {
        val p = ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE)
        return Settings(
            autoDiscover = p.getBoolean(K_AUTO, true),
            host = p.getString(K_HOST, null)?.takeIf { it.isNotBlank() },
            port = p.getString(K_PORT, null)?.toIntOrNull(),
            token = p.getString(K_TOKEN, "") ?: "",
        )
    }

    fun save(ctx: Context, s: Settings) {
        ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit()
            .putBoolean(K_AUTO, s.autoDiscover)
            .putString(K_HOST, s.host.orEmpty())
            .putString(K_PORT, s.port?.toString().orEmpty())
            .putString(K_TOKEN, s.token)
            .apply()
    }
}
