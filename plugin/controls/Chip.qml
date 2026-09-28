import QtQuick
import qs.Commons
import qs.Ui

// A choice among several, side by side: a course, a sheet. `dot` marks one of
// them (the newest sheet), `dimmed` one that has nothing in it yet.
Button {
  id: root

  property var look: null
  property bool dot: false
  property bool dimmed: false

  bordered: !selected
  foreground: look.fg
  fontFamily: look.font
  horizontalPadding: Style.space(10)
  verticalPadding: Style.space(4)
  opacity: enabled ? (dimmed && !selected ? 0.55 : 1) : 0.4

  Rectangle {
    visible: root.dot
    width: Style.space(6)
    height: width
    radius: width / 2
    color: root.look.accent
    anchors.top: parent.top
    anchors.right: parent.right
    anchors.topMargin: Style.space(3)
    anchors.rightMargin: Style.space(3)
  }
}
