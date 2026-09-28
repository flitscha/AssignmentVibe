import QtQuick
import qs.Commons
import qs.Ui
import "../Glyphs.js" as Glyphs
import "../controls"

// The prompt exactly as "Copy prompt" puts it on the clipboard - to see what
// the model will get before sending it.
Item {
  id: root

  property var service: null
  property var look: null
  readonly property bool editing: false

  signal back()

  property string text: ""
  property bool loading: true

  Component.onCompleted: reload()

  // A different task or context while this is open means a different prompt.
  readonly property var st: service ? service.state : null
  readonly property string where: st && st.course
    ? [st.course.slug, st.sheet ? st.sheet.id : "", st.task, st.summary ? st.summary.size : 0,
       st.summary ? st.summary.earlier : 0].join("|") : ""
  onWhereChanged: reload()

  function reload() {
    if (!service) return
    service.request("prompt", {}, function(r) {
      root.loading = false
      root.text = r.ok && r.result ? r.result.text : ""
    })
  }

  function key(t) {
    if (t === "p" || t === "P") root.back()
  }

  function move(dx, dy) {
    flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height,
                                          flick.contentY + dy * Style.space(60)))
  }

  Item {
    id: top
    width: parent.width
    height: backButton.implicitHeight

    Button {
      id: backButton
      iconText: Glyphs.back
      text: "Task"
      foreground: root.look.fg
      fontFamily: root.look.font
      tooltipText: "Esc"
      onClicked: root.back()
    }

    Label {
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      look: root.look
      secondary: true
      text: root.loading ? "Building …" : Number(root.text.length).toLocaleString(Qt.locale(), "f", 0) + " characters"
    }
  }

  BorderSurface {
    anchors.top: top.bottom
    anchors.topMargin: Style.space(8)
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    radius: Style.cornerRadius
    color: root.look.veil
    borderSpec: Border.none()

    Flickable {
      id: flick
      anchors.fill: parent
      anchors.margins: Style.space(12)
      contentWidth: width
      contentHeight: body.implicitHeight
      clip: true
      boundsBehavior: Flickable.StopAtBounds

      TextEdit {
        id: body
        width: flick.width
        readOnly: true
        selectByMouse: true
        textFormat: TextEdit.PlainText
        wrapMode: TextEdit.Wrap
        text: root.text
        color: root.look.fg
        selectionColor: Style.selectionFillFor(root.look.fg, root.look.accent)
        font.family: root.look.font
        font.pixelSize: Style.font.bodySmall
      }
    }
  }
}
