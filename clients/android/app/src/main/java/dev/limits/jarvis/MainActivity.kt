package dev.limits.jarvis

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.wifi.WifiManager
import android.os.Bundle
import android.speech.RecognizerIntent
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import dev.limits.jarvis.data.SettingsStore
import dev.limits.jarvis.net.ConnState
import dev.limits.jarvis.net.LogEntry
import dev.limits.jarvis.net.LimitsDiscovery
import dev.limits.jarvis.net.Pairing
import dev.limits.jarvis.net.WsClient
import kotlinx.coroutines.delay

// ── Paleta HUD ──────────────────────────────────────────────────────────────
val HudBg = Color(0xFF0A0E14)
val HudCyan = Color(0xFF00E5FF)
val HudViolet = Color(0xFF7C4DFF)
val HudRed = Color(0xFFFF5252)
val HudText = Color(0xFFE8EAF0)

class MainActivity : ComponentActivity() {

    /** URI limits://pair?... recibida por deep link (cámara del móvil). */
    private val incomingPairing = mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        incomingPairing.value = intent?.dataString
        setContent {
            JarvisScreen(
                pairingUri = incomingPairing,
                onPairingConsumed = { incomingPairing.value = null },
            )
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.dataString?.let { incomingPairing.value = it }
    }
}

