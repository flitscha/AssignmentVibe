import QtQuick
import qs.Commons
import qs.Ui
import "../Model.js" as Model

// Jev's effort estimate for a task, 1 (routine) to 10 (hard): the number on
// a colour from green to red. Hover says what the scale means.
Rectangle {
  id: root

  property var look: null
  property real effort: -1
  property string word: ""

  readonly property var hsl: Model.effortHsl(effort)

  visible: effort >= 0
  width: Style.space(34)
  height: Style.space(18)
  radius: Math.min(height / 2, Math.max(Style.space(3), Style.cornerRadius))
  color: Qt.hsla(hsl[0], hsl[1], hsl[2], 1)

  Text {
    anchors.centerIn: parent
    textFormat: Text.PlainText
    text: root.effort >= 0 ? root.effort.toFixed(1) : ""
    color: "#161616"
    font.family: root.look.font
    font.pixelSize: Style.font.caption
    font.bold: true
  }

  MouseArea {
    id: hover
    anchors.fill: parent
    hoverEnabled: true
    acceptedButtons: Qt.NoButton
  }

  PanelToolTip {
    visible: hover.containsMouse
    text: "Effort " + root.effort.toFixed(1) + " of 10 as Jev rates it"
      + (root.word ? " - " + root.word : "") + ".\n1 is a direct application, 10 needs an idea of its own."
  }
}
