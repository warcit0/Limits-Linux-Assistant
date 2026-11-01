import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland

ShellRoot {
    id: raiz
    property var dato: ({estado: "oculto", nivel: 0, detenible: false, ajustes: {}})
    property var ajustes: dato.ajustes || ({})
    property int secuencia: -1
    property string turno: ""
    property bool pantallaElegida: false
    property var pantalla: Quickshell.screens[0] || null
    property bool desconectado: false
    property bool avisoConexion: false
    property bool simulacion: false
    property alias vista: contenido
    property real reloj: 0
    property real energia: 0
    property bool reducido: ajustes.movimiento_reducido === true
    property bool mostrar: avisoConexion || dato.estado !== "oculto"
    onDatoChanged: if (!mostrar || dato.pausado) energia = 0

    function recibir(texto) {
        if (texto.length > 4096) return;
        try {
            const nuevo = JSON.parse(texto);
            if (nuevo.v !== 1 || typeof nuevo.seq !== "number" || nuevo.seq <= secuencia) return;
            secuencia = nuevo.seq;
            if (nuevo.turno !== turno || !pantallaElegida) {
                pantallaElegida = true;
                turno = nuevo.turno;
                const nombre = (nuevo.ajustes || {}).monitor || (Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : "");
                pantalla = Quickshell.screens.find(s => s.name === nombre) || Quickshell.screens[0] || null;
            }
            dato = nuevo;
            desconectado = false;
            avisoConexion = false;
        } catch (e) { /* Un paquete inválido no cambia el estado visible. */ }
    }
    Socket {
        id: conexion
        path: Quickshell.env("XDG_RUNTIME_DIR") + "/limits/presence.sock"
        connected: !raiz.simulacion
        parser: SplitParser { onRead: data => raiz.recibir(data) }
        onConnectedChanged: {
            if (!connected && !raiz.simulacion) {
                raiz.secuencia = -1;
                raiz.desconectado = true;
                raiz.avisoConexion = raiz.dato.estado !== "oculto";
                raiz.dato = {estado: "oculto", nivel: 0, detenible: false, ajustes: raiz.ajustes};
                despedirConexion.restart();
            }
        }
    }
    Timer { interval: 2000; running: !conexion.connected && !raiz.simulacion; repeat: true; onTriggered: conexion.connected = true }
    Timer { id: despedirConexion; interval: 2200; onTriggered: raiz.avisoConexion = false }
    Timer {
        interval: 33; running: panel.visible && raiz.mostrar && !raiz.reducido; repeat: true
        onTriggered: {
            raiz.reloj += (raiz.dato.estado === "hablando" ? .045 : .022);
            const objetivo = raiz.dato.pausado ? 0 : (raiz.dato.nivel || 0);
            raiz.energia += (objetivo - raiz.energia)*.4;
        }
    }
    Timer {
        interval: 4000; running: raiz.simulacion; repeat: true; triggeredOnStart: true
        property int paso: 0
        onTriggered: {
            const estados = ["pensando", "investigando", "hablando", "confirmacion", "error"];
            const estado = estados[paso++ % estados.length];
            raiz.dato = {estado: estado, etiqueta: estado === "hablando" ? "Hablando" : estado === "pensando" ? "Pensando" : estado === "investigando" ? "Investigando" : estado === "confirmacion" ? "Esperando confirmación" : "No pude completarlo", nivel: estado === "hablando" ? .65 : 0, detenible: false, ajustes: {}};
        }
    }
    PanelWindow {
        id: panel
        screen: Quickshell.screens.indexOf(raiz.pantalla) >= 0 ? raiz.pantalla : Quickshell.screens[0] || null
        anchors { top: true; right: true }
        margins { top: raiz.ajustes.arriba === undefined ? 76 : raiz.ajustes.arriba; right: raiz.ajustes.derecha === undefined ? 18 : raiz.ajustes.derecha }
        implicitWidth: Math.max(190, (raiz.ajustes.tamano || 172) + 12)
        implicitHeight: (raiz.ajustes.tamano || 172) + 80
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        focusable: false
        WlrLayershell.namespace: "limits-presence"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        visible: raiz.mostrar || contenido.opacity > .01
        mask: Region { item: pie }
        Item {
            id: contenido
            anchors.fill: parent
            opacity: raiz.mostrar ? (raiz.ajustes.opacidad || .95) : 0
            Behavior on opacity { NumberAnimation { duration: raiz.reducido ? 0 : 180 } }
            ShaderEffect {
                id: nucleo
                anchors.top: parent.top
                anchors.horizontalCenter: parent.horizontalCenter
                width: raiz.ajustes.tamano || 172
                height: width
                property vector2d resolution: Qt.vector2d(width, height)
                property real clock: raiz.reducido ? 0 : raiz.reloj
                property real energy: raiz.reducido ? 0 : raiz.energia
                property real phase: raiz.dato.estado === "error" ? 5 : raiz.dato.estado === "confirmacion" ? 4 : raiz.dato.estado === "investigando" ? 2 : raiz.dato.estado === "escuchando" ? 3 : 1
                fragmentShader: "nucleo.frag.qsb"
                onStatusChanged: if (status === ShaderEffect.Error) console.warn("Núcleo: " + log)
            }
            Rectangle {
                id: pie
                anchors.top: nucleo.bottom
                anchors.topMargin: -7
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(panel.width, textoEstado.implicitWidth + 30)
                height: raiz.dato.detenible ? 62 : 34
                radius: 15
                color: "#ed162127"
                border.color: "#3553636b"
                Text {
                    id: textoEstado
                    anchors.top: parent.top
                    anchors.topMargin: 9
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: raiz.avisoConexion ? "Limits desconectado" : raiz.dato.pausado ? "Escuchando interrupción" : raiz.dato.etiqueta || "Limits"
                    font.family: "Inter"
                    font.pixelSize: 12
                    color: "#e5f4f5"
                    Accessible.name: text
                }
                Rectangle {
                    visible: raiz.dato.detenible === true
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 7
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 84; height: 23; radius: 9
                    color: raton.containsMouse ? "#405860" : "#283b43"
                    Text { anchors.centerIn: parent; text: "Detener"; color: "#f1f6f6"; font.pixelSize: 12 }
                    Accessible.role: Accessible.Button
                    Accessible.name: "Detener Limits"
                    MouseArea {
                        id: raton
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            conexion.write(JSON.stringify({cmd: "stop", turno: raiz.turno})+"\n");
                            conexion.flush();
                        }
                    }
                }
            }
        }
    }
}
