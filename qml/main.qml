// Stage 1 OVERVIEW — driven by the `view` bridge (qtview.QtView).
// Layout/tokens follow docs/ui-design-rules.md (800x480, 7" DSI, 2-tier).
import QtQuick
import QtQuick.Window
import QtQuick.Shapes

Window {
    id: win
    width: 800
    height: 480
    visible: true
    title: "Synapse (mock)"
    color: "#0e1118"

    // -- color tokens (design rules §6) --
    readonly property color cScreen: "#0e1118"
    readonly property color cPanel:  "#141925"
    readonly property color cGraph:  "#0a0d13"
    readonly property color cBorder: "#2c3648"
    readonly property color cGreen:  "#5fd0a0"
    readonly property color cText:   "#e8edf4"
    readonly property color cMuted:  "#7e8694"
    readonly property color cDim:    "#5a6270"

    // ===== Tier-1 glance header (~120px): board name + snapshot =====
    Item {
        id: header
        x: 12; y: 6
        width: parent.width - 24
        height: 120

        Text {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: view.boardName
            color: cText
            font.family: uiFont
            font.pixelSize: 96            // ~80px glyph @133PPI -> glance @1.5m
            elide: Text.ElideRight
            width: 540
        }

        Column {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Text {
                anchors.right: parent.right
                text: "◆ " + view.snapshotLabel
                color: cMuted
                font.family: uiFont
                font.pixelSize: 44
            }
            Text {
                anchors.right: parent.right
                text: view.modeLabel
                color: cGreen
                font.family: uiFont
                font.pixelSize: 22
            }
        }
    }

    Rectangle {
        id: hr
        x: 12; y: header.y + header.height
        width: parent.width - 24; height: 2
        color: "#232b3a"
    }

    // ===== Routing graph =====
    // 776x176 MUST match qtview._GW/_GH — cable PathSvg coords are precomputed in
    // that pixel space on the Python side; changing one without the other misaligns.
    Item {
        id: graph
        x: 12; y: hr.y + 10
        width: 776; height: 176

        Rectangle { anchors.fill: parent; color: cGraph; radius: 10 }

        // cables (under nodes)
        Repeater {
            model: view.cables
            Shape {
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeColor: modelData.color
                    strokeWidth: 2.5
                    fillColor: "transparent"
                    capStyle: ShapePath.RoundCap
                    PathSvg { path: modelData.path }
                }
            }
        }

        // nodes
        Repeater {
            model: view.nodes
            Rectangle {
                x: modelData.x; y: modelData.y
                width: modelData.w; height: modelData.h
                radius: 9
                color: modelData.isIo ? "#10212a"
                                      : (modelData.on ? "#161b26" : "#13161d")
                border.width: modelData.isIo ? 1 : (modelData.selected ? 2 : 1)
                border.color: modelData.isIo ? "#2a4a44"
                                             : (modelData.selected ? cGreen : cBorder)
                opacity: (!modelData.isIo && !modelData.on) ? 0.55 : 1.0

                Column {
                    anchors.centerIn: parent
                    spacing: 1
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.label
                        color: modelData.isIo ? cGreen : cText
                        font.family: uiFont
                        font.pixelSize: modelData.isIo ? 22 : 21
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        visible: modelData.sub !== ""
                        text: modelData.sub
                        color: "#6f8a82"
                        font.family: uiFont
                        font.pixelSize: 13
                    }
                }
            }
        }
    }

    // legend / status line
    Row {
        x: 12; y: graph.y + graph.height + 6
        spacing: 18
        Row {
            spacing: 6
            Rectangle { width: 18; height: 4; radius: 2; color: cGreen; anchors.verticalCenter: parent.verticalCenter }
            Text { text: "SIGNAL"; color: "#9aa3b2"; font.family: uiFont; font.pixelSize: 16 }
        }
        Text { text: "노드 탭 → 포커스 (Stage 2)"; color: cDim; font.family: uiFont; font.pixelSize: 16 }
        Text { text: "BPM " + view.bpm; color: cMuted; font.family: uiFont; font.pixelSize: 16 }
    }

    // ===== footswitch status strip (read-only) =====
    Row {
        id: strip
        x: 12
        width: parent.width - 24
        height: 64
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 12
        spacing: 8

        Repeater {
            model: view.footswitches
            Rectangle {
                width: (strip.width - 8 * 3) / 4
                height: 64
                radius: 8
                color: cPanel
                Row {
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    Rectangle {
                        width: 15; height: 15; radius: 7.5
                        color: modelData.led
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        Text { text: modelData.label; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 20 }
                        Text { text: modelData.sub; color: modelData.led; font.family: uiFont; font.pixelSize: 15 }
                    }
                }
            }
        }
    }
}
