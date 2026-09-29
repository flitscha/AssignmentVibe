import QtQuick
import qs.Commons

// Colours and type shared by every view, derived from the bar's theme so the
// panel follows theme switches.
QtObject {
  id: look

  property var bar: null

  readonly property color fg: bar ? bar.foreground : Color.foreground
  readonly property color muted: Qt.darker(fg, 1.45)
  readonly property color faint: Util.alpha(fg, 0.12)
  readonly property color veil: Util.alpha(fg, 0.05)
  readonly property color accent: Color.accent
  readonly property color urgent: Color.urgent
  readonly property color surface: Color.popups.background
  readonly property string font: bar && bar.fontFamily ? bar.fontFamily : Style.font.family

  readonly property int gap: Style.space(8)
  readonly property int rowHeight: Style.space(34)
  readonly property int indent: Style.space(18)
}