@Composable
fun JarvisScreen(
    pairingUri: State<String?>,
    onPairingConsumed: () -> Unit,
) {
    val context = LocalContext.current
    val scope = androidx.compose.runtime.rememberCoroutineScope()
    val session = remember { WsClient(scope) }

    var settings by remember {
        mutableStateOf(SettingsStore.load(context))
    }
    var showConfig by remember { mutableStateOf(false) }

    // Endpoint resuelto: manual gana sobre descubrimiento mDNS
    var discovered by remember { mutableStateOf<Pair<String, Int>?>(null) }

    // Emparejamiento: aplica host/puerto/token de un QR y persiste
    fun applyPairing(raw: String): Boolean {
        val ep = Pairing.parse(raw)
        if (ep == null) {
            // Mostrar lo leído es clave para distinguir «QR equivocado» de
            // «el lector devolvió basura».
            session.addLog(
                "QR no reconocido. Leí: \"${raw.trim().take(70)}\"\n" +
                        "En el PC: ./bin/limits-qr  (o limits-qr --png)",
                mine = false, ok = false)
            return false
        }
        val s = SettingsStore.Settings(
            autoDiscover = false, host = ep.host, port = ep.port, token = ep.token)
        SettingsStore.save(context, s)
        settings = s
        discovered = null
        session.addLog("emparejado con ${ep.host}:${ep.port}", mine = false, ok = true)
        return true
    }

    val scanLauncher = rememberLauncherForActivityResult(ScanContract()) { result ->
        val contents = result.contents
        if (contents != null) {
            applyPairing(contents)
        } else {
            session.addLog("escaneo cancelado", mine = false)
        }
    }

    fun launchScan() {
        val opts = ScanOptions().apply {
            setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            setPrompt("Escanea el QR de ./bin/limits-qr")
            setBeepEnabled(false)
            setOrientationLocked(true)
        }
        scanLauncher.launch(opts)
    }

    // Deep link (QR escaneado con la cámara del móvil)
    LaunchedEffect(pairingUri.value) {
        val raw = pairingUri.value ?: return@LaunchedEffect
        applyPairing(raw)
        onPairingConsumed()
    }

    // BUGFIX: sin multicast lock muchos móviles NUNCA ven los anuncios mDNS.
    // Defensivo: cualquier rareza del vendor no debe tumbar la app (requiere
    // CHANGE_WIFI_MULTICAST_STATE, ya en el manifest).
    val multicastLock = remember {
        runCatching {
            (context.applicationContext.getSystemService(Context.WIFI_SERVICE)
                    as WifiManager)
                .createMulticastLock("limits_mdns")
                .apply { setReferenceCounted(false); acquire() }
        }.getOrNull()
    }
    DisposableEffect(Unit) {
        onDispose {
            runCatching { if (multicastLock?.isHeld == true) multicastLock.release() }
        }
    }

    val tokenMissing = settings.token.isBlank()

    // Descubrimiento mDNS mientras esté en modo automático
    DisposableEffect(settings.autoDiscover) {
        val disc = if (settings.autoDiscover) {
            LimitsDiscovery(context.applicationContext) { h, p ->
                discovered = h to p
            }.also { it.start() }
        } else null
        onDispose { disc?.stop() }
    }

    // Conexión al endpoint vigente (sin mensajes falsos en el historial)
    LaunchedEffect(
        settings.autoDiscover,
        settings.host, settings.port, settings.token,
        discovered?.first, discovered?.second,
    ) {
        // IP manual sin puerto → 8765 (antes se ignoraba la IP en silencio)
        val ep = if (!settings.autoDiscover && settings.host != null) {
            settings.host!! to (settings.port ?: 8765)
        } else {
            discovered
        }
        if (!tokenMissing && ep != null) {
            session.start(ep.first, ep.second, settings.token.trim())
        } else if (tokenMissing) {
            session.stop()
        }
    }

    // Ayuda una sola vez si el mDNS no encuentra nada teniendo token válido
    var hinted by remember { mutableStateOf(false) }
    LaunchedEffect(settings.autoDiscover, settings.token, discovered) {
        val hasEp = (!settings.autoDiscover && settings.host != null) ||
                discovered != null
        if (!hinted && !tokenMissing && !hasEp && settings.autoDiscover) {
            delay(8000)
            if (discovered == null && settings.token.isNotBlank()) {
                session.addLog(
                    "mDNS no encuentra el PC. Toca ⚙, desactiva 'auto' y pon " +
                            "la IP manual (o vuelve a escanear el QR).",
                    mine = false, ok = false)
                hinted = true
            }
        }
    }

    DisposableEffect(Unit) {
        onDispose { session.stop() }
    }

    val state by session.state.collectAsState()
    val entries by session.log.collectAsState()
    val processing by session.processing.collectAsState()
    val speaking by session.speaking.collectAsState()

    // Lanzador de reconocimiento de voz nativo
    val speechLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val text = result.data
                ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull()
            if (!text.isNullOrBlank()) session.sendCommand(text)
        }
    }

    Surface(color = HudBg, modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            // El escaneo debe estar SIEMPRE visible: el botón grande solo lo
            // ofrece cuando falta el token, y con uno viejo guardado quedaba
            // escondido en ⚙ (reportado por el usuario).
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                StatusHeader(state, Modifier.weight(1f))
                TextButton(onClick = { launchScan() }) {
                    Text(
                        "Escanear QR",
                        color = HudCyan,
                        fontFamily = FontFamily.Monospace,
                        fontSize = 12.sp,
                    )
                }
            }

            Spacer(Modifier.height(8.dp))
            Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                Orb(processing = processing, speaking = speaking,
                    connected = state is ConnState.Connected)
            }

            val st = state  // smart cast imposible en propiedades delegadas
            val statusText = when {
                tokenMissing -> "Sin emparejar: escanea el QR del PC"
                processing -> "Procesando…"
                speaking -> "Hablando…"
                st is ConnState.Connected -> "Escuchando…"
                st is ConnState.Connecting -> "Conectando…"
                st is ConnState.Searching -> "Buscando Limits en la red…"
                st is ConnState.Failed ->
                    "Sin conexión: ${st.reason.take(120)}"
                else -> ""
            }
            Text(
                statusText,
                color = if (state is ConnState.Failed) HudRed else HudText.copy(alpha = 0.85f),
                fontFamily = FontFamily.Monospace,
                fontSize = 12.sp,
                lineHeight = 16.sp,
                textAlign = TextAlign.Center,
            )

            Spacer(Modifier.height(10.dp))
            HorizontalDivider(color = HudText.copy(alpha = 0.15f))
            Spacer(Modifier.height(6.dp))

            HistoryLog(entries, Modifier.weight(1f))

            Spacer(Modifier.height(10.dp))
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Button(
                    onClick = {
                        if (tokenMissing) {
                            launchScan()
                            return@Button
                        }
                        try {
                            speechLauncher.launch(speechIntent())
                        } catch (_: ActivityNotFoundException) {
                            Toast.makeText(context,
                                "No hay motor de voz instalado",
                                Toast.LENGTH_SHORT).show()
                        }
                    },
                    enabled = tokenMissing || state is ConnState.Connected,
                    shape = RoundedCornerShape(24.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = HudCyan.copy(alpha = 0.15f),
                        contentColor = HudCyan),
                    modifier = Modifier.weight(1f).height(52.dp),
                ) {
                    Text(
                        if (tokenMissing) "Escanear QR" else "Hablar",
                        fontFamily = FontFamily.Monospace, fontSize = 16.sp)
                }
                Spacer(Modifier.width(8.dp))
                IconButton(onClick = { showConfig = true }) {
                    Icon(Icons.Default.Settings, contentDescription = "Ajustes",
                         tint = HudText.copy(alpha = 0.7f))
                }
            }
        }
    }

    if (showConfig) {
        ConfigDialog(
            initial = settings,
            onScan = { showConfig = false; launchScan() },
            onClose = { showConfig = false },
            onSave = {
                SettingsStore.save(context, it)
                settings = it
                discovered = null
                showConfig = false
            },
        )
    }
}

