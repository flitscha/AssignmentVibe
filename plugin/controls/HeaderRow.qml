import QtQuick
import qs.Commons

// A section heading with a note beside it and small buttons on the right.
Item {
  id: root

  property var look: null
  property string text: ""
  property string note: ""
  default property alias actions: actionRow.data

  width: parent ? parent.width : 0
  implicitHeight: Math.max(title.implicitHeight, actionRow.implicitHeight)

  Text {
    id: title
    anchors.verticalCenter: parent.verticalCenter
    textFormat: Text.PlainText
    text: root.text.toUpperCase()
    color: root.look.muted
    font.family: root.look.font
    font.pixelSize: Style.font.caption
    font.bold: true
    font.letterSpacing: 1
  }

  Text {
    anchors.left: title.right
    anchors.leftMargin: Style.space(10)
    anchors.right: actionRow.left
    anchors.rightMargin: Style.space(10)
    anchors.verticalCenter: parent.verticalCenter
    textFormat: Text.PlainText
    text: root.note
    color: root.look.muted
    font.family: root.look.font
    font.pixelSize: Style.font.caption
    elide: Text.ElideRight
  }

  Row {
    id: actionRow
    anchors.right: parent.right
    anchors.verticalCenter: parent.verticalCenter
    spacing: Style.space(4)
  }
}
