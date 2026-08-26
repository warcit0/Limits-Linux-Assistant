package dev.limits.jarvis.net

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/** Estado de conexión con el gateway de Limits en el PC. */
sealed interface ConnState {
    data object Searching : ConnState
    data object Connecting : ConnState
    data class Connected(val host: String, val port: Int) : ConnState
    data class Failed(val reason: String) : ConnState
}

data class LogEntry(
    val timeMs: Long,
    val text: String,
    val mine: Boolean,
    val ok: Boolean? = null,
)

/**
 * Cliente WebSocket del protocolo v1 del gateway (docs/plan-control-remoto-android.md).
 * Reconexión automática con backoff exponencial; ping lo maneja OkHttp.
 */
class WsClient(private val scope: CoroutineScope) {

    private val http = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()

    private var ws: WebSocket? = null
    private var host = ""
    private var port = 0
    private var token = ""
    private val running = AtomicBoolean(false)
    private var loopJob: Job? = null

    val state = MutableStateFlow<ConnState>(ConnState.Searching)
    val processing = MutableStateFlow(false)
    val log = MutableStateFlow<List<LogEntry>>(emptyList())

    fun addLog(text: String, mine: Boolean, ok: Boolean? = null) {
        log.value = log.value + LogEntry(System.currentTimeMillis(), text, mine, ok)
    }

    fun start(host: String, port: Int, token: String) {
        val changed = host != this.host || port != this.port || token != this.token
        this.host = host
        this.port = port
        this.token = token
        if (!running.getAndSet(true) || loopJob == null) {
            loopJob = reconnectLoop()
        } else if (changed) {
            ws?.cancel()  // rompe la sesión actual; el loop reconecta al destino nuevo
        }
    }

    fun stop() {
        running.set(false)
        loopJob?.cancel()
        ws?.close(1000, "bye")
        ws = null
        state.value = ConnState.Searching
    }

    fun sendCommand(text: String): Boolean {
        val socket = ws
        if (socket == null || state.value !is ConnState.Connected) {
            addLog("(sin conexión: no se envió \"$text\")", mine = true, ok = false)
            return false
        }
        val json = JSONObject()
            .put("v", 1)
            .put("type", "command")
            .put("text", text)
        val sent = socket.send(json.toString())
        if (sent) addLog("> $text", mine = true)
        return sent
    }

    // ── internos ─────────────────────────────────────────────────────────────

    private fun reconnectLoop() = scope.launch(Dispatchers.IO) {
        while (isActive && running.get()) {
            val opened = CompletableDeferred<Boolean>()
            val closed = CompletableDeferred<Unit>()
            state.value = ConnState.Connecting

            val request = Request.Builder()
                .url("ws://$host:$port/ws")
                .header("Authorization", "Bearer $token")
                .build()

            val session = http.newWebSocket(request, listener(opened, closed))
            ws = session

            val openResult = try {
                opened.await()
            } catch (e: Exception) {
                break  // scope cancelado en stop()
            }
            if (openResult) {
                processing.value = false
            }
            try {
                closed.await()
            } catch (e: Exception) {
                break
            }

            if (!running.get()) break
            if (openResult) {
                onMain { state.value = ConnState.Connecting }
                delay(1000)
            } else {
                delay(backoffMs * 1000)
                backoffMs = (backoffMs * 2).coerceAtMost(15)
            }
        }
    }

    private var backoffMs = 1L

    private fun listener(
        opened: CompletableDeferred<Boolean>,
        closed: CompletableDeferred<Unit>,
    ) = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            backoffMs = 1
            opened.complete(true)
            onMain {
                state.value = ConnState.Connected(host, port)
                addLog("conectado a $host:$port", mine = false, ok = true)
            }
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            handle(text)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            opened.complete(false)
            if (closed.complete(Unit)) {
                onMain {
                    state.value = ConnState.Failed(t.message ?: "error de red")
                    processing.value = false
                }
            }
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            closed.complete(Unit)
            if (code == 4401) {
                onMain { addLog("token rechazado por el servidor", mine = false, ok = false) }
            }
        }
    }

    private fun handle(text: String) {
        val obj = runCatching { JSONObject(text) }.getOrNull() ?: return
        when (obj.optString("type")) {
            "welcome" -> Unit  // el estado Connected ya lo refleja
            "pong" -> Unit
            "event" -> if (obj.optString("kind") == "processing") {
                onMain { processing.value = true }
            }
            "response" -> {
                val ok = obj.optBoolean("ok")
                val shown = if (ok) obj.optString("text") else obj.optString("msg")
                processing.value = false
                onMain { addLog(if (ok) shown else "! $shown", mine = false, ok = ok) }
            }
        }
    }

    private fun onMain(block: () -> Unit) {
        scope.launch(kotlinx.coroutines.Dispatchers.Main) { block() }
    }
}
