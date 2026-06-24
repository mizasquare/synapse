// Qt mock UI — OVERVIEW (Stage 1) + FOCUS (Stage 2), driven by the `view` bridge.
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
    readonly property color cElev:   "#1d2433"
    readonly property color cBorder: "#2c3648"
    readonly property color cGreen:  "#5fd0a0"
    readonly property color cText:   "#e8edf4"
    readonly property color cMuted:  "#7e8694"
    readonly property color cDim:    "#5a6270"

    // dev: map keyboard Z/X/C/V -> footswitch 0..3 (mouse can't chord)
    function fsKeyIndex(k) {
        if (k === Qt.Key_Z) return 0;
        if (k === Qt.Key_X) return 1;
        if (k === Qt.Key_C) return 2;
        if (k === Qt.Key_V) return 3;
        return -1;
    }

    // Key catcher: Z/X/C/V press/release -> view.footswitchKey -> fake controller,
    // which the poll loop debounces + latches into real (combo-capable) events.
    Item {
        anchors.fill: parent
        focus: true
        Component.onCompleted: forceActiveFocus()
        Keys.onPressed: function(event) {
            if (event.isAutoRepeat) return;
            var i = win.fsKeyIndex(event.key);
            if (i >= 0) { view.footswitchKey(i, true); event.accepted = true; }
        }
        Keys.onReleased: function(event) {
            if (event.isAutoRepeat) return;
            var i = win.fsKeyIndex(event.key);
            if (i >= 0) { view.footswitchKey(i, false); event.accepted = true; }
        }
    }

    // =========================================================== OVERVIEW
    Item {
        id: overviewScreen
        anchors.fill: parent
        visible: view.screen === "overview"

        // -- Tier-1 glance header (~120px): board name + snapshot --
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

        // -- Routing graph --
        // 776x176 MUST match qtview._GW/_GH — cable PathSvg coords are precomputed in
        // that pixel space on the Python side; changing one without the other misaligns.
        Item {
            id: graph
            x: 12; y: hr.y + 10
            width: 776; height: 176

            Rectangle { anchors.fill: parent; color: cGraph; radius: 10 }

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

                    // tap an effect node -> FOCUS (IO nodes are not interactive)
                    MouseArea {
                        anchors.fill: parent
                        enabled: !modelData.isIo
                        onClicked: view.selectNode(modelData.id)
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
            Text { text: "노드 탭 → 포커스"; color: cDim; font.family: uiFont; font.pixelSize: 16 }
            Text { text: "BPM " + view.bpm; color: cMuted; font.family: uiFont; font.pixelSize: 16 }
        }

        // footswitch status strip (read-only frame; mode-switching is master-side later)
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
                    // dev keymap hint: which keyboard key fires this footswitch
                    Text {
                        anchors.right: parent.right; anchors.top: parent.top
                        anchors.rightMargin: 7; anchors.topMargin: 4
                        text: ["Z", "X", "C", "V"][index]
                        color: cDim; font.family: uiFont; font.pixelSize: 15
                    }
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

    // ============================================================== FOCUS
    Item {
        id: focusScreen
        anchors.fill: parent
        visible: view.screen === "focus"
        property var f: view.focus

        // -- top bar: back + prev/next nav + bypass --
        Row {
            id: navrow
            x: 12; y: 12
            spacing: 8
            // back
            Rectangle {
                width: 124; height: 44; radius: 8
                color: "#1b2230"; border.width: 1; border.color: cBorder
                Text { anchors.centerIn: parent; text: "◄ OVERVIEW"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 20 }
                MouseArea { anchors.fill: parent; onClicked: view.goOverview() }
            }
            Rectangle {
                width: 48; height: 44; radius: 8; color: "#1b2230"; border.width: 1; border.color: cBorder
                Text { anchors.centerIn: parent; text: "◄"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 22 }
                MouseArea { anchors.fill: parent; onClicked: view.focusPrev() }
            }
            Rectangle {
                width: 48; height: 44; radius: 8; color: "#1b2230"; border.width: 1; border.color: cBorder
                Text { anchors.centerIn: parent; text: "►"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 22 }
                MouseArea { anchors.fill: parent; onClicked: view.focusNext() }
            }
        }

        // bypass toggle (right) — bound to f.bypassed (bridge keeps it in sync)
        Rectangle {
            id: bypassToggle
            anchors.verticalCenter: navrow.verticalCenter
            x: parent.width - width - 12
            width: 116; height: 44; radius: 22
            property bool on: focusScreen.f ? focusScreen.f.bypassed === false : true
            color: on ? cGreen : "#2c3648"
            Text {
                anchors.centerIn: parent
                text: parent.on ? "ENGAGED" : "BYPASS"
                color: parent.on ? "#0e1118" : "#9aa3b2"
                font.family: uiFont; font.pixelSize: 18
            }
            MouseArea {
                anchors.fill: parent
                onClicked: if (focusScreen.f) view.toggleBypass(focusScreen.f.instance, focusScreen.f.bypassed === false)
            }
        }

        // -- effect identity card --
        Rectangle {
            id: idcard
            x: 12; y: 68
            width: parent.width - 24; height: 60
            radius: 10; color: cElev; border.width: 2; border.color: cGreen
            Column {
                anchors.left: parent.left; anchors.leftMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1
                Text {
                    text: focusScreen.f ? (focusScreen.f.name + "  ·  " + focusScreen.f.category) : ""
                    color: cText; font.family: uiFont; font.pixelSize: 28
                }
                Text {
                    visible: focusScreen.f && focusScreen.f.patches && focusScreen.f.patches.length > 0
                    text: (focusScreen.f && focusScreen.f.patches && focusScreen.f.patches.length > 0)
                          ? ("▦ " + focusScreen.f.patches[0].label + ": " + focusScreen.f.patches[0].value) : ""
                    color: cGreen; font.family: uiFont; font.pixelSize: 16
                }
            }
        }

        // -- routing IN / OUT --
        Row {
            id: routing
            x: 12; y: idcard.y + idcard.height + 10
            width: parent.width - 24; height: 56
            spacing: 10
            Repeater {
                model: [ { t: "◄ INPUTS",  list: focusScreen.f ? focusScreen.f.inputs : [] },
                         { t: "OUTPUTS ►", list: focusScreen.f ? focusScreen.f.outputs : [] } ]
                Rectangle {
                    width: (routing.width - 10) / 2; height: 56
                    radius: 10; color: cPanel
                    Column {
                        anchors.left: parent.left; anchors.leftMargin: 14
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Text { text: modelData.t; color: cGreen; font.family: uiFont; font.pixelSize: 15 }
                        Text { text: (modelData.list || []).join("   "); color: cText; font.family: uiFont; font.pixelSize: 22 }
                    }
                }
            }
        }

        // -- knobs (vertical-drag to change; local value reflected) --
        Rectangle {
            id: knobpanel
            x: 12; y: routing.y + routing.height + 10
            width: parent.width - 24
            height: 200
            radius: 10; color: cPanel
            Row {
                anchors.centerIn: parent
                spacing: 24
                Repeater {
                    model: focusScreen.f ? focusScreen.f.knobs : []
                    Item {
                        width: 150; height: 168
                        property real dispNorm: modelData.norm
                        property real liveVal: modelData.min + dispNorm * (modelData.max - modelData.min)

                        Column {
                            anchors.centerIn: parent
                            spacing: 8
                            // ring
                            Item {
                                width: 96; height: 96
                                anchors.horizontalCenter: parent.horizontalCenter
                                Shape {
                                    anchors.fill: parent
                                    preferredRendererType: Shape.CurveRenderer
                                    ShapePath {
                                        strokeColor: cBorder; strokeWidth: 9; fillColor: "transparent"
                                        PathAngleArc { centerX: 48; centerY: 48; radiusX: 40; radiusY: 40; startAngle: -90; sweepAngle: 360 }
                                    }
                                    ShapePath {
                                        strokeColor: cGreen; strokeWidth: 9; fillColor: "transparent"
                                        capStyle: ShapePath.RoundCap
                                        PathAngleArc { centerX: 48; centerY: 48; radiusX: 40; radiusY: 40; startAngle: -90; sweepAngle: 360 * dispNorm }
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    preventStealing: true
                                    property real sy: 0
                                    property real sv: 0
                                    onPressed: { sy = mouseY; sv = dispNorm }
                                    onPositionChanged: {
                                        var nv = Math.max(0, Math.min(1, sv + (sy - mouseY) / 180))
                                        dispNorm = nv
                                        if (focusScreen.f)
                                            view.setParameter(focusScreen.f.instance, modelData.symbol,
                                                              modelData.min + nv * (modelData.max - modelData.min))
                                    }
                                }
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: modelData.name; color: cMuted; font.family: uiFont; font.pixelSize: 18
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: liveVal.toFixed(2) + (modelData.unit ? (" " + modelData.unit) : "")
                                color: cGreen; font.family: uiFont; font.pixelSize: 20
                            }
                        }
                    }
                }
            }
        }

        Text {
            x: 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 10
            text: "노브를 위/아래로 드래그 · 값은 로컬 반영 (가짜 백엔드)"
            color: cDim; font.family: uiFont; font.pixelSize: 15
        }
    }

    // ============================================================ TAP TEMPO
    // Beat blinking lives on the PHYSICAL footswitch LEDs (presenter drives them);
    // this screen is just the last-set BPM + meter readout (design: no on-screen LEDs).
    Item {
        id: tapScreen
        anchors.fill: parent
        visible: view.screen === "taptempo"
        property var t: view.tap

        // header: title (left) + meter class (right)
        Text {
            x: 16; y: 16
            text: "TAP TEMPO"
            color: cGreen; font.family: uiFont; font.pixelSize: 44
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 16; y: 26
            text: tapScreen.t && tapScreen.t.klass ? tapScreen.t.klass : ""
            color: cMuted; font.family: uiFont; font.pixelSize: 28
        }

        // big last-set BPM, centred
        Column {
            anchors.centerIn: parent
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: view.bpm
                color: cText; font.family: uiFont; font.pixelSize: 200
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "BPM"
                color: cMuted; font.family: uiFont; font.pixelSize: 38
            }
        }

        // meter + how-to footer
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - 92
            text: (tapScreen.t && tapScreen.t.bpb ? tapScreen.t.bpb : 4) + " BEATS / BAR"
            color: cGreen; font.family: uiFont; font.pixelSize: 30
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom; anchors.bottomMargin: 16
            text: "탭: 풋스위치 아무거나  ·  종료: 콤보(2개 동시)"
            color: cDim; font.family: uiFont; font.pixelSize: 22
        }
    }
}
