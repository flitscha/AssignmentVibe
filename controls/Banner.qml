import QtQuick
import qs.Commons
import qs.Ui
import "../Glyphs.js" as Glyphs

// What the last action had to say - "Jev picked 12 statements", "Sheet not
// found" - shown in the panel rather than as a toast in a corner. Warnings stay
// until closed; everything else fades after a while.
BorderSurface {
  id: root

  property var look: null
  property string level: "info"
  property string title: ""
  property string body: ""
  property bool busy: false

  signal dismissed()

  readonly property color tint: level === "warn" ? look.urgent : look.accent

  implicitHeight: content.implicitHeight + Style.space(16)
  radius: Style.cornerRadius
  color: Util.alpha(tint, 0.10)
  borderSpec: Border.none()
  border.width: Math.max(1, Style.space(1))
  border.color: Util.alpha(tint, 0.45)

  Row {
    id: content
    anchors.left: parent.left
    anchors.right: closeButton.left
    anchors.verticalCenter: parent.verticalCenter
    anchors.leftMargin: Style.space(10)
    anchors.rightMargin: Style.space(6)
    spacing: Style.space(10)

    Text {
      id: icon
      anchors.top: parent.top
      textFormat: Text.PlainText
      text: root.busy ? Glyphs.loading : (root.level === "warn" ? Glyphs.alert
            : root.level === "ok" ? Glyphs.check : Glyphs.info)
      color: root.tint
      font.family: root.look.font
      font.pixelSize: Style.font.icon

      RotationAnimation on rotation {
        running: root.busy
        from: 0; to: 360; duration: 900
        loops: Animation.Infinite
      }
      rotation: 0
    }

    Column {
      width: parent.width - icon.width - parent.spacing
      spacing: Style.space(2)

      Text {
        width: parent.width
        textFormat: Text.PlainText
        text: root.title
        color: root.look.fg
        font.family: root.look.font
        font.pixelSize: Style.font.body
        font.bold: true
        wrapMode: Text.WordWrap
      }

      Text {
        width: parent.width
        visible: root.body !== ""
        textFormat: Text.PlainText
        text: root.body
        color: root.look.muted
        font.family: root.look.font
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
        maximumLineCount: 8
        elide: Text.ElideRight
      }
    }
  }

  Button {
    id: closeButton
    visible: !root.busy
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.margins: Style.space(3)
    iconText: Glyphs.close
    iconSize: Style.font.bodySmall
    horizontalPadding: Style.space(5)
    verticalPadding: Style.space(3)
    foreground: root.look.muted
    fontFamily: root.look.font
    tooltipText: "Dismiss"
    onClicked: root.dismissed()
  }
}
