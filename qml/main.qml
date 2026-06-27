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

                    Column {
                        anchors.centerIn: parent
                        width: parent.width - 14
                        spacing: 1
                        Text {
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            text: modelData.label
                            color: modelData.isIo ? cGreen : cText
                            font.family: uiFont
                            font.pixelSize: modelData.isIo ? 22 : 20
                            wrapMode: Text.WrapAtWordBoundaryOrAnywhere
                            maximumLineCount: 2
                            elide: Text.ElideRight
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

    // ====================================================== PEDALBOARD EDIT
    // The pedalboard editor, embedded from PedalboardEditorView.qml (same body the
    // standalone qt_editor.py window uses). Loaded by file URL (own context, like the
    // standalone window) and only while in EDIT — so it is created fresh on each entry
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
