// One focus-card monitor (output port), rendered read-only by its `kind`
// (meter / clip / numeric / gauge). No MouseArea -- monitors are display-only.
// Live values arrive via view.monitorUpdated (the monitor feed); each widget
// listens and updates ONLY itself (no focus-card rebuild). Before any live
// frame it shows the seeded value, so it also renders correctly off-device.
import QtQuick

Item {
    id: root
    property var m                 // {symbol,name,value,norm,min,max,unit,kind,display}
    width: 118; height: 96

    // live state, re-seeded from m on (re)assignment, then driven by the feed
    property real   liveNorm: 0
    property real   liveValue: 0
    property string liveDisplay: ""
    onMChanged: reseed()
    Component.onCompleted: reseed()
    function reseed() {
        liveNorm    = m ? m.norm : 0
        liveValue   = m ? m.value : 0
        liveDisplay = m ? m.display : ""
    }
    Connections {
        target: view
        function onMonitorUpdated(sym, norm, val, disp) {
            if (root.m && sym === root.m.symbol) {
                root.liveNorm = norm; root.liveValue = val; root.liveDisplay = disp
            }
        }
    }

    readonly property color cGreen:  "#5fd0a0"
    readonly property color cText:   "#e8edf4"
    readonly property color cMuted:  "#7e8694"
    readonly property color cTrack:  "#222a38"

    Column {
        anchors.centerIn: parent
        spacing: 6
        Loader {
            anchors.horizontalCenter: parent.horizontalCenter
            sourceComponent: {
                if (!root.m) return numericC
                if (root.m.kind === "meter") return meterC
                if (root.m.kind === "clip")  return clipC
                if (root.m.kind === "gauge") return gaugeC
                return numericC            // numeric (and fallback)
            }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.m ? root.m.name : ""; color: root.cMuted
            font.family: uiFont; font.pixelSize: 15
            // long port names (e.g. "Gain Reduction") overflowed the 118px cell
            width: Math.min(implicitWidth, root.width - 8)
            elide: Text.ElideRight
        }
    }

    // --- vertical bar meter (level/peak/rms) ---
    Component {
        id: meterC
        Item {
            width: 26; height: 56
            Rectangle { anchors.fill: parent; radius: 4; color: root.cTrack }
            Rectangle {
                width: parent.width; radius: 4; color: root.cGreen
                anchors.bottom: parent.bottom
                height: parent.height * Math.max(0, Math.min(1, root.liveNorm))
            }
        }
    }

    // --- clip indicator LED ---
    Component {
        id: clipC
        Rectangle {
            width: 30; height: 30; radius: 15
            property bool lit: root.liveValue >= 0.5
            color: lit ? "#e2524a" : "#3a2222"
            border.width: 2; border.color: lit ? "#ff7a70" : "#5a2a2a"
        }
    }

    // --- numeric readout (tuner note/freq, bpm, position) ---
    Component {
        id: numericC
        Text {
            text: root.liveDisplay
            color: root.cText; font.family: uiFont; font.pixelSize: 28
        }
    }

    // --- center-zero gauge (cent ±) ---
    Component {
        id: gaugeC
        Item {
            width: 92; height: 28
            Rectangle { anchors.fill: parent; radius: 4; color: root.cTrack }
            Rectangle { width: 2; height: parent.height; color: root.cMuted; anchors.horizontalCenter: parent.horizontalCenter }
            Rectangle {
                color: root.cGreen; height: parent.height; radius: 2
                property real n: Math.max(0, Math.min(1, root.liveNorm))   // 0..1, 0.5 = center
                width: Math.abs(n - 0.5) * parent.width
                x: n >= 0.5 ? parent.width / 2 : parent.width / 2 - width
            }
        }
    }
}
