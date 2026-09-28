import QtQuick
import qs.Commons
import qs.Ui

// A setting that is on or off, as a box with its label - the same box as the
// list below it, so on reads as on at a glance.
Item {
  id: root

  property var look: null
  property string text: ""
  property string hint: ""
  property bool checked: false

  signal toggled()

  implicitWidth: row.implicitWidth + Style.space(12)
  implicitHeight: row.implicitHeight + Style.space(8)
  opacity: enabled ? 1 : 0.45

  Rectangle {
    anchors.fill: parent
    radius: Style.cornerRadius
    color: mouse.containsMouse ? Style.hoverFillFor(root.look.fg, root.look.accent) : "transparent"
  }

  Row {
    id: row
    anchors.centerIn: parent
    spacing: Style.space(8)

    CheckBox {
      anchors.verticalCenter: parent.verticalCenter
      look: root.look
      value: root.checked ? 2 : 0
    }

    Label {
      anchors.verticalCenter: parent.verticalCenter
      look: root.look
      text: root.text
    }
  }

  MouseArea {
    id: mouse
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: root.toggled()
  }

  PanelToolTip {
    visible: root.hint !== "" && mouse.containsMouse
    text: root.hint
  }
}
