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
    color: Theme.color("bg.screen")

    // -- color tokens (design rules §6) — resolve from the shared Theme source
    //    (theme/tokens.json); alias names retained so cX call sites stay untouched.
    readonly property color cScreen: Theme.color("bg.screen")
    readonly property color cPanel:  Theme.color("surface.panel")
    readonly property color cGraph:  Theme.color("bg.graph")
    readonly property color cElev:   Theme.color("surface.elevated")
    readonly property color cBorder: Theme.color("border.default")
    readonly property color cGreen:  Theme.color("accent.green")
    readonly property color cText:   Theme.color("text.primary")
    readonly property color cMuted:  Theme.color("text.secondary")
    readonly property color cDim:    Theme.color("text.tertiary")
    readonly property color cPurple: Theme.color("accent.purple")   // tuner accent
    readonly property color cAmber:  Theme.color("accent.amber")    // tuner: slightly off pitch
    readonly property color cRed:    Theme.color("state.danger")    // tuner: far off pitch

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
                font: Theme.typeFont("displayLg")
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: Tr.tr("boot.waiting")
                color: cMuted
                font: Theme.typeFont("title")
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

        // -- Tier-1 glance header (~152px): title row over a control row --
        // Two rows so the board name owns the full width up top (long names were
        // squeezed to ~3 glyphs when it shared the row with the action buttons);
        // the buttons drop to their own row below, with live BPM on their left.
        Item {
            id: header
            x: 12; y: 6
            width: parent.width - 24
            height: 152

            // --- title row: board name (left) + snapshot/mode (right) ---
            Text {
                anchors.left: parent.left
                anchors.top: parent.top
                text: view.boardName
                color: cText
                font: Theme.typeFont("hero")   // ~96px glance @1.5m (board name)
                elide: Text.ElideRight
                // Now owns the whole top row; only the snapshot/mode column on the
                // right is subtracted (buttons moved to the control row below).
                width: parent.width - snapCol.width - 20
            }
            Column {
                id: snapCol
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.topMargin: 4
                spacing: 6
                width: 300
                Text {
                    anchors.right: parent.right
                    text: "◆ " + view.snapshotLabel
                    color: cMuted
                    font: Theme.typeFont("display")
                    // long snapshot names grew leftward over the board name
                    width: Math.min(implicitWidth, parent.width)
                    elide: Text.ElideRight
                }
                Text {
                    anchors.right: parent.right
                    text: view.modeLabel
                    color: cGreen
                    font: Theme.typeFont("heading")
                }
            }

            // --- control row: live BPM (left) + action buttons (right) ---
            Text {
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 9
                text: "BPM " + view.bpm
                color: cMuted
                font: Theme.typeFont("heading")
            }
            // snapshot save / pedalboard edit actions
            Row {
                id: headerBtnRow
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 2
                spacing: 6
                // pressed = brighter fill + border, so a touch is acked even
                // while the backend round-trip is still in flight
                Rectangle {
                        width: 92; height: 38; radius: 8
                        color: boardsMa.pressed ? Theme.color("btn.blue.fillPressed") : Theme.color("btn.blue.fill")
                        border.width: 1; border.color: boardsMa.pressed ? Theme.color("accent.blueBright") : Theme.color("accent.blue")
                        Text { anchors.centerIn: parent; text: Tr.tr("chrome.boards"); color: Theme.color("accent.blueBright"); font: Theme.typeFont("button") }
                        MouseArea { id: boardsMa; anchors.fill: parent
                                    onClicked: { view.refreshBoards(); overviewScreen.boardsOpen = true } }
                    }
                    Rectangle {
                        width: 66; height: 38; radius: 8
                        color: snapMa.pressed ? Theme.color("btn.purple.fillPressed") : Theme.color("btn.purple.fill")
                        border.width: 1; border.color: snapMa.pressed ? Theme.color("accent.purpleBright") : Theme.color("btn.purple.border")
                        Text { anchors.centerIn: parent; text: Tr.tr("chrome.snap"); color: Theme.color("accent.purpleBright"); font: Theme.typeFont("button") }
                        MouseArea { id: snapMa; anchors.fill: parent
                                    onClicked: { view.refreshSnaps(); overviewScreen.snapsOpen = true } }
                    }
                    Rectangle {
                        width: 70; height: 38; radius: 8
                        color: bankMa.pressed ? Theme.color("btn.blue.fillPressed") : Theme.color("btn.blue.fill")
                        border.width: 1; border.color: bankMa.pressed ? Theme.color("accent.blueBright") : Theme.color("accent.blue")
                        Text { anchors.centerIn: parent; text: Tr.tr("chrome.bank"); color: Theme.color("accent.blueBright"); font: Theme.typeFont("button") }
                        MouseArea { id: bankMa; anchors.fill: parent
                                    onClicked: { view.refreshBanks(); overviewScreen.bankMgrOpen = true } }
                    }
                    Rectangle {
                        width: 72; height: 38; radius: 8
                        color: saveMa.pressed ? Theme.color("btn.neutral.fillPressed") : Theme.color("surface.control")
                        border.width: 1; border.color: saveMa.pressed ? Theme.color("text.secondary") : cBorder
                        Text { anchors.centerIn: parent; text: Tr.tr("chrome.save"); color: Theme.color("text.onLight"); font: Theme.typeFont("button") }
                        MouseArea { id: saveMa; anchors.fill: parent; onClicked: view.saveSnapshot() }
                    }
                    Rectangle {
                        width: 98; height: 38; radius: 8
                        color: saveAsMa.pressed ? Theme.color("btn.neutral.fillPressed") : Theme.color("surface.control")
                        border.width: 1; border.color: saveAsMa.pressed ? Theme.color("text.secondary") : cBorder
                        Text { anchors.centerIn: parent; text: Tr.tr("chrome.saveAs"); color: Theme.color("text.onLight"); font: Theme.typeFont("button") }
                        MouseArea { id: saveAsMa; anchors.fill: parent; onClicked: saveAsModal.open = true }
                    }
                    Rectangle {
                        width: 66; height: 38; radius: 8
                        color: editMa.pressed ? Theme.color("btn.purple.fillPressed") : Theme.color("btn.purple.fill")
                        border.width: 1; border.color: editMa.pressed ? Theme.color("accent.purpleBright") : Theme.color("btn.purple.border")
                        Text { anchors.centerIn: parent; text: Tr.tr("chrome.edit"); color: Theme.color("accent.purpleBright"); font: Theme.typeFont("button") }
                        MouseArea { id: editMa; anchors.fill: parent; onClicked: view.enterEdit() }
                    }
                    Rectangle {
                        width: 66; height: 38; radius: 8
                        color: menuMa.pressed ? Theme.color("btn.neutral.fillPressed") : Theme.color("surface.control")
                        border.width: 1; border.color: menuMa.pressed ? Theme.color("text.secondary") : cBorder
                        Text { anchors.centerIn: parent; text: Tr.tr("chrome.menu"); color: Theme.color("text.onLight"); font: Theme.typeFont("button") }
                        MouseArea { id: menuMa; anchors.fill: parent; onClicked: { overviewScreen.hubLeaf = "menu"; overviewScreen.hubOpen = true } }
                    }
                }
        }

        Rectangle {
            id: hr
            x: 12; y: header.y + header.height
            width: parent.width - 24; height: 2
            color: Theme.color("border.divider")
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
            height: Math.min(view.graphHeight, 220)
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
                    // touch ack: brighten while the finger is down (backend follows later)
                    color: nodeMa.pressed ? Theme.color("node.pressed")
                         : modelData.isIo ? Theme.color("surface.inset")
                                          : (modelData.on ? Theme.color("surface.card") : Theme.color("surface.bypassed"))
                    border.width: modelData.isIo ? 1 : (modelData.selected || nodeMa.pressed ? 2 : 1)
                    border.color: nodeMa.pressed ? Theme.color("accent.blueBright")
                                : modelData.isIo ? Theme.color("border.io")
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
                            color: ioMeter.liveNorm > 0.92 ? Theme.color("accent.midi") : cGreen
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
                            // node names -> heading tier (was 20-24 by kind; per-kind
                            // emphasis flattened to one clean size — restore via role if wanted).
                            font: Theme.typeFont("heading")
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
                            color: Theme.color("text.onGraph")
                            font: Theme.typeFont("caption")
                            maximumLineCount: 1
                            elide: Text.ElideRight
                        }
                    }

                    // tap an effect node -> FOCUS (IO nodes are not interactive)
                    MouseArea {
                        id: nodeMa
                        anchors.fill: parent
                        enabled: !modelData.isIo
                        onClicked: view.selectNode(modelData.id)
                    }
                }
            }
        }

        // (status line dropped — BPM now lives in the header control row, and the
        // single-cable-color UI needs no legend; "tap node -> focus" is learned once)

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
                    id: fsCell
                    width: (strip.width - 8 * 3) / 4
                    height: 64
                    radius: 8
                    color: cPanel
                    // (dev Z/X/C/V keymap label dropped — PC-mock-only, meaningless on
                    // the panel; the keyboard shortcut itself still works for dev use)
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
                            // room left of the LED: cell - leftMargin(12) - led(15) - spacing(10) - pad(8)
                            width: fsCell.width - 45
                            Text {
                                text: modelData.label; color: Theme.color("text.onLight"); font: Theme.typeFont("heading")
                                width: Math.min(implicitWidth, parent.width)
                                elide: Text.ElideRight
                            }
                            Text { text: modelData.sub; color: modelData.led; font: Theme.typeFont("smallLabel") }
                        }
                    }
                }
            }
        }
        // -------- board manager (overlay) --------
        Item {
            visible: overviewScreen.boardsOpen; anchors.fill: parent; z: 90
            MouseArea { anchors.fill: parent; onClicked: overviewScreen.boardsOpen = false }
            Rectangle { anchors.fill: parent; color: Theme.color("overlay.scrim"); opacity: 0.6 }
            Rectangle {
                width: 560; height: 420; radius: 12; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBorder
                MouseArea { anchors.fill: parent }   // swallow clicks (don't close on panel tap)
                Column {
                    anchors.fill: parent; anchors.margins: 18; spacing: 12
                    Item {
                        width: parent.width; height: 30
                        Text { text: Tr.tr("boardSwitch.title"); color: cText; font: Theme.typeFont("overlayTitle")
                               anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: "✕"; color: cMuted; font.pixelSize: Theme.typeSize("heading")
                               anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                               MouseArea { anchors.fill: parent; onClicked: overviewScreen.boardsOpen = false } }
                    }
                    Text { text: Tr.trf("boardSwitch.hostBoards", [view.boardList.length]); color: cDim
                           font: Theme.typeFont("label") }
                    Flickable {
                        width: parent.width; height: 324; contentHeight: bcol.height; clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        Column {
                            id: bcol; width: parent.width; spacing: 7
                            Repeater {
                                model: view.boardList
                                Rectangle {
                                    width: bcol.width; height: 50; radius: 7
                                    color: modelData.current ? cElev : Theme.color("surface.card")
                                    border.width: 1; border.color: modelData.current ? Theme.color("accent.blue") : cBorder
                                    Row {
                                        anchors.fill: parent; anchors.margins: 10; spacing: 10
                                        Text {
                                            width: parent.width - 228; anchors.verticalCenter: parent.verticalCenter
                                            text: (modelData.current ? "● " : "") + modelData.title
                                            color: modelData.current ? Theme.color("accent.blueBright") : cText
                                            font: Theme.typeFont("body"); elide: Text.ElideRight
                                        }
                                        // 위/아래: reorder the saved display order (footswitch NAVIGATE
                                        // steps through the same order). Opposite actions side by side,
                                        // so touch rules apply: ≥48px-ish targets, ≥12px gap (a mistap
                                        // here silently rewires the live NAVIGATE order). Hit areas are
                                        // padded past the visuals to reach the full 50px row height.
                                        Row {
                                            spacing: 12; anchors.verticalCenter: parent.verticalCenter
                                            Rectangle { width: 48; height: 40; radius: 5; color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                                                opacity: index === 0 ? 0.35 : 1.0
                                                Text { anchors.centerIn: parent; text: Tr.tr("common.up"); color: Theme.color("text.onLight"); font: Theme.typeFont("smallLabel") }
                                                MouseArea { anchors.fill: parent; anchors.margins: -5; enabled: index > 0
                                                            onClicked: view.moveBoardOrder(modelData.bundle, -1) } }
                                            Rectangle { width: 48; height: 40; radius: 5; color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                                                opacity: index === view.boardList.length - 1 ? 0.35 : 1.0
                                                Text { anchors.centerIn: parent; text: Tr.tr("common.down"); color: Theme.color("text.onLight"); font: Theme.typeFont("smallLabel") }
                                                MouseArea { anchors.fill: parent; anchors.margins: -5; enabled: index < view.boardList.length - 1
                                                            onClicked: view.moveBoardOrder(modelData.bundle, 1) } }
                                        }
                                        Rectangle {
                                            width: 84; height: 34; radius: 7; anchors.verticalCenter: parent.verticalCenter
                                            color: modelData.current ? "transparent" : Theme.color("btn.blue.fill")
                                            border.width: 1; border.color: modelData.current ? cBorder : Theme.color("accent.blue")
                                            Text { anchors.centerIn: parent; text: modelData.current ? Tr.tr("common.current") : Tr.tr("common.switch")
                                                   color: modelData.current ? cMuted : Theme.color("accent.blueBright"); font: Theme.typeFont("body") }
                                            MouseArea { anchors.fill: parent; enabled: !modelData.current
                                                        onClicked: { view.switchBoard(modelData.bundle); overviewScreen.boardsOpen = false } }
                                        }
                                    }
                                }
                            }
                            Text { visible: view.boardList.length === 0
                                   text: Tr.tr("boardSwitch.empty"); color: cDim
                                   font: Theme.typeFont("body"); topPadding: 20 }
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
            Rectangle { anchors.fill: parent; color: Theme.color("overlay.scrim"); opacity: 0.6 }
            Rectangle {
                width: 560; height: 420; radius: 12; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBorder
                MouseArea { anchors.fill: parent }   // swallow clicks (don't close on panel tap)
                Column {
                    anchors.fill: parent; anchors.margins: 18; spacing: 12
                    Item {
                        width: parent.width; height: 30
                        Text { text: "스냅샷"; color: cText; font: Theme.typeFont("overlayTitle")
                               anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: "✕"; color: cMuted; font.pixelSize: Theme.typeSize("heading")
                               anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                               MouseArea { anchors.fill: parent; onClicked: overviewScreen.snapsOpen = false } }
                    }
                    Text { text: "보드 스냅샷 (" + view.snapList.length + ")"; color: cDim
                           font: Theme.typeFont("label") }
                    Flickable {
                        width: parent.width; height: 324; contentHeight: scol.height; clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        Column {
                            id: scol; width: parent.width; spacing: 7
                            Repeater {
                                model: view.snapList
                                Rectangle {
                                    width: scol.width; height: 50; radius: 7
                                    color: modelData.current ? cElev : Theme.color("surface.card")
                                    border.width: 1; border.color: modelData.current ? Theme.color("btn.purple.border") : cBorder
                                    Row {
                                        anchors.fill: parent; anchors.margins: 10; spacing: 10
                                        Text {
                                            width: parent.width - 110; anchors.verticalCenter: parent.verticalCenter
                                            text: (modelData.current ? "◆ " : "") + modelData.idx + " · " + modelData.name
                                            color: modelData.current ? cPurple : cText
                                            font: Theme.typeFont("body"); elide: Text.ElideRight
                                        }
                                        Rectangle {
                                            width: 84; height: 34; radius: 7; anchors.verticalCenter: parent.verticalCenter
                                            color: modelData.current ? "transparent" : Theme.color("btn.purple.fill")
                                            border.width: 1; border.color: modelData.current ? cBorder : Theme.color("btn.purple.border")
                                            Text { anchors.centerIn: parent; text: modelData.current ? Tr.tr("common.current") : Tr.tr("common.switch")
                                                   color: modelData.current ? cMuted : Theme.color("accent.purpleBright"); font: Theme.typeFont("body") }
                                            MouseArea { anchors.fill: parent; enabled: !modelData.current
                                                        onClicked: { view.selectSnapshot(modelData.idx); overviewScreen.snapsOpen = false } }
                                        }
                                    }
                                }
                            }
                            Text { visible: view.snapList.length === 0
                                   text: "스냅샷 없음"; color: cDim
                                   font: Theme.typeFont("body"); topPadding: 20 }
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
            Rectangle { anchors.fill: parent; color: Theme.color("overlay.scrim"); opacity: 0.6 }

            Rectangle {
                width: 776; height: 460; radius: 12; anchors.centerIn: parent
                color: cPanel; border.width: 1; border.color: cBorder
                MouseArea { anchors.fill: parent }   // swallow clicks

                Item {
                    id: bmHeader
                    anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right
                    anchors.margins: 16; height: 30
                    Text { text: Tr.tr("bank.manager"); color: cText; font: Theme.typeFont("overlayTitle")
                           anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: "✕"; color: cMuted; font.pixelSize: Theme.typeSize("heading")
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
                        color: Theme.color("bg.screen"); border.width: 1; border.color: cBorder
                        Column {
                            anchors.fill: parent; anchors.margins: 10; spacing: 8
                            Rectangle {
                                width: parent.width; height: 40; radius: 6
                                color: Theme.color("btn.blue.fill"); border.width: 1; border.color: Theme.color("accent.blue")
                                Text { anchors.centerIn: parent; text: Tr.tr("bank.new"); color: Theme.color("accent.blueBright"); font: Theme.typeFont("button") }
                                MouseArea { anchors.fill: parent
                                    onClicked: { bankName.target = -1; bankName.open = true;
                                                 nameInput.text = view.suggestDateName(); nameInput.forceActiveFocus() } }
                            }
                            ListView {
                                width: parent.width; height: parent.height - 48
                                clip: true; spacing: 6; model: view.bankList
                                delegate: Rectangle {
                                    width: ListView.view.width; height: 56; radius: 6
                                    color: index === bankMgr.sel ? Theme.color("surface.elevated") : Theme.color("surface.card")
                                    border.width: 1; border.color: index === bankMgr.sel ? cGreen : cBorder
                                    Column {
                                        anchors.left: parent.left; anchors.leftMargin: 10
                                        anchors.right: parent.right; anchors.rightMargin: 8
                                        anchors.verticalCenter: parent.verticalCenter; spacing: 2
                                        Text { text: (modelData.active ? "● " : "") + modelData.title
                                               color: modelData.active ? cGreen : cText; font: Theme.typeFont("body")
                                               elide: Text.ElideRight; width: parent.width }
                                        Text { text: Tr.trf("bank.boardCount", [modelData.pedalboards.length]); color: cDim; font: Theme.typeFont("caption") }
                                    }
                                    MouseArea { anchors.fill: parent; onClicked: { bankMgr.sel = index; bankMgr.delArmed = -1 } }
                                }
                            }
                        }
                    }

                    // ---- right: selected bank detail ----
                    Rectangle {
                        width: parent.width - 264; height: parent.height; radius: 8
                        color: Theme.color("bg.screen"); border.width: 1; border.color: cBorder

                        Text { visible: bankMgr.selBank === null; anchors.centerIn: parent
                               text: Tr.tr("bank.emptyHint")
                               horizontalAlignment: Text.AlignHCenter
                               color: cDim; font: Theme.typeFont("body") }

                        Column {
                            visible: bankMgr.selBank !== null
                            anchors.fill: parent; anchors.margins: 12; spacing: 9

                            // title + actions
                            Item {
                                width: parent.width; height: 32
                                Text { text: bankMgr.selBank ? bankMgr.selBank.title : ""
                                       color: cText; font: Theme.typeFont("heading")
                                       anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                                       elide: Text.ElideRight; width: 180 }
                                Row {
                                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 6
                                    Rectangle {
                                        width: 84; height: 30; radius: 6
                                        visible: bankMgr.selBank && !bankMgr.selBank.active
                                        color: Theme.color("btn.affirm.fill"); border.width: 1; border.color: cGreen
                                        Text { anchors.centerIn: parent; text: Tr.tr("bank.activate"); color: cGreen; font: Theme.typeFont("body") }
                                        MouseArea { anchors.fill: parent; onClicked: view.setActiveBank(bankMgr.sel) }
                                    }
                                    Text { visible: bankMgr.selBank && bankMgr.selBank.active
                                           text: "● " + Tr.tr("bank.active"); color: cGreen; font: Theme.typeFont("label")
                                           anchors.verticalCenter: parent.verticalCenter }
                                    Rectangle {
                                        width: 76; height: 30; radius: 6
                                        color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                                        Text { anchors.centerIn: parent; text: Tr.tr("bank.rename"); color: Theme.color("text.onLight"); font: Theme.typeFont("body") }
                                        MouseArea { anchors.fill: parent
                                            onClicked: { bankName.target = bankMgr.sel; bankName.open = true;
                                                         nameInput.text = bankMgr.selBank.title; nameInput.forceActiveFocus() } }
                                    }
                                    Rectangle {
                                        // The last bank can't be deleted (mode-2 needs one); dim it.
                                        property bool canDel: view.bankList.length > 1
                                        width: 70; height: 30; radius: 6
                                        opacity: canDel ? 1.0 : 0.4
                                        color: Theme.color("btn.danger.fill"); border.width: 1; border.color: Theme.color("btn.danger.border")
                                        Text { anchors.centerIn: parent
                                               text: bankMgr.delArmed === bankMgr.sel ? Tr.tr("common.confirm") : Tr.tr("common.delete")
                                               color: Theme.color("btn.danger.text"); font: Theme.typeFont("body") }
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

                            Text { text: Tr.tr("bank.boardsHint"); color: cDim; font: Theme.typeFont("caption") }

                            ListView {
                                width: parent.width; height: 116; clip: true; spacing: 5
                                model: bankMgr.selBank ? bankMgr.selBank.pedalboards : []
                                delegate: Rectangle {
                                    width: ListView.view.width; height: 38; radius: 6
                                    color: index < 4 ? Theme.color("surface.controlActive") : Theme.color("surface.controlAlt")
                                    border.width: 1; border.color: cBorder
                                    Text { text: (index < 4 ? ["A","B","C","D"][index] + "  " : "") + modelData.title
                                           color: index < 4 ? cText : cMuted; font: Theme.typeFont("body")
                                           anchors.left: parent.left; anchors.leftMargin: 10
                                           anchors.verticalCenter: parent.verticalCenter
                                           elide: Text.ElideRight; width: parent.width - 178 }
                                    // 위/아래/✕: opposite + destructive actions side by side — widen the
                                    // targets and gaps toward the 48px/12px touch rule (row is 38px, so
                                    // hit areas are padded to its full height with negative margins).
                                    Row {
                                        anchors.right: parent.right; anchors.rightMargin: 8
                                        anchors.verticalCenter: parent.verticalCenter; spacing: 12
                                        Rectangle { width: 48; height: 34; radius: 5; color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                                            Text { anchors.centerIn: parent; text: Tr.tr("common.up"); color: Theme.color("text.onLight"); font: Theme.typeFont("smallLabel") }
                                            MouseArea { anchors.fill: parent; anchors.margins: -4; onClicked: view.bankMoveBoard(bankMgr.sel, index, -1) } }
                                        Rectangle { width: 48; height: 34; radius: 5; color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                                            Text { anchors.centerIn: parent; text: Tr.tr("common.down"); color: Theme.color("text.onLight"); font: Theme.typeFont("smallLabel") }
                                            MouseArea { anchors.fill: parent; anchors.margins: -4; onClicked: view.bankMoveBoard(bankMgr.sel, index, 1) } }
                                        Rectangle { width: 40; height: 34; radius: 5; color: Theme.color("btn.purple.fill"); border.width: 1; border.color: cBorder
                                            Text { anchors.centerIn: parent; text: "✕"; color: Theme.color("btn.danger.text"); font.pixelSize: Theme.typeSize("label") }
                                            MouseArea { anchors.fill: parent; anchors.margins: -4; onClicked: view.bankRemoveBoard(bankMgr.sel, index) } }
                                    }
                                }
                            }

                            Text { text: Tr.trf("bank.addBoard", [view.boardCatalog.length]); color: cDim; font: Theme.typeFont("caption") }

                            ListView {
                                width: parent.width; height: 126; clip: true; spacing: 5
                                model: view.boardCatalog
                                delegate: Rectangle {
                                    width: ListView.view.width; height: 36; radius: 6
                                    color: Theme.color("surface.controlAlt"); border.width: 1; border.color: cBorder
                                    Text { text: modelData.title; color: cText; font: Theme.typeFont("body")
                                           anchors.left: parent.left; anchors.leftMargin: 10
                                           anchors.verticalCenter: parent.verticalCenter
                                           elide: Text.ElideRight; width: parent.width - 60 }
                                    Rectangle {
                                        width: 40; height: 28; radius: 5
                                        anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
                                        color: Theme.color("btn.blue.fill"); border.width: 1; border.color: Theme.color("accent.blue")
                                        Text { anchors.centerIn: parent; text: "+"; color: Theme.color("accent.blueBright"); font.pixelSize: Theme.typeSize("heading") }
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
                    Rectangle { anchors.fill: parent; color: Theme.color("overlay.scrim"); opacity: 0.6
                                MouseArea { anchors.fill: parent; onClicked: bankName.open = false } }
                    Rectangle {
                        width: 520; height: 200; radius: 12; anchors.centerIn: parent
                        color: cPanel; border.width: 1; border.color: cBorder
                        MouseArea { anchors.fill: parent }
                        Column {
                            anchors.fill: parent; anchors.margins: 18; spacing: 14
                            Text { text: bankName.target < 0 ? Tr.tr("bank.newTitle") : Tr.tr("bank.renameTitle")
                                   color: cText; font: Theme.typeFont("overlayTitle") }
                            Rectangle {
                                width: parent.width; height: 52; radius: 8; color: Theme.color("surface.inset")
                                border.width: 1; border.color: cGreen
                                TextInput {
                                    id: nameInput
                                    anchors.fill: parent; anchors.margins: 12
                                    verticalAlignment: TextInput.AlignVCenter
                                    color: cText; font: Theme.typeFont("heading"); clip: true
                                    selectByMouse: true
                                    onAccepted: bankName.commit()
                                }
                            }
                            Row {
                                spacing: 10
                                Rectangle { width: 120; height: 44; radius: 8; color: Theme.color("btn.affirm.fill"); border.width: 1; border.color: cGreen
                                    Text { anchors.centerIn: parent; text: Tr.tr("action.save"); color: cGreen; font: Theme.typeFont("button") }
                                    MouseArea { anchors.fill: parent; onClicked: bankName.commit() } }
                                Rectangle { width: 110; height: 44; radius: 8; color: Theme.color("btn.purple.fill"); border.width: 1; border.color: cBorder
                                    Text { anchors.centerIn: parent; text: Tr.tr("action.cancel"); color: Theme.color("text.onLight"); font: Theme.typeFont("button") }
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
            Rectangle { anchors.fill: parent; color: Theme.color("overlay.scrim"); opacity: 0.6 }
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
                               text: "< 뒤로"; color: cMuted; font: Theme.typeFont("button")
                               anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter
                               MouseArea { anchors.fill: parent
                                           onClicked: { overviewScreen.hubLeaf = "menu"; overviewScreen.sysConfirm = false } } }
                        Text { text: overviewScreen.hubLeaf === "system" ? "시스템"
                                     : overviewScreen.hubLeaf === "config" ? "설정" : "설정 / 시스템"
                               color: cText; font: Theme.typeFont("overlayTitle")
                               anchors.horizontalCenter: parent.horizontalCenter
                               anchors.verticalCenter: parent.verticalCenter }
                        Text { text: "✕"; color: cMuted; font.pixelSize: Theme.typeSize("heading")
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
                                color: Theme.color("surface.card"); border.width: 1; border.color: cBorder
                                Column {
                                    anchors.left: parent.left; anchors.leftMargin: 14
                                    anchors.verticalCenter: parent.verticalCenter; spacing: 3
                                    Text { text: modelData.t; color: cText; font: Theme.typeFont("heading") }
                                    Text { text: modelData.s; color: cDim;  font: Theme.typeFont("smallLabel") }
                                }
                                Text { text: ">"; color: cMuted; font.pixelSize: Theme.typeSize("heading")
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
                               color: cText; font: Theme.typeFont("heading") }

                        // slider row (hand-rolled, house style) — hidden if gain stage unavailable
                        Row {
                            visible: configLeaf.volAvail
                            width: parent.width; spacing: 14
                            Rectangle {
                                id: volTrack
                                width: parent.width - 78; height: 16; radius: 8
                                anchors.verticalCenter: parent.verticalCenter
                                color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
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
                                   color: cGreen; font: Theme.typeFont("heading") }
                        }
                        Text { visible: configLeaf.volAvail
                               text: "출력단 소프트웨어 게인(JACK)입니다. 100% = 유니티, 아래로 감쇠.\n보드의 물리 노브가 최종 아날로그 마스터입니다."
                               color: cDim; font: Theme.typeFont("smallLabel")
                               wrapMode: Text.WordWrap; width: parent.width }
                        Text { visible: !configLeaf.volAvail
                               text: "게인 스테이지를 찾을 수 없습니다 (synapse-mastervol 서비스 확인)."
                               color: cMuted; font: Theme.typeFont("label")
                               wrapMode: Text.WordWrap; width: parent.width }

                        // --- time signature (beats per bar) section ---
                        Text { text: "박자표 BEATS / BAR"
                               color: cText; font: Theme.typeFont("heading") }
                        Row {
                            spacing: 14
                            Rectangle {   // minus
                                width: 64; height: 48; radius: 8
                                color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                                Text { text: "−"; anchors.centerIn: parent
                                       color: configLeaf.bpbVal > 2 ? cText : cMuted
                                       font: Theme.typeFont("title") }
                                MouseArea { anchors.fill: parent
                                            onClicked: if (configLeaf.bpbVal > 2) {
                                                configLeaf.bpbVal -= 1;
                                                view.setBpb(configLeaf.bpbVal);
                                            } }
                            }
                            Text { text: configLeaf.bpbVal
                                   width: 72; horizontalAlignment: Text.AlignHCenter
                                   anchors.verticalCenter: parent.verticalCenter
                                   color: cGreen; font: Theme.typeFont("title") }
                            Rectangle {   // plus
                                width: 64; height: 48; radius: 8
                                color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                                Text { text: "＋"; anchors.centerIn: parent
                                       color: configLeaf.bpbVal < 12 ? cText : cMuted
                                       font: Theme.typeFont("title") }
                                MouseArea { anchors.fill: parent
                                            onClicked: if (configLeaf.bpbVal < 12) {
                                                configLeaf.bpbVal += 1;
                                                view.setBpb(configLeaf.bpbVal);
                                            } }
                            }
                        }
                        Text { text: "탭 템포 메트로놈의 마디당 비트 수입니다 (2–12)."
                               color: cDim; font: Theme.typeFont("smallLabel")
                               wrapMode: Text.WordWrap; width: parent.width }
                    }
                    // ---- system (real: shutdown / reboot, 2-tap confirm) ----
                    Column {
                        visible: overviewScreen.hubLeaf === "system"
                        width: parent.width; spacing: 14
                        Text { text: "장치를 안전하게 종료/재부팅합니다.\n전원을 그냥 뽑으면 SD 카드가 손상될 수 있습니다."
                               color: cDim; font: Theme.typeFont("label")
                               wrapMode: Text.WordWrap; width: parent.width }
                        Row {
                            spacing: 14
                            Rectangle {
                                width: 220; height: 70; radius: 8
                                color: Theme.color("btn.danger.fill"); border.width: 1; border.color: Theme.color("btn.danger.border")
                                Text { anchors.centerIn: parent
                                       text: (overviewScreen.sysConfirm && overviewScreen.sysAction === "shutdown") ? "정말 종료?" : "안전 종료"
                                       color: Theme.color("btn.danger.text"); font: Theme.typeFont("button") }
                                MouseArea { anchors.fill: parent
                                    onClicked: {
                                        if (overviewScreen.sysConfirm && overviewScreen.sysAction === "shutdown") view.systemShutdown();
                                        else { overviewScreen.sysAction = "shutdown"; overviewScreen.sysConfirm = true; }
                                    } }
                            }
                            Rectangle {
                                width: 220; height: 70; radius: 8
                                color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                                Text { anchors.centerIn: parent
                                       text: (overviewScreen.sysConfirm && overviewScreen.sysAction === "reboot") ? "정말 재부팅?" : "재부팅"
                                       color: Theme.color("text.onLight"); font: Theme.typeFont("button") }
                                MouseArea { anchors.fill: parent
                                    onClicked: {
                                        if (overviewScreen.sysConfirm && overviewScreen.sysAction === "reboot") view.systemReboot();
                                        else { overviewScreen.sysAction = "reboot"; overviewScreen.sysConfirm = true; }
                                    } }
                            }
                        }
                        Text { visible: overviewScreen.sysConfirm
                               text: "한 번 더 누르면 실행됩니다. (취소: 패널 밖을 탭)"
                               color: cMuted; font: Theme.typeFont("smallLabel") }
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
                color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                Text { anchors.centerIn: parent; text: "◄ OVERVIEW"; color: Theme.color("text.onLight"); font: Theme.typeFont("button") }
                MouseArea { anchors.fill: parent; onClicked: view.goOverview() }
            }
            Rectangle {
                width: 48; height: 44; radius: 8; color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                Text { anchors.centerIn: parent; text: "◄"; color: Theme.color("text.onLight"); font: Theme.typeFont("button") }
                MouseArea { anchors.fill: parent; onClicked: view.focusPrev() }
            }
            Rectangle {
                width: 48; height: 44; radius: 8; color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                Text { anchors.centerIn: parent; text: "►"; color: Theme.color("text.onLight"); font: Theme.typeFont("button") }
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
            color: on ? cGreen : Theme.color("border.default")
            Text {
                anchors.centerIn: parent
                text: parent.on ? "ENGAGED" : "BYPASS"
                color: parent.on ? Theme.color("bg.screen") : Theme.color("text.mutedAlt")
                font: Theme.typeFont("toggle")
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
                    color: cText; font: Theme.typeFont("title")
                    width: Math.min(implicitWidth, idcard.width - 32)
                    elide: Text.ElideRight
                }
                // patch chips (NAM model / IR / cabsim) — tap to open the file picker
                Row {
                    spacing: 8
                    visible: !!(focusScreen.f && focusScreen.f.patches && focusScreen.f.patches.length > 0)
                    Repeater {
                        model: focusScreen.f ? focusScreen.f.patches : []
                        Rectangle {
                            height: 24; radius: 6; width: pchTxt.width + 18
                            color: Theme.alpha("accent.green", 0.12); border.width: 1; border.color: cGreen
                            Text {
                                id: pchTxt; anchors.centerIn: parent
                                text: "▦ " + modelData.label + ": " + (modelData.value || "—") + "  ▾"
                                color: cGreen; font: Theme.typeFont("smallLabel")
                                // long IR paths filled the card; keep the filename end visible
                                width: Math.min(implicitWidth, idcard.width - 64)
                                elide: Text.ElideMiddle
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
                        Text { text: modelData.t; color: cGreen; font: Theme.typeFont("smallLabel") }
                        Text {
                            text: (modelData.list || []).join("   ")
                            color: cText; font: Theme.typeFont("heading")
                            // 3+ ports used to overflow the card (no clip on it either)
                            width: Math.min(implicitWidth, (routing.width - 10) / 2 - 28)
                            elide: Text.ElideRight
                        }
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
                text: "⟷ 스크롤"; color: cDim; font: Theme.typeFont("caption")
            }
        }

        // -- monitors (left, read-only) | FS assign (right) --
        // The monitor readout is unused by most plugins and the few that use it
        // aren't real-estate hungry, so the right half hosts the STOMP footswitch
        // assignment for the focused effect (tap A/B/C/D to pin/unpin).
        Rectangle {
            id: monpanel
            x: 12; y: ctrlpanel.y + ctrlpanel.height + 8
            width: parent.width - 24; height: 104
            radius: 10; color: cPanel

            // left half: monitors
            Item {
                id: monLeft
                anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom
                width: parent.width / 2
                Text {
                    visible: monrow.children.length <= 1
                    anchors.centerIn: parent; text: "모니터 없음"
                    color: cDim; font: Theme.typeFont("label")
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

            // divider
            Rectangle {
                width: 1; color: cBorder
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.top; anchors.bottom: parent.bottom
                anchors.topMargin: 12; anchors.bottomMargin: 12
            }

            // right half: STOMP footswitch assignment
            Column {
                anchors.left: parent.horizontalCenter; anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                Text {
                    text: "STOMP FS 배정"; color: cDim
                    font: Theme.typeFont("caption")
                    anchors.horizontalCenter: parent.horizontalCenter
                }
                Row {
                    anchors.horizontalCenter: parent.horizontalCenter
                    spacing: 8
                    Repeater {
                        model: 4
                        Rectangle {
                            width: 46; height: 40; radius: 8
                            property bool sel: !!(focusScreen.f && focusScreen.f.fsSlot === index)
                            color: sel ? cGreen : cElev
                            border.width: 1; border.color: sel ? cGreen : cBorder
                            Text {
                                anchors.centerIn: parent
                                text: ["A", "B", "C", "D"][index]
                                color: sel ? cGraph : cText
                                font: Theme.typeFont("heading")
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: if (focusScreen.f) view.assignFs(focusScreen.f.instance, index)
                            }
                        }
                    }
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
            color: cGreen; font: Theme.typeFont("display")
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 16; y: 26
            text: tapScreen.t && tapScreen.t.klass ? tapScreen.t.klass : ""
            color: cMuted; font: Theme.typeFont("title")
        }

        // big last-set BPM, centred
        Column {
            anchors.centerIn: parent
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: view.bpm
                color: cText; font: Theme.typeFont("heroNumeric")
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "BPM"
                color: cMuted; font: Theme.typeFont("display")
            }
        }

        // meter + how-to footer
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - 92
            text: (tapScreen.t && tapScreen.t.bpb ? tapScreen.t.bpb : 4) + " BEATS / BAR"
            color: cGreen; font: Theme.typeFont("title")
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom; anchors.bottomMargin: 16
            text: "탭: 풋스위치 아무거나  ·  종료: 콤보(2개 동시)"
            color: cDim; font: Theme.typeFont("heading")
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
            color: cPurple; font: Theme.typeFont("display")
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 16; y: 26
            text: "A 440"
            color: cMuted; font: Theme.typeFont("title")
        }

        // big note name
        Text {
            id: noteText
            anchors.horizontalCenter: parent.horizontalCenter
            y: 92
            text: tunerScreen.live ? tunerScreen.note : "--"
            color: tunerScreen.stateColor
            font: Theme.typeFont("heroNumeric")
        }

        // cents readout
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: noteText.bottom; anchors.topMargin: -16
            text: tunerScreen.live
                  ? ((tunerScreen.cents >= 0 ? "+" : "") + tunerScreen.cents.toFixed(1) + "¢")
                  : ""
            color: tunerScreen.stateColor
            font: Theme.typeFont("display")
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
            font: Theme.typeFont("title")
        }

        // footer
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom; anchors.bottomMargin: 12
            text: "종료: 풋스위치 아무거나"
            color: cDim; font: Theme.typeFont("heading")
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
            color: Theme.color("overlay.scrim"); opacity: 0.62
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

                Text { text: "스냅샷 다른 이름으로 저장"; color: cText; font: Theme.typeFont("title") }

                // suggestion box: tap to save (or, when typing, a text field)
                Rectangle {
                    width: parent.width; height: 56; radius: 10
                    color: Theme.color("surface.inset")
                    border.width: 1
                    border.color: (saveAsModal.suggestion !== "" || saveAsModal.typing) ? cGreen : cBorder
                    Text {
                        visible: !saveAsModal.typing
                        anchors.centerIn: parent
                        text: saveAsModal.suggestion !== "" ? saveAsModal.suggestion : "아래 용어를 눌러 이름 제안 받기"
                        color: saveAsModal.suggestion !== "" ? cGreen : cDim
                        font: Theme.typeFont("title")
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
                        color: cText; font: Theme.typeFont("title"); clip: true
                        onAccepted: if (text.trim().length) { view.saveSnapshotNamed(text); saveAsModal.close(); }
                    }
                }
                Text {
                    text: saveAsModal.typing ? "Enter로 저장"
                        : (saveAsModal.suggestion !== "" ? "↑ 이 이름을 누르면 저장 · 용어 다시 누르면 새 제안"
                                                         : "용어를 누르면 무작위 접미사가 붙은 제안이 떠요")
                    color: cDim; font: Theme.typeFont("label")
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
                            color: Theme.color("surface.control"); border.width: 1; border.color: cBorder
                            Text { anchors.centerIn: parent; text: modelData; color: Theme.color("text.onLight"); font: Theme.typeFont("heading") }
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
                        color: saveAsModal.typing ? cGreen : Theme.color("surface.control"); border.width: 1; border.color: cBorder
                        Text { anchors.centerIn: parent; text: "✎ 직접입력"; color: saveAsModal.typing ? Theme.color("bg.screen") : Theme.color("text.onLight"); font: Theme.typeFont("button") }
                        MouseArea { anchors.fill: parent; onClicked: { saveAsModal.typing = true; kb.forceActiveFocus(); } }
                    }
                    Rectangle {
                        width: 120; height: 44; radius: 8
                        color: Theme.color("btn.purple.fill"); border.width: 1; border.color: cBorder
                        Text { anchors.centerIn: parent; text: "취소"; color: Theme.color("text.onLight"); font: Theme.typeFont("button") }
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
        color: Theme.color("surface.elevated"); border.width: 1; border.color: cGreen
        Text {
            id: toastText
            anchors.centerIn: parent
            text: toast.msg
            color: cText; font: Theme.typeFont("heading")
        }
        Timer { id: toastTimer; interval: 2600; onTriggered: toast.visible = false }
        Connections {
            target: view
            function onToastRequested(text) { toast.msg = text; toast.visible = true; toastTimer.restart() }
        }
    }
}
