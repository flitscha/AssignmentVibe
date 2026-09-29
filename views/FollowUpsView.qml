import QtQuick
import qs.Commons
import qs.Ui
import "../Glyphs.js" as Glyphs
import "../controls"

// Canned replies for the chat - for the moment after the answer, when typing
// "explain that step again" is the expensive part. One click copies one and
// closes the panel; paste it into the chat.
//
// Keys: arrows move, Enter copies.
Flickable {
  id: root

  property var service: null
  property var look: null
  readonly property bool editing: false

  signal closeRequested()

  readonly property var items: service && service.state ? service.state.followUps : []
  readonly property int columns: 2
  property int cursor: -1

  contentWidth: width
  contentHeight: column.implicitHeight
  clip: true
  boundsBehavior: Flickable.StopAtBounds
  interactive: contentHeight > height

  function copy(item) {
    service.request("copy_text", { text: item.text, label: item.emoji + " " + item.label }, function(r) {
      if (r.ok && r.result && r.result.copied) root.closeRequested()
    })
  }

  function move(dx, dy) {
    if (!items.length) return
    if (cursor < 0) { cursor = 0; return }
    cursor = Math.max(0, Math.min(items.length - 1, cursor + dx + dy * columns))
  }

  function activate() {
    if (cursor < 0) return false
    copy(items[cursor])
    return true
  }

  Column {
    id: column
    width: root.width
    spacing: Style.space(10)

    Label {
      width: parent.width
      look: root.look
      secondary: true
      wrapMode: Text.WordWrap
      elide: Text.ElideNone
      text: "Copied to the clipboard in one click - paste it into the chat. "
        + "Right click on the bar button opens this tab directly."
    }

    Grid {
      id: grid
      width: parent.width
      columns: root.columns
      columnSpacing: Style.space(8)
      rowSpacing: Style.space(8)

      Repeater {
        model: root.items

        BorderSurface {
          id: card
          required property var modelData
          required property int index
          readonly property bool hot: mouse.containsMouse || root.cursor === index

          width: (grid.width - grid.columnSpacing * (root.columns - 1)) / root.columns
          height: Style.space(84)
          radius: Style.cornerRadius
          color: hot ? Style.hoverFillFor(root.look.fg, root.look.accent)
            : Style.normalFillFor(root.look.fg, root.look.accent)
          borderSpec: hot ? Border.controlSpec("hover-cursor", root.look.fg, root.look.accent)
            : Border.controlSpec("normal", root.look.fg, root.look.accent)

          MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.copy(card.modelData)
          }

          Column {
            x: Style.space(12)
            y: Style.space(10)
            width: parent.width - Style.space(24)
            spacing: Style.space(4)

            Label {
              width: parent.width
              look: root.look
              font.bold: true
              text: card.modelData.emoji + "  " + card.modelData.label
            }

            Label {
              width: parent.width
              look: root.look
              secondary: true
              wrapMode: Text.WordWrap
              maximumLineCount: 3
              text: card.modelData.text
            }
          }

          Text {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Style.space(8)
            visible: card.hot
            textFormat: Text.PlainText
            text: Glyphs.copy
            color: root.look.muted
            font.family: root.look.font
            font.pixelSize: Style.font.icon
          }
        }
      }
    }
  }
}
