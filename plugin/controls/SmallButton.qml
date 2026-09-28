import QtQuick
import qs.Commons
import qs.Ui

// A button for a header line: caption-sized, and greyed out while disabled.
Button {
  property var look: null

  fontSize: Style.font.caption
  iconSize: Style.font.bodySmall
  horizontalPadding: Style.space(7)
  verticalPadding: Style.space(3)
  bordered: true
  foreground: look.fg
  fontFamily: look.font
  opacity: enabled ? 1 : 0.4
}