private fun speechIntent() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
             RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
    putExtra(RecognizerIntent.EXTRA_LANGUAGE, "es-ES")
    putExtra(RecognizerIntent.EXTRA_PROMPT, "Habla con Limits")
}

// ── Componentes HUD ─────────────────────────────────────────────────────────

@Composable
private fun StatusHeader(state: ConnState, modifier: Modifier = Modifier) {
    val (color, label) = when (state) {
        is ConnState.Connected -> HudCyan to "● Conectado — ${state.host}"
        is ConnState.Connecting -> HudViolet to "● Conectando…"
        is ConnState.Searching -> HudViolet.copy(alpha = 0.7f) to "● Buscando servidor…"
        is ConnState.Failed -> HudRed to "● ${state.reason.take(40)}"
    }
    Text(label, color = color, fontFamily = FontFamily.Monospace, fontSize = 12.sp,
         modifier = modifier)
}

@Composable
private fun Orb(processing: Boolean, speaking: Boolean, connected: Boolean) {
    val t = rememberInfiniteTransition(label = "orb")
    val breathe by t.animateFloat(
        0f, 1f,
        infiniteRepeatable(tween(3000), RepeatMode.Reverse),
        label = "breathe")
    val spin by t.animateFloat(
        0f, 360f,
        infiniteRepeatable(tween(if (processing) 1100 else 6000, easing = LinearEasing)),
        label = "spin")

    val core = when {
        processing -> HudViolet
        speaking -> HudCyan
        connected -> HudCyan
        else -> HudRed.copy(alpha = 0.6f)
    }
    // Hablando el halo queda encendido (no respira): se distingue de
    // "escuchando" de un vistazo, aunque ambos sean cyan.
    val glow = if (speaking) 0.92f else breathe
    val sizeDp = 150.dp

    Canvas(Modifier.size(sizeDp)) {
        val c = center
        val r = size.minDimension / 2f

        // halo respirando
        drawCircle(
            color = core.copy(alpha = 0.08f + glow * 0.10f),
            radius = r * (0.95f + glow * 0.05f),
            center = c,
        )
        // núcleo
        drawCircle(
            color = core.copy(alpha = 0.55f + glow * 0.25f),
            radius = r * 0.45f,
            center = c,
            style = Stroke(width = 2.dp.toPx()),
        )
        drawCircle(
            brush = androidx.compose.ui.graphics.Brush.radialGradient(
                colors = listOf(core.copy(alpha = 0.25f + glow * 0.2f),
                                Color.Transparent),
                center = c, radius = r * 0.45f),
            radius = r * 0.45f, center = c,
        )
        // anillo giratorio (rápido y violeta al procesar; lento en reposo)
        drawArc(
            color = core.copy(alpha = 0.9f),
            startAngle = spin,
            sweepAngle = when {
                processing -> 90f
                speaking -> 150f
                else -> 40f
            },
            useCenter = false,
            topLeft = Offset(c.x - r * 0.75f, c.y - r * 0.75f),
            size = androidx.compose.ui.geometry.Size(r * 1.5f, r * 1.5f),
            style = Stroke(width = 1.5.dp.toPx(), cap = StrokeCap.Round),
        )
    }
}

