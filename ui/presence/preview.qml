import QtQuick

Presence {
    id: demostracion
    simulacion: true
    Timer {
        interval: 1800; running: true
        onTriggered: demostracion.vista.grabToImage(resultado => resultado.saveToFile("/tmp/limits-widget-preview.png"))
    }
}
