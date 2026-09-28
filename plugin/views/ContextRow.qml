import QtQuick
import qs.Commons
import qs.Ui
import "../Glyphs.js" as Glyphs
import "../controls"

// One line of the context list (see Model.rows for what `row` holds):
//
//   header      LECTURE NOTES                               96 statements
//   node        ▸ [◐] 3 Konvexe Funktionen                     2/17 · 3.1k
//   statement       [✓] Satz 3.1.5  Charakterisierung …  [proof 1.2k]  0.3k
//   sheet       ▸ [ ] Sheet 2                                        0/5
//   earlier         [✓] Task 3  Zeigen Sie, dass …
//
// On a chapter or sheet the box ticks everything in it and the rest of the
// line opens it; on a statement or task the whole line is the box.
BorderSurface {
  id: root

  property var look: null
  property var row: ({})
  property bool hasCursor: false

  signal toggled()
  signal expandToggled()
  signal proofToggled()

  readonly property bool folder: row.kind === "node" || row.kind === "sheet"
  readonly property bool tickable: folder || row.kind === "statement" || row.kind === "earlier"
  readonly property bool hot: tickable && (mouse.containsMouse || hasCursor)

  implicitHeight: row.kind === "header" ? header.implicitHeight + Style.space(16)
    : row.kind === "empty" ? emptyText.implicitHeight + Style.space(16)
    : Math.max(look.rowHeight - Style.space(4), line.implicitHeight + Style.space(10))
  radius: Style.cornerRadius
  color: hot ? Style.hoverFillFor(look.fg, look.accent) : "transparent"
  borderSpec: hasCursor ? Border.controlSpec("hover-cursor", look.fg, look.accent) : Border.none()
  opacity: enabled ? 1 : 0.5

  SectionTitle {
    id: header
    visible: root.row.kind === "header"
    anchors.bottom: parent.bottom
    anchors.bottomMargin: Style.space(4)
    anchors.left: parent.left
    anchors.leftMargin: Style.space(2)
    width: parent.width - Style.space(8)
    look: root.look
    text: root.row.text || ""
    detail: root.row.detail || ""
  }

  Label {
    id: emptyText
    visible: root.row.kind === "empty"
    anchors.verticalCenter: parent.verticalCenter
    x: Style.space(8)
    width: parent.width - Style.space(16)
    look: root.look
    secondary: true
    wrapMode: Text.WordWrap
    text: root.row.text || ""
  }

  MouseArea {
    id: mouse
    anchors.fill: parent
    visible: root.tickable
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: root.folder ? root.expandToggled() : root.toggled()
  }

  Item {
    id: line
    visible: root.tickable
    anchors.verticalCenter: parent.verticalCenter
    x: Style.space(4) + (root.row.level || 0) * root.look.indent
    width: parent.width - x - Style.space(8)
    implicitHeight: Math.max(box.height, labels.implicitHeight)
    height: implicitHeight

    // The chevron; statements get the same space, so the boxes line up.
    Text {
      id: chevron
      width: Style.space(16)
      anchors.verticalCenter: parent.verticalCenter
      horizontalAlignment: Text.AlignHCenter
      textFormat: Text.PlainText
      text: root.folder ? (root.row.expanded ? Glyphs.chevronDown : Glyphs.chevronRight) : ""
      color: root.look.muted
      font.family: root.look.font
      font.pixelSize: Style.font.icon
    }

    // A bigger target than the box itself: ticking should not need aim.
    MouseArea {
      id: boxArea
      anchors.left: chevron.right
      width: box.width + Style.space(12)
      height: parent.height + Style.space(10)
      anchors.verticalCenter: parent.verticalCenter
      cursorShape: Qt.PointingHandCursor
      onClicked: root.toggled()
    }

    CheckBox {
      id: box
      anchors.left: chevron.right
      anchors.leftMargin: Style.space(4)
      anchors.verticalCenter: parent.verticalCenter
      look: root.look
      value: root.folder ? (root.row.state || 0) : (root.row.on ? 2 : 0)
    }

    Column {
      id: labels
      anchors.left: box.right
      anchors.leftMargin: Style.space(10)
      anchors.right: right.left
      anchors.rightMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(1)

      Row {
        width: parent.width
        spacing: Style.space(8)

        Label {
          id: name
          look: root.look
          text: root.row.label || ""
          font.bold: root.folder ? (root.row.level === 0) : root.row.on
          width: Math.min(implicitWidth, parent.width)
        }

        Label {
          visible: !root.folder && (root.row.about || "") !== ""
          width: Math.max(0, parent.width - name.width - parent.spacing)
          look: root.look
          secondary: true
          font.pixelSize: Style.font.bodySmall
          anchors.baseline: name.baseline
          text: (root.row.about || "").replace(/\s+/g, " ")
        }
      }

      Label {
        visible: (root.row.caption || "") !== ""
        width: parent.width
        look: root.look
        secondary: true
        text: root.row.caption || ""
      }
    }

    Row {
      id: right
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(8)

      Button {
        visible: root.row.kind === "statement" && root.row.hasProof === true
        text: root.row.proofText || ""
        iconText: root.row.proofOn ? Glyphs.check : ""
        iconSize: Style.font.caption
        fontSize: Style.font.caption
        selected: root.row.proofOn === true
        bordered: true
        horizontalPadding: Style.space(6)
        verticalPadding: Style.space(1)
        foreground: root.row.proofOn ? root.look.fg : root.look.muted
        fontFamily: root.look.font
        tooltipText: root.row.proofOn ? "The proof goes in too (P)"
          : "Add the proof (P) - it may give the solution away"
        onClicked: root.proofToggled()
      }

      Label {
        anchors.verticalCenter: parent.verticalCenter
        look: root.look
        secondary: true
        visible: text !== ""
        text: root.folder
          ? (root.row.count || "") + (root.row.size ? "  ·  " + root.row.size : "")
          : (root.row.kind === "statement" ? (root.row.size || "") : "")
      }
    }
  }
}
