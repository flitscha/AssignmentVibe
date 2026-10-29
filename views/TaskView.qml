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
// S the newest slide deck, A ask Jev, E edit the context, P preview the
// prompt, R read my attempt again, W copy only my attempt. A line of the
// context opens the script or slide deck at its page when clicked, an
// earlier task its sheet; its box takes it out of the prompt.
Flickable {
  id: root

  property var service: null
  property var look: null
  readonly property bool editing: false

  signal navigate(string target)
  signal copyRequested()
  signal copyWorkRequested()
  signal closeRequested()

  readonly property var st: service ? service.state : null
  readonly property bool busy: !!(service && service.busy !== "")
  readonly property var tasks: st ? st.tasks : []
  readonly property var decks: st && st.course ? (st.course.decks || []) : []
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
    else if (t === "s" || t === "S") openNewestDeck()
    else if (t === "a" || t === "A") askJev()
    else if (t === "e" || t === "E") navigate("context")
    else if (t === "p" || t === "P") { if (currentTask) navigate("prompt") }
    else if (t === "r" || t === "R") readWork()
    else if (t === "w" || t === "W") copyWorkRequested()
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

  // A line of the context card in or out of the prompt, by its box. Out, it
  // stays on the card (hub.set_item).
  function toggleLine(line) {
    if (line.kind && !busy) request("set_item", { kind: line.kind, id: line.id, on: !!line.off })
  }

  function openNewestDeck() {
    for (var i = 0; i < decks.length; i++) if (decks[i].newest) openDeck(decks[i].path)
  }

  function openDeck(path) {
    if (service) service.request("open_deck", { path: path }, function(r) {
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

  readonly property var work: st ? st.work : null
  readonly property var attempt: work ? work.attempt : null

  // Reading shows its result where it lands: the card scrolls to the top.
  function readWork() {
    if (!(work && work.notebook && currentTask)) return
    revealTop(workTitle)
    request("read_work", {}, function() { revealAfterLayout.restart() })
  }

  // The Column places the new lines a frame later; scrolling right away would
  // clamp to the height of the card while it still said "Reading …".
  Timer {
    id: revealAfterLayout
    interval: 60
    onTriggered: root.revealTop(workTitle)
  }

  function revealTop(item) {
    var p = item.mapToItem(column, 0, 0)
    contentY = Math.max(0, Math.min(contentHeight - height, p.y - Style.space(8)))
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

    // ---- Course, material, sheet, plan: a line each, labelled on the left ------

    FieldRow {
      look: root.look
      text: "Course"

      Repeater {
        model: root.st ? root.st.courses : []

        Chip {
          required property var modelData
          look: root.look
          text: modelData.name
          fontSize: Style.font.caption
          horizontalPadding: Style.space(8)
          verticalPadding: Style.space(3)
          selected: root.st.course && root.st.course.slug === modelData.slug
          dimmed: modelData.sheets === 0 && !modelData.hasNotes
          enabled: !root.busy
          tooltipText: (modelData.sheets === 1 ? "1 sheet" : modelData.sheets + " sheets")
            + (modelData.hasNotes ? " · lecture notes read in" : " · no lecture notes")
          onClicked: if (!selected) root.request("select_course", { slug: modelData.slug })
        }
      }
    }

    // What there is to read for the course: the script, and every slide deck
    // by its number - one click each, the newest in the accent colour.
    FieldRow {
      look: root.look
      text: "Material"
      visible: notesButton.visible || root.decks.length > 0

      SmallButton {
        id: notesButton
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

      // A gap between the script and the slides.
      Item { width: Style.space(6); height: 1; visible: notesButton.visible && root.decks.length > 0 }

      Repeater {
        model: root.decks

        SmallButton {
          required property var modelData
          required property int index
          look: root.look
          text: String(index + 1)
          foreground: modelData.newest ? root.look.accent : root.look.fg
          tooltipText: "Slides: " + modelData.title + " · " + modelData.path.split("/").pop()
            + (modelData.newest ? " · the newest (S)" : "")
          onClicked: root.openDeck(modelData.path)
        }
      }
    }

    FieldRow {
      look: root.look
      text: "Sheet"
      visible: !!(root.st && root.st.sheets.length)

      SmallButton {
        visible: !!(root.st && root.st.sheet)
        look: root.look
        iconText: Glyphs.pdf
        text: "Open PDF"
        tooltipText: "O · the sheet in the PDF viewer"
        onClicked: root.openSheet()
      }

      Item { width: Style.space(6); height: 1 }

      Repeater {
        model: root.st ? root.st.sheets : []

        Chip {
          required property var modelData
          look: root.look
          text: modelData.label
          fontSize: Style.font.caption
          horizontalPadding: Style.space(8)
          verticalPadding: Style.space(3)
          selected: !!(root.st.sheet && root.st.sheet.id === modelData.id)
          dot: modelData.newest
          enabled: !root.busy
          tooltipText: "Sheet " + modelData.label + " · " + modelData.tasks + " tasks"
            + (modelData.newest ? " · the newest" : "") + (modelData.planned ? " · planned by Jev" : "")
          onClicked: if (!selected) root.request("select_sheet", { id: modelData.id })
        }
      }
    }

    // Jev's plan, and what it may pick from: the course's extra scripts
    // (uni.json "zusatzskript") and its slides. Off, Jev does not look there
    // and the prompt does not carry what was picked there.
    FieldRow {
      id: jevRow
      look: root.look
      text: "Jev"
      readonly property var extraNames: root.st && root.st.summary ? (root.st.summary.extraNames || []) : []
      readonly property bool hasSlides: !!(root.st && root.st.summary && root.st.summary.hasSlides)
      visible: planButton.visible || extraNames.length > 0 || hasSlides

      SmallButton {
        id: planButton
        visible: !!(root.st && root.st.sheet && root.st.jev.configured)
        look: root.look
        iconText: Glyphs.sparkle
        text: root.st && root.st.sheet && root.st.sheet.plan ? "Plan again" : "Plan with Jev"
        enabled: !root.busy
        tooltipText: "Jev picks every task's context at once, rates how much work each is, "
          + "and finds which task builds on which"
          + (root.st && root.st.jev.usage ? "\nJev so far: " + root.st.jev.usage : "")
        onClicked: root.request("plan")
      }

      Item { width: Style.space(6); height: 1 }

      OptionRow {
        visible: jevRow.extraNames.length > 0
        small: true
        look: root.look
        text: jevRow.extraNames.join(", ")
        hint: "Let Jev pick from this script too, and put what is picked there into the prompt"
        checked: !!(root.st && root.st.summary && root.st.summary.extra)
        enabled: !root.busy
        onToggled: root.request("set_extra", { on: !checked })
      }

      OptionRow {
        visible: jevRow.hasSlides
        small: true
        look: root.look
        text: "Slides"
        hint: "Let Jev pick slides too, and put what is picked there into the prompt. "
          + "Off by default where the course has a script"
        checked: !!(root.st && root.st.summary && root.st.summary.slidesOn)
        enabled: !root.busy
        onToggled: root.request("set_slides", { on: !checked })
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
      // The sheet's date here rather than beside its chips: fourteen of them
      // fill that line.
      note: {
        if (root.service && root.service.busy === "plan") return "Jev is planning this sheet …"
        var parts = []
        if (root.st && root.st.sheet && root.st.sheet.discussion)
          parts.push("discussed " + root.st.sheet.discussion)
        if (root.st && root.st.sheet && root.st.sheet.plan)
          parts.push(Model.dependencyText(root.tasks) || "no task builds on another")
        return parts.join("  ·  ")
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
          implicitHeight: Math.max(Style.space(24), taskText.implicitHeight + Style.space(6))
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
            height: parent.height - Style.space(10)
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

    HeaderRow {
      look: root.look
      visible: root.currentTask !== null
      text: "In the prompt"
      spinning: contextCard.asking
      noteColor: contextCard.asking ? root.look.accent : root.look.fg
      note: {
        if (contextCard.asking) return "Jev is reading the task and the lecture notes …"
        var s = contextCard.summary
        if (!s) return ""
        if (contextCard.empty) return "the task alone"
        var parts = []
        var slides = s.slides || 0
        if (s.statements - slides) parts.push(Model.plural(s.statements - slides, "statement"))
        if (slides) parts.push(Model.plural(slides, "slide"))
        if (s.proofs) parts.push(Model.plural(s.proofs, "proof"))
        if (s.earlier) parts.push(Model.plural(s.earlier, "earlier task"))
        var picked = root.st.jev.picked === "jev" ? "  ·  " + Glyphs.sparkle + " picked by Jev"
          : root.st.jev.picked === "edited" ? "  ·  " + Glyphs.sparkle + " by Jev, changed by hand" : ""
        return parts.join(" · ") + picked
      }

      SmallButton {
        look: root.look
        iconText: Glyphs.pencil
        text: contextCard.empty && !contextCard.items.length ? "Choose" : "Edit"
        tooltipText: "E · tick chapters, statements, proofs and earlier tasks"
        onClicked: root.navigate("context")
      }

      SmallButton {
        visible: contextCard.items.length > 0
        look: root.look
        iconText: Glyphs.close
        text: "Clear"
        enabled: !root.busy
        tooltipText: "The prompt then carries the task alone"
        onClicked: root.request("clear_selection")
      }
    }

    BorderSurface {
      id: contextCard
      width: parent.width
      // Only when there is something to list: counts and buttons are above.
      visible: root.currentTask !== null && !asking && (lines.length > 0 || infoLabel.text !== "")
      implicitHeight: contextColumn.implicitHeight + Style.space(16)
      radius: Style.cornerRadius
      color: Style.normalFillFor(root.look.fg, root.look.accent)
      borderSpec: Border.controlSpec("normal", root.look.fg, root.look.accent)

      readonly property var summary: root.st ? root.st.summary : null
      readonly property bool empty: !summary || (summary.statements === 0 && summary.earlier === 0)
      readonly property bool asking: !!(root.service && root.service.busy === "jev")
      readonly property var items: summary && summary.items ? summary.items : []
      property bool allItems: false
      // Every line chosen, the unticked ones too: they stay, Jev's pick is
      // worth reading even where the prompt is better off without it.
      readonly property var lines: items

      Connections {
        target: root
        function onCurrentTaskChanged() { contextCard.allItems = false }
      }

      Column {
        id: contextColumn
        x: Style.space(10)
        y: Style.space(8)
        width: parent.width - Style.space(20)
        spacing: Style.space(4)

        Label {
          id: infoLabel
          width: parent.width
          look: root.look
          secondary: true
          visible: text !== "" && !contextCard.asking
          wrapMode: Text.WordWrap
          maximumLineCount: 3
          text: {
            if (!root.st) return ""
            var dropped = root.st.jev.dropped || []
            if (root.st.jev.picked === "jev" && dropped.length)
              return Model.plural(dropped.length, "proof") + " left out to stay under "
                + Math.round(root.st.limit / 1000) + "k characters: " + dropped.slice(0, 3).join(", ")
                + (dropped.length > 3 ? " …" : "")
            if (contextCard.empty && contextCard.summary && !contextCard.summary.hasNotes)
              return "No lecture notes read in for this course."
            return ""
          }
        }

        Column {
          width: parent.width
          visible: !contextCard.asking

          Repeater {
            id: itemRepeater
            readonly property var shown: contextCard.allItems ? contextCard.lines
                                                              : contextCard.lines.slice(0, 5)
            model: shown

            Column {
              id: itemBlock
              required property var modelData
              required property int index
              // An extra script's lines come together, after the course's own
              // (hub.selection_items); its name heads them.
              readonly property bool startsExtra: !!modelData.extra
                && (index === 0 || itemRepeater.shown[index - 1].extra !== modelData.extra)

              width: contextColumn.width

              Label {
                visible: itemBlock.startsExtra
                topPadding: Style.space(4)
                bottomPadding: Style.space(2)
                look: root.look
                secondary: true
                font.bold: true
                font.pixelSize: Style.font.caption
                text: "From " + itemBlock.modelData.extra
              }

              Rectangle {
                id: itemRow
                readonly property var modelData: itemBlock.modelData
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

                CheckBox {
                  id: itemBox
                  x: Style.space(6)
                  anchors.verticalCenter: parent.verticalCenter
                  visible: !!itemRow.modelData.kind
                  look: root.look
                  value: itemRow.modelData.off ? 0 : 2
                }

                // Above the row's own area: the box takes the click, the
                // rest of the line opens it.
                MouseArea {
                  anchors.fill: itemBox
                  anchors.margins: -Style.space(4)
                  enabled: itemBox.visible && !root.busy
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.toggleLine(itemRow.modelData)
                }

                Label {
                  id: itemLabel
                  x: itemBox.visible ? itemBox.x + itemBox.width + Style.space(8) : Style.space(8)
                  anchors.verticalCenter: parent.verticalCenter
                  width: parent.width - x - openIcon.width - Style.space(12)
                  look: root.look
                  secondary: !itemMouse.containsMouse || !!itemRow.modelData.off
                  font.pixelSize: Style.font.caption
                  font.strikeout: !!itemRow.modelData.off
                  text: (itemBox.visible ? "" : "·  ") + itemRow.modelData.text
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
          }

          Button {
            visible: contextCard.lines.length > 5
            text: contextCard.allItems ? "Show less"
                                       : "… and " + (contextCard.lines.length - 5) + " more"
            fontSize: Style.font.caption
            verticalPadding: Style.space(2)
            horizontalPadding: Style.space(6)
            foreground: root.look.muted
            fontFamily: root.look.font
            onClicked: contextCard.allItems = !contextCard.allItems
          }
        }
      }
    }

    // ---- My attempt -------------------------------------------------------------

    Item { width: 1; height: Style.space(4); visible: workCard.visible }

    SectionTitle {
      id: workTitle
      look: root.look
      visible: workCard.visible
      text: "My attempt"
      detail: {
        if (!root.work || !root.work.notebook) return ""
        var a = root.attempt
        var pages = a && a.pages && a.pages.length
          ? " · p. " + (a.pages.length > 1 ? a.pages[0] + "-" + a.pages[a.pages.length - 1] : a.pages[0])
          : ""
        return root.work.notebook + pages
      }
    }

    BorderSurface {
      id: workCard
      width: parent.width
      visible: root.currentTask !== null && root.work !== null
      implicitHeight: workColumn.implicitHeight + Style.space(22)
      radius: Style.cornerRadius
      color: Style.normalFillFor(root.look.fg, root.look.accent)
      borderSpec: Border.controlSpec("normal", root.look.fg, root.look.accent)

      readonly property bool reading: !!(root.service && (root.service.busy === "read_work"
        || root.service.busy === "copy_work" || root.service.busy === "copy_prompt"))
      readonly property var shown: root.attempt && root.attempt.lines ? root.attempt.lines : []
      property bool allLines: false

      Connections {
        target: root
        function onCurrentTaskChanged() { workCard.allLines = false }
      }

      Column {
        id: workColumn
        x: Style.space(12)
        y: Style.space(11)
        width: parent.width - Style.space(24)
        spacing: Style.space(6)

        Label {
          width: parent.width
          look: root.look
          font.bold: true
          color: workCard.reading ? root.look.accent : root.look.fg
          wrapMode: Text.WordWrap
          text: {
            var w = root.work, a = root.attempt
            if (!w) return ""
            if (workCard.reading) return "Reading my handwriting …"
            if (!w.notebook) return "No Xournal++ notebook for this sheet in the course folder"
            if (!w.reader) return "StrokeReader not found - set strokereader_dir in settings.json"
            if (!a) return "Not read yet - copying the prompt reads it"
            if (a.status === "nothing") return "Nothing written for this task yet"
            if (a.status === "no-reader") return "StrokeReader failed: " + a.error
            return Model.plural(workCard.shown.length, "line") + " read"
              + (a.stale ? " · notebook changed since" : "")
          }
        }

        Column {
          width: parent.width
          visible: workCard.shown.length > 0 && !workCard.reading
          spacing: Style.space(1)

          Repeater {
            model: workCard.allLines ? workCard.shown : workCard.shown.slice(0, 8)

            Text {
              required property var modelData
              width: workColumn.width
              textFormat: Text.PlainText
              elide: Text.ElideRight
              text: modelData
              color: root.look.fg
              font.family: root.look.font
              font.pixelSize: Style.font.caption
            }
          }
        }

        Row {
          spacing: Style.space(6)

          Button {
            iconText: Glyphs.sync
            text: root.attempt ? "Read again" : "Read now"
            bordered: true
            visible: !!(root.work && root.work.notebook && root.work.reader)
            enabled: !root.busy
            opacity: enabled ? 1 : 0.45
            foreground: root.look.fg
            fontFamily: root.look.font
            tooltipText: "R · find this task in the notebook and read what is written for it"
              + (root.part ? " (up to part " + root.part + ")" : "")
            onClicked: root.readWork()
          }

          Button {
            visible: workCard.shown.length > 8
            text: workCard.allLines ? "Show less" : "… and " + (workCard.shown.length - 8) + " more"
            fontSize: Style.font.caption
            verticalPadding: Style.space(2)
            horizontalPadding: Style.space(6)
            foreground: root.look.muted
            fontFamily: root.look.font
            onClicked: workCard.allLines = !workCard.allLines
          }
        }
      }
    }

    Item { width: 1; height: Style.space(6) }
  }
}