@Composable
private fun HistoryLog(entries: List<LogEntry>, modifier: Modifier = Modifier) {
    val listState = rememberLazyListState()
    LaunchedEffect(entries.size) {
        if (entries.isNotEmpty()) listState.animateScrollToItem(entries.lastIndex)
    }
    LazyColumn(state = listState, modifier = modifier.fillMaxWidth()) {
        items(entries) { e ->
            val color = when {
                e.mine -> HudText.copy(alpha = 0.9f)
                e.ok == true -> HudCyan.copy(alpha = 0.95f)
                else -> HudRed.copy(alpha = 0.9f)
            }
            Text(
                e.text,
                color = color,
                fontFamily = FontFamily.Monospace,
                fontSize = 12.sp,
                lineHeight = 17.sp,
            )
        }
    }
}

@Composable
private fun ConfigDialog(
    initial: SettingsStore.Settings,
    onScan: () -> Unit,
    onClose: () -> Unit,
    onSave: (SettingsStore.Settings) -> Unit,
) {
    var auto by remember { mutableStateOf(initial.autoDiscover) }
    var host by remember { mutableStateOf(initial.host.orEmpty()) }
    var port by remember { mutableStateOf(initial.port?.toString().orEmpty()) }
    var token by remember { mutableStateOf(initial.token) }

    androidx.compose.material3.AlertDialog(
        onDismissRequest = onClose,
        title = { Text("Ajustes", color = HudText, fontFamily = FontFamily.Monospace) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onScan) {
                    Text("Escanear QR del PC", color = HudCyan,
                         fontFamily = FontFamily.Monospace, fontSize = 14.sp)
                }
                Text("En el PC: ./bin/limits-qr",
                     color = HudText.copy(alpha = 0.6f), fontSize = 11.sp)
                HorizontalDivider(color = HudText.copy(alpha = 0.15f))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Auto-descubrir (mDNS)", color = HudText, fontSize = 13.sp)
                    Spacer(Modifier.weight(1f))
                    Switch(checked = auto, onCheckedChange = { auto = it })
                }
                if (!auto) {
                    OutlinedTextField(value = host, onValueChange = { host = it },
                        label = { Text("IP del PC") }, singleLine = true)
                    OutlinedTextField(value = port, onValueChange = { port = it },
                        label = { Text("Puerto (vacío = 8765)") }, singleLine = true)
                }
                OutlinedTextField(value = token, onValueChange = { token = it },
                    label = { Text("Token (mejor escanea el QR)") },
                    singleLine = true)
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onSave(SettingsStore.Settings(auto, host.takeIf { it.isNotBlank() },
                                              port.toIntOrNull(), token.trim()))
            }) { Text("Guardar", color = HudCyan) }
        },
        dismissButton = {
            TextButton(onClick = onClose) { Text("Cerrar", color = HudText) }
        },
        containerColor = Color(0xFF10151F),
    )
}
