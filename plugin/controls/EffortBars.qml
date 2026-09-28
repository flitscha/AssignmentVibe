import QtQuick
import qs.Commons

// Jev's effort estimate for a task: one bar for routine up to four for hard.
Row {
  id: root

  property var look: null
  property int effort: -1
  property bool highlighted: false

  spacing: Style.space(2)
  visible: effort >= 0

  Repeater {
    model: 4

    Rectangle {
      required property int index
      width: Style.space(4)
      height: Style.space(11)
      radius: Style.space(1)
      color: index <= root.effort ? (root.highlighted ? root.look.fg : root.look.accent) : root.look.faint
    }
  }
}
