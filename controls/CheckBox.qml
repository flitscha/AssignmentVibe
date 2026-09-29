import QtQuick
import qs.Commons
import "../Glyphs.js" as Glyphs

// A box with three states: 0 empty, 1 some (a chapter partly chosen), 2 all.
// Only draws; the row around it takes the click.
Rectangle {
  id: root

  property var look: null
  property int value: 0

  width: Style.space(15)
  height: width
  radius: Math.min(Style.space(3), Style.cornerRadius > 0 ? Style.space(4) : 0)
  color: value > 0 ? look.accent : "transparent"
  border.width: value > 0 ? 0 : Math.max(1, Style.space(1.5))
  border.color: look.muted

  Behavior on color { ColorAnimation { duration: 90 } }

  Text {
    anchors.centerIn: parent
    visible: root.value > 0
    textFormat: Text.PlainText
    text: root.value === 2 ? Glyphs.check : Glyphs.minus
    color: root.look.surface
    font.family: root.look.font
    font.pixelSize: Style.font.bodySmall
    font.bold: true
  }
}
