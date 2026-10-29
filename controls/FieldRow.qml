import QtQuick
import qs.Commons

// One line of the panel's top block: a label in a fixed column on the left,
// what it labels flowing beside it, and `trailing` items on the right - so
// course, material, sheet and plan each take a line instead of a heading and
// a line. The label sits level with the first row of the content.
Item {
  id: root

  property var look: null
  property string text: ""
  property real labelWidth: Style.space(78)
  // Height of one row of the content, to centre the label on the first row.
  property real rowHeight: Style.space(26)
  default property alias content: flow.data
  property alias trailing: trailingRow.data

  width: parent ? parent.width : 0
  implicitHeight: Math.max(rowHeight, flow.implicitHeight, trailingRow.implicitHeight)

  Text {
    width: root.labelWidth
    height: root.rowHeight
    verticalAlignment: Text.AlignVCenter
    textFormat: Text.PlainText
    text: root.text.toUpperCase()
    color: root.look.muted
    font.family: root.look.font
    font.pixelSize: Style.font.caption
    font.bold: true
    font.letterSpacing: 1
  }

  Flow {
    id: flow
    x: root.labelWidth
    width: parent.width - x - (trailingRow.width > 0 ? trailingRow.width + Style.space(10) : 0)
    spacing: Style.space(4)
  }

  Row {
    id: trailingRow
    anchors.right: parent.right
    height: root.rowHeight
    spacing: Style.space(4)
  }
}
