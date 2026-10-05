import QtQuick
import qs.Commons
import qs.Ui
import "../Glyphs.js" as Glyphs
import "../Model.js" as Model
import "../controls"

// What goes into the prompt: the outline of the lecture notes, each chapter
// and section with a box that ticks all of its statements, each statement
// with its own box and one for its proof; below them the tasks of earlier
// sheets. The ticking happens here (Model.js), and the result is saved a
// moment after the last click.
//
// Keys: ↑↓ move, → open, ← close, Space or Enter tick, P tick the proof,
// O open the script or slides at that page, / search, Esc leaves the search.
Item {
  id: root

  property var service: null
  property var look: null
  readonly property bool editing: search.activeFocus

  readonly property var st: service ? service.state : null
  readonly property bool busy: !!(service && service.busy !== "")

  property var ctx: null
  property var idx: null
  property var sel: Model.cleared()
  property var expanded: ({})
  property string mode: "all"
  property int cursor: -1

  readonly property var rows: ctx && idx ? Model.rows(ctx, idx, sel, expanded, search.text, mode) : []
  readonly property var totals: ctx && idx ? Model.totals(ctx, idx, sel) : null
  // The footer's meter follows the ticks before they are saved.
  readonly property int liveSize: totals ? totals.size : (st && st.summary ? st.summary.size : 0)

  // ---- Loading and saving -----------------------------------------------------

  function load() {
    var c = service ? service.context : null
    if (!c) return
    ctx = c
    idx = Model.index(c)
    sel = Model.selectionFrom(c)
    expanded = Model.initiallyExpanded(c, idx, sel)
    cursor = -1
  }

  Connections {
    target: root.service
    function onContextReloaded() { root.load() }
  }

  // Whatever moved the state elsewhere - a course switch, another task - means
  // a different selection to show.
  readonly property string where: st && st.course
    ? st.course.slug + "|" + (st.sheet ? st.sheet.id : "") + "|" + st.task : ""
  onWhereChanged: if (service) { flush(); service.request("context") }

  Component.onCompleted: if (service) service.request("context")
  Component.onDestruction: flush()

  function change(next) {
    if (busy) return
    sel = next
    saveTimer.restart()
  }

  function flush() {
    if (!saveTimer.running || !service) return
    saveTimer.stop()
    service.request("set_selection", Model.toRequest(sel))
  }

  Timer {
    id: saveTimer
    interval: 250
    onTriggered: root.service.request("set_selection", Model.toRequest(root.sel))
  }

  function reloadWith(cmd, args) {
    if (busy || !service) return
    flush()
    var a = args || {}
    a.withContext = true
    service.request(cmd, a)
  }

  // ---- Clicks -------------------------------------------------------------------

  function toggleRow(r) {
    if (!r) return
    if (r.kind === "node") change(Model.toggleNode(ctx, idx, sel, r.key))
    else if (r.kind === "statement") change(Model.toggleIds(sel, [r.id]))
    else if (r.kind === "sheet") change(Model.toggleEarlier(sel, Model.sheetRefs(idx, r.key)))
    else if (r.kind === "earlier") change(Model.toggleEarlier(sel, [r.ref]))
  }

  function toggleProof(r) {
    if (r && r.kind === "statement" && r.hasProof) change(Model.toggleProof(ctx, idx, sel, r.id))
  }

  // Opening a PDF races with nothing, so it works while Jev is busy too.
  function openRow(r) {
    if (service && r && (r.kind === "node" || r.kind === "statement") && r.page)
      service.request("open_source", { target: Model.target(r) })
  }

  function setExpanded(r, open) {
    if (!r || (r.kind !== "node" && r.kind !== "sheet")) return
    var id = (r.kind === "node" ? "n:" : "s:") + r.key
    var next = Object.assign({}, expanded)
    if (open) next[id] = true
    else delete next[id]
    expanded = next
  }

  // ---- Keys ---------------------------------------------------------------------

  function selectable(r) { return r.kind !== "header" && r.kind !== "empty" }

  function move(dx, dy) {
    if (!rows.length) return
    if (dy !== 0) {
      var i = cursor
      do { i += dy } while (i >= 0 && i < rows.length && !selectable(rows[i]))
      if (i >= 0 && i < rows.length) cursor = i
      else if (cursor < 0) cursor = dy > 0 ? firstSelectable() : -1
    } else if (cursor >= 0 && cursor < rows.length) {
      var r = rows[cursor]
      if (dx > 0) setExpanded(r, true)
      else if (r.expanded) setExpanded(r, false)
      else cursor = parentRow(cursor)
    }
  }

  function firstSelectable() {
    for (var i = 0; i < rows.length; i++) if (selectable(rows[i])) return i
    return -1
  }

  function parentRow(i) {
    var level = rows[i].level
    for (var k = i - 1; k >= 0; k--)
      if (selectable(rows[k]) && rows[k].level < level) return k
    return i
  }

  function activate() {
    if (cursor < 0 || cursor >= rows.length) return false
    toggleRow(rows[cursor])
    return true
  }

  function key(t) {
    if (t === "/") search.forceActiveFocus()
    else if ((t === "p" || t === "P") && cursor >= 0) toggleProof(rows[cursor])
    else if ((t === "o" || t === "O") && cursor >= 0) openRow(rows[cursor])
  }

  onRowsChanged: if (cursor >= rows.length) cursor = rows.length - 1

  // ---- Top ----------------------------------------------------------------------

  Column {
    id: top
    width: parent.width
    spacing: Style.space(8)

    Item {
      width: parent.width
      height: Math.max(countsColumn.implicitHeight, topButtons.implicitHeight)

      Column {
        id: countsColumn
        anchors.left: parent.left
        anchors.right: topButtons.left
        anchors.rightMargin: Style.space(10)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(2)

        Label {
          width: parent.width
          look: root.look
          font.bold: true
          text: {
            var t = root.totals
            if (!t) return root.ctx ? "" : "Loading …"
            if (!t.statements && !t.earlier) return "Nothing chosen - the prompt carries the task alone"
            var parts = [Model.plural(t.statements, Model.noun(root.ctx))]
            if (t.withProof) parts.push(t.proofs + " of " + Model.plural(t.withProof, "proof"))
            if (t.earlier) parts.push(Model.plural(t.earlier, "earlier task"))
            return parts.join(" · ")
          }
        }

        Label {
          width: parent.width
          look: root.look
          secondary: true
          visible: text !== ""
          text: {
            if (!root.st || !root.st.task) return ""
            var dropped = root.st.jev.dropped || []
            var who = root.st.jev.picked === "jev"
              ? " · picked by Jev" + (dropped.length ? ", " + Model.plural(dropped.length, "proof")
                                                       + " left out for length" : "")
              : root.st.jev.picked === "edited" ? " · picked by Jev, changed by hand" : ""
            return "For task " + root.st.task + (root.st.sheet ? " of sheet " + root.st.sheet.label : "") + who
          }
        }
      }

      Row {
        id: topButtons
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(6)

        Button {
          visible: !!(root.st && root.st.jev.configured)
          readonly property bool asking: !!(root.service && root.service.busy === "jev")
          iconText: asking ? Glyphs.loading : Glyphs.sparkle
          iconSpinning: asking
          text: asking ? "Jev is picking …" : "Let Jev pick"
          bordered: true
          enabled: !root.busy && !!(root.st && root.st.task !== null)
          opacity: enabled || asking ? 1 : 0.45
          foreground: root.look.fg
          fontFamily: root.look.font
          tooltipText: "Replaces the selection with what Jev judges the task to need"
          onClicked: root.reloadWith("jev")
        }

        Button {
          iconText: Glyphs.close
          text: "Clear"
          bordered: true
          enabled: !root.busy && !!(root.totals && (root.totals.statements || root.totals.earlier))
          opacity: enabled ? 1 : 0.45
          foreground: root.look.fg
          fontFamily: root.look.font
          onClicked: root.change(Model.cleared())
        }
      }
    }

    Item {
      width: parent.width
      height: search.implicitHeight

      TextField {
        id: search
        anchors.left: parent.left
        anchors.right: modeRow.left
        anchors.rightMargin: Style.space(8)
        placeholderText: Glyphs.search + "  Search statements and tasks   ( / )"
        foreground: root.look.fg
        font.family: root.look.font
        Keys.onEscapePressed: {
          if (text !== "") text = ""
          else focus = false
        }
        Keys.onDownPressed: { focus = false; root.cursor = root.firstSelectable() }
        onTextChanged: root.cursor = -1
      }

      Row {
        id: modeRow
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(2)

        Button {
          text: "Outline"
          selected: root.mode === "all"
          foreground: root.look.fg
          fontFamily: root.look.font
          tooltipText: "Every chapter, with what is chosen in it"
          onClicked: { root.mode = "all"; root.cursor = -1 }
        }

        Button {
          text: "Chosen"
          selected: root.mode === "chosen"
          foreground: root.look.fg
          fontFamily: root.look.font
          tooltipText: "Only what goes into the prompt"
          onClicked: { root.mode = "chosen"; root.cursor = -1 }
        }
      }
    }

    Flow {
      width: parent.width
      spacing: Style.space(14)
      visible: !!root.ctx

      OptionRow {
        visible: !!(root.ctx && root.ctx.hasAlgorithms)
        look: root.look
        text: "Algorithms"
        hint: "Count the script's algorithms as statements - wanted when a task says to implement one"
        checked: !!(root.ctx && root.ctx.algorithms)
        enabled: !root.busy
        onToggled: root.reloadWith("set_algorithms", { on: !checked })
      }

      OptionRow {
        // Slides have no proofs of their own to add.
        visible: !!(root.ctx && root.ctx.statements.some(function(s) { return s.proofSize > 0 }))
        look: root.look
        text: "All proofs"
        hint: "Proofs often give the solution away - one by one, beside each statement, is usually better"
        checked: root.sel.allProofs
        enabled: !root.busy
        onToggled: root.change(Model.setAllProofs(root.sel, !checked))
      }
    }
  }

  // ---- The list -----------------------------------------------------------------

  Flickable {
    id: list
    anchors.top: top.bottom
    anchors.topMargin: Style.space(8)
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    contentWidth: width
    contentHeight: rowColumn.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    interactive: contentHeight > height

    function reveal(item) {
      var p = item.mapToItem(rowColumn, 0, 0)
      if (p.y < contentY) contentY = Math.max(0, p.y - Style.space(24))
      else if (p.y + item.height > contentY + height)
        contentY = Math.min(contentHeight - height, p.y + item.height - height + Style.space(8))
    }

    Column {
      id: rowColumn
      width: list.width
      spacing: Style.space(1)

      Repeater {
        model: root.rows

        ContextRow {
          id: contextRow
          required property var modelData
          required property int index
          width: rowColumn.width
          look: root.look
          row: modelData
          hasCursor: root.cursor === index
          enabled: !root.busy
          onToggled: { root.cursor = index; root.toggleRow(modelData) }
          onExpandToggled: { root.cursor = index; root.setExpanded(modelData, !modelData.expanded) }
          onProofToggled: { root.cursor = index; root.toggleProof(modelData) }
          onOpenRequested: { root.cursor = index; root.openRow(modelData) }
          onHasCursorChanged: if (hasCursor) Qt.callLater(function() { list.reveal(contextRow) })
        }
      }
    }
  }
}
