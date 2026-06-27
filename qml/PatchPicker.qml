// Modal file picker for patch params (NAM model / IR / cabsim). Shared by the
// FOCUS card (main.qml) and the pedalboard editor inspector (PedalboardEditorView).
// The host fills it via present(files, label, current) and reacts to picked(path);
// theme tokens are passed in so it matches whichever screen embeds it.
//
// Vertical scrollbar: thumb position is a pure binding on the ListView's
// visibleArea (so it follows flick) and is NEVER set imperatively — the track
// MouseArea computes contentY directly, so the binding never breaks. Tap anywhere
// on the rail to jump, drag the thumb to scrub (handy for hundreds of files).
import QtQuick

Rectangle {
    id: root
    anchors.fill: parent
    visible: false
    z: 200
    color: "#e60a0d14"

    // theme tokens (host-provided)
    property color colElev: "#171c26"
    property color colBorder: "#2a3344"
    property color colText: "#cfd6e2"
    property color colAccent: "#5fd0a0"
    property string fontFamily: ""

    property var files: []
    property string titleLabel: "PATCH"
    property string currentName: ""        // basename of the loaded file (highlight)
    signal picked(string path)

    function present(filesList, label, current) {
        files = filesList || [];
        titleLabel = label || "PATCH";
        currentName = current || "";
        visible = true;
    }

    MouseArea { anchors.fill: parent; onClicked: root.visible = false }   // tap-out closes
    Rectangle {
        anchors.centerIn: parent
        width: parent.width - 72; height: parent.height - 48
        radius: 12; color: root.colElev; border.width: 1; border.color: root.colBorder
        MouseArea { anchors.fill: parent }   // swallow taps inside the panel
        Column {
            anchors.fill: parent; anchors.margins: 14; spacing: 8
            Row {
                width: parent.width
                Text {
                    width: parent.width - 60
                    text: root.titleLabel + " 선택  (" + root.files.length + ")"
                    color: root.colAccent; font.family: root.fontFamily; font.pixelSize: 22
                    elide: Text.ElideRight
                }
                Rectangle {
                    width: 52; height: 36; radius: 8; color: "#2c3648"
                    Text { anchors.centerIn: parent; text: "✕"; color: root.colText; font.family: root.fontFamily; font.pixelSize: 20 }
                    MouseArea { anchors.fill: parent; onClicked: root.visible = false }
                }
            }
            Item {
                width: parent.width; height: parent.height - 48
                ListView {
                    id: fileList
                    anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
                    width: parent.width - (sbTrack.visible ? 20 : 0)
                    clip: true; model: root.files
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: Rectangle {
                        width: ListView.view ? ListView.view.width : 0; height: 46
                        property bool isCur: (("" + modelData.label).split("/").pop() === root.currentName)
                        color: isCur ? "#2e5fd0a0" : "transparent"
                        Text {
                            anchors.left: parent.left; anchors.leftMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 20
                            text: modelData.label; color: isCur ? root.colAccent : root.colText
                            font.family: root.fontFamily; font.pixelSize: 18; elide: Text.ElideMiddle
                        }
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#1b2230" }
                        MouseArea {
                            anchors.fill: parent
                            onClicked: { root.picked(modelData.path); root.visible = false; }
                        }
                    }
                }
                Rectangle {
                    id: sbTrack
                    visible: fileList.contentHeight > fileList.height
                    anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
                    width: 14; radius: 7; color: "#141a24"
                    function scrollTo(my) {
                        var usable = sbTrack.height - sbThumb.height;
                        if (usable <= 0) return;
                        var top = Math.max(0, Math.min(usable, my - sbThumb.height / 2));
                        fileList.contentY = (top / usable) * (fileList.contentHeight - fileList.height);
                    }
                    Rectangle {
                        id: sbThumb
                        x: 0; width: parent.width; radius: 7
                        color: sbArea.pressed ? root.colAccent : "#3a4458"
                        height: Math.max(40, sbTrack.height * fileList.visibleArea.heightRatio)
                        y: fileList.visibleArea.yPosition * sbTrack.height   // follows flick; never set imperatively
                    }
                    MouseArea {
                        id: sbArea
                        anchors.fill: parent
                        onPressed: (mouse) => sbTrack.scrollTo(mouse.y)
                        onPositionChanged: (mouse) => { if (pressed) sbTrack.scrollTo(mouse.y) }
                    }
                }
            }
        }
    }
}
