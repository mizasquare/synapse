import QtQuick
import QtQuick.Shapes

// Pedalboard Editor body — the live app's EDIT screen (embedded in qml/main.qml).
// QUICK (auto-routing) and ADVANCED (manual port-level routing) share one 734x446 canvas.
// Visual tokens live here; data/logic in the `editor` context property. The host wires
// `exitRequested` (-> return to overview).
Item {
    id: win
    anchors.fill: parent

    // Emitted by the header "나가기" affordance. The host decides what leaving means.
    signal exitRequested()

    readonly property color cScreen: "#0e1118"
    readonly property color cPanel:  "#141925"
    readonly property color cGraph:  "#0a0d13"
    readonly property color cElev:   "#1d2433"
    readonly property color cBorder: "#2c3648"
    readonly property color cGreen:  "#5fd0a0"
    readonly property color cOrange: "#d99a4e"
    readonly property color cBlue:   "#3b6fe0"
    readonly property color cPurple: "#b58af0"
    readonly property color cText:   "#e8edf4"
    readonly property color cMuted:  "#7e8694"
    readonly property color cDim:    "#5a6270"

    property bool trashHot: false
    property bool liveBoardsOpen: false   // live host board switcher (M6a)
    property bool snapsOpen: false        // live snapshot manager (M6c)
    property bool snapNaming: false       // snapshot save-as naming panel (M6c)
    property bool newBoardOpen: false     // live NEW BOARD quick/advanced modal (M6d-1)
    property string pendingSwitchBundle: ""  // live switch awaiting dirty-discard confirm
    property string pendingSwitchTitle: ""
    property string namingMode: ""       // ""=closed, "save"=first save, "saveas"=save copy

    // Save: overwrite in place, unless it's a scratch NEW board (the shared
    // default) — then ask for a name first (save-as) so default is never clobbered
    function doSave() {
        if (editor.boardSaved) editor.saveBoard()
        else win.namingMode = "save"
    }

    property string toastText: ""
    Connections {
        target: editor
        function onToast(msg) { win.toastText = msg; toastTimer.restart() }
        // dirty live board switch -> raise the discard-confirm dialog (don't switch yet)
        function onConfirmBoardSwitch(bundle, title) {
            win.pendingSwitchBundle = bundle; win.pendingSwitchTitle = title
        }
        // a switch actually completed (clean tap OR confirmed discard) -> close the
        // switcher overlay so both paths land on the editor consistently.
        function onBoardSwitched() { win.liveBoardsOpen = false }
        function onModeFlash(dir) { modeFx.start(dir) }
        function onSpawnFly(name, color, fromX, fromY, toX, toY) {
            flyName.text = name; flyGhost.accent = color
            flyGhost.x = fromX; flyGhost.y = fromY; flyGhost.visible = true
            flyAnim.stop(); flyAnimX.to = toX; flyAnimY.to = toY; flyAnim.start()
        }
    }
    Timer { id: toastTimer; interval: 3200; onTriggered: win.toastText = "" }

    // ============================== 800x480 DEVICE SCREEN ==============================
    Rectangle {
        id: screen
        y: 0; width: 800; height: 480; color: cScreen; clip: true

        // -------- slim header: mode label + status --------
        Item {
            id: header
            width: parent.width; height: 34; z: 9
            Row {
                anchors.left: parent.left; anchors.leftMargin: 10; anchors.verticalCenter: parent.verticalCenter
                spacing: 7
                Pill { label: "◄ 나가기"; accent: cMuted; onTap: win.exitRequested() }
                // ADV/QUICK indicator — tappable in live to toggle modes (M6d-3).
                // QUICK only engages for a quick-representable board.
                Text {
                    text: (editor.advanced ? "ADV" : "QUICK") + (editor.live ? " ⇄" : "")
                    color: editor.advanced ? cOrange : cMuted
                    font.family: uiFont; font.pixelSize: 15; anchors.verticalCenter: parent.verticalCenter
                    MouseArea { anchors.fill: parent; enabled: editor.live
                                onClicked: editor.toggleLiveMode() }
                }
                Pill { label: "BOARD"; accent: cBlue
                       onTap: { editor.refreshBoards(); win.liveBoardsOpen = true } }
                Text {
                    text: editor.boardName + (editor.dirty ? " *" : "")
                    color: editor.dirty ? cOrange : cText
                    font.family: uiFont; font.pixelSize: 14; anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideRight; width: 110
                }
                // NEW BOARD: start fresh on the empty default (modal: quick/advanced)
                Pill { label: "NEW"; accent: cBlue; visible: editor.live
                       onTap: win.newBoardOpen = true }
                // live in-place SAVE — via doSave() so a scratch NEW board routes to
                // save-as (naming) instead of overwriting the shared default.
                Pill { label: editor.dirty ? "SAVE *" : "SAVE"; accent: cGreen
                       visible: editor.live; dim: !(editor.dirty || !editor.boardSaved)
                       onTap: win.doSave() }
                // live snapshot manager (change / save / save-as)
                Pill { label: "SNAP"; accent: cPurple; visible: editor.live
                       onTap: win.snapsOpen = true }
                Pill { label: "SHUF"; accent: cGreen; visible: !editor.live; dim: editor.advanced
                       onTap: if (!editor.advanced) editor.demoScramble() }
            }
            Text {
                anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                text: win.toastText !== "" ? win.toastText : editor.status
                color: win.toastText !== "" ? cGreen : (editor.advanced ? cOrange : cMuted)
                font.family: uiFont; font.pixelSize: 14; elide: Text.ElideRight; width: 360
                horizontalAlignment: Text.AlignRight
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#1b2230" }
        }

        // -------- category rail (shared) --------
        Rectangle {
            id: rail
            x: 0; y: 34; width: 66; height: parent.height - 34; z: 6
            color: cPanel
            Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: "#1b2230" }
            // Scrollable: 16 buckets don't all fit the 446px rail (only ~9 do), so
            // a fixed Column clipped the tail (Pitch/Amp·Cab/…/MIDI). Flick to reach them.
            Flickable {
                anchors.fill: parent; anchors.margins: 6
                contentHeight: railCol.height; clip: true
                boundsBehavior: Flickable.StopAtBounds
                Column {
                    id: railCol
                    width: parent.width; spacing: 5
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
        }

        // ============================================== CANVAS (both modes draw here)
        Rectangle {
            id: canvas
            x: 66; y: 34; width: 734; height: 446; clip: true
            // ADVANCED gets a warm amber-tinted board so it reads differently from QUICK
            color: editor.advanced ? "#140f09" : cGraph

            // grid
            Canvas {
                id: grid
                anchors.fill: parent
                property color gridColor: editor.advanced ? "#241a0d" : "#11161f"
                onGridColorChanged: requestPaint()
                onPaint: {
                    var c = getContext("2d"); c.strokeStyle = grid.gridColor; c.lineWidth = 1
                    for (var gx = 0; gx < width; gx += 30) { c.beginPath(); c.moveTo(gx, 0); c.lineTo(gx, height); c.stroke() }
                    for (var gy = 0; gy < height; gy += 30) { c.beginPath(); c.moveTo(0, gy); c.lineTo(width, gy); c.stroke() }
                }
            }

            // ================= QUICK MODE =================
            Item {
                visible: !editor.advanced
                anchors.fill: parent

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
                        width: 30; height: 30; radius: 15; color: cPanel
                        border.width: 2; border.color: cGreen
                        Text { anchors.centerIn: parent; text: "IN"; color: cGreen; font.family: uiFont; font.pixelSize: 13 }
                        MouseArea { anchors.fill: parent; onClicked: editor.toggleInMode() }
                    }
                    Text { text: editor.inMode === "stereo" ? "STEREO" : "L-MONO"; color: cGreen
                           font.family: uiFont; font.pixelSize: 12; anchors.horizontalCenter: parent.horizontalCenter }
                }
                Column {
                    x: canvas.width - 36; y: canvas.height / 2 - 24; spacing: 3
                    Rectangle {
                        width: 30; height: 30; radius: 15; color: cPanel
                        border.width: 2; border.color: cOrange
                        Text { anchors.centerIn: parent; text: "OUT"; color: cOrange; font.family: uiFont; font.pixelSize: 12 }
                    }
                    Text { text: "STEREO"; color: cOrange; font.family: uiFont; font.pixelSize: 12
                           anchors.horizontalCenter: parent.horizontalCenter }
                }

                // empty hint
                Column {
                    visible: editor.empty; anchors.centerIn: parent; spacing: 6
                    Text { text: "＋"; color: cBorder; font.pixelSize: 60; anchors.horizontalCenter: parent.horizontalCenter }
                    Text { text: "왼쪽 카테고리에서 이펙터를 추가하세요"; color: cMuted
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
                        opacity: modelData.flying ? 0 : (modelData.pending ? 0.4 : (modelData.bypass ? 0.55 : 1.0))
                        property bool dragged: false

                        Column {
                            x: -7; anchors.verticalCenter: parent.verticalCenter; spacing: 5
                            Repeater {
                                model: modelData.inPins
                                Rectangle { width: 11; height: 11; radius: 5.5; color: cGreen; border.width: 2; border.color: cGraph }
                            }
                        }
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

            // ================= ADVANCED MODE =================
            Item {
                visible: editor.advanced
                anchors.fill: parent

                // cables
                Repeater {
                    model: editor.gWires
                    Item {
                        anchors.fill: parent
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
                        // tap handle at the cable midpoint (touch-friendly select)
                        MouseArea {
                            x: modelData.mx - 13; y: modelData.my - 13; width: 26; height: 26
                            onClicked: editor.selectWire(modelData.id)
                        }
                    }
                }

                // merge ⊕ markers
                Repeater {
                    model: editor.gMerges
                    Rectangle {
                        x: modelData.x - 9; y: modelData.y - 9; width: 18; height: 18; radius: 9
                        color: "#16241c"; border.width: 1; border.color: cGreen
                        Text { anchors.centerIn: parent; text: "+"; color: "#8fe0bd"; font.family: uiFont; font.pixelSize: 14 }
                    }
                }
                // feedback tags
                Repeater {
                    model: editor.gFbTags
                    Rectangle {
                        x: modelData.x - width / 2; y: modelData.y - 9; height: 18; width: fbTxt.width + 12; radius: 9
                        color: "#2a221a"; border.width: 1; border.color: "#e0a458"
                        Text { id: fbTxt; anchors.centerIn: parent; text: "FB"; color: "#e8b06a"; font.family: uiFont; font.pixelSize: 12 }
                    }
                }
                // selected-cable delete
                Rectangle {
                    visible: editor.gWireDel
                    x: editor.gWireDelX - 14; y: editor.gWireDelY - 14; width: 28; height: 28; radius: 14
                    color: "#3a1f1a"; border.width: 1; border.color: "#e8694a"; z: 20
                    Text { anchors.centerIn: parent; text: "X"; color: "#ff8a6a"; font.family: uiFont; font.pixelSize: 15 }
                    MouseArea { anchors.fill: parent; onClicked: editor.removeSelectedWire() }
                }

                // cancel an in-progress connection by tapping empty canvas
                MouseArea {
                    anchors.fill: parent
                    visible: editor.radActive || editor.targeting
                    onClicked: editor.cancelConn()
                }

                // HW IN / OUT blocks
                Repeater {
                    model: editor.gHw
                    Rectangle {
                        x: modelData.x; y: modelData.y; width: modelData.w; height: modelData.h; radius: 8
                        color: cPanel; border.width: 2; border.color: modelData.color
                        Column {
                            anchors.centerIn: parent; spacing: 2
                            Text { text: modelData.label; color: modelData.color; font.family: uiFont; font.pixelSize: 13
                                   anchors.horizontalCenter: parent.horizontalCenter }
                            Text { text: modelData.sub; color: modelData.color; opacity: 0.7; font.family: uiFont; font.pixelSize: 11
                                   anchors.horizontalCenter: parent.horizontalCenter }
                        }
                        MouseArea { anchors.fill: parent; onClicked: if (modelData.label === "IN") editor.toggleInMode() }
                    }
                }
                // HW edges (start/finish a connection)
                Repeater {
                    model: editor.hwEdges
                    Rectangle {
                        x: modelData.x; y: modelData.y; width: modelData.w; height: modelData.h; radius: 5; z: 13
                        color: modelData.glow ? "#1c3550" : "transparent"
                        border.width: modelData.glow ? 1 : 0; border.color: "#78c8ff"
                        MouseArea {
                            anchors.fill: parent
                            onClicked: editor.edgeTap(modelData.node, modelData.side,
                                                      modelData.x + modelData.w / 2, modelData.y + modelData.h / 2)
                        }
                    }
                }

                // port dots (non-interactive)
                Repeater {
                    model: editor.gPorts
                    Rectangle {
                        x: modelData.x - 6.5; y: modelData.y - 6.5; width: 13; height: 13; radius: 6.5
                        color: modelData.color; border.width: 2; border.color: cGraph
                        Text { anchors.centerIn: parent; visible: modelData.ch !== ""; text: modelData.ch
                               color: cGraph; font.family: uiFont; font.pixelSize: 8 }
                    }
                }

                // advanced nodes (port cards)
                Repeater {
                    model: editor.gNodes
                    Rectangle {
                        id: gn
                        x: modelData.x; y: modelData.y; width: 124; height: modelData.h; radius: 7
                        color: "#161b26"; border.width: 2; border.color: modelData.border
                        opacity: modelData.flying ? 0 : (modelData.pending ? 0.4 : (modelData.bypass ? 0.55 : 1.0))
                        property bool dragged: false

                        Column {
                            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                            Row {
                                width: parent.width; height: 24; leftPadding: 7; rightPadding: 7; spacing: 6
                                Rectangle {
                                    id: gByp
                                    width: 14; height: 14; radius: 7; color: modelData.dot
                                    anchors.verticalCenter: parent.verticalCenter
                                    MouseArea { anchors.fill: parent; onClicked: editor.toggleBypass(modelData.id) }
                                }
                                Text { text: modelData.name; color: cText; font.family: uiFont; font.pixelSize: 15
                                       elide: Text.ElideRight; width: parent.width - 30
                                       anchors.verticalCenter: parent.verticalCenter }
                            }
                            Row {
                                width: parent.width; height: 18; leftPadding: 8
                                Text { text: modelData.bucket; color: cDim; font.family: uiFont; font.pixelSize: 12 }
                            }
                        }

                        // base drag / select (below edge strips)
                        MouseArea {
                            anchors.fill: parent
                            drag.target: gn; drag.threshold: 4
                            onPressed: gn.dragged = false
                            onPositionChanged: {
                                if (drag.active) {
                                    gn.dragged = true
                                    win.trashHot = (gn.x + 62 > canvas.width - 70 && gn.y + 26 > canvas.height - 70)
                                    editor.gNodeDragMove(modelData.id, gn.x, gn.y)
                                }
                            }
                            onReleased: {
                                if (gn.dragged) {
                                    var ot = (gn.x + 62 > canvas.width - 70 && gn.y + 26 > canvas.height - 70)
                                    win.trashHot = false
                                    editor.gNodeDragEnd(modelData.id, gn.x, gn.y, ot)
                                } else {
                                    editor.selectNode(modelData.id)
                                }
                            }
                        }
                        // bypass dot (above base) — re-stated so it wins the press
                        MouseArea {
                            x: 5; y: 5; width: 18; height: 18
                            onClicked: editor.toggleBypass(modelData.id)
                        }
                        // left edge = input side; right edge = output side
                        Rectangle {
                            visible: modelData.hasIn
                            x: -3; y: 5; width: 16; height: parent.height - 10; radius: 5
                            color: modelData.edgeInGlow ? "#1c3550" : "transparent"
                            MouseArea { anchors.fill: parent
                                onClicked: editor.edgeTap("" + modelData.id, "in", gn.x, gn.y + gn.height / 2) }
                        }
                        Rectangle {
                            visible: modelData.hasOut
                            x: parent.width - 13; y: 5; width: 16; height: parent.height - 10; radius: 5
                            color: modelData.edgeOutGlow ? "#1c3550" : "transparent"
                            MouseArea { anchors.fill: parent
                                onClicked: editor.edgeTap("" + modelData.id, "out", gn.x + gn.width, gn.y + gn.height / 2) }
                        }
                    }
                }

                // empty hint
                Column {
                    visible: editor.empty; anchors.centerIn: parent; spacing: 6
                    Text { text: "⌗"; color: cBorder; font.pixelSize: 52; anchors.horizontalCenter: parent.horizontalCenter }
                    Text { text: "이펙터를 추가하고 · 노드의 좌/우 변을 터치해 연결"; color: cMuted
                           font.family: uiFont; font.pixelSize: 18; anchors.horizontalCenter: parent.horizontalCenter }
                    Text { text: "변 터치 → 부채꼴 포트 메뉴(AUDIO·L·R·MIDI·CV) → 대상 노드 변 터치"; color: cDim
                           font.family: uiFont; font.pixelSize: 14; anchors.horizontalCenter: parent.horizontalCenter }
                }

                // targeting hint bar
                Rectangle {
                    visible: editor.targeting
                    anchors.horizontalCenter: parent.horizontalCenter; y: parent.height - 46
                    height: 32; width: tgtTxt.width + 24; radius: 16; z: 46
                    color: "#162338"; border.width: 1; border.color: cBlue
                    Text { id: tgtTxt; anchors.centerIn: parent; text: editor.targetHint
                           color: "#cfe0ff"; font.family: uiFont; font.pixelSize: 14 }
                }

                // radial port menu
                Item {
                    visible: editor.radActive; anchors.fill: parent; z: 56
                    Text {
                        x: editor.radCx; y: editor.radCy - 88
                        text: editor.radTitle; color: cMuted; font.family: uiFont; font.pixelSize: 13
                        transform: Translate { x: -tt.width / 2 }
                        TextMetrics { id: tt; text: editor.radTitle; font.family: uiFont; font.pixelSize: 13 }
                    }
                    Rectangle {
                        x: editor.radCx - 15; y: editor.radCy - 15; width: 30; height: 30; radius: 15
                        color: "#3a1f1a"; border.width: 1; border.color: "#e8694a"
                        Text { anchors.centerIn: parent; text: "X"; color: "#ff8a6a"; font.family: uiFont; font.pixelSize: 13 }
                        MouseArea { anchors.fill: parent; onClicked: editor.cancelConn() }
                    }
                    Repeater {
                        model: editor.radItems
                        Rectangle {
                            x: modelData.x - width / 2; y: modelData.y - 17
                            height: 34; width: Math.max(36, riTxt.width + 20); radius: 17
                            color: "#161b26"; border.width: 1; border.color: modelData.color
                            Text { id: riTxt; anchors.centerIn: parent; text: modelData.label
                                   color: "#cfe0ff"; font.family: uiFont; font.pixelSize: 14 }
                            MouseArea { anchors.fill: parent; onClicked: editor.commitRadialOpt(modelData.idx) }
                        }
                    }
                }

                // legend
                Row {
                    x: 8; y: parent.height - 22; spacing: 12; z: 7
                    LegendDot { c: cBlue; t: "AUDIO" }
                    LegendDot { c: "#e8694a"; t: "MIDI" }
                    LegendDot { c: cPurple; t: "CV" }
                }
            }

            // trash badge (drag a node here to delete) — shared
            Rectangle {
                id: trash
                x: canvas.width - 52; y: canvas.height - 52; width: 40; height: 40; radius: 8
                color: win.trashHot ? "#3a2026" : "#12161f"
                border.width: 1; border.color: win.trashHot ? "#e8694a" : cBorder
                Text { anchors.centerIn: parent; text: "DEL"; color: win.trashHot ? "#e8694a" : cDim
                       font.family: uiFont; font.pixelSize: 14 }
            }

            // fly-in ghost: a new node sails in from the palette side to its landing slot
            Rectangle {
                id: flyGhost
                visible: false; width: 124; height: 52; radius: 7; z: 80
                color: "#161b26"; border.width: 2; border.color: accent
                property color accent: cBlue
                Row {
                    width: parent.width; height: 30; leftPadding: 7; rightPadding: 7; spacing: 6
                    Rectangle { width: 14; height: 14; radius: 7; color: flyGhost.accent
                                anchors.verticalCenter: parent.verticalCenter }
                    Text { id: flyName; text: ""; color: cText; font.family: uiFont; font.pixelSize: 15
                           elide: Text.ElideRight; width: parent.width - 30
                           anchors.verticalCenter: parent.verticalCenter }
                }
                ParallelAnimation {
                    id: flyAnim
                    NumberAnimation { id: flyAnimX; target: flyGhost; property: "x"; duration: 320; easing.type: Easing.OutCubic }
                    NumberAnimation { id: flyAnimY; target: flyGhost; property: "y"; duration: 320; easing.type: Easing.OutCubic }
                    onFinished: { flyGhost.visible = false; editor.clearFly() }
                }
            }
        }

        // -------- stage-2 effect flyout (overlay) --------
        Rectangle {
            visible: editor.flyOpen
            x: 66; y: 34; width: 200; height: parent.height - 34; z: 40
            color: cPanel; border.width: 1; border.color: cBorder
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
            x: parent.width - 214; y: 34; width: 214; height: parent.height - 34; z: 45
            color: cPanel; border.width: 1; border.color: cBorder
            clip: true   // defense: panel content must never paint over the canvas/footer
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
                Column {
                    width: parent.width; spacing: 4; topPadding: 6; bottomPadding: 4
                    Flow {
                        width: parent.width - 20; x: 10; spacing: 6
                        Rectangle {
                            height: 30; width: bypTxt.width + 22; radius: 5
                            color: editor.inspBypassed ? "transparent" : "rgba(95,208,160,0.12)"
                            border.width: 1; border.color: editor.inspBypassed ? cDim : cGreen
                            Text { id: bypTxt; anchors.centerIn: parent; text: editor.inspBypassed ? "BYPASSED" : "ACTIVE"
                                   color: editor.inspBypassed ? cMuted : cGreen; font.family: uiFont; font.pixelSize: 14 }
                            MouseArea { anchors.fill: parent; onClicked: editor.toggleSelectedBypass() }
                        }
                        WideBtn { label: "리셋"; accent: cBorder; onTap: editor.resetParams() }
                        WideBtn { label: "연결 →"; accent: cBlue; visible: editor.inspCanConnect
                                  onTap: editor.connectFromSelected() }
                    }
                    Text { x: 10; text: editor.inspMeta + " · 노브 더블탭=기본값"; color: cDim
                           font.family: uiFont; font.pixelSize: 12 }
                }
                // patch params (NAM model / IR / cabsim) — live nodes only; tap to pick a file
                Column {
                    id: patchSection
                    width: parent.width; spacing: 4
                    visible: editor.inspPatches.length > 0
                    topPadding: visible ? 2 : 0; bottomPadding: visible ? 6 : 0
                    Repeater {
                        model: editor.inspPatches
                        Rectangle {
                            x: 10; width: parent.width - 20; height: 30; radius: 5
                            color: "#1f5fd0a0"; border.width: 1; border.color: cGreen
                            Text {
                                anchors.left: parent.left; anchors.leftMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - 16
                                text: "▦ " + modelData.label + ": " + (modelData.value || "—") + "  ▾"
                                color: cGreen; font.family: uiFont; font.pixelSize: 13; elide: Text.ElideMiddle
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: editPatchPicker.openFor(modelData.uri, modelData.label, modelData.value || "")
                            }
                        }
                    }
                }
                // LV2 presets — tap a chip to apply (live only; a preset rewrites
                // several params host-side, so the bridge reloads + reseeds after).
                // Real-host plugins carry 25+ presets (amsynth 27, Dragonfly 25) and
                // long labels wrap to ~1 chip per row, so the chip Flow is clamped
                // to ~3 rows and scrolls inside — unbounded it would swallow the
                // whole panel, push the knob Flickable to negative height and paint
                // chips over the canvas/footer below.
                Column {
                    id: presetSection
                    width: parent.width; spacing: 4
                    visible: editor.inspPresets.length > 0
                    topPadding: visible ? 2 : 0; bottomPadding: visible ? 6 : 0
                    Flickable {
                        x: 10; width: presetSection.width - 20
                        height: Math.min(presetFlow.height, 110)
                        contentHeight: presetFlow.height
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        Flow {
                            id: presetFlow
                            width: presetSection.width - 20; spacing: 6
                            Repeater {
                                model: editor.inspPresets
                                Rectangle {
                                    height: 30; radius: 5
                                    width: Math.min(prTxt.implicitWidth + 22, presetSection.width - 20)
                                    color: "transparent"; border.width: 1; border.color: cBlue
                                    Text {
                                        id: prTxt; anchors.centerIn: parent
                                        width: Math.min(implicitWidth, parent.width - 12)
                                        text: modelData.label; color: cBlue
                                        font.family: uiFont; font.pixelSize: 13; elide: Text.ElideRight
                                    }
                                    MouseArea { anchors.fill: parent; onClicked: editor.selectPreset(modelData.uri) }
                                }
                            }
                        }
                    }
                }
                Flickable {
                    width: parent.width; clip: true; contentHeight: knobGrid.height
                    height: Math.max(0, parent.height - 96
                                        - (patchSection.visible ? patchSection.height : 0)
                                        - (presetSection.visible ? presetSection.height : 0))
                    Grid {
                        id: knobGrid; width: parent.width; columns: 2; rowSpacing: 12; columnSpacing: 8
                        padding: 10
                        Repeater {
                            model: editor.knobs
                            Column {
                                id: kcol
                                width: 90; spacing: 3
                                // live state: rotates smoothly during a drag without a model rebuild
                                property real liveNorm: modelData.norm
                                property string liveVal: modelData.valueText
                                Rectangle {
                                    visible: modelData.kind === "dial"
                                    width: 48; height: 48; radius: 24
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: "#252e40" }
                                        GradientStop { position: 1.0; color: "#161b26" }
                                    }
                                    border.width: 2; border.color: dialMA.pressed ? cBlue : cBorder
                                    Rectangle {
                                        width: 3; height: 18; radius: 2; color: cText
                                        x: parent.width / 2 - 1.5; y: 6
                                        transformOrigin: Item.Bottom
                                        rotation: -135 + 270 * kcol.liveNorm
                                    }
                                    MouseArea {
                                        id: dialMA
                                        anchors.fill: parent
                                        preventStealing: true     // hold the gesture even over the Flickable
                                        property real startY: 0
                                        property real startNorm: 0
                                        onPressed: function(m) { startY = m.y; startNorm = kcol.liveNorm }
                                        onPositionChanged: function(m) {
                                            var n = Math.max(0, Math.min(1, startNorm + (startY - m.y) / 90.0))
                                            kcol.liveNorm = n
                                            kcol.liveVal = editor.setKnobNorm(modelData.sym, n)
                                        }
                                        onReleased: editor.syncInspector()
                                        onDoubleClicked: editor.resetKnob(modelData.sym)
                                    }
                                }
                                Rectangle {
                                    visible: modelData.kind === "toggle"
                                    width: 46; height: 26; radius: 13
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    color: modelData.on ? cGreen : cBorder
                                    Rectangle { width: 20; height: 20; radius: 10; color: "#0e1118"
                                                y: 3; x: modelData.on ? 23 : 3; Behavior on x { NumberAnimation { duration: 120 } } }
                                    MouseArea { anchors.fill: parent; onClicked: editor.toggleSwitch(modelData.sym) }
                                }
                                Rectangle {
                                    visible: modelData.kind === "enum"
                                    height: 30; width: Math.max(54, enumTxt.width + 16); radius: 5
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    color: cElev; border.width: 1; border.color: cBorder
                                    Text { id: enumTxt; anchors.centerIn: parent; text: kcol.liveVal
                                           color: cPurple; font.family: uiFont; font.pixelSize: 15 }
                                    MouseArea { anchors.fill: parent; onClicked: editor.cycleEnum(modelData.sym) }
                                }
                                Text { text: modelData.label; color: cMuted; font.family: uiFont; font.pixelSize: 13
                                       anchors.horizontalCenter: parent.horizontalCenter
                                       elide: Text.ElideRight; width: 90; horizontalAlignment: Text.AlignHCenter }
                                Text { text: kcol.liveVal; color: cText; font.family: uiFont; font.pixelSize: 14
                                       anchors.horizontalCenter: parent.horizontalCenter }
                            }
                        }
                    }
                }
            }
        }

        // -------- naming panel (first save / save-as) with the term suggester --------
        Item {
            visible: win.namingMode !== ""; anchors.fill: parent; z: 80
            onVisibleChanged: if (visible) {
                nameField.text = (win.namingMode === "saveas" && editor.boardName !== "Untitled") ? editor.boardName : ""
                nameField.forceActiveFocus()
            }
            MouseArea { anchors.fill: parent; onClicked: win.namingMode = "" }
            Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.62 }
            Rectangle {
                width: 478; height: 286; radius: 10; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBlue
                MouseArea { anchors.fill: parent }
                Column {
                    anchors.fill: parent; anchors.margins: 16; spacing: 11
                    Text { text: win.namingMode === "saveas" ? "다른 이름으로 저장" : "이름을 정해 저장"
                           color: cText; font.family: uiFont; font.pixelSize: 18 }
                    Rectangle {
                        width: parent.width; height: 34; radius: 5; color: cElev; border.width: 1
                        border.color: nameField.activeFocus ? cBlue : cBorder
                        TextInput {
                            id: nameField; anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 8
                            verticalAlignment: TextInput.AlignVCenter; clip: true; selectByMouse: true
                            color: cText; font.family: uiFont; font.pixelSize: 16
                            onAccepted: if (text.trim().length) { editor.saveBoardNamed(text); win.namingMode = ""; win.liveBoardsOpen = false }
                        }
                        Text { visible: nameField.text === ""; anchors.fill: parent; anchors.leftMargin: 8
                               verticalAlignment: Text.AlignVCenter; text: "이름 입력 또는 아래 용어로 추천"
                               color: cDim; font.family: uiFont; font.pixelSize: 15 }
                    }
                    Text { text: "용어를 눌러 이름 추천 (다시 누르면 새 제안)"; color: cDim
                           font.family: uiFont; font.pixelSize: 13 }
                    Flow {
                        width: parent.width; spacing: 6
                        Repeater {
                            model: editor.boardTerms
                            Rectangle {
                                height: 26; width: termTxt.width + 16; radius: 13
                                color: "#1b2230"; border.width: 1; border.color: cBorder
                                Text { id: termTxt; anchors.centerIn: parent; text: modelData
                                       color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 14 }
                                MouseArea { anchors.fill: parent; onClicked: nameField.text = editor.suggestName(modelData) }
                            }
                        }
                    }
                    Row {
                        anchors.right: parent.right; spacing: 8
                        WideBtn { label: "취소"; accent: cBorder; onTap: win.namingMode = "" }
                        WideBtn { label: "저장"; accent: cGreen; dim: nameField.text.trim().length === 0
                                  onTap: if (nameField.text.trim().length) { editor.saveBoardNamed(nameField.text); win.namingMode = ""; win.liveBoardsOpen = false } }
                    }
                }
            }
        }

        // -------- LIVE board switcher (overlay, M6a) --------
        // Lists the host's pedalboards; tapping 전환 routes through
        // editor.requestLiveBoardSwitch (no-op on current, dirty-confirm gated).
        // Read-only switcher — no save/delete/new here (live save = M6b).
        Item {
            visible: win.liveBoardsOpen; anchors.fill: parent; z: 72
            MouseArea { anchors.fill: parent; onClicked: win.liveBoardsOpen = false }
            Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.55 }
            Rectangle {
                width: 478; height: 408; radius: 10; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBorder
                MouseArea { anchors.fill: parent }   // swallow clicks
                Column {
                    anchors.fill: parent; anchors.margins: 14; spacing: 10
                    Item {
                        width: parent.width; height: 24
                        Text { text: "보드 전환 (라이브)"; color: cText; font.family: uiFont; font.pixelSize: 18
                               anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: "✕"; color: cMuted; font.pixelSize: 18
                               anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                               MouseArea { anchors.fill: parent; onClicked: win.liveBoardsOpen = false } }
                    }
                    // save actions for the live (current) board
                    Flow {
                        width: parent.width; spacing: 8
                        WideBtn { label: editor.dirty ? "저장 *" : "저장"; accent: cGreen
                                  dim: !(editor.dirty || !editor.boardSaved)
                                  onTap: win.doSave() }
                        WideBtn { label: "다른 이름으로 저장"; accent: cGreen
                                  onTap: win.namingMode = "saveas" }
                    }
                    Text { text: "호스트 보드 (" + editor.liveBoardList.length + ")  ·  현재 편집 미저장 시 전환 전 확인"
                           color: cDim; font.family: uiFont; font.pixelSize: 13 }
                    Flickable {
                        width: parent.width; height: 268; contentHeight: liveCol.height; clip: true
                        Column {
                            id: liveCol; width: parent.width; spacing: 6
                            Repeater {
                                model: editor.liveBoardList
                                Rectangle {
                                    width: liveCol.width; height: 44; radius: 5
                                    color: modelData.current ? cElev : "#161b26"
                                    border.width: 1; border.color: modelData.current ? cBlue : cBorder
                                    Row {
                                        anchors.fill: parent; anchors.margins: 8; spacing: 8
                                        Text {
                                            width: parent.width - 96; anchors.verticalCenter: parent.verticalCenter
                                            text: (modelData.current ? "● " : "") + modelData.title
                                            color: modelData.current ? cBlue : cText
                                            font.family: uiFont; font.pixelSize: 15; elide: Text.ElideRight
                                        }
                                        Pill { label: modelData.current ? "현재" : "전환"
                                               accent: modelData.current ? cBorder : cBlue
                                               dim: modelData.current
                                               // clean switch -> boardSwitched closes the overlay;
                                               // dirty -> confirmBoardSwitch raises the dialog (stays open).
                                               onTap: if (!modelData.current)
                                                          editor.requestLiveBoardSwitch(modelData.bundle, modelData.title) }
                                    }
                                }
                            }
                            Text { visible: editor.liveBoardList.length === 0
                                   text: "호스트 보드 목록 없음"; color: cDim
                                   font.family: uiFont; font.pixelSize: 14; topPadding: 18 }
                        }
                    }
                }
            }
        }

        // -------- LIVE switch discard-confirm (unsaved live edits) --------
        Item {
            visible: win.pendingSwitchBundle !== ""; anchors.fill: parent; z: 82
            MouseArea { anchors.fill: parent; onClicked: win.pendingSwitchBundle = "" }
            Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.6 }
            Rectangle {
                width: 388; height: 168; radius: 10; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cOrange
                MouseArea { anchors.fill: parent }
                Column {
                    anchors.fill: parent; anchors.margins: 16; spacing: 12
                    Text { text: "미저장 변경을 폐기할까요?"; color: cText; font.family: uiFont; font.pixelSize: 18 }
                    Text {
                        width: parent.width; wrapMode: Text.WordWrap
                        text: "저장하지 않은 라이브 편집이 사라지고 '" + win.pendingSwitchTitle + "'(으)로 전환합니다."
                        color: cMuted; font.family: uiFont; font.pixelSize: 14
                    }
                    Row {
                        anchors.right: parent.right; spacing: 8
                        WideBtn { label: "취소"; accent: cBorder; onTap: win.pendingSwitchBundle = "" }
                        WideBtn { label: "폐기하고 전환"; accent: cOrange
                                  // clear the dialog; the overlay closes via onBoardSwitched on success
                                  // (a failed switch keeps the overlay + shows a failure toast).
                                  onTap: { editor.confirmedLiveBoardSwitch(win.pendingSwitchBundle)
                                           win.pendingSwitchBundle = "" } }
                    }
                }
            }
        }

        // -------- LIVE snapshot manager (overlay, M6c) --------
        // Snapshots = param/bypass/preset presets within the current board.
        // Tap a row to load; 저장 overwrites current (also persists the board);
        // 새로 저장 opens the naming panel.
        Item {
            visible: win.snapsOpen; anchors.fill: parent; z: 73
            MouseArea { anchors.fill: parent; onClicked: win.snapsOpen = false }
            Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.55 }
            Rectangle {
                width: 478; height: 408; radius: 10; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBorder
                MouseArea { anchors.fill: parent }
                Column {
                    anchors.fill: parent; anchors.margins: 14; spacing: 10
                    Item {
                        width: parent.width; height: 24
                        Text { text: "스냅샷"; color: cText; font.family: uiFont; font.pixelSize: 18
                               anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: "✕"; color: cMuted; font.pixelSize: 18
                               anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                               MouseArea { anchors.fill: parent; onClicked: win.snapsOpen = false } }
                    }
                    Flow {
                        width: parent.width; spacing: 8
                        WideBtn { label: editor.dirty ? "현재 스냅샷 저장 *" : "현재 스냅샷 저장"; accent: cPurple
                                  onTap: editor.saveSnapshot() }
                        WideBtn { label: "새 스냅샷으로 저장"; accent: cPurple
                                  onTap: win.snapNaming = true }
                    }
                    Text { text: "스냅샷 (" + editor.snapList.length + ")  ·  탭하면 그 세팅으로 전환"
                           color: cDim; font.family: uiFont; font.pixelSize: 13 }
                    Flickable {
                        width: parent.width; height: 268; contentHeight: snapCol.height; clip: true
                        Column {
                            id: snapCol; width: parent.width; spacing: 6
                            Repeater {
                                model: editor.snapList
                                Rectangle {
                                    width: snapCol.width; height: 44; radius: 5
                                    color: modelData.current ? cElev : "#161b26"
                                    border.width: 1; border.color: modelData.current ? cPurple : cBorder
                                    Row {
                                        anchors.fill: parent; anchors.margins: 8; spacing: 8
                                        Text {
                                            width: parent.width - 96; anchors.verticalCenter: parent.verticalCenter
                                            text: (modelData.current ? "● " : "") + modelData.name
                                            color: modelData.current ? cPurple : cText
                                            font.family: uiFont; font.pixelSize: 15; elide: Text.ElideRight
                                        }
                                        Pill { label: modelData.current ? "현재" : "전환"
                                               accent: modelData.current ? cBorder : cPurple
                                               dim: modelData.current
                                               onTap: if (!modelData.current) editor.selectSnapshot(modelData.idx) }
                                    }
                                }
                            }
                            Text { visible: editor.snapList.length === 0
                                   text: "스냅샷 없음"; color: cDim
                                   font.family: uiFont; font.pixelSize: 14; topPadding: 18 }
                        }
                    }
                }
            }
        }

        // -------- snapshot save-as naming panel (M6c) --------
        Item {
            visible: win.snapNaming; anchors.fill: parent; z: 83
            onVisibleChanged: if (visible) snapNameField.text = ""
            MouseArea { anchors.fill: parent; onClicked: win.snapNaming = false }
            Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.6 }
            Rectangle {
                width: 460; height: 300; radius: 10; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cPurple
                MouseArea { anchors.fill: parent }
                Column {
                    anchors.fill: parent; anchors.margins: 16; spacing: 12
                    Text { text: "새 스냅샷 이름"; color: cText; font.family: uiFont; font.pixelSize: 18 }
                    Rectangle {
                        width: parent.width; height: 40; radius: 6; color: cElev; border.width: 1; border.color: cBorder
                        TextInput {
                            id: snapNameField; anchors.fill: parent; anchors.leftMargin: 8
                            verticalAlignment: Text.AlignVCenter; color: cText
                            font.family: uiFont; font.pixelSize: 16; clip: true
                            onAccepted: if (text.trim().length) { editor.saveSnapshotNamed(text); win.snapNaming = false; win.snapsOpen = false }
                        }
                        Text { visible: snapNameField.text === ""; anchors.fill: parent; anchors.leftMargin: 8
                               verticalAlignment: Text.AlignVCenter; text: "이름 입력 또는 아래 용어로 추천"
                               color: cDim; font.family: uiFont; font.pixelSize: 15 }
                    }
                    Flow {
                        width: parent.width; spacing: 6
                        Repeater {
                            model: editor.boardTerms
                            Rectangle {
                                height: 26; width: stTxt.width + 16; radius: 13
                                color: "#1b2230"; border.width: 1; border.color: cBorder
                                Text { id: stTxt; anchors.centerIn: parent; text: modelData
                                       color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 14 }
                                MouseArea { anchors.fill: parent; onClicked: snapNameField.text = editor.suggestSnapshotName(modelData) }
                            }
                        }
                    }
                    Row {
                        anchors.right: parent.right; spacing: 8
                        WideBtn { label: "취소"; accent: cBorder; onTap: win.snapNaming = false }
                        WideBtn { label: "저장"; accent: cPurple; dim: snapNameField.text.trim().length === 0
                                  onTap: if (snapNameField.text.trim().length) { editor.saveSnapshotNamed(snapNameField.text); win.snapNaming = false; win.snapsOpen = false } }
                    }
                }
            }
        }

        // -------- NEW BOARD modal (live, M6d): quick / advanced --------
        // Loads the empty default bundle as a scratch board (SAVE forced to
        // save-as). The kind picks the initial editor mode for the empty board.
        Item {
            visible: win.newBoardOpen; anchors.fill: parent; z: 84
            MouseArea { anchors.fill: parent; onClicked: win.newBoardOpen = false }
            Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.6 }
            Rectangle {
                width: 440; height: 196; radius: 10; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBlue
                MouseArea { anchors.fill: parent }
                Column {
                    anchors.fill: parent; anchors.margins: 16; spacing: 12
                    Text { text: "새 보드"; color: cText; font.family: uiFont; font.pixelSize: 18 }
                    Text { width: parent.width; wrapMode: Text.WordWrap
                           text: "빈 보드에서 시작합니다. 저장 시 이름을 정해 새 보드로 저장돼요(기존 보드 안전). 퀵=직렬 빌드, 어드밴스드=자유 그래프."
                           color: cMuted; font.family: uiFont; font.pixelSize: 14 }
                    Row {
                        anchors.right: parent.right; spacing: 8
                        WideBtn { label: "취소"; accent: cBorder; onTap: win.newBoardOpen = false }
                        WideBtn { label: "퀵"; accent: cGreen
                                  onTap: { win.newBoardOpen = false; editor.requestNewLiveBoard("quick") } }
                        WideBtn { label: "어드밴스드"; accent: cOrange
                                  onTap: { win.newBoardOpen = false; editor.requestNewLiveBoard("advanced") } }
                    }
                }
            }
        }

        // mode-transition FX (scan-rectify) — a particle overlay over the board,
        // driven by editor.modeFlash(dir). → ADVANCED: a warm scan bar sweeps L→R
        // charging the board (energetic). → QUICK: a cool scan bar combs top→down,
        // raking scattered particles into a single rectified line (calm). The motion
        // alone carries the "powerful vs smart" feel — no on-screen text, no sound.
        // Ported from the 'Mode Transition Lab' design (concept B); board-local
        // coords match the Lab's 734×446 board, so the sim numbers transfer 1:1.
        Canvas {
            id: modeFx
            x: canvas.x; y: canvas.y; width: canvas.width; height: canvas.height
            z: 200; clip: true; visible: running
            property bool running: false
            property bool adv: true        // direction: true = QUICK→ADVANCED
            property real dms: 900         // total duration (ms)
            property int steps: 54         // discrete sim steps (≈ dms / 16.67)
            property int simStep: -1
            property real elapsed: 0
            property var parts: []
            property var rng: null
            readonly property var hot:  ["#fff4e0", "#ffd49a", "#ff9a4e", "#e8694a"]
            readonly property var cool: ["#eafff5", "#bdf0d8", "#8fe0bd", "#5fd0a0"]

            // small deterministic LCG so the scatter looks the same each run (no Math.imul dep)
            function _mk(seed) { var a = seed >>> 0; return function () { a = (a * 1664525 + 1013904223) >>> 0; return a / 4294967296; }; }
            function _smooth(a, b, t) { if (t <= a) return 0; if (t >= b) return 1; var x = (t - a) / (b - a); return x * x * (3 - 2 * x); }
            function _easeIn(x) { return x * x; }
            function _rgba(hex, al) { var n = parseInt(hex.slice(1), 16); return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + al + ")"; }

            function start(dir) {
                adv = (dir === "advanced");
                dms = adv ? 900 : 1150;
                steps = Math.max(1, Math.round(dms / 16.667));
                rng = _mk((66 * 131 + (adv ? 7 : 23)) >>> 0);   // 'B' concept seed
                parts = []; simStep = -1; elapsed = 0;
                running = true; ticker.restart(); requestPaint();
            }

            function _onStep(step, t) {
                var R = rng, W = width, H = height, MID = height / 2;
                var pick = function (a) { return a[(R() * a.length) | 0]; };
                var add = function (p) { if (parts.length < 2200) parts.push(p); };
                if (adv) {
                    // warm sprays kicked up ahead of the L→R scan bar
                    var sx = W * _easeIn(Math.min(1, t / 0.72));
                    if (t < 0.72) for (var i = 0; i < 8; i++)
                        add({ x: sx + (R() - .5) * 8, y: R() * H, vx: 2 + R() * 5, vy: -(R() * 9) * (R() < .5 ? 1 : .3),
                              life: 16 + R() * 20, max: 36, s: 2 + R() * 2, col: pick(hot), drag: .95, grav: .12 });
                } else {
                    // seed a cool cloud once, then the top→down scan captures each particle
                    // and rakes it to its 40px column on the centre line
                    if (step < 2) for (var j = 0; j < 105; j++) {
                        var x = R() * W, y = R() * H;
                        add({ x: x, y: y, vx: (R() - .5) * 2.5, vy: (R() - .5) * 2.5, life: steps + 30, max: steps + 30,
                              s: 2 + R() * 1.5, col: pick(cool), drag: .92, slot: Math.round(x / 40) * 40 });
                    }
                    var sy = H * _smooth(0, 1, Math.min(1, t / 0.75)), kk = 0.012 + 0.06 * _smooth(.1, .85, t);
                    for (var m = 0; m < parts.length; m++) {
                        var p = parts[m];
                        if (p.y < sy + 6 || p.captured) {
                            p.captured = true; p.attract = true;
                            p.tx = Math.max(12, Math.min(W - 12, p.slot)); p.ty = MID; p.k = kk;
                        }
                    }
                }
            }
            function _updateParts() {
                for (var i = parts.length - 1; i >= 0; i--) {
                    var p = parts[i];
                    if (p.attract) { var dx = p.tx - p.x, dy = p.ty - p.y; p.vx = (p.vx + dx * p.k) * p.drag; p.vy = (p.vy + dy * p.k) * p.drag; }
                    else { p.vx *= p.drag; p.vy += (p.grav || 0); }
                    p.x += p.vx; p.y += p.vy; p.life--;
                    if (p.life <= 0) parts.splice(i, 1);
                }
            }
            function _simTo(step) { while (simStep < step) { simStep++; _onStep(simStep, simStep / steps); _updateParts(); } }

            onPaint: {
                var ctx = getContext("2d"), W = width, H = height;
                ctx.clearRect(0, 0, W, H);
                var t = Math.min(1, elapsed / dms);
                // --- back layer ---
                if (adv) {
                    var sxb = W * _easeIn(Math.min(1, t / 0.72));
                    ctx.fillStyle = "rgba(8,6,3,0.45)"; ctx.fillRect(sxb, 0, W - sxb, H);   // dim the un-charged side
                    var end = Math.max(0, (t - 0.78) / 0.22);
                    if (end > 0) { ctx.fillStyle = _rgba("#ff9a4e", 0.4 * (1 - end)); ctx.fillRect(0, 0, W, H); }
                }
                // --- particles (additive) ---
                ctx.save(); ctx.globalCompositeOperation = "lighter";
                for (var k = 0; k < parts.length; k++) {
                    var p = parts[k]; ctx.globalAlpha = Math.max(0, Math.min(1, p.life / p.max));
                    ctx.fillStyle = p.col; var s = p.s; ctx.fillRect(p.x - s / 2, p.y - s / 2, s, s);
                }
                ctx.restore();
                // --- front layer (scan bar) ---
                if (adv) {
                    var sxf = W * _easeIn(Math.min(1, t / 0.72));
                    if (t < 0.74) {
                        ctx.save(); ctx.globalCompositeOperation = "lighter"; ctx.strokeStyle = _rgba("#ffd49a", 0.85);
                        ctx.shadowColor = "#ff9a4e"; ctx.shadowBlur = 16; ctx.lineWidth = 3;
                        ctx.beginPath(); ctx.moveTo(sxf, 0); ctx.lineTo(sxf, H); ctx.stroke(); ctx.restore();
                    }
                } else {
                    var sy = H * _smooth(0, 1, Math.min(1, t / 0.75));
                    if (t < 0.8) {
                        ctx.save(); ctx.globalCompositeOperation = "lighter"; ctx.strokeStyle = _rgba("#8fe0bd", 0.8);
                        ctx.shadowColor = "#5fd0a0"; ctx.shadowBlur = 10; ctx.lineWidth = 2;
                        ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(W, sy); ctx.stroke();
                        for (var gx = 20; gx < W; gx += 40) { ctx.beginPath(); ctx.moveTo(gx, sy); ctx.lineTo(gx, sy + 9); ctx.stroke(); }
                        ctx.restore();
                    }
                    var va = 0.16 * _smooth(.5, .9, t);
                    if (va > 0) {
                        var g = ctx.createRadialGradient(W / 2, H / 2, H * 0.22, W / 2, H / 2, W * 0.62);
                        g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, _rgba("#5fd0a0", va));
                        ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
                    }
                }
            }

            Timer {
                id: ticker; interval: 16; repeat: true; running: false
                onTriggered: {
                    modeFx.elapsed += 16;
                    var t = Math.min(1, modeFx.elapsed / modeFx.dms);
                    modeFx._simTo(Math.round(t * modeFx.steps));
                    modeFx.requestPaint();
                    if (t >= 1) { stop(); modeFx.running = false; modeFx.parts = []; }
                }
            }
        }
    }

    // patch file picker (shared PatchPicker.qml) — opened from an inspector patch
    // chip; lists/loads via the editor bridge (selected live node). Top z overlay.
    PatchPicker {
        id: editPatchPicker
        colElev: cElev; colBorder: cBorder; colText: cText; colAccent: cGreen; fontFamily: uiFont
        property string pUri: ""
        onPicked: (path) => editor.setPatch(pUri, path)
        function openFor(uri, label, current) {
            pUri = uri;
            present(editor.patchFiles(uri), label, current);
        }
    }

    // --- small reusable controls ---
    component Pill: Rectangle {
        property string label: ""
        property color accent: cBorder
        property bool dim: false
        signal tap()
        height: 22; width: pillTxt.width + 16; radius: 5
        color: "transparent"; border.width: 1; border.color: dim ? "#1b2230" : accent
        anchors.verticalCenter: parent.verticalCenter
        Text { id: pillTxt; anchors.centerIn: parent; text: label; color: dim ? "#3a4252" : "#cfe0ff"
               font.family: uiFont; font.pixelSize: 13 }
        MouseArea { anchors.fill: parent; onClicked: parent.tap() }
    }

    component WideBtn: Rectangle {
        property string label: ""
        property color accent: cBlue
        property bool dim: false
        signal tap()
        height: 32; width: wbTxt.width + 24; radius: 6
        color: "#161b26"; border.width: 1; border.color: dim ? "#1b2230" : accent
        opacity: dim ? 0.45 : 1.0
        Text { id: wbTxt; anchors.centerIn: parent; text: label; color: dim ? cDim : cText
               font.family: uiFont; font.pixelSize: 14 }
        MouseArea { anchors.fill: parent; onClicked: parent.tap() }
    }

    component LegendDot: Row {
        property color c: "#3b6fe0"
        property string t: ""
        spacing: 5
        Rectangle { width: 9; height: 9; radius: 4.5; color: c; anchors.verticalCenter: parent.verticalCenter }
        Text { text: t; color: cMuted; font.family: uiFont; font.pixelSize: 12 }
    }
}
