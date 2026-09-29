import QtQuick
import qs.Commons
import "../Glyphs.js" as Glyphs

// A section heading with a note beside it and small buttons on the right.
Item {
  id: root

  property var look: null
  property string text: ""
  property string note: ""
  property color noteColor: look.muted
  // A spinner before the note, for "Jev is planning …".
  property bool spinning: false
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
    id: spinner
    visible: root.spinning
    anchors.left: title.right
    anchors.leftMargin: Style.space(10)
    anchors.verticalCenter: parent.verticalCenter
    textFormat: Text.PlainText
    text: Glyphs.loading
    color: root.noteColor
    font.family: root.look.font
    font.pixelSize: Style.font.body
    RotationAnimation on rotation {
      running: root.spinning
      from: 0; to: 360; duration: 900
      loops: Animation.Infinite
    }
  }

  Text {
    anchors.left: root.spinning ? spinner.right : title.right
    anchors.leftMargin: root.spinning ? Style.space(6) : Style.space(10)
    anchors.right: actionRow.left
    anchors.rightMargin: Style.space(10)
    anchors.verticalCenter: parent.verticalCenter
    textFormat: Text.PlainText
    text: root.note
    color: root.noteColor
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
