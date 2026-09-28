import QtQuick
import qs.Commons

// How full the context is, against the limit from settings.json. Past the
// limit the bar turns the theme's urgent colour and stays full.
Item {
  id: root

  property var look: null
  property real value: 0
  property real limit: 1

  readonly property bool over: value > limit

  implicitHeight: Style.space(6)

  Rectangle {
    anchors.fill: parent
    radius: height / 2
    color: root.look.faint
  }

  Rectangle {
    width: root.value > 0 ? Math.max(height, parent.width * Math.min(1, root.value / Math.max(1, root.limit))) : 0
    height: parent.height
    radius: height / 2
    color: root.over ? root.look.urgent : root.look.accent
    Behavior on width { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
  }
}
