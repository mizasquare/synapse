import QtQuick
import QtQuick.Window

// Standalone pedalboard-editor window (driven by qt_editor.py). The whole editor
// body lives in PedalboardEditorView.qml so the live app can embed the same Item
// in its EDIT screen. Here it just gets a 800x480 window + the dev quit shortcut.
Window {
    id: win
    visible: true
    width: 800
    height: 480
    color: "#0e1118"
    title: "Pedalboard Editor — mock"

    // dev: quit a true-fullscreen instance (no title bar to close)
    Shortcut { sequences: ["Ctrl+Q"]; context: Qt.ApplicationShortcut; onActivated: Qt.quit() }

    PedalboardEditorView {
        anchors.fill: parent
        // standalone has no overview to return to — leaving = quit the dev app
        onExitRequested: Qt.quit()
    }
}
