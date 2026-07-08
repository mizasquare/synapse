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
    readonly property color cPurple: "#b58af0"   // tuner accent (design rules §6)
    readonly property color cAmber:  "#d99a4e"   // tuner: slightly off pitch
    readonly property color cRed:    "#e6402e"   // tuner: far off pitch

    // dev: quit a true-fullscreen instance (no title bar to close) — mirrors the editor
    Shortcut { sequences: ["Ctrl+Q"]; context: Qt.ApplicationShortcut; onActivated: Qt.quit() }

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

    // =========================================================== BOOTING (splash)
    // Shown while qt_main waits for the MODEP host to start answering (cold boot).
    // The presenter/overview are only built once the host is ready, so this avoids
    // a blank/broken first paint. `view.screen` flips to "overview" then.
    Item {
        id: bootingScreen
        anchors.fill: parent
        visible: view.screen === "booting"

        Column {
            anchors.centerIn: parent
            spacing: 20

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "SYNAPSE"
                color: cText
                font.family: uiFont
                font.pixelSize: 56
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "MODEP 대기 중…"
                color: cMuted
                font.family: uiFont
                font.pixelSize: 30
                // Pulse while the splash is up; stops when hidden (no idle work).
                SequentialAnimation on opacity {
                    running: bootingScreen.visible
                    loops: Animation.Infinite
                    NumberAnimation { from: 1.0; to: 0.25; duration: 750; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 0.25; to: 1.0; duration: 750; easing.type: Easing.InOutSine }
                }
            }
        }
    }

    // =========================================================== OVERVIEW
    Item {
        id: overviewScreen
        objectName: "overviewScreen"
        anchors.fill: parent
        visible: view.screen === "overview"
        property bool boardsOpen: false   // board-manager overlay
        property bool snapsOpen: false    // snapshot-browser overlay
        property bool bankMgrOpen: false  // bank-manager overlay (create/edit banks)
        property bool hubOpen: false      // settings / system hub overlay
        property string hubLeaf: "menu"   // hub content: "menu" | "config" | "banks" | "system"
        property bool sysConfirm: false   // system: an action is armed, awaiting 2nd tap
        property string sysAction: ""     // "shutdown" | "reboot"

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
                width: 500
            }
            Column {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.topMargin: 4
                spacing: 6
                Text {
                    anchors.right: parent.right
                    text: "◆ " + view.snapshotLabel
                    color: cMuted
                    font.family: uiFont
                    font.pixelSize: 40
                }
                Text {
                    anchors.right: parent.right
                    text: view.modeLabel
                    color: cGreen
                    font.family: uiFont
                    font.pixelSize: 20
                }
                // snapshot save / pedalboard edit actions
                Row {
                    anchors.right: parent.right
                    spacing: 6
                    Rectangle {
                        width: 92; height: 38; radius: 8
                        color: "#162033"; border.width: 1; border.color: "#3b6fe0"
                        Text { anchors.centerIn: parent; text: "BOARDS"; color: "#9cc2ff"; font.family: uiFont; font.pixelSize: 19 }
                        MouseArea { anchors.fill: parent
                                    onClicked: { view.refreshBoards(); overviewScreen.boardsOpen = true } }
                    }
                    Rectangle {
                        width: 66; height: 38; radius: 8
                        color: "#241b2e"; border.width: 1; border.color: "#54407a"
                        Text { anchors.centerIn: parent; text: "SNAP"; color: "#cdb6f0"; font.family: uiFont; font.pixelSize: 19 }
                        MouseArea { anchors.fill: parent
                                    onClicked: { view.refreshSnaps(); overviewScreen.snapsOpen = true } }
                    }
                    Rectangle {
                        width: 70; height: 38; radius: 8
                        color: "#162033"; border.width: 1; border.color: "#3b6fe0"
                        Text { anchors.centerIn: parent; text: "BANK"; color: "#9cc2ff"; font.family: uiFont; font.pixelSize: 19 }
                        MouseArea { anchors.fill: parent
                                    onClicked: { view.refreshBanks(); overviewScreen.bankMgrOpen = true } }
                    }
                    Rectangle {
                        width: 72; height: 38; radius: 8
                        color: "#1b2230"; border.width: 1; border.color: cBorder
                        Text { anchors.centerIn: parent; text: "SAVE"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 19 }
                        MouseArea { anchors.fill: parent; onClicked: view.saveSnapshot() }
                    }
                    Rectangle {
                        width: 98; height: 38; radius: 8
                        color: "#1b2230"; border.width: 1; border.color: cBorder
                        Text { anchors.centerIn: parent; text: "SAVE AS"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 19 }
                        MouseArea { anchors.fill: parent; onClicked: saveAsModal.open = true }
                    }
                    Rectangle {
                        width: 66; height: 38; radius: 8
                        color: "#241b2e"; border.width: 1; border.color: "#54407a"
                        Text { anchors.centerIn: parent; text: "EDIT"; color: "#cdb6f0"; font.family: uiFont; font.pixelSize: 19 }
                        MouseArea { anchors.fill: parent; onClicked: view.enterEdit() }
                    }
                    Rectangle {
                        width: 66; height: 38; radius: 8
                        color: "#1b2230"; border.width: 1; border.color: cBorder
                        Text { anchors.centerIn: parent; text: "MENU"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 19 }
                        MouseArea { anchors.fill: parent; onClicked: { overviewScreen.hubLeaf = "menu"; overviewScreen.hubOpen = true } }
                    }
                }
            }
        }

        Rectangle {
            id: hr
            x: 12; y: header.y + header.height
            width: parent.width - 24; height: 2
            color: "#232b3a"
        }

        // -- Routing graph (snake-grid, vertical-scroll) --
        // Width 776 MUST match qtview._GW — cable PathSvg coords are precomputed in
        // that pixel space on the Python side. Height is dynamic: view.graphHeight
        // (= rows * row-height) drives contentHeight; the viewport is capped so it
        // never overlaps the legend / footswitch strip below.
        Flickable {
            id: graph
            x: 12; y: hr.y + 10
            width: 776
            height: Math.min(view.graphHeight, 236)
            contentWidth: 776
            contentHeight: view.graphHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Rectangle { width: 776; height: view.graphHeight; color: cGraph; radius: 10 }

            Repeater {
                model: view.cables
                Shape {
                    anchors.fill: parent
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

                    // IN/OUT nodes double as live level meters: the app taps JACK
                    // directly (levelmeter.py) and pushes via view.levelUpdated.
                    // Fill rises from the bottom (live peak, since last frame); a
                    // thin tick marks the 5s window peak (its dB shows as the sub).
                    Item {
                        id: ioMeter
                        anchors.fill: parent
                        anchors.margins: 4
                        visible: modelData.isIo
                        property real liveNorm: 0
                        property real peakNorm: 0
                        property string dbText: ""
                        Connections {
                            target: view
                            function onLevelUpdated(p) {
                                if (modelData.id === "IN") {
                                    ioMeter.liveNorm = p.inNorm; ioMeter.peakNorm = p.inPeak; ioMeter.dbText = p.inDb
                                } else if (modelData.id === "OUT") {
                                    ioMeter.liveNorm = p.outNorm; ioMeter.peakNorm = p.outPeak; ioMeter.dbText = p.outDb
                                }
                            }
                        }
                        Rectangle {        // live level fill
                            anchors.left: parent.left; anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            radius: 6
                            height: parent.height * Math.max(0, Math.min(1, ioMeter.liveNorm))
                            color: ioMeter.liveNorm > 0.92 ? "#e6724a" : cGreen
                            opacity: 0.22
                            Behavior on height { NumberAnimation { duration: 80 } }
                        }
                        Rectangle {        // 5s peak-hold tick
                            anchors.left: parent.left; anchors.right: parent.right
                            height: 2; color: cGreen
                            visible: ioMeter.peakNorm > 0.001
                            y: (parent.height - 2) * (1 - Math.max(0, Math.min(1, ioMeter.peakNorm)))
                        }
                    }

                    Column {
                        z: 1
                        anchors.centerIn: parent
                        width: parent.width - 14
                        spacing: 1
                        Text {
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            text: modelData.label
                            color: modelData.isIo ? cGreen : cText
                            font.family: uiFont
                            // model-based effects (NAM/IR) get a bigger name line;
                            // clamp it to one row so name+file always fit the box.
                            font.pixelSize: modelData.isIo ? 22
                                          : (modelData.kind === "model" ? 24 : 20)
                            wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                            maximumLineCount: modelData.kind === "model" ? 1 : 2
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            visible: text !== ""
                            // IN/OUT nodes show their live 5s-peak dB once audio flows,
                            // else the static role label (GUITAR / STEREO). Model-based
                            // effects show the loaded file name (category fallback).
                            text: (modelData.isIo && ioMeter.dbText !== "") ? ioMeter.dbText
                                  : (modelData.kind === "model" && modelData.model !== "") ? modelData.model
                                  : modelData.sub
                            color: "#6f8a82"
                            font.family: uiFont
                            font.pixelSize: 13
                            maximumLineCount: 1
                            elide: Text.ElideRight
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
        // -------- board manager (overlay) --------
        Item {
            visible: overviewScreen.boardsOpen; anchors.fill: parent; z: 90
            MouseArea { anchors.fill: parent; onClicked: overviewScreen.boardsOpen = false }
            Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.6 }
            Rectangle {
                width: 560; height: 420; radius: 12; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBorder
                MouseArea { anchors.fill: parent }   // swallow clicks (don't close on panel tap)
                Column {
                    anchors.fill: parent; anchors.margins: 18; spacing: 12
                    Item {
                        width: parent.width; height: 30
                        Text { text: "보드 전환"; color: cText; font.family: uiFont; font.pixelSize: 24
                               anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: "✕"; color: cMuted; font.pixelSize: 24
                               anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                               MouseArea { anchors.fill: parent; onClicked: overviewScreen.boardsOpen = false } }
                    }
                    Text { text: "호스트 보드 (" + view.boardList.length + ")"; color: cDim
                           font.family: uiFont; font.pixelSize: 16 }
                    Flickable {
                        width: parent.width; height: 324; contentHeight: bcol.height; clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        Column {
                            id: bcol; width: parent.width; spacing: 7
                            Repeater {
                                model: view.boardList
                                Rectangle {
                                    width: bcol.width; height: 50; radius: 7
                                    color: modelData.current ? cElev : "#161b26"
                                    border.width: 1; border.color: modelData.current ? "#3b6fe0" : cBorder
                                    Row {
                                        anchors.fill: parent; anchors.margins: 10; spacing: 10
                                        Text {
                                            width: parent.width - 198; anchors.verticalCenter: parent.verticalCenter
                                            text: (modelData.current ? "● " : "") + modelData.title
                                            color: modelData.current ? "#9cc2ff" : cText
                                            font.family: uiFont; font.pixelSize: 19; elide: Text.ElideRight
                                        }
                                        // 위/아래: reorder the saved display order (footswitch NAVIGATE
                                        // steps through the same order) — bank-manager button style
                                        Row {
                                            spacing: 4; anchors.verticalCenter: parent.verticalCenter
                                            Rectangle { width: 34; height: 28; radius: 5; color: "#1b2230"; border.width: 1; border.color: cBorder
                                                opacity: index === 0 ? 0.35 : 1.0
                                                Text { anchors.centerIn: parent; text: "위"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 15 }
                                                MouseArea { anchors.fill: parent; enabled: index > 0
                                                            onClicked: view.moveBoardOrder(modelData.bundle, -1) } }
                                            Rectangle { width: 40; height: 28; radius: 5; color: "#1b2230"; border.width: 1; border.color: cBorder
                                                opacity: index === view.boardList.length - 1 ? 0.35 : 1.0
                                                Text { anchors.centerIn: parent; text: "아래"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 15 }
                                                MouseArea { anchors.fill: parent; enabled: index < view.boardList.length - 1
                                                            onClicked: view.moveBoardOrder(modelData.bundle, 1) } }
                                        }
                                        Rectangle {
                                            width: 84; height: 34; radius: 7; anchors.verticalCenter: parent.verticalCenter
                                            color: modelData.current ? "transparent" : "#162033"
                                            border.width: 1; border.color: modelData.current ? cBorder : "#3b6fe0"
                                            Text { anchors.centerIn: parent; text: modelData.current ? "현재" : "전환"
                                                   color: modelData.current ? cMuted : "#9cc2ff"; font.family: uiFont; font.pixelSize: 17 }
                                            MouseArea { anchors.fill: parent; enabled: !modelData.current
                                                        onClicked: { view.switchBoard(modelData.bundle); overviewScreen.boardsOpen = false } }
                                        }
                                    }
                                }
                            }
                            Text { visible: view.boardList.length === 0
                                   text: "호스트 보드 목록 없음"; color: cDim
                                   font.family: uiFont; font.pixelSize: 17; topPadding: 20 }
                        }
                    }
                }
            }
        }

        // -------- snapshot browser (overlay) --------
        // Board-manager clone: same dim + centered panel, rows from view.snapList,
        // "전환" loads the snapshot via view.selectSnapshot (header ◆ label follows).
        Item {
            visible: overviewScreen.snapsOpen; anchors.fill: parent; z: 90
            MouseArea { anchors.fill: parent; onClicked: overviewScreen.snapsOpen = false }
            Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.6 }
            Rectangle {
                width: 560; height: 420; radius: 12; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBorder
                MouseArea { anchors.fill: parent }   // swallow clicks (don't close on panel tap)
                Column {
                    anchors.fill: parent; anchors.margins: 18; spacing: 12
                    Item {
                        width: parent.width; height: 30
                        Text { text: "스냅샷"; color: cText; font.family: uiFont; font.pixelSize: 24
                               anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: "✕"; color: cMuted; font.pixelSize: 24
                               anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                               MouseArea { anchors.fill: parent; onClicked: overviewScreen.snapsOpen = false } }
                    }
                    Text { text: "보드 스냅샷 (" + view.snapList.length + ")"; color: cDim
                           font.family: uiFont; font.pixelSize: 16 }
                    Flickable {
                        width: parent.width; height: 324; contentHeight: scol.height; clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        Column {
                            id: scol; width: parent.width; spacing: 7
                            Repeater {
                                model: view.snapList
                                Rectangle {
                                    width: scol.width; height: 50; radius: 7
                                    color: modelData.current ? cElev : "#161b26"
                                    border.width: 1; border.color: modelData.current ? "#54407a" : cBorder
                                    Row {
                                        anchors.fill: parent; anchors.margins: 10; spacing: 10
                                        Text {
                                            width: parent.width - 110; anchors.verticalCenter: parent.verticalCenter
                                            text: (modelData.current ? "◆ " : "") + modelData.idx + " · " + modelData.name
                                            color: modelData.current ? cPurple : cText
                                            font.family: uiFont; font.pixelSize: 19; elide: Text.ElideRight
                                        }
                                        Rectangle {
                                            width: 84; height: 34; radius: 7; anchors.verticalCenter: parent.verticalCenter
                                            color: modelData.current ? "transparent" : "#241b2e"
                                            border.width: 1; border.color: modelData.current ? cBorder : "#54407a"
                                            Text { anchors.centerIn: parent; text: modelData.current ? "현재" : "전환"
                                                   color: modelData.current ? cMuted : "#cdb6f0"; font.family: uiFont; font.pixelSize: 17 }
                                            MouseArea { anchors.fill: parent; enabled: !modelData.current
                                                        onClicked: { view.selectSnapshot(modelData.idx); overviewScreen.snapsOpen = false } }
                                        }
                                    }
                                }
                            }
                            Text { visible: view.snapList.length === 0
                                   text: "스냅샷 없음"; color: cDim
                                   font.family: uiFont; font.pixelSize: 17; topPadding: 20 }
                        }
                    }
                }
            }
        }

        // -------- bank manager (overlay) --------
        // Left pane lists banks (+ new bank); right pane edits the selected bank's
        // board order (= mode-2 FS A/B/C/D), adds/removes boards, sets it active,
        // renames, deletes. Every edit POSTs the whole bank list via the bridge.
        Item {
            id: bankMgr
            visible: overviewScreen.bankMgrOpen; anchors.fill: parent; z: 92
            property int sel: 0
            property int delArmed: -1   // bank idx armed for 2-tap delete
            property var selBank: (sel >= 0 && sel < view.bankList.length) ? view.bankList[sel] : null
            function close() { overviewScreen.bankMgrOpen = false; delArmed = -1; bankName.open = false }

            MouseArea { anchors.fill: parent; onClicked: bankMgr.close() }
            Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.6 }

            Rectangle {
                width: 776; height: 460; radius: 12; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBorder
                MouseArea { anchors.fill: parent }   // swallow clicks

                Item {
                    id: bmHeader
                    anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
                    anchors.margins: 16; height: 30
                    Text { text: "뱅크 매니저"; color: cText; font.family: uiFont; font.pixelSize: 24
                           anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: "✕"; color: cMuted; font.pixelSize: 24
                           anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                           MouseArea { anchors.fill: parent; onClicked: bankMgr.close() } }
                }

                Row {
                    anchors.top: bmHeader.bottom; anchors.topMargin: 12
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.bottom: parent.bottom; anchors.leftMargin: 16
                    anchors.rightMargin: 16; anchors.bottomMargin: 16
                    spacing: 14

                    // ---- left: bank list ----
                    Rectangle {
                        width: 250; height: parent.height; radius: 8
                        color: "#10141d"; border.width: 1; border.color: cBorder
                        Column {
                            anchors.fill: parent; anchors.margins: 10; spacing: 8
                            Rectangle {
                                width: parent.width; height: 40; radius: 6
                                color: "#162033"; border.width: 1; border.color: "#3b6fe0"
                                Text { anchors.centerIn: parent; text: "+ 새 뱅크"; color: "#9cc2ff"; font.family: uiFont; font.pixelSize: 19 }
                                MouseArea { anchors.fill: parent
                                    onClicked: { bankName.target = -1; bankName.open = true;
                                                 nameInput.text = view.suggestDateName(); nameInput.forceActiveFocus() } }
                            }
                            ListView {
                                width: parent.width; height: parent.height - 48
                                clip: true; spacing: 6; model: view.bankList
                                delegate: Rectangle {
                                    width: ListView.view.width; height: 56; radius: 6
                                    color: index === bankMgr.sel ? "#1d2433" : "#161b26"
                                    border.width: 1; border.color: index === bankMgr.sel ? cGreen : cBorder
                                    Column {
                                        anchors.left: parent.left; anchors.leftMargin: 10
                                        anchors.right: parent.right; anchors.rightMargin: 8
                                        anchors.verticalCenter: parent.verticalCenter; spacing: 2
                                        Text { text: (modelData.active ? "● " : "") + modelData.title
                                               color: modelData.active ? cGreen : cText; font.family: uiFont; font.pixelSize: 19
                                               elide: Text.ElideRight; width: parent.width }
                                        Text { text: modelData.pedalboards.length + "개 보드"; color: cDim; font.family: uiFont; font.pixelSize: 14 }
                                    }
                                    MouseArea { anchors.fill: parent; onClicked: { bankMgr.sel = index; bankMgr.delArmed = -1 } }
                                }
                            }
                        }
                    }

                    // ---- right: selected bank detail ----
                    Rectangle {
                        width: parent.width - 264; height: parent.height; radius: 8
                        color: "#10141d"; border.width: 1; border.color: cBorder

                        Text { visible: bankMgr.selBank === null; anchors.centerIn: parent
                               text: "왼쪽에서 뱅크를 고르거나\n+ 새 뱅크로 만드세요."
                               horizontalAlignment: Text.AlignHCenter
                               color: cDim; font.family: uiFont; font.pixelSize: 18 }

                        Column {
                            visible: bankMgr.selBank !== null
                            anchors.fill: parent; anchors.margins: 12; spacing: 9

                            // title + actions
                            Item {
                                width: parent.width; height: 32
                                Text { text: bankMgr.selBank ? bankMgr.selBank.title : ""
                                       color: cText; font.family: uiFont; font.pixelSize: 22
                                       anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                                       elide: Text.ElideRight; width: 180 }
                                Row {
                                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                                    Rectangle {
                                        width: 56; height: 30; radius: 6
                                        visible: bankMgr.selBank && !bankMgr.selBank.active
                                        color: "#13241c"; border.width: 1; border.color: cGreen
                                        Text { anchors.centerIn: parent; text: "활성"; color: cGreen; font.family: uiFont; font.pixelSize: 17 }
                                        MouseArea { anchors.fill: parent; onClicked: view.setActiveBank(bankMgr.sel) }
                                    }
                                    Text { visible: bankMgr.selBank && bankMgr.selBank.active
                                           text: "● 활성"; color: cGreen; font.family: uiFont; font.pixelSize: 16
                                           anchors.verticalCenter: parent.verticalCenter }
                                    Rectangle {
                                        width: 56; height: 30; radius: 6
                                        color: "#1b2230"; border.width: 1; border.color: cBorder
                                        Text { anchors.centerIn: parent; text: "이름"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 17 }
                                        MouseArea { anchors.fill: parent
                                            onClicked: { bankName.target = bankMgr.sel; bankName.open = true;
                                                         nameInput.text = bankMgr.selBank.title; nameInput.forceActiveFocus() } }
                                    }
                                    Rectangle {
                                        // The last bank can't be deleted (mode-2 needs one); dim it.
                                        property bool canDel: view.bankList.length > 1
                                        width: 70; height: 30; radius: 6
                                        opacity: canDel ? 1.0 : 0.4
                                        color: "#2a1416"; border.width: 1; border.color: "#7a3b3b"
                                        Text { anchors.centerIn: parent
                                               text: bankMgr.delArmed === bankMgr.sel ? "정말?" : "삭제"
                                               color: "#ffb3b3"; font.family: uiFont; font.pixelSize: 17 }
                                        MouseArea { anchors.fill: parent
                                            onClicked: {
                                                if (!parent.canDel) return;
                                                if (bankMgr.delArmed === bankMgr.sel) {
                                                    view.deleteBank(bankMgr.sel); bankMgr.delArmed = -1;
                                                    if (bankMgr.sel >= view.bankList.length) bankMgr.sel = Math.max(0, view.bankList.length - 1);
                                                } else { bankMgr.delArmed = bankMgr.sel }
                                            } }
                                    }
                                }
                            }

                            Text { text: "이 뱅크의 보드 — 순서 = 풋스위치 A·B·C·D (앞 4개)"; color: cDim; font.family: uiFont; font.pixelSize: 14 }

                            ListView {
                                width: parent.width; height: 116; clip: true; spacing: 5
                                model: bankMgr.selBank ? bankMgr.selBank.pedalboards : []
                                delegate: Rectangle {
                                    width: ListView.view.width; height: 38; radius: 6
                                    color: index < 4 ? "#161f2b" : "#141821"
                                    border.width: 1; border.color: cBorder
                                    Text { text: (index < 4 ? ["A","B","C","D"][index] + "  " : "") + modelData.title
                                           color: index < 4 ? cText : cMuted; font.family: uiFont; font.pixelSize: 17
                                           anchors.left: parent.left; anchors.leftMargin: 10
                                           anchors.verticalCenter: parent.verticalCenter
                                           elide: Text.ElideRight; width: parent.width - 130 }
                                    Row {
                                        anchors.right: parent.right; anchors.rightMargin: 8
                                        anchors.verticalCenter: parent.verticalCenter; spacing: 4
                                        Rectangle { width: 34; height: 28; radius: 5; color: "#1b2230"; border.width: 1; border.color: cBorder
                                            Text { anchors.centerIn: parent; text: "위"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 15 }
                                            MouseArea { anchors.fill: parent; onClicked: view.bankMoveBoard(bankMgr.sel, index, -1) } }
                                        Rectangle { width: 40; height: 28; radius: 5; color: "#1b2230"; border.width: 1; border.color: cBorder
                                            Text { anchors.centerIn: parent; text: "아래"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 15 }
                                            MouseArea { anchors.fill: parent; onClicked: view.bankMoveBoard(bankMgr.sel, index, 1) } }
                                        Rectangle { width: 30; height: 28; radius: 5; color: "#241b2e"; border.width: 1; border.color: cBorder
                                            Text { anchors.centerIn: parent; text: "✕"; color: "#ffb3b3"; font.pixelSize: 16 }
                                            MouseArea { anchors.fill: parent; onClicked: view.bankRemoveBoard(bankMgr.sel, index) } }
                                    }
                                }
                            }

                            Text { text: "보드 추가 — 호스트 보드 (" + view.boardCatalog.length + ")"; color: cDim; font.family: uiFont; font.pixelSize: 14 }

                            ListView {
                                width: parent.width; height: 126; clip: true; spacing: 5
                                model: view.boardCatalog
                                delegate: Rectangle {
                                    width: ListView.view.width; height: 36; radius: 6
                                    color: "#141821"; border.width: 1; border.color: cBorder
                                    Text { text: modelData.title; color: cText; font.family: uiFont; font.pixelSize: 17
                                           anchors.left: parent.left; anchors.leftMargin: 10
                                           anchors.verticalCenter: parent.verticalCenter
                                           elide: Text.ElideRight; width: parent.width - 60 }
                                    Rectangle {
                                        width: 40; height: 28; radius: 5
                                        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                                        color: "#162033"; border.width: 1; border.color: "#3b6fe0"
                                        Text { anchors.centerIn: parent; text: "+"; color: "#9cc2ff"; font.pixelSize: 20 }
                                        MouseArea { anchors.fill: parent; onClicked: view.bankAddBoard(bankMgr.sel, modelData.bundle) }
                                    }
                                }
                            }
                        }
                    }
                }

                // ---- naming sub-modal (create / rename) ----
                // Banks are edited at a desk with a real keyboard (wvkbd doesn't
                // come up on this device), so the field is just a plain TextInput:
                // a new bank defaults to the current date-time (setlist-by-date),
                // a rename prefills the bank's current title (non-destructive).
                Item {
                    id: bankName
                    anchors.fill: parent
                    property bool open: false
                    property int target: -1     // -1 = create new, >=0 = rename idx
                    visible: open
                    function commit() {
                        var t = nameInput.text.trim();
                        if (t.length) {
                            if (bankName.target < 0) {
                                view.createBank(t);
                                bankMgr.sel = view.bankList.length - 1;
                                bankMgr.delArmed = -1;
                            } else {
                                view.renameBank(bankName.target, t);
                            }
                        }
                        bankName.open = false;
                    }
                    Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.6
                                MouseArea { anchors.fill: parent; onClicked: bankName.open = false } }
                    Rectangle {
                        width: 520; height: 200; radius: 12; anchors.centerIn: parent
                        color: cPanel; border.width: 1; border.color: cBorder
                        MouseArea { anchors.fill: parent }
                        Column {
                            anchors.fill: parent; anchors.margins: 18; spacing: 14
                            Text { text: bankName.target < 0 ? "새 뱅크" : "뱅크 이름 변경"
                                   color: cText; font.family: uiFont; font.pixelSize: 22 }
                            Rectangle {
                                width: parent.width; height: 52; radius: 8; color: "#10212a"
                                border.width: 1; border.color: cGreen
                                TextInput {
                                    id: nameInput
                                    anchors.fill: parent; anchors.margins: 12
                                    verticalAlignment: TextInput.AlignVCenter
                                    color: cText; font.family: uiFont; font.pixelSize: 24; clip: true
                                    selectByMouse: true
                                    onAccepted: bankName.commit()
                                }
                            }
                            Row {
                                spacing: 10
                                Rectangle { width: 120; height: 44; radius: 8; color: "#13241c"; border.width: 1; border.color: cGreen
                                    Text { anchors.centerIn: parent; text: "저장"; color: cGreen; font.family: uiFont; font.pixelSize: 19 }
                                    MouseArea { anchors.fill: parent; onClicked: bankName.commit() } }
                                Rectangle { width: 110; height: 44; radius: 8; color: "#241b2e"; border.width: 1; border.color: cBorder
                                    Text { anchors.centerIn: parent; text: "취소"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 19 }
                                    MouseArea { anchors.fill: parent; onClicked: bankName.open = false } }
                            }
                        }
                    }
                }
            }
        }

        // -------- settings / system hub (overlay) --------
        Item {
            visible: overviewScreen.hubOpen; anchors.fill: parent; z: 95
            MouseArea { anchors.fill: parent
                        onClicked: { overviewScreen.hubOpen = false; overviewScreen.sysConfirm = false } }
            Rectangle { anchors.fill: parent; color: "#000000"; opacity: 0.6 }
            Rectangle {
                width: 560; height: 420; radius: 12; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBorder
                MouseArea { anchors.fill: parent }   // swallow clicks
                Column {
                    anchors.fill: parent; anchors.margins: 18; spacing: 14
                    // header (back + title + close)
                    Item {
                        width: parent.width; height: 30
                        Text { visible: overviewScreen.hubLeaf !== "menu"
                               text: "< 뒤로"; color: cMuted; font.family: uiFont; font.pixelSize: 20
                               anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                               MouseArea { anchors.fill: parent
                                           onClicked: { overviewScreen.hubLeaf = "menu"; overviewScreen.sysConfirm = false } } }
                        Text { text: overviewScreen.hubLeaf === "system" ? "시스템"
                                     : overviewScreen.hubLeaf === "config" ? "설정" : "설정 / 시스템"
                               color: cText; font.family: uiFont; font.pixelSize: 24
                               anchors.horizontalCenter: parent.horizontalCenter
                               anchors.verticalCenter: parent.verticalCenter }
                        Text { text: "✕"; color: cMuted; font.pixelSize: 24
                               anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                               MouseArea { anchors.fill: parent
                                           onClicked: { overviewScreen.hubOpen = false; overviewScreen.sysConfirm = false } } }
                    }
                    // ---- menu ----
                    Column {
                        visible: overviewScreen.hubLeaf === "menu"
                        width: parent.width; spacing: 10
                        Repeater {
                            model: [ {k:"config", t:"설정 (CONFIG)",   s:"마스터 볼륨 · 박자표"},
                                     {k:"system", t:"시스템 (SYSTEM)",  s:"안전 종료 · 재부팅"} ]
                            Rectangle {
                                width: parent.width; height: 64; radius: 8
                                color: "#161b26"; border.width: 1; border.color: cBorder
                                Column {
                                    anchors.left: parent.left; anchors.leftMargin: 14
                                    anchors.verticalCenter: parent.verticalCenter; spacing: 3
                                    Text { text: modelData.t; color: cText; font.family: uiFont; font.pixelSize: 20 }
                                    Text { text: modelData.s; color: cDim;  font.family: uiFont; font.pixelSize: 15 }
                                }
                                Text { text: ">"; color: cMuted; font.pixelSize: 24
                                       anchors.right: parent.right; anchors.rightMargin: 16
                                       anchors.verticalCenter: parent.verticalCenter }
                                MouseArea { anchors.fill: parent
                                            onClicked: { overviewScreen.hubLeaf = modelData.k; overviewScreen.sysConfirm = false } }
                            }
                        }
                    }
                    // ---- config ----
                    Column {
                        id: configLeaf
                        visible: overviewScreen.hubLeaf === "config"
                        width: parent.width; spacing: 16
                        property int  masterVol: 100
                        property bool volAvail: true
                        property int  bpbVal: 4
                        // seed from the live volume daemon + model whenever this leaf opens
                        onVisibleChanged: if (visible) {
                            var v = view.masterVolume();
                            volAvail = v >= 0;
                            masterVol = v >= 0 ? v : 0;
                            bpbVal = view.bpb();
                        }
                        // follow the daemon's applied-state echo (the reflex
                        // pedal or any controller may move the volume) — but
                        // never fight an active finger drag.
                        Connections {
                            target: view
                            function onMasterVolumeEchoed(p) {
                                if (!volDrag.pressed) configLeaf.masterVol = p;
                            }
                        }
                        // Throttle CC writes DURING a drag: leading edge fires
                        // immediately, then flush the latest value at most every
                        // interval while the finger keeps moving (repeat timer,
                        // stops itself when idle). restart()-per-move would instead
                        // defer everything until the finger paused — the bug we fix.
                        property bool volDirty: false
                        Timer { id: volApply; interval: 70; repeat: true; running: false
                                onTriggered: {
                                    if (configLeaf.volDirty) {
                                        view.setMasterVolume(configLeaf.masterVol);
                                        configLeaf.volDirty = false;
                                    } else {
                                        volApply.stop();
                                    }
                                } }
                        function applyVol() {
                            if (volApply.running) {
                                configLeaf.volDirty = true;             // coalesce within window
                            } else {
                                view.setMasterVolume(configLeaf.masterVol);  // leading edge
                                volApply.start();
                            }
                        }

                        // --- master volume (software) section ---
                        Text { text: "마스터 볼륨"
                               color: cText; font.family: uiFont; font.pixelSize: 20 }

                        // slider row (hand-rolled, house style) — hidden if gain stage unavailable
                        Row {
                            visible: configLeaf.volAvail
                            width: parent.width; spacing: 14
                            Rectangle {
                                id: volTrack
                                width: parent.width - 78; height: 16; radius: 8
                                anchors.verticalCenter: parent.verticalCenter
                                color: "#1b2230"; border.width: 1; border.color: cBorder
                                Rectangle {   // fill
                                    width: volTrack.width * configLeaf.masterVol / 100
                                    height: parent.height; radius: 8; color: cGreen
                                }
                                Rectangle {   // handle
                                    width: 24; height: 24; radius: 12; color: cText
                                    border.width: 2; border.color: cGreen
                                    y: (parent.height - height) / 2
                                    x: Math.max(0, Math.min(volTrack.width - width,
                                                volTrack.width * configLeaf.masterVol / 100 - width / 2))
                                }
                                MouseArea {
                                    id: volDrag
                                    anchors.fill: parent; preventStealing: true
                                    function setFromX(mx) {
                                        var p = Math.max(0, Math.min(1, mx / volTrack.width));
                                        configLeaf.masterVol = Math.round(p * 100);
                                        configLeaf.applyVol();
                                    }
                                    onPressed: setFromX(mouseX)
                                    onPositionChanged: setFromX(mouseX)
                                    onReleased: view.setMasterVolume(configLeaf.masterVol)
                                }
                            }
                            Text { text: configLeaf.masterVol + "%"
                                   width: 64; horizontalAlignment: Text.AlignRight
                                   anchors.verticalCenter: parent.verticalCenter
                                   color: cGreen; font.family: uiFont; font.pixelSize: 22 }
                        }
                        Text { visible: configLeaf.volAvail
                               text: "출력단 소프트웨어 게인(JACK)입니다. 100% = 유니티, 아래로 감쇠.\n보드의 물리 노브가 최종 아날로그 마스터입니다."
                               color: cDim; font.family: uiFont; font.pixelSize: 15
                               wrapMode: Text.WordWrap; width: parent.width }
                        Text { visible: !configLeaf.volAvail
                               text: "게인 스테이지를 찾을 수 없습니다 (synapse-mastervol 서비스 확인)."
                               color: cMuted; font.family: uiFont; font.pixelSize: 16
                               wrapMode: Text.WordWrap; width: parent.width }

                        // --- time signature (beats per bar) section ---
                        Text { text: "박자표 BEATS / BAR"
                               color: cText; font.family: uiFont; font.pixelSize: 20 }
                        Row {
                            spacing: 14
                            Rectangle {   // minus
                                width: 64; height: 48; radius: 8
                                color: "#1b2230"; border.width: 1; border.color: cBorder
                                Text { text: "−"; anchors.centerIn: parent
                                       color: configLeaf.bpbVal > 2 ? cText : cMuted
                                       font.family: uiFont; font.pixelSize: 30 }
                                MouseArea { anchors.fill: parent
                                            onClicked: if (configLeaf.bpbVal > 2) {
                                                configLeaf.bpbVal -= 1;
                                                view.setBpb(configLeaf.bpbVal);
                                            } }
                            }
                            Text { text: configLeaf.bpbVal
                                   width: 72; horizontalAlignment: Text.AlignHCenter
                                   anchors.verticalCenter: parent.verticalCenter
                                   color: cGreen; font.family: uiFont; font.pixelSize: 32 }
                            Rectangle {   // plus
                                width: 64; height: 48; radius: 8
                                color: "#1b2230"; border.width: 1; border.color: cBorder
                                Text { text: "＋"; anchors.centerIn: parent
                                       color: configLeaf.bpbVal < 12 ? cText : cMuted
                                       font.family: uiFont; font.pixelSize: 30 }
                                MouseArea { anchors.fill: parent
                                            onClicked: if (configLeaf.bpbVal < 12) {
                                                configLeaf.bpbVal += 1;
                                                view.setBpb(configLeaf.bpbVal);
                                            } }
                            }
                        }
                        Text { text: "탭 템포 메트로놈의 마디당 비트 수입니다 (2–12)."
                               color: cDim; font.family: uiFont; font.pixelSize: 15
                               wrapMode: Text.WordWrap; width: parent.width }
                    }
                    // ---- system (real: shutdown / reboot, 2-tap confirm) ----
                    Column {
                        visible: overviewScreen.hubLeaf === "system"
                        width: parent.width; spacing: 14
                        Text { text: "장치를 안전하게 종료/재부팅합니다.\n전원을 그냥 뽑으면 SD 카드가 손상될 수 있습니다."
                               color: cDim; font.family: uiFont; font.pixelSize: 16
                               wrapMode: Text.WordWrap; width: parent.width }
                        Row {
                            spacing: 14
                            Rectangle {
                                width: 220; height: 70; radius: 8
                                color: "#2a1416"; border.width: 1; border.color: "#7a3b3b"
                                Text { anchors.centerIn: parent
                                       text: (overviewScreen.sysConfirm && overviewScreen.sysAction === "shutdown") ? "정말 종료?" : "안전 종료"
                                       color: "#ffb3b3"; font.family: uiFont; font.pixelSize: 23 }
                                MouseArea { anchors.fill: parent
                                    onClicked: {
                                        if (overviewScreen.sysConfirm && overviewScreen.sysAction === "shutdown") view.systemShutdown();
                                        else { overviewScreen.sysAction = "shutdown"; overviewScreen.sysConfirm = true; }
                                    } }
                            }
                            Rectangle {
                                width: 220; height: 70; radius: 8
                                color: "#1b2230"; border.width: 1; border.color: cBorder
                                Text { anchors.centerIn: parent
                                       text: (overviewScreen.sysConfirm && overviewScreen.sysAction === "reboot") ? "정말 재부팅?" : "재부팅"
                                       color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 23 }
                                MouseArea { anchors.fill: parent
                                    onClicked: {
                                        if (overviewScreen.sysConfirm && overviewScreen.sysAction === "reboot") view.systemReboot();
                                        else { overviewScreen.sysAction = "reboot"; overviewScreen.sysConfirm = true; }
                                    } }
                            }
                        }
                        Text { visible: overviewScreen.sysConfirm
                               text: "한 번 더 누르면 실행됩니다. (취소: 패널 밖을 탭)"
                               color: cMuted; font.family: uiFont; font.pixelSize: 15 }
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
                spacing: 3
                Text {
                    text: focusScreen.f ? (focusScreen.f.name + "  ·  " + focusScreen.f.category) : ""
                    color: cText; font.family: uiFont; font.pixelSize: 28
                }
                // patch chips (NAM model / IR / cabsim) — tap to open the file picker
                Row {
                    spacing: 8
                    visible: !!(focusScreen.f && focusScreen.f.patches && focusScreen.f.patches.length > 0)
                    Repeater {
                        model: focusScreen.f ? focusScreen.f.patches : []
                        Rectangle {
                            height: 24; radius: 6; width: pchTxt.width + 18
                            color: "#1f5fd0a0"; border.width: 1; border.color: cGreen
                            Text {
                                id: pchTxt; anchors.centerIn: parent
                                text: "▦ " + modelData.label + ": " + (modelData.value || "—") + "  ▾"
                                color: cGreen; font.family: uiFont; font.pixelSize: 15
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: patchPicker.openFor(focusScreen.f.instance, modelData.uri,
                                                               modelData.label, modelData.value || "")
                            }
                        }
                    }
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

        // -- controls (one widget per port, by kind; single row, horizontal-scroll if many) --
        Rectangle {
            id: ctrlpanel
            x: 12; y: routing.y + routing.height + 10
            width: parent.width - 24; height: 150
            radius: 10; color: cPanel
            clip: true
            Flickable {
                id: ctrlflick
                anchors.fill: parent; anchors.margins: 8
                contentWidth: ctrlrow.width; contentHeight: height
                flickableDirection: Flickable.HorizontalFlick
                boundsBehavior: Flickable.StopAtBounds
                Row {
                    id: ctrlrow
                    height: ctrlflick.height
                    spacing: 6
                    Repeater {
                        model: focusScreen.f ? focusScreen.f.knobs : []
                        ControlWidget { m: modelData; instance: focusScreen.f ? focusScreen.f.instance : "" }
                    }
                }
            }
            Text {  // overflow hint
                visible: ctrlrow.width > ctrlflick.width
                anchors.right: parent.right; anchors.rightMargin: 10
                anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                text: "⟷ 스크롤"; color: cDim; font.family: uiFont; font.pixelSize: 14
            }
        }

        // -- monitors (output ports, read-only) --
        Rectangle {
            id: monpanel
            x: 12; y: ctrlpanel.y + ctrlpanel.height + 8
            width: parent.width - 24; height: 104
            radius: 10; color: cPanel
            Text {
                visible: monrow.children.length <= 1
                anchors.centerIn: parent; text: "모니터 없음"
                color: cDim; font.family: uiFont; font.pixelSize: 16
            }
            Row {
                id: monrow
                anchors.centerIn: parent; spacing: 18
                Repeater {
                    model: focusScreen.f ? focusScreen.f.monitors : []
                    MonitorWidget { m: modelData }
                }
            }
        }

        // -- patch file picker (shared PatchPicker.qml; NAM model / IR / cabsim) --
        // Opened from a patch chip; lists files via view.listPatchFiles, loads the
        // pick via view.setPatch. Drawn last = top z over the FOCUS screen.
        PatchPicker {
            id: patchPicker
            colElev: cElev; colBorder: cBorder; colText: cText; colAccent: cGreen; fontFamily: uiFont
            property string pInstance: ""
            property string pUri: ""
            onPicked: (path) => view.setPatch(pInstance, pUri, path)
            function openFor(instance, uri, label, current) {
                pInstance = instance; pUri = uri;
                present(view.listPatchFiles(instance, uri), label, current);
            }
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

    // ============================================================ TUNER
    // Guitar tuner (cochlea engine). B+C enters (presenter.enter_tuner); any
    // footswitch exits. view.tunerUpdated pushes readings ({} == listening).
    Item {
        id: tunerScreen
        anchors.fill: parent
        visible: view.screen === "tuner"

        property bool live: false
        property string note: "--"
        property real cents: 0
        property real freq: 0
        property string strg: ""
        property real conf: 0
        property bool inTune: false

        // in-tune -> green, slightly off -> amber, far off -> red, no signal -> dim.
        // A property binding (not a function) so it re-evaluates on cents/live change.
        readonly property color stateColor: !live ? cDim
            : (Math.abs(cents) < 3 ? cGreen : (Math.abs(cents) < 15 ? cAmber : cRed))

        Connections {
            target: view
            function onTunerUpdated(r) {
                if (!r || r.note === undefined) {
                    tunerScreen.live = false;
                } else {
                    tunerScreen.live = true;
                    tunerScreen.note = r.note;
                    tunerScreen.cents = r.cents;
                    tunerScreen.freq = r.freq;
                    tunerScreen.strg = r.string;
                    tunerScreen.conf = r.confidence;
                    tunerScreen.inTune = r.inTune;
                }
            }
        }

        // header
        Text {
            x: 16; y: 16; text: "TUNER"
            color: cPurple; font.family: uiFont; font.pixelSize: 44
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 16; y: 26
            text: "A 440"
            color: cMuted; font.family: uiFont; font.pixelSize: 28
        }

        // big note name
        Text {
            id: noteText
            anchors.horizontalCenter: parent.horizontalCenter
            y: 92
            text: tunerScreen.live ? tunerScreen.note : "--"
            color: tunerScreen.stateColor
            font.family: uiFont; font.pixelSize: 190
        }

        // cents readout
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: noteText.bottom; anchors.topMargin: -16
            text: tunerScreen.live
                  ? ((tunerScreen.cents >= 0 ? "+" : "") + tunerScreen.cents.toFixed(1) + "¢")
                  : ""
            color: tunerScreen.stateColor
            font.family: uiFont; font.pixelSize: 40
        }

        // deviation meter: a needle over a +/-50 cent scale
        Item {
            id: meter
            width: 640; height: 56
            anchors.horizontalCenter: parent.horizontalCenter
            y: 348
            Rectangle {                                   // baseline
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width; height: 3; color: cBorder
            }
            Rectangle {                                   // centre (in-tune) tick
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                width: 4; height: 40; color: cGreen
            }
            Repeater {                                    // +/-25, +/-50 ticks
                model: [-50, -25, 25, 50]
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    x: parent.width / 2 + (modelData / 50.0) * (parent.width / 2) - 1
                    width: 2; height: 22; color: cDim
                }
            }
            Rectangle {                                   // moving needle
                visible: tunerScreen.live
                width: 10; height: 50; radius: 3
                color: tunerScreen.stateColor
                anchors.verticalCenter: parent.verticalCenter
                x: parent.width / 2
                   + (Math.max(-50, Math.min(50, tunerScreen.cents)) / 50.0) * (parent.width / 2)
                   - width / 2
                Behavior on x { NumberAnimation { duration: 60 } }
            }
        }

        // nearest open string + measured frequency (or "listening")
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            y: 418
            text: tunerScreen.live
                  ? (tunerScreen.strg + "    " + tunerScreen.freq.toFixed(1) + " Hz")
                  : "듣는 중…"
            color: tunerScreen.live ? cText : cDim
            font.family: uiFont; font.pixelSize: 28
        }

        // footer
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom; anchors.bottomMargin: 12
            text: "종료: 풋스위치 아무거나"
            color: cDim; font.family: uiFont; font.pixelSize: 22
        }
    }

    // ====================================================== PEDALBOARD EDIT
    // The pedalboard editor, embedded from PedalboardEditorView.qml. Loaded by file URL
    // (its own context) and only while in EDIT — so it is created fresh on each entry
    // (re-seeding from the live board) and adds no idle cost elsewhere. Its own header
    // hosts the "나가기" affordance (exitRequested -> back to overview).
    Loader {
        id: editScreen
        anchors.fill: parent
        active: view.screen === "edit"
        visible: active
        source: "PedalboardEditorView.qml"
        // On each entry, seed the editor's advanced graph from the live board.
        onLoaded: editor.enterLive()
        Connections {
            target: editScreen.item
            function onExitRequested() { view.goOverview() }
        }
    }

    // ============================================ SAVE SNAPSHOT AS (modal)
    // 3+2 naming: tap a stage term -> "term-quirkysuffix" suggestion (re-tap to
    // re-roll), tap the suggestion to save. ✎ opens a HW-keyboard text field for a
    // fully custom name (the on-screen keyboard will later host the same field).
    Item {
        id: saveAsModal
        objectName: "saveAsModal"
        anchors.fill: parent
        property bool open: false
        property string suggestion: ""
        property bool typing: false
        visible: open

        function close() { open = false; suggestion = ""; typing = false; kb.text = ""; }

        // scrim: dim everything behind + tap-outside cancels
        Rectangle {
            anchors.fill: parent
            color: "#000000"; opacity: 0.62
            MouseArea { anchors.fill: parent; onClicked: saveAsModal.close() }
        }

        Rectangle {
            anchors.centerIn: parent
            width: 660; height: 424
            radius: 14; color: cPanel; border.width: 1; border.color: cBorder
            MouseArea { anchors.fill: parent }   // swallow clicks so they don't reach the scrim

            Column {
                anchors.fill: parent
                anchors.margins: 20
                spacing: 14

                Text { text: "스냅샷 다른 이름으로 저장"; color: cText; font.family: uiFont; font.pixelSize: 28 }

                // suggestion box: tap to save (or, when typing, a text field)
                Rectangle {
                    width: parent.width; height: 56; radius: 10
                    color: "#10212a"
                    border.width: 1
                    border.color: (saveAsModal.suggestion !== "" || saveAsModal.typing) ? cGreen : cBorder
                    Text {
                        visible: !saveAsModal.typing
                        anchors.centerIn: parent
                        text: saveAsModal.suggestion !== "" ? saveAsModal.suggestion : "아래 용어를 눌러 이름 제안 받기"
                        color: saveAsModal.suggestion !== "" ? cGreen : cDim
                        font.family: uiFont; font.pixelSize: 26
                    }
                    MouseArea {
                        anchors.fill: parent
                        visible: !saveAsModal.typing
                        enabled: saveAsModal.suggestion !== ""
                        onClicked: { view.saveSnapshotNamed(saveAsModal.suggestion); saveAsModal.close(); }
                    }
                    TextInput {
                        id: kb
                        visible: saveAsModal.typing
                        anchors.fill: parent; anchors.margins: 14
                        verticalAlignment: TextInput.AlignVCenter
                        color: cText; font.family: uiFont; font.pixelSize: 26; clip: true
                        onAccepted: if (text.trim().length) { view.saveSnapshotNamed(text); saveAsModal.close(); }
                    }
                }
                Text {
                    text: saveAsModal.typing ? "Enter로 저장"
                        : (saveAsModal.suggestion !== "" ? "↑ 이 이름을 누르면 저장 · 용어 다시 누르면 새 제안"
                                                         : "용어를 누르면 무작위 접미사가 붙은 제안이 떠요")
                    color: cDim; font.family: uiFont; font.pixelSize: 16
                }

                // stage-term grid (tap -> suggestion)
                Grid {
                    width: parent.width
                    columns: 4
                    rowSpacing: 8; columnSpacing: 8
                    Repeater {
                        model: view.snapshotTerms
                        Rectangle {
                            width: (660 - 40 - 8 * 3) / 4; height: 46; radius: 8
                            color: "#1b2230"; border.width: 1; border.color: cBorder
                            Text { anchors.centerIn: parent; text: modelData; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 20 }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: { saveAsModal.typing = false; saveAsModal.suggestion = view.suggestSnapshotName(modelData); }
                            }
                        }
                    }
                }

                // keyboard escape hatch + cancel
                Row {
                    spacing: 8
                    Rectangle {
                        width: 156; height: 44; radius: 8
                        color: saveAsModal.typing ? cGreen : "#1b2230"; border.width: 1; border.color: cBorder
                        Text { anchors.centerIn: parent; text: "✎ 직접입력"; color: saveAsModal.typing ? "#0e1118" : "#cfd6e2"; font.family: uiFont; font.pixelSize: 20 }
                        MouseArea { anchors.fill: parent; onClicked: { saveAsModal.typing = true; kb.forceActiveFocus(); } }
                    }
                    Rectangle {
                        width: 120; height: 44; radius: 8
                        color: "#241b2e"; border.width: 1; border.color: cBorder
                        Text { anchors.centerIn: parent; text: "취소"; color: "#cfd6e2"; font.family: uiFont; font.pixelSize: 20 }
                        MouseArea { anchors.fill: parent; onClicked: saveAsModal.close() }
                    }
                }
            }
        }
    }

    // ===================================================== TOAST (transient)
    // Presenter messages (e.g. "뱅크 없음 — STOMP 모드로"). Auto-hides. Top-most so
    // it floats over every screen + the SAVE AS modal.
    Rectangle {
        id: toast
        property string msg: ""
        visible: false
        anchors.horizontalCenter: parent.horizontalCenter
        y: 22
        width: toastText.implicitWidth + 44
        height: 52
        radius: 10
        color: "#1d2433"; border.width: 1; border.color: cGreen
        Text {
            id: toastText
            anchors.centerIn: parent
            text: toast.msg
            color: cText; font.family: uiFont; font.pixelSize: 22
        }
        Timer { id: toastTimer; interval: 2600; onTriggered: toast.visible = false }
        Connections {
            target: view
            function onToastRequested(text) { toast.msg = text; toast.visible = true; toastTimer.restart() }
        }
    }
}
