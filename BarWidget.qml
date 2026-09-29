import QtQuick
import Quickshell
import qs.Commons
import qs.Ui
import "Glyphs.js" as Glyphs

// The bar pill: "󰷉 Optimierung A3" - the course and the task, the two things
// worth checking without a click. The tooltip lists what the prompt carries.
//
//   left click    the panel
//   right click   the panel on the follow-ups, which are wanted mid-chat
//   middle click  copy the prompt straight away
BarWidget {
  id: root
  moduleName: "felix.assignmentvibe"

  // The service is created by the shell, possibly after this widget, and a
  // function call in a binding would never be re-evaluated. Poll until it
  // shows up.
  property var service: null

  Timer {
    interval: 300
    repeat: true
    triggeredOnStart: true
    running: root.service === null
    onTriggered: {
      if (root.bar && root.bar.shell && typeof root.bar.shell.serviceFor === "function")
        root.service = root.bar.shell.serviceFor(root.moduleName)
    }
  }

  readonly property var st: service ? service.state : null
  readonly property bool hasTask: !!(st && st.course && st.task !== null && st.task !== undefined)
  readonly property bool working: !!(service && service.busy !== "")
  // "A3" or, with one part asked for, "A3b".
  readonly property string taskLabel: hasTask ? " A" + st.task + (st.part || "") : ""

  readonly property string pillText: {
    if (working) return Glyphs.sparkle + (hasTask ? " " + st.course.short + taskLabel : "")
    if (!hasTask) return Glyphs.school
    return Glyphs.school + " " + st.course.short + taskLabel
  }

  readonly property string tooltip: {
    if (!service) return "AssignmentVibe"
    if (service.backendError) return "AssignmentVibe: " + service.backendError
    if (!st) return "AssignmentVibe - starting"
    if (st.error) return "AssignmentVibe: " + st.error.title
    if (!hasTask) return "AssignmentVibe - no task selected\nClick to pick one"
    var sheet = st.sheet ? "Sheet " + st.sheet.label + ", " : ""
    var lines = st.summary.lines.slice(0, 12)
    if (st.summary.lines.length > 12) lines.push("… and " + (st.summary.lines.length - 12) + " more")
    var notes = lines.length ? lines.map(function(l) { return "  " + l }).join("\n") : "  none"
    return st.course.name + "\n" + sheet + "task " + st.task + (st.part ? ", part " + st.part + ")" : "")
      + "\n\nIn the prompt:\n" + notes
      + "\n\nLeft: panel · Right: follow-ups · Middle: copy prompt"
  }

  function pressed(button) {
    if (!service) return
    if (button === Qt.RightButton) {
      openOn("followups")
    } else if (button === Qt.MiddleButton) {
      service.request("copy_prompt")
    } else {
      if (popupOpen) close()
      else openOn("task")
    }
  }

  function openOn(tab) {
    popup.tab = tab
    open()
  }

  Connections {
    target: root.service
    function onOpenRequested(tab) {
      if (tab === "toggle") {
        if (root.popupOpen) root.close()
        else root.openOn("task")
      } else {
        root.openOn(tab)
      }
    }
    function onCloseRequested() { root.close() }
  }

  // ---- Popup shape contract (open/close/opened on the widget root) ----------

  property bool popupOpen: false
  property bool popoutSwitchClosing: false
  readonly property bool opened: popupOpen

  function open() { popupOpen = true }
  function close() { popupOpen = false }
  function toggle() { popupOpen = !popupOpen }
  function closeForPopoutSwitch() {
    popoutSwitchClosing = true
    close()
    Qt.callLater(function() { root.popoutSwitchClosing = false })
  }

  // ---- Pill ---------------------------------------------------------------------

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.pillText
    horizontalMargin: 6
    tooltipText: root.tooltip
    onPressed: function(b) { root.pressed(b) }
  }

  SequentialAnimation {
    id: pulse
    running: root.working
    loops: Animation.Infinite
    NumberAnimation { target: button; property: "opacity"; to: 0.35; duration: 600; easing.type: Easing.InOutSine }
    NumberAnimation { target: button; property: "opacity"; to: 1.0; duration: 600; easing.type: Easing.InOutSine }
    onRunningChanged: if (!running) button.opacity = 1
  }

  Popup {
    id: popup
    anchorItem: button
    bar: root.bar
    owner: root
    open: root.popupOpen
    service: root.service
    onCloseRequested: root.close()
  }
}
