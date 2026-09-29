import QtQuick
import qs.Commons

// Plain text in the panel's font; `look` supplies the colours.
Text {
  property var look: null
  property bool secondary: false

  textFormat: Text.PlainText
  color: look ? (secondary ? look.muted : look.fg) : Color.foreground
  font.family: look ? look.font : Style.font.family
  font.pixelSize: secondary ? Style.font.caption : Style.font.body
  elide: Text.ElideRight
}
