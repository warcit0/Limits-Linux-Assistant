package dev.limits.jarvis.net

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo

/**
 * Descubre el gateway de Limits vía mDNS/NSD (`_limits._tcp`).
 * Llama a [onEndpoint] cada vez que se resuelve una instancia "Limits".
 */
class LimitsDiscovery(
    context: Context,
    private val onEndpoint: (host: String, port: Int) -> Unit,
) {
    private val nsd =
        context.getSystemService(Context.NSD_SERVICE) as NsdManager

    private var discovering = false

    private val discoveryListener = object : NsdManager.DiscoveryListener {
        override fun onDiscoveryStarted(serviceType: String?) {}
        override fun onStartDiscoveryFailed(serviceType: String?, errorCode: Int) {
            discovering = false
        }
        override fun onStopDiscoveryFailed(serviceType: String?, errorCode: Int) {
            discovering = false
        }
        override fun onDiscoveryStopped(serviceType: String?) {
            discovering = false
        }
        override fun onServiceLost(serviceInfo: NsdServiceInfo?) {}

        override fun onServiceFound(serviceInfo: NsdServiceInfo?) {
            val info = serviceInfo ?: return
            if (!info.serviceName.startsWith("Limits")) return
            nsd.resolveService(info, resolveListener)
        }
    }

    private val resolveListener = object : NsdManager.ResolveListener {
        override fun onResolveFailed(info: NsdServiceInfo?, errorCode: Int) {}
        override fun onServiceResolved(info: NsdServiceInfo?) {
            val i = info ?: return
            val host = i.host?.hostAddress ?: return
            onEndpoint(host, i.port)
        }
    }

    fun start() {
        if (discovering) return
        discovering = true
        nsd.discoverServices(
            "_limits._tcp.", NsdManager.PROTOCOL_DNS_SD, discoveryListener)
    }

    fun stop() {
        if (!discovering) return
        try {
            nsd.stopServiceDiscovery(discoveryListener)
        } catch (_: IllegalArgumentException) {
        }
        discovering = false
    }
}
