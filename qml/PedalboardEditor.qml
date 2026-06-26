import QtQuick
import QtQuick.Window
import QtQuick.Shapes

// Pedalboard Editor mock — PyQt6 port of Claude Design "Concept A".
// Device screen is exactly 800x480; a thin dev band on top hosts the demo triggers
// (the 5 additions) and toast. Visual tokens live here; data/logic come from `editor`.
Window {
    id: win
    visible: true
    width: 800
    height: 524
    color: cScreen
    title: "Pedalboard Editor — mock"

    readonly property color cScreen: "#0e1118"
    readonly property color cPanel:  "#141925"
    readonly property color cGraph:  "#0a0d13"
    readonly property color cElev:   "#1d2433"
    readonly property color cBorder: "#2c3648"
    readonly property color cGreen:  "#5fd0a0"
    readonly property color cOrange: "#d99a4e"
    readonly property color cBlue:   "#3b6fe0"
    readonly property color cText:   "#e8edf4"
    readonly property color cMuted:  "#7e8694"
    readonly property color cDim:    "#5a6270"

    property string toastText: ""
    Connections {
        target: editor
        function onToast(msg) { win.toastText = msg; toastTimer.restart() }
    }
    Timer { id: toastTimer; interval: 3200; onTriggered: win.toastText = "" }

    // ============================== DEV BAND (harness, not the device UI) ==============================
    Rectangle {
        id: devBar
        width: parent.width; height: 44; color: "#0b0d12"
        Row {
            anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            DevBtn { label: "흩뜨림→퀵 재오픈"; accent: cGreen; onTap: editor.demoScramble() }
            DevBtn { label: "병렬 보드 로드"; accent: cOrange; onTap: editor.demoParallel() }
            DevBtn { label: "IN: " + (editor.inMode === "stereo" ? "STEREO" : "MONO"); accent: cBlue; onTap: editor.toggleInMode() }
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
            text: win.toastText !== "" ? win.toastText
                  : ("round-trip: " + (editor.roundTripOK ? "OK ✓" : "FAIL ✗"))
            color: win.toastText !== "" ? cGreen : cDim
            font.family: uiFont; font.pixelSize: 15
            elide: Text.ElideRight; width: 440; horizontalAlignment: Text.AlignRight
        }
    }

    // ============================== 800x480 DEVICE SCREEN ==============================
    Rectangle {
        id: screen
        y: 44; width: 800; height: 480; color: cScreen; clip: true

        // -------- slim header: QUICK | ADV tabs + status --------
        Item {
            id: header
            width: parent.width; height: 34
            Row {
                anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter
                spacing: 7
                Tab { label: "QUICK"; active: !editor.advanced; onTap: editor.switchMode("quick") }
                Tab { label: "ADV"; active: editor.advanced; onTap: editor.switchMode("advanced") }
                Text { text: "자동 라우팅"; color: cDim; font.family: uiFont; font.pixelSize: 14
                       anchors.verticalCenter: parent.verticalCenter }
            }
            Text {
                anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                text: editor.advanced ? editor.advBadge : editor.status
                color: editor.advanced ? cOrange : cMuted
                font.family: uiFont; font.pixelSize: 14; elide: Text.ElideRight; width: 380
                horizontalAlignment: Text.AlignRight
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#1b2230" }
        }

        // ======================================================== QUICK MODE
        Item {
            visible: !editor.advanced
            anchors.fill: parent

            // -------- category rail (stage 1) --------
            Rectangle {
                id: rail
                x: 0; y: 34; width: 66; height: parent.height - 34
                color: "#141925"
                Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: "#1b2230" }
                Column {
                    anchors.fill: parent; anchors.margins: 6; spacing: 5
                    Repeater {
                        model: editor.rail
                        Rectangle {
                            width: 54; height: 44; radius: 5
                            color: modelData.sel ? cElev : "transparent"
                            border.width: 1; border.color: modelData.sel ? modelData.color : "#1b2230"
                            Column {
                                anchors.centerIn: parent; spacing: 2
                                Rectangle { width: 8; height: 8; radius: 2; color: modelData.color
                                            anchors.horizontalCenter: parent.horizontalCenter }
                                Text { text: modelData.abbr; color: cText; font.family: uiFont; font.pixelSize: 14
                                       anchors.horizontalCenter: parent.horizontalCenter }
                                Text { text: modelData.count; color: cDim; font.family: uiFont; font.pixelSize: 11
                                       anchors.horizontalCenter: parent.horizontalCenter }
                            }
                            MouseArea { anchors.fill: parent; onClicked: editor.pickCategory(modelData.key) }
                        }
                    }
                }
            }

            // -------- canvas --------
            Rectangle {
                id: canvas
                x: 66; y: 34; width: 734; height: 446; color: cGraph; clip: true

                // grid
                Canvas {
                    anchors.fill: parent
                    onPaint: {
                        var c = getContext("2d"); c.strokeStyle = "#11161f"; c.lineWidth = 1
                        for (var gx = 0; gx < width; gx += 30) { c.beginPath(); c.moveTo(gx, 0); c.lineTo(gx, height); c.stroke() }
                        for (var gy = 0; gy < height; gy += 30) { c.beginPath(); c.moveTo(0, gy); c.lineTo(width, gy); c.stroke() }
                    }
                }

                // wires (live — notify wiresChanged)
                Repeater {
                    model: editor.wires
                    Shape {
                        anchors.fill: parent
                        ShapePath {
                            strokeColor: modelData.color; strokeWidth: modelData.w; fillColor: "transparent"
                            capStyle: ShapePath.RoundCap
                            strokeStyle: modelData.dash !== "" ? ShapePath.DashLine : ShapePath.SolidLine
                            dashPattern: [4, 3]
                            PathSvg { path: modelData.d }
                        }
                    }
                }

                // adapter chips (channel negotiation — tap to cycle mode)
                Repeater {
                    model: editor.chips
                    Rectangle {
                        x: modelData.x - width / 2; y: modelData.y - height / 2
                        height: 20; width: chipTxt.width + 14; radius: 10
                        color: modelData.bg; border.width: 1; border.color: modelData.accent
                        Text { id: chipTxt; anchors.centerIn: parent; text: modelData.label
                               color: modelData.fg; font.family: uiFont; font.pixelSize: 13 }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: {
                                if (modelData.kind === "in") editor.cycleInAdapter(modelData.nid)
                                else if (modelData.kind === "merge") editor.cycleMergeAdapter(modelData.nid)
                                else editor.cycleOutAdapter()
                            }
                        }
                    }
                }

                // IN terminal (click toggles mono/stereo)
                Column {
                    x: 6; y: canvas.height / 2 - 24; spacing: 3
                    Rectangle {
                        width: 30; height: 30; radius: 15; color: "#141925"
                        border.width: 2; border.color: cGreen
                        Text { anchors.centerIn: parent; text: "IN"; color: cGreen; font.family: uiFont; font.pixelSize: 13 }
                        MouseArea { anchors.fill: parent; onClicked: editor.toggleInMode() }
                    }
                    Text { text: editor.inMode === "stereo" ? "STEREO" : "L-MONO"; color: cGreen
                           font.family: uiFont; font.pixelSize: 12; anchors.horizontalCenter: parent.horizontalCenter }
                }
                // OUT terminal
                Column {
                    x: canvas.width - 36; y: canvas.height / 2 - 24; spacing: 3
                    Rectangle {
                        width: 30; height: 30; radius: 15; color: "#141925"
                        border.width: 2; border.color: cOrange
                        Text { anchors.centerIn: parent; text: "OUT"; color: cOrange; font.family: uiFont; font.pixelSize: 12 }
                    }
                    Text { text: "STEREO"; color: cOrange; font.family: uiFont; font.pixelSize: 12
                           anchors.horizontalCenter: parent.horizontalCenter }
                }

                // trash badge (drag a node here to delete)
                Rectangle {
                    id: trash
                    x: canvas.width - 52; y: canvas.height - 52; width: 40; height: 40; radius: 8
                    color: win.trashHot ? "#3a2026" : "#12161f"
                    border.width: 1; border.color: win.trashHot ? "#e8694a" : cBorder
                    Text { anchors.centerIn: parent; text: "DEL"; color: win.trashHot ? "#e8694a" : cDim
                           font.family: uiFont; font.pixelSize: 14 }
                }

                // empty hint
                Column {
                    visible: editor.empty; anchors.centerIn: parent; spacing: 6
                    Text { text: "＋"; color: cBorder; font.pixelSize: 60; anchors.horizontalCenter: parent.horizontalCenter }
                    Text { text: "왼쪽 카테고리에서 이펙터를 끌어다 놓으세요"; color: cMuted
                           font.family: uiFont; font.pixelSize: 18; anchors.horizontalCenter: parent.horizontalCenter }
                    Text { text: "가로 순서대로 직렬 연결 · 모노/스테레오 채널은 자동 협상"; color: cDim
                           font.family: uiFont; font.pixelSize: 14; anchors.horizontalCenter: parent.horizontalCenter }
                }

                // nodes
                Repeater {
                    model: editor.nodesView
                    Rectangle {
                        id: nd
                        x: modelData.x; y: modelData.y; width: 124; height: 52; radius: 7
                        color: "#161b26"; border.width: 2; border.color: modelData.border
                        opacity: modelData.bypass ? 0.55 : 1.0
                        property bool dragged: false

                        // in pins (left)
                        Column {
                            x: -7; anchors.verticalCenter: parent.verticalCenter; spacing: 5
                            Repeater {
                                model: modelData.inPins
                                Rectangle { width: 11; height: 11; radius: 5.5; color: cGreen; border.width: 2; border.color: cGraph }
                            }
                        }
                        // out pins (right)
                        Column {
                            x: parent.width - 4; anchors.verticalCenter: parent.verticalCenter; spacing: 5
                            Repeater {
                                model: modelData.outPins
                                Rectangle { width: 11; height: 11; radius: 5.5; color: cOrange; border.width: 2; border.color: cGraph }
                            }
                        }

                        Column {
                            anchors.fill: parent
                            Row {
                                width: parent.width; height: 30; leftPadding: 7; rightPadding: 7; spacing: 6
                                Rectangle { width: 14; height: 14; radius: 7; color: modelData.dot
                                            anchors.verticalCenter: parent.verticalCenter }
                                Text { text: modelData.name; color: cText; font.family: uiFont; font.pixelSize: 15
                                       elide: Text.ElideRight; width: parent.width - 30
                                       anchors.verticalCenter: parent.verticalCenter }
                            }
                            Row {
                                width: parent.width; height: 20; spacing: 7
                                Text { text: modelData.bucket; color: cDim; font.family: uiFont; font.pixelSize: 12
                                       anchors.verticalCenter: parent.verticalCenter; leftPadding: 8 }
                                Text { visible: modelData.hasBadge; text: modelData.badge; color: modelData.badgeColor
                                       font.family: uiFont; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            drag.target: nd; drag.threshold: 4
                            onPressed: nd.dragged = false
                            onPositionChanged: {
                                if (drag.active) {
                                    nd.dragged = true
                                    win.trashHot = (nd.x + 62 > canvas.width - 70 && nd.y + 26 > canvas.height - 70)
                                    editor.nodeDragMove(modelData.id, nd.x, nd.y)
                                }
                            }
                            onReleased: {
                                if (nd.dragged) {
                                    var ot = (nd.x + 62 > canvas.width - 70 && nd.y + 26 > canvas.height - 70)
                                    win.trashHot = false
                                    editor.nodeDragEnd(modelData.id, nd.x, nd.y, ot)
                                } else {
                                    editor.selectNode(modelData.id)
                                }
                            }
                        }
                    }
                }
            }

            // -------- stage-2 effect flyout (overlay) --------
            Rectangle {
                visible: editor.flyOpen
                x: 66; y: 34; width: 200; height: parent.height - 34
                color: "#141925"; border.width: 1; border.color: cBorder
                Column {
                    anchors.fill: parent
                    Item {
                        width: parent.width; height: 32
                        Text { anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter
                               text: editor.flyTitle; color: editor.flyColor; font.family: uiFont; font.pixelSize: 18 }
                        Text { anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                               text: "✕"; color: cMuted; font.pixelSize: 18
                               MouseArea { anchors.fill: parent; onClicked: editor.closeFly() } }
                    }
                    Flickable {
                        width: parent.width; height: parent.height - 32; contentHeight: flyCol.height; clip: true
                        Column {
                            id: flyCol; width: parent.width; spacing: 6; padding: 8
                            Repeater {
                                model: editor.flyItems
                                Rectangle {
                                    width: 184; height: 42; radius: 5; color: cElev; border.width: 1; border.color: cBorder
                                    Row {
                                        anchors.fill: parent; anchors.margins: 7; spacing: 8
                                        Column {
                                            width: parent.width - 30
                                            Text { text: modelData.name; color: cText; font.family: uiFont; font.pixelSize: 15
                                                   elide: Text.ElideRight; width: parent.width }
                                            Text { text: modelData.brand; color: cMuted; font.family: uiFont; font.pixelSize: 12
                                                   elide: Text.ElideRight; width: parent.width }
                                        }
                                        Text { text: modelData.pins; color: cGreen; font.family: uiFont; font.pixelSize: 14
                                               anchors.verticalCenter: parent.verticalCenter }
                                    }
                                    MouseArea { anchors.fill: parent; onClicked: editor.addEffect(modelData.uri) }
                                }
                            }
                        }
                    }
                }
            }

            // -------- inspector (overlay, right) --------
            Rectangle {
                visible: editor.inspOpen
                x: parent.width - 214; y: 34; width: 214; height: parent.height - 34
                color: "#141925"; border.width: 1; border.color: cBorder
                Column {
                    anchors.fill: parent
                    Item {
                        width: parent.width; height: 40
                        Column {
                            anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 40
                            Text { text: editor.inspName; color: cText; font.family: uiFont; font.pixelSize: 17
                                   elide: Text.ElideRight; width: parent.width }
                            Text { text: editor.inspSub; color: cMuted; font.family: uiFont; font.pixelSize: 13
                                   elide: Text.ElideRight; width: parent.width }
                        }
                        Text { anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                               text: "✕"; color: cMuted; font.pixelSize: 18
                               MouseArea { anchors.fill: parent; onClicked: editor.closeInspector() } }
                    }
                    Item {
                        width: parent.width; height: 38
                        Rectangle {
                            x: 10; anchors.verticalCenter: parent.verticalCenter
                            height: 28; width: bypTxt.width + 24; radius: 5
                            color: editor.inspBypassed ? "transparent" : "rgba(95,208,160,0.12)"
                            border.width: 1; border.color: editor.inspBypassed ? cDim : cGreen
                            Text { id: bypTxt; anchors.centerIn: parent; text: editor.inspBypassed ? "BYPASSED" : "ACTIVE"
                                   color: editor.inspBypassed ? cMuted : cGreen; font.family: uiFont; font.pixelSize: 15 }
                            MouseArea { anchors.fill: parent; onClicked: editor.toggleBypass(editor.sel) }
                        }
                        Text { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                               text: editor.inspMeta; color: cDim; font.family: uiFont; font.pixelSize: 13 }
                    }
                    Flickable {
                        width: parent.width; height: parent.height - 78; contentHeight: knobGrid.height; clip: true
                        Grid {
                            id: knobGrid; width: parent.width; columns: 2; rowSpacing: 12; columnSpacing: 8
                            padding: 10
                            Repeater {
                                model: editor.knobs
                                Column {
                                    width: 90; spacing: 3
                                    // dial
                                    Rectangle {
                                        visible: modelData.kind === "dial"
                                        width: 48; height: 48; radius: 24
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        gradient: Gradient {
                                            GradientStop { position: 0.0; color: "#252e40" }
                                            GradientStop { position: 1.0; color: "#161b26" }
                                        }
                                        border.width: 2; border.color: cBorder
                                        Rectangle {
                                            width: 3; height: 18; radius: 2; color: cText
                                            x: parent.width / 2 - 1.5; y: 6
                                            transformOrigin: Item.Bottom
                                            rotation: -135 + 270 * modelData.norm
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            property real startY: 0
                                            property real startNorm: 0
                                            onPressed: function(m) { startY = m.y; startNorm = modelData.norm }
                                            onPositionChanged: function(m) {
                                                var dn = (startY - m.y) / 120.0
                                                editor.setKnobNorm(modelData.sym, Math.max(0, Math.min(1, startNorm + dn)))
                                            }
                                        }
                                    }
                                    // toggle
                                    Rectangle {
                                        visible: modelData.kind === "toggle"
                                        width: 46; height: 26; radius: 13
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        color: modelData.on ? cGreen : cBorder
                                        Rectangle { width: 20; height: 20; radius: 10; color: "#0e1118"
                                                    y: 3; x: modelData.on ? 23 : 3; Behavior on x { NumberAnimation { duration: 120 } } }
                                        MouseArea { anchors.fill: parent; onClicked: editor.toggleSwitch(modelData.sym) }
                                    }
                                    // enum
                                    Rectangle {
                                        visible: modelData.kind === "enum"
                                        height: 30; width: Math.max(54, enumTxt.width + 16); radius: 5
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        color: cElev; border.width: 1; border.color: cBorder
                                        Text { id: enumTxt; anchors.centerIn: parent; text: modelData.valueText
                                               color: "#b58af0"; font.family: uiFont; font.pixelSize: 15 }
                                        MouseArea { anchors.fill: parent; onClicked: editor.cycleEnum(modelData.sym) }
                                    }
                                    Text { text: modelData.label; color: cMuted; font.family: uiFont; font.pixelSize: 13
                                           anchors.horizontalCenter: parent.horizontalCenter
                                           elide: Text.ElideRight; width: 90; horizontalAlignment: Text.AlignHCenter }
                                    Text { text: modelData.valueText; color: cText; font.family: uiFont; font.pixelSize: 14
                                           anchors.horizontalCenter: parent.horizontalCenter }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ======================================================== ADVANCED VIEWER (read-only)
        Item {
            visible: editor.advanced
            anchors.fill: parent

            Rectangle {
                x: 0; y: 34; width: parent.width; height: parent.height - 34; color: cGraph

                Repeater {
                    model: editor.advWires
                    Shape {
                        anchors.fill: parent
                        ShapePath { strokeColor: modelData.color; strokeWidth: modelData.w; fillColor: "transparent"
                                    capStyle: ShapePath.RoundCap; PathSvg { path: modelData.d } }
                    }
                }
                // IN / OUT terminals
                Rectangle { x: 22; y: parent.height / 2 - 13; width: 26; height: 26; radius: 13; color: "#141925"
                            border.width: 2; border.color: cGreen
                            Text { anchors.centerIn: parent; text: "IN"; color: cGreen; font.family: uiFont; font.pixelSize: 12 } }
                Rectangle { x: parent.width - 48; y: parent.height / 2 - 13; width: 26; height: 26; radius: 13; color: "#141925"
                            border.width: 2; border.color: cOrange
                            Text { anchors.centerIn: parent; text: "OUT"; color: cOrange; font.family: uiFont; font.pixelSize: 11 } }

                Repeater {
                    model: editor.advNodes
                    Rectangle {
                        x: modelData.x; y: modelData.y; width: 124; height: 50; radius: 7
                        color: "#161b26"; border.width: 2; border.color: modelData.border
                        Row {
                            anchors.fill: parent; anchors.margins: 7; spacing: 6
                            Rectangle { width: 13; height: 13; radius: 6.5; color: modelData.dot
                                        anchors.verticalCenter: parent.verticalCenter }
                            Text { text: modelData.name; color: cText; font.family: uiFont; font.pixelSize: 15
                                   elide: Text.ElideRight; width: parent.width - 24; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }

                // read-only badge
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter; y: 12
                    height: 26; width: badgeTxt.width + 22; radius: 13
                    color: "#2a221a"; border.width: 1; border.color: cOrange
                    Text { id: badgeTxt; anchors.centerIn: parent; text: "읽기전용 뷰어 · 자동 라우팅 없음"
                           color: cOrange; font.family: uiFont; font.pixelSize: 13 }
                }
            }
        }
    }

    property bool trashHot: false

    // --- small reusable controls ---
    component Tab: Rectangle {
        property string label: ""
        property bool active: false
        signal tap()
        height: 22; width: tabTxt.width + 18; radius: 5
        color: active ? "#162338" : "transparent"
        border.width: 1; border.color: active ? cBlue : cBorder
        anchors.verticalCenter: parent.verticalCenter
        Text { id: tabTxt; anchors.centerIn: parent; text: label; color: active ? "#cfe0ff" : cDim
               font.family: uiFont; font.pixelSize: 14 }
        MouseArea { anchors.fill: parent; onClicked: parent.tap() }
    }

    component DevBtn: Rectangle {
        property string label: ""
        property color accent: cBlue
        signal tap()
        height: 28; width: btnTxt.width + 20; radius: 6
        color: "#141925"; border.width: 1; border.color: accent
        Text { id: btnTxt; anchors.centerIn: parent; text: label; color: cText
               font.family: uiFont; font.pixelSize: 14 }
        MouseArea { anchors.fill: parent; onClicked: parent.tap() }
    }
}
