import QtQuick
import qs.Commons
import qs.Ui
import "../Glyphs.js" as Glyphs
import "../controls"

// Everything that is not the everyday: reading in new PDFs, the files the
// tool is configured with, what Jev has cost, and the keys.
Flickable {
  id: root

  property var service: null
  property var look: null
  readonly property bool editing: false

  signal closeRequested()

  readonly property var st: service ? service.state : null
  readonly property bool busy: !!(service && service.busy !== "")

  contentWidth: width
  contentHeight: column.implicitHeight
  clip: true
  boundsBehavior: Flickable.StopAtBounds
  interactive: contentHeight > height

  function openConfig(name) {
    service.request("open_config", { name: name }, function(r) {
      if (r.ok && r.result && r.result.opened) root.closeRequested()
    })
  }

  Column {
    id: column
    width: root.width
    spacing: Style.space(8)

    // ---- New PDFs ---------------------------------------------------------------

    SectionTitle {
      look: root.look
      text: "Lecture notes and sheets"
      detail: root.st && root.st.semester ? "semester " + root.st.semester : ""
    }

    Item {
      width: parent.width
      height: Math.max(ingestText.implicitHeight, ingestButton.implicitHeight)

      Label {
        id: ingestText
        anchors.left: parent.left
        anchors.right: ingestButton.left
        anchors.rightMargin: Style.space(12)
        anchors.verticalCenter: parent.verticalCenter
        look: root.look
        secondary: true
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
        text: "Reads what the course folders have and the knowledge base does not: new sheets, "
          + "and lecture notes that changed. Files get into the folders with Super+Shift+U."
      }

      Button {
        id: ingestButton
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        iconText: Glyphs.sync
        iconSpinning: root.service && root.service.busy === "ingest"
        text: "Read in new PDFs"
        bordered: true
        enabled: !root.busy
        opacity: enabled ? 1 : 0.45
        foreground: root.look.fg
        fontFamily: root.look.font
        onClicked: root.service.request("ingest")
      }
    }

    Repeater {
      model: root.st ? root.st.courses : []

      Item {
        required property var modelData
        width: column.width
        height: Style.space(22)

        Label {
          x: Style.space(10)
          anchors.verticalCenter: parent.verticalCenter
          look: root.look
          text: modelData.name
        }

        Label {
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          look: root.look
          secondary: true
          text: (modelData.sheets === 1 ? "1 sheet" : modelData.sheets + " sheets")
            + "  ·  " + (modelData.hasNotes ? "lecture notes read in" : "no lecture notes")
        }
      }
    }

    Item { width: 1; height: Style.space(8) }

    // ---- Jev --------------------------------------------------------------------

    SectionTitle { look: root.look; text: "Jev" }

    Label {
      width: parent.width
      look: root.look
      wrapMode: Text.WordWrap
      elide: Text.ElideNone
      text: {
        if (!root.st) return ""
        if (!root.st.jev.configured)
          return "Not set up. Jev picks the lecture notes a task needs - it needs an OpenRouter "
            + "API key in openrouter.key (below)."
        return root.st.jev.usage ? "Costs so far: " + root.st.jev.usage
                                 : "Set up, not used yet."
      }
    }

    Item { width: 1; height: Style.space(8) }

    // ---- Config files -----------------------------------------------------------

    SectionTitle { look: root.look; text: "Config files"; detail: "open in the editor" }

    Repeater {
      model: root.st ? root.st.configFiles : []

      BorderSurface {
        id: fileRow
        required property var modelData
        readonly property bool hot: fileMouse.containsMouse

        width: column.width
        implicitHeight: root.look.rowHeight + Style.space(6)
        radius: Style.cornerRadius
        color: hot ? Style.hoverFillFor(root.look.fg, root.look.accent) : "transparent"
        borderSpec: Border.none()

        MouseArea {
          id: fileMouse
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: root.openConfig(fileRow.modelData.name)
        }

        Text {
          id: fileIcon
          x: Style.space(10)
          anchors.verticalCenter: parent.verticalCenter
          textFormat: Text.PlainText
          text: fileRow.modelData.name === "openrouter.key" ? Glyphs.key : Glyphs.file
          color: root.look.muted
          font.family: root.look.font
          font.pixelSize: Style.font.icon
        }

        Column {
          anchors.left: fileIcon.right
          anchors.leftMargin: Style.space(10)
          anchors.right: openLabel.left
          anchors.rightMargin: Style.space(10)
          anchors.verticalCenter: parent.verticalCenter
          spacing: Style.space(1)

          Label {
            width: parent.width
            look: root.look
            font.bold: true
            text: fileRow.modelData.name + (fileRow.modelData.exists ? "" : "   (not there yet - opens a template)")
          }

          Label {
            width: parent.width
            look: root.look
            secondary: true
            text: fileRow.modelData.about
          }
        }

        Text {
          id: openLabel
          anchors.right: parent.right
          anchors.rightMargin: Style.space(12)
          anchors.verticalCenter: parent.verticalCenter
          textFormat: Text.PlainText
          text: Glyphs.openExternal
          color: fileRow.hot ? root.look.fg : root.look.muted
          font.family: root.look.font
          font.pixelSize: Style.font.icon
        }
      }
    }

    Item { width: 1; height: Style.space(8) }

    // ---- Keys -------------------------------------------------------------------

    SectionTitle { look: root.look; text: "Keys" }

    Grid {
      columns: 2
      columnSpacing: Style.space(18)
      rowSpacing: Style.space(4)

      Repeater {
        model: [
          "1 – 4, Tab", "switch tabs",
          "Enter", "copy the prompt",
          "Esc", "close",
          "↑ ↓", "task (Task tab), row (Context tab)",
          "← →", "sheet (Task tab), close / open (Context tab)",
          "Space", "tick the row (Context tab)",
          "P", "preview the prompt; on a statement, tick its proof",
          "O", "open the sheet's PDF",
          "A", "let Jev pick the context",
          "E", "edit the context",
          "/", "search the lecture notes"
        ]

        Label {
          required property var modelData
          required property int index
          look: root.look
          secondary: index % 2 === 1
          font.bold: index % 2 === 0
          font.pixelSize: Style.font.caption
          text: modelData
        }
      }
    }

    Label {
      width: parent.width
      topPadding: Style.space(6)
      look: root.look
      secondary: true
      wrapMode: Text.WordWrap
      elide: Text.ElideNone
      text: "A shortcut for the panel: bind  qs ipc -p $OMARCHY_PATH/shell call assignmentvibe toggle  "
        + "in Hyprland. Right click on the bar button opens the follow-ups, middle click copies the prompt."
    }

    Item { width: 1; height: Style.space(6) }
  }
}
