import QtQuick
import qs.Commons
import qs.Ui
import "../Glyphs.js" as Glyphs
import "../Model.js" as Model
import "../controls"

// Where you stand: course, sheet and task side by side, the task's text, and
// what the prompt carries - with the buttons that change each right beside it.
//
// Keys: ↑↓ task, ←→ sheet, O open the sheet, N open the lecture notes,
// A ask Jev, E edit the context, P preview the prompt. A line of the context
// opens the script or slide deck at its page when clicked.
Flickable {
  id: root

  property var service: null
  property var look: null
  readonly property bool editing: false

  signal navigate(string target)
  signal copyRequested()
  signal closeRequested()

  readonly property var st: service ? service.state : null
  readonly property bool busy: !!(service && service.busy !== "")
  readonly property var tasks: st ? st.tasks : []
  readonly property var parts: currentTask && currentTask.parts ? currentTask.parts : []
  readonly property string part: st && st.part ? st.part : ""
  readonly property var chosenPart: {
    for (var i = 0; i < parts.length; i++) if (parts[i].label === part) return parts[i]
    return null
  }
  readonly property var currentTask: {
    if (!st) return null
    for (var i = 0; i < tasks.length; i++) if (tasks[i].number === st.task) return tasks[i]
    return null
  }

  contentWidth: width
  contentHeight: column.implicitHeight
  clip: true
  boundsBehavior: Flickable.StopAtBounds
  interactive: contentHeight > height

  function request(cmd, args, callback) {
    if (service && !busy) service.request(cmd, args, callback)
  }

  function move(dx, dy) {
    if (!st || busy) return
    if (dy !== 0 && tasks.length) {
      var i = 0
      for (var k = 0; k < tasks.length; k++) if (tasks[k].number === st.task) i = k
      i = Math.max(0, Math.min(tasks.length - 1, i + dy))
      request("select_task", { number: tasks[i].number })
    } else if (dx !== 0 && st.sheets.length && st.sheet) {
      var j = 0
      for (var s = 0; s < st.sheets.length; s++) if (st.sheets[s].id === st.sheet.id) j = s
      j = Math.max(0, Math.min(st.sheets.length - 1, j + dx))
      request("select_sheet", { id: st.sheets[j].id })
    }
  }

  function key(t) {
    if (t === "o" || t === "O") openSheet()
    else if (t === "n" || t === "N") openNotes()
    else if (t === "a" || t === "A") askJev()
    else if (t === "e" || t === "E") navigate("context")
    else if (t === "p" || t === "P") { if (currentTask) navigate("prompt") }
  }

  // Opening a PDF races with nothing, so it works while Jev is busy too.
  function openSheet() {
    if (service) service.request("open_sheet", {}, function(r) {
      if (r.ok && r.result && r.result.opened) root.closeRequested()
    })
  }

  function openNotes() {
    if (service && st && st.course && st.course.notesPdf) service.request("open_notes", {}, function(r) {
      if (r.ok && r.result && r.result.opened) root.closeRequested()
    })
  }

  // A statement, slide or section of the context, in its PDF at its page -
  // for looking up what Jev picked without searching the script for it.
  function openSource(target) {
    if (service && target) service.request("open_source", { target: target }, function(r) {
      if (r.ok && r.result && r.result.opened) root.closeRequested()
    })
  }

  function askJev() {
    if (st && st.jev.configured && currentTask) request("jev")
  }

  // Keep the chosen task in view when it moves by keyboard.
  function reveal(item) {
    var p = item.mapToItem(column, 0, 0)
    if (p.y < contentY) contentY = Math.max(0, p.y - Style.space(8))
    else if (p.y + item.height > contentY + height)
      contentY = Math.min(contentHeight - height, p.y + item.height - height + Style.space(8))
  }

  Column {
    id: column
    width: root.width
    spacing: Style.space(8)

    // ---- Course -----------------------------------------------------------------

    HeaderRow {
      look: root.look
      text: "Course"

      SmallButton {
        visible: !!(root.st && root.st.course && root.st.course.notesPdf)
        look: root.look
        iconText: Glyphs.book
        text: root.currentTask && root.currentTask.page ? "Lecture notes · p. " + root.currentTask.page
                                                       : "Lecture notes"
        tooltipText: root.currentTask && root.currentTask.page
          ? "N · the script, at the exercise this task points at"
          : "N · the script of this course"
        onClicked: root.openNotes()
      }
    }

    Flow {
      width: parent.width
      spacing: Style.space(6)

      Repeater {
        model: root.st ? root.st.courses : []

        Chip {
          required property var modelData
          look: root.look
          text: modelData.name
          selected: root.st.course && root.st.course.slug === modelData.slug
          dimmed: modelData.sheets === 0 && !modelData.hasNotes
          enabled: !root.busy
          tooltipText: (modelData.sheets === 1 ? "1 sheet" : modelData.sheets + " sheets")
            + (modelData.hasNotes ? " · lecture notes read in" : " · no lecture notes")
          onClicked: if (!selected) root.request("select_course", { slug: modelData.slug })
        }
      }
    }

    Item { width: 1; height: Style.space(4) }

    // ---- Sheet ------------------------------------------------------------------

    HeaderRow {
      look: root.look
      text: "Sheet"
      note: root.st && root.st.sheet && root.st.sheet.discussion
        ? "discussed " + root.st.sheet.discussion : ""

      SmallButton {
        visible: !!(root.st && root.st.sheet)
        look: root.look
        iconText: Glyphs.pdf
        text: "Open PDF"
        tooltipText: "O · the sheet in the PDF viewer"
        onClicked: root.openSheet()
      }

      SmallButton {
        visible: !!(root.st && root.st.sheet && root.st.jev.configured)
        look: root.look
        iconText: Glyphs.sparkle
        text: root.st && root.st.sheet && root.st.sheet.plan ? "Plan again" : "Plan with Jev"
        enabled: !root.busy
        tooltipText: "Jev picks every task's context at once, rates how much work each is, "
          + "and finds which task builds on which"
        onClicked: root.request("plan")
      }
    }

    Flow {
      width: parent.width
      spacing: Style.space(6)
      visible: !!(root.st && root.st.sheets.length)

      Repeater {
        model: root.st ? root.st.sheets : []

        Chip {
          required property var modelData
          look: root.look
          text: modelData.label
          selected: !!(root.st.sheet && root.st.sheet.id === modelData.id)
          dot: modelData.newest
          enabled: !root.busy
          horizontalPadding: Style.space(9)
          tooltipText: "Sheet " + modelData.label + " · " + modelData.tasks + " tasks"
            + (modelData.newest ? " · the newest" : "") + (modelData.planned ? " · planned by Jev" : "")
          onClicked: if (!selected) root.request("select_sheet", { id: modelData.id })
        }
      }
    }

    Column {
      width: parent.width
      spacing: Style.space(8)
      visible: !!(root.st && root.st.course && !root.st.sheets.length)

      Label {
        width: parent.width
        look: root.look
        secondary: true
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
        text: "No sheets read in for " + (root.st && root.st.course ? root.st.course.name : "this course")
          + " yet. Sheets come from the course folder, as uni.json describes it."
      }

      Button {
        iconText: Glyphs.sync
        text: "Read in new PDFs"
        bordered: true
        enabled: !root.busy
        foreground: root.look.fg
        fontFamily: root.look.font
        onClicked: root.request("ingest")
      }
    }

    Item { width: 1; height: Style.space(4); visible: root.tasks.length > 0 }

    // ---- Tasks ------------------------------------------------------------------

    HeaderRow {
      look: root.look
      visible: root.tasks.length > 0
      text: "Task"
      note: {
        if (root.service && root.service.busy === "plan") return "Jev is planning this sheet …"
        if (!root.st || !root.st.sheet || !root.st.sheet.plan) return ""
        return Model.dependencyText(root.tasks) || "no task builds on another"
      }
      noteColor: root.service && root.service.busy === "plan" ? root.look.accent : root.look.fg
      spinning: !!(root.service && root.service.busy === "plan")

      Label {
        visible: !!(root.st && root.st.sheet && root.st.sheet.plan)
        look: root.look
        secondary: true
        text: "bar: effort, as Jev rates it"
      }
    }

    Column {
      width: parent.width
      spacing: Style.space(2)

      Repeater {
        model: root.tasks

        BorderSurface {
          id: taskRow
          required property var modelData
          readonly property bool current: root.st.task === modelData.number
          readonly property bool hot: taskMouse.containsMouse

          width: parent.width
          implicitHeight: Math.max(Style.space(30), taskText.implicitHeight + Style.space(10))
          radius: Style.cornerRadius
          color: current ? Style.selectedFillFor(root.look.fg, root.look.accent)
            : (hot ? Style.hoverFillFor(root.look.fg, root.look.accent) : "transparent")
          borderSpec: current ? Border.controlSpec("selected", root.look.fg, root.look.accent) : Border.none()

          onCurrentChanged: if (current) Qt.callLater(function() { root.reveal(taskRow) })

          MouseArea {
            id: taskMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            enabled: !root.busy
            onClicked: if (!taskRow.current) root.request("select_task", { number: taskRow.modelData.number })
          }

          Rectangle {
            visible: taskRow.current
            x: Style.space(4)
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(3)
            height: parent.height - Style.space(14)
            radius: width / 2
            color: root.look.accent
          }

          Label {
            id: number
            x: Style.space(14)
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(22)
            look: root.look
            text: taskRow.modelData.number
            font.bold: true
          }

          EffortMeter {
            id: bars
            anchors.left: number.right
            anchors.verticalCenter: parent.verticalCenter
            look: root.look
            effort: taskRow.modelData.effort === null ? -1 : taskRow.modelData.effort
            word: taskRow.modelData.effortWord
          }

          Label {
            id: taskText
            anchors.left: bars.visible ? bars.right : number.right
            anchors.leftMargin: bars.visible ? Style.space(10) : 0
            anchors.right: after.left
            anchors.rightMargin: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            look: root.look
            font.bold: taskRow.current
            text: {
              var m = taskRow.modelData
              if (m.title) return m.title
              var first = m.text.split("\n")[0].trim()
              return first.length > 90 ? first.slice(0, 89) + "…" : first
            }
          }

          Label {
            id: after
            anchors.right: warn.left
            anchors.rightMargin: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            look: root.look
            secondary: true
            text: taskRow.modelData.after.length ? "builds on " + taskRow.modelData.after.join(", ") : ""
          }

          Text {
            id: warn
            anchors.right: parent.right
            anchors.rightMargin: Style.space(10)
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: taskRow.modelData.missing.length ? Glyphs.alert : ""
            color: root.look.urgent
            font.family: root.look.font
            font.pixelSize: Style.font.icon
          }
        }
      }
    }

    // ---- The task's text --------------------------------------------------------

    BorderSurface {
      id: textCard
      width: parent.width
      visible: root.currentTask !== null
      property bool expanded: false
      implicitHeight: textColumn.implicitHeight + Style.space(20)
      radius: Style.cornerRadius
      color: root.look.veil
      borderSpec: Border.none()

      Connections {
        target: root
        function onCurrentTaskChanged() { textCard.expanded = false }
      }

      Column {
        id: textColumn
        x: Style.space(12)
        y: Style.space(10)
        width: parent.width - Style.space(24)
        spacing: Style.space(6)

        // Which part the prompt asks for. A long part is often a prompt of
        // its own; the whole task is the default.
        Flow {
          width: parent.width
          spacing: Style.space(4)
          visible: root.parts.length > 0

          Label {
            height: Style.space(24)
            verticalAlignment: Text.AlignVCenter
            rightPadding: Style.space(4)
            look: root.look
            secondary: true
            text: "Ask for"
          }

          Chip {
            look: root.look
            text: "the whole task"
            selected: root.part === ""
            enabled: !root.busy
            horizontalPadding: Style.space(8)
            verticalPadding: Style.space(2)
            tooltipText: "One prompt for all parts"
            onClicked: if (!selected) root.request("select_part", { label: "" })
          }

          Repeater {
            model: root.parts

            Chip {
              required property var modelData
              look: root.look
              text: modelData.label + ")"
              selected: root.part === modelData.label
              enabled: !root.busy
              horizontalPadding: Style.space(8)
              verticalPadding: Style.space(2)
              tooltipText: "Only part " + modelData.label + ") - the earlier parts stay in the prompt for reference"
              onClicked: if (!selected) root.request("select_part", { label: modelData.label })
            }
          }
        }

        Label {
          id: fullText
          width: parent.width
          look: root.look
          wrapMode: Text.WordWrap
          elide: Text.ElideRight
          maximumLineCount: textCard.expanded ? 400 : (root.chosenPart ? 5 : 3)
          font.pixelSize: Style.font.bodySmall
          lineHeight: 1.15
          text: {
            if (!root.currentTask) return ""
            if (root.chosenPart) return root.chosenPart.label + ")  " + root.chosenPart.text
            return root.currentTask.text
          }
        }

        Row {
          spacing: Style.space(10)

          Button {
            visible: fullText.truncated || textCard.expanded
            text: textCard.expanded ? "Show less" : "Show all"
            fontSize: Style.font.caption
            verticalPadding: Style.space(2)
            horizontalPadding: Style.space(6)
            foreground: root.look.muted
            fontFamily: root.look.font
            onClicked: textCard.expanded = !textCard.expanded
          }

          Label {
            anchors.verticalCenter: parent.verticalCenter
            visible: !!(root.currentTask && root.currentTask.missing.length)
            look: root.look
            secondary: true
            color: root.look.urgent
            text: root.currentTask && root.currentTask.missing.length
              ? "Aufgabe " + root.currentTask.missing.join(", ") + " is not in the lecture notes - paste it yourself"
              : ""
          }
        }
      }
    }

    Item { width: 1; height: Style.space(4); visible: root.currentTask !== null }

    // ---- Context ----------------------------------------------------------------

    SectionTitle {
      look: root.look
      visible: root.currentTask !== null
      text: "In the prompt"
      detail: root.st && root.st.jev.usage ? "Jev: " + root.st.jev.usage : ""
    }

    BorderSurface {
      id: contextCard
      width: parent.width
      visible: root.currentTask !== null
      implicitHeight: contextColumn.implicitHeight + Style.space(22)
      radius: Style.cornerRadius
      color: Style.normalFillFor(root.look.fg, root.look.accent)
      borderSpec: Border.controlSpec("normal", root.look.fg, root.look.accent)

      readonly property var summary: root.st ? root.st.summary : null
      readonly property bool empty: !summary || (summary.statements === 0 && summary.earlier === 0)
      readonly property bool asking: !!(root.service && root.service.busy === "jev")
      readonly property var items: summary && summary.items ? summary.items : []
      property bool allItems: false

      Connections {
        target: root
        function onCurrentTaskChanged() { contextCard.allItems = false }
      }

      Column {
        id: contextColumn
        x: Style.space(12)
        y: Style.space(11)
        width: parent.width - Style.space(24)
        spacing: Style.space(6)

        // While Jev picks, the card says so right where its pick will appear.
        Row {
          visible: contextCard.asking
          spacing: Style.space(8)

          Text {
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: Glyphs.loading
            color: root.look.accent
            font.family: root.look.font
            font.pixelSize: Style.font.icon
            RotationAnimation on rotation {
              running: contextCard.asking
              from: 0; to: 360; duration: 900
              loops: Animation.Infinite
            }
          }

          Label {
            anchors.verticalCenter: parent.verticalCenter
            look: root.look
            color: root.look.accent
            font.bold: true
            text: "Jev is reading the task and the lecture notes …"
          }
        }

        Label {
          width: parent.width
          visible: !contextCard.asking
          look: root.look
          font.bold: true
          text: {
            var s = contextCard.summary
            if (!s) return ""
            if (contextCard.empty) return "No lecture notes - the prompt carries the task alone"
            var parts = []
            var slides = s.slides || 0
            if (s.statements - slides) parts.push(Model.plural(s.statements - slides, "statement"))
            if (slides) parts.push(Model.plural(slides, "slide"))
            if (s.proofs) parts.push(Model.plural(s.proofs, "proof"))
            if (s.earlier) parts.push(Model.plural(s.earlier, "earlier task"))
            return parts.join(" · ")
          }
        }

        Label {
          width: parent.width
          look: root.look
          secondary: true
          visible: text !== "" && !contextCard.asking
          wrapMode: Text.WordWrap
          maximumLineCount: 3
          text: {
            if (!root.st) return ""
            var dropped = root.st.jev.dropped || []
            var left = dropped.length
              ? " · " + Model.plural(dropped.length, "proof") + " left out to stay under "
                + Math.round(root.st.limit / 1000) + "k characters: " + dropped.slice(0, 3).join(", ")
                + (dropped.length > 3 ? " …" : "")
              : ""
            if (root.st.jev.picked === "jev") return Glyphs.sparkle + " Picked by Jev" + left
            if (root.st.jev.picked === "edited") return Glyphs.sparkle + " Picked by Jev, changed by hand"
            if (contextCard.empty && contextCard.summary && !contextCard.summary.hasNotes)
              return "No lecture notes read in for this course."
            return ""
          }
        }

        Column {
          width: parent.width
          visible: !contextCard.asking

          Repeater {
            model: contextCard.allItems ? contextCard.items : contextCard.items.slice(0, 5)

            Rectangle {
              id: itemRow
              required property var modelData
              readonly property bool openable: !!modelData.target

              width: contextColumn.width
              height: itemLabel.implicitHeight + Style.space(6)
              radius: Style.cornerRadius
              color: itemMouse.containsMouse ? Style.hoverFillFor(root.look.fg, root.look.accent)
                                             : "transparent"

              MouseArea {
                id: itemMouse
                anchors.fill: parent
                enabled: itemRow.openable
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openSource(itemRow.modelData.target)
              }

              Label {
                id: itemLabel
                x: Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - x - openIcon.width - Style.space(12)
                look: root.look
                secondary: !itemMouse.containsMouse
                font.pixelSize: Style.font.caption
                text: "·  " + itemRow.modelData.text
              }

              Text {
                id: openIcon
                visible: itemRow.openable
                anchors.right: parent.right
                anchors.rightMargin: Style.space(6)
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: Glyphs.openExternal
                color: itemMouse.containsMouse ? root.look.accent : root.look.muted
                font.family: root.look.font
                font.pixelSize: Style.font.bodySmall
              }
            }
          }

          Button {
            visible: contextCard.items.length > 5
            text: contextCard.allItems ? "Show less"
                                       : "… and " + (contextCard.items.length - 5) + " more"
            fontSize: Style.font.caption
            verticalPadding: Style.space(2)
            horizontalPadding: Style.space(6)
            foreground: root.look.muted
            fontFamily: root.look.font
            onClicked: contextCard.allItems = !contextCard.allItems
          }
        }

        Item { width: 1; height: Style.space(2) }

        Row {
          spacing: Style.space(6)

          Button {
            iconText: Glyphs.pencil
            text: contextCard.empty ? "Choose context" : "Edit context"
            bordered: true
            foreground: root.look.fg
            fontFamily: root.look.font
            tooltipText: "E · tick chapters, statements, proofs and earlier tasks"
            onClicked: root.navigate("context")
          }

          Button {
            visible: !!(root.st && root.st.jev.configured)
            iconText: Glyphs.sparkle
            text: root.st && root.st.jev.picked ? "Ask Jev again" : "Let Jev pick"
            bordered: true
            enabled: !root.busy
            opacity: enabled ? 1 : 0.45
            foreground: root.look.fg
            fontFamily: root.look.font
            tooltipText: "A · Jev reads the task and picks the statements, proofs and earlier tasks it needs"
            onClicked: root.askJev()
          }

          Button {
            visible: !contextCard.empty
            iconText: Glyphs.close
            text: "Clear"
            enabled: !root.busy
            foreground: root.look.muted
            fontFamily: root.look.font
            tooltipText: "The prompt then carries the task alone"
            onClicked: root.request("clear_selection")
          }
        }
      }
    }

    Item { width: 1; height: Style.space(6) }
  }
}
