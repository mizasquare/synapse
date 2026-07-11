// One focus-card control, rendered by its widget `kind` (the interpretation
// computed in EffectPort.widget_kind / qtview). main.qml just repeats this.
// `view` and `uiFont` are engine context properties -> available here.
import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property var m                 // {symbol,name,value,norm,min,max,unit,kind,options,display}
    property string instance
    width: 118; height: 130

    // Palette resolves from the shared Theme token source (theme/tokens.json);
    // aliases retained so the `root.cX` call sites below stay untouched.
    readonly property color cGreen:  Theme.color("accent.green")
    readonly property color cBorder: Theme.color("border.default")
    readonly property color cText:   Theme.color("text.primary")
    readonly property color cMuted:  Theme.color("text.secondary")
    readonly property color cElev:   Theme.color("surface.elevated")

    property real dispNorm: m ? m.norm : 0
    readonly property bool isKnob: m && (m.kind === "knob" || m.kind === "knob_int" || m.kind === "knob_log")
    property real liveVal: valueFromNorm(dispNorm)

    // norm (0..1 drag position) -> real port value, honoring log/int kinds
    function valueFromNorm(nv) {
        if (!m) return 0
        var val
        if (m.kind === "knob_log" && m.min > 0 && m.max > 0)
            val = m.min * Math.pow(m.max / m.min, nv)
        else
            val = m.min + nv * (m.max - m.min)
        if (m.kind === "knob_int") val = Math.round(val)
        return val
    }

    Column {
        anchors.centerIn: parent
        spacing: 6
        Loader {
            anchors.horizontalCenter: parent.horizontalCenter
            sourceComponent: {
                if (!root.m) return knobC
                if (root.m.kind === "toggle")  return toggleC
                if (root.m.kind === "trigger") return triggerC
                if (root.m.kind === "enum")    return enumC
                return knobC               // knob / knob_int / knob_log
            }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.m ? root.m.name : ""; color: root.cMuted
            font: Theme.typeFont("controlName")
        }
        Text {  // live value -- knobs only (toggle/trigger/enum show state in the body)
            visible: root.isKnob
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.isKnob ? (root.liveVal.toFixed(root.m.kind === "knob_int" ? 0 : 2)
                                 + (root.m.unit ? (" " + root.m.unit) : "")) : ""
            color: root.cGreen; font: Theme.typeFont("label")
        }
    }

    // --- rotary knob (also int/log for now; mapping refinement = increment 2) ---
    Component {
        id: knobC
        Item {
            width: 84; height: 84
            Shape {
                anchors.fill: parent
                ShapePath {
                    strokeColor: root.cBorder; strokeWidth: 8; fillColor: "transparent"
                    PathAngleArc { centerX: 42; centerY: 42; radiusX: 34; radiusY: 34; startAngle: -90; sweepAngle: 360 }
                }
                ShapePath {
                    strokeColor: root.cGreen; strokeWidth: 8; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                    PathAngleArc { centerX: 42; centerY: 42; radiusX: 34; radiusY: 34; startAngle: -90; sweepAngle: 360 * root.dispNorm }
                }
            }
            MouseArea {
                anchors.fill: parent; preventStealing: true
                property real sy: 0; property real sv: 0
                onPressed: { sy = mouseY; sv = root.dispNorm }
                onPositionChanged: {
                    var nv = Math.max(0, Math.min(1, sv + (sy - mouseY) / 180))
                    root.dispNorm = nv
                    if (root.m) view.setParameter(root.instance, root.m.symbol, root.valueFromNorm(nv))
                }
            }
        }
    }

    // --- on/off toggle ---
    // `on` seeds from the model but is owned locally after a tap (like the knob's
    // dispNorm): update_parameter_display syncs the model silently (no emit), so a
    // pure m.value binding would never flip. The next full rebuild re-seeds it.
    Component {
        id: toggleC
        Rectangle {
            id: tgl
            width: 84; height: 44; radius: 22
            property bool on: root.m ? root.m.value >= 0.5 : false
            color: on ? root.cGreen : root.cBorder
            Text {
                anchors.centerIn: parent; text: tgl.on ? "ON" : "OFF"
                // dark text on the green ON fill; muted grey when OFF
                color: tgl.on ? Theme.color("bg.screen") : Theme.color("text.mutedAlt"); font: Theme.typeFont("toggle")
            }
            MouseArea {
                anchors.fill: parent
                onClicked: {
                    if (!root.m) return
                    tgl.on = !tgl.on                 // optimistic flip (breaks the seed binding)
                    view.setParameter(root.instance, root.m.symbol, tgl.on ? 1 : 0)
                }
            }
        }
    }

    // --- momentary trigger (record/stop/reset) ---
    Component {
        id: triggerC
        Rectangle {
            width: 84; height: 84; radius: 42
            color: ma.pressed ? root.cGreen : root.cElev
            border.width: 2; border.color: root.cGreen
            Text { anchors.centerIn: parent; text: "↻"
                   color: ma.pressed ? Theme.color("bg.screen") : root.cGreen; font: Theme.typeFont("title") }
            MouseArea {
                id: ma; anchors.fill: parent
                onPressed:  if (root.m) view.setParameter(root.instance, root.m.symbol, root.m.max)
                onReleased: if (root.m) view.setParameter(root.instance, root.m.symbol, root.m.min)
            }
        }
    }

    // --- enumeration selector (tap to cycle) ---
    // curVal is locally owned after a tap (same reason as the toggle: the model
    // syncs silently). label derives from it so the readout updates immediately.
    Component {
        id: enumC
        Rectangle {
            id: enr
            width: 100; height: 84; radius: 8
            color: root.cElev; border.width: 1; border.color: root.cBorder
            property real curVal: root.m ? root.m.value : 0
            property string label: {
                if (!root.m) return ""
                var opts = root.m.options || []
                for (var k = 0; k < opts.length; k++)
                    if (Math.abs(opts[k].value - enr.curVal) < 1e-6) return opts[k].label
                return root.m.display
            }
            Text { anchors.centerIn: parent; text: enr.label
                   color: root.cText; font: Theme.typeFont("body") }
            Text { anchors.bottom: parent.bottom; anchors.bottomMargin: 4
                   anchors.horizontalCenter: parent.horizontalCenter; text: "▾"
                   color: root.cMuted; font: Theme.typeFont("caption") }
            MouseArea {
                anchors.fill: parent
                onClicked: {
                    if (!root.m || !root.m.options || root.m.options.length === 0) return
                    var i = 0
                    for (var k = 0; k < root.m.options.length; k++)
                        if (Math.abs(root.m.options[k].value - enr.curVal) < 1e-6) { i = k; break }
                    var nx = root.m.options[(i + 1) % root.m.options.length]
                    enr.curVal = nx.value           // optimistic advance (breaks the seed binding)
                    view.setParameter(root.instance, root.m.symbol, nx.value)
                }
            }
        }
    }
}
