import QtQuick
import qs.Commons
import qs.Ui
import "../Model.js" as Model

// Jev's effort estimate for a task as a short bar: the longer and the redder,
// the more work - from a stub in green (routine) to a full bar in red (hard).
// No number: a task row already carries the task's number and often the
// exercise's, and a third one beside them read as noise. Length and colour
// say the same thing, so neither depends on telling colours apart; the exact
// value is in the tooltip.
Item {
  id: root

  property var look: null
  property real effort: -1
  property string word: ""

  readonly property real fraction: Math.max(0, Math.min(1, (effort - 1) / 9))
  readonly property var hsl: Model.effortHsl(effort)

  visible: effort >= 0
  width: Style.space(40)
  height: Style.space(16)

  Rectangle {
    anchors.verticalCenter: parent.verticalCenter
    width: parent.width
    height: Style.space(6)
    radius: height / 2
    color: root.look.faint
  }

  Rectangle {
    anchors.verticalCenter: parent.verticalCenter
    width: Math.max(height, parent.width * (0.12 + 0.88 * root.fraction))
    height: Style.space(6)
    radius: height / 2
    color: Qt.hsla(root.hsl[0], root.hsl[1], root.hsl[2], 1)
  }

  MouseArea {
    id: hover
    anchors.fill: parent
    hoverEnabled: true
    acceptedButtons: Qt.NoButton
  }

  PanelToolTip {
    visible: hover.containsMouse
    text: "Effort as Jev rates it: " + (root.word || "") + " (" + root.effort.toFixed(1) + " of 10)"
  }
}
