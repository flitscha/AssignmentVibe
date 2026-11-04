import QtQuick
import qs.Commons
import qs.Ui
import "../Glyphs.js" as Glyphs
import "../controls"

// Every lecture script uni.json knows - this semester's, past courses', the
// "zusatzskript"s and "weitere_skripte" - to open one without knowing where
// it lies. Type to narrow it down (name, semester or filename, every word),
// ↑↓ and Enter to open, Esc back to the task.
Item {
  id: root

  property var service: null
  property var look: null
  readonly property bool editing: search.activeFocus

  signal back()
  signal closeRequested()

  property var scripts: []
  property bool loading: true
  property int cursor: 0

  readonly property var shown: {
    var words = search.text.toLowerCase().split(/\s+/).filter(function(w) { return w !== "" })
    return scripts.filter(function(s) {
      var hay = (s.name + " " + s.semester + " " + s.path.split("/").pop()).toLowerCase()
      return words.every(function(w) { return hay.indexOf(w) >= 0 })
    })
  }
  onShownChanged: cursor = 0

  Component.onCompleted: {
    search.forceActiveFocus()
    if (service) service.request("scripts", {}, function(r) {
      root.loading = false
      root.scripts = r.ok && r.result ? r.result.scripts : []
    })
  }

  function open(script) {
    if (service && script) service.request("open_script", { path: script.path }, function(r) {
      if (r.ok && r.result && r.result.opened) root.closeRequested()
    })
  }

  function move(dx, dy) {
    if (dy !== 0 && shown.length) {
      cursor = Math.max(0, Math.min(shown.length - 1, cursor + dy))
      list.positionViewAtIndex(cursor, ListView.Contain)
    }
  }

  function activate() {
    if (cursor < 0 || cursor >= shown.length) return false
    open(shown[cursor])
    return true
  }

  function key(t) {
    if (t === "/") search.forceActiveFocus()
  }

  Item {
    id: top
    width: parent.width
    height: Math.max(backButton.implicitHeight, search.implicitHeight)

    Button {
      id: backButton
      anchors.verticalCenter: parent.verticalCenter
      iconText: Glyphs.back
      text: "Task"
      foreground: root.look.fg
      fontFamily: root.look.font
      tooltipText: "Esc"
      onClicked: root.back()
    }

    TextField {
      id: search
      anchors.left: backButton.right
      anchors.leftMargin: Style.space(8)
      anchors.right: count.left
      anchors.rightMargin: Style.space(8)
      anchors.verticalCenter: parent.verticalCenter
      placeholderText: Glyphs.search + "  Search every script   ( / )"
      foreground: root.look.fg
      font.family: root.look.font
      Keys.onEscapePressed: {
        if (text !== "") text = ""
        else root.back()
      }
      Keys.onDownPressed: root.move(0, 1)
      Keys.onUpPressed: root.move(0, -1)
      Keys.onReturnPressed: root.activate()
      Keys.onEnterPressed: root.activate()
    }

    Label {
      id: count
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      look: root.look
      secondary: true
      text: root.loading ? "Looking …"
        : root.shown.length === root.scripts.length ? root.scripts.length + " scripts"
        : root.shown.length + " of " + root.scripts.length
    }
  }

  ListView {
    id: list
    anchors.top: top.bottom
    anchors.topMargin: Style.space(8)
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    spacing: Style.space(2)
    model: root.shown

    delegate: BorderSurface {
      id: row
      required property var modelData
      required property int index
      readonly property bool hasCursor: index === root.cursor
      // A line between this semester's scripts and the rest.
      readonly property bool firstPast: !modelData.active && index > 0 && root.shown[index - 1].active

      width: list.width
      implicitHeight: Math.max(root.look.rowHeight - Style.space(4), line.implicitHeight + Style.space(10))
        + (firstPast ? Style.space(10) : 0)
      radius: Style.cornerRadius
      color: mouse.containsMouse || hasCursor ? Style.hoverFillFor(root.look.fg, root.look.accent) : "transparent"
      borderSpec: hasCursor ? Border.controlSpec("hover-cursor", root.look.fg, root.look.accent) : Border.none()

      Row {
        id: line
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: row.firstPast ? Style.space(5) : 0
        x: Style.space(8)
        width: parent.width - Style.space(16)
        spacing: Style.space(10)

        Label {
          id: glyph
          anchors.verticalCenter: parent.verticalCenter
          look: root.look
          text: Glyphs.book
          color: row.modelData.active ? root.look.accent : root.look.muted
        }

        Label {
          id: name
          anchors.verticalCenter: parent.verticalCenter
          width: Math.min(implicitWidth, line.width - glyph.width - semester.width - Style.space(20))
          look: root.look
          text: row.modelData.name
        }

        Label {
          id: semester
          anchors.verticalCenter: parent.verticalCenter
          look: root.look
          secondary: true
          text: (row.modelData.semester ? row.modelData.semester + "  ·  " : "")
            + row.modelData.path.split("/").pop()
          width: Math.min(implicitWidth, line.width * 0.45)
        }
      }

      MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.open(row.modelData)
      }
    }
  }

  Label {
    visible: !root.loading && root.shown.length === 0
    anchors.top: top.bottom
    anchors.topMargin: Style.space(16)
    width: parent.width
    look: root.look
    secondary: true
    wrapMode: Text.WordWrap
    elide: Text.ElideNone
    text: root.scripts.length
      ? "No script matches."
      : "No scripts found. A script counts once uni.json names it: a course's \"skript\", "
        + "a \"zusatzskript\", or \"weitere_skripte\" for older courses."
  }
}
