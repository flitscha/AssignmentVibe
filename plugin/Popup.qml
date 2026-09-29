import QtQuick
import Quickshell
import qs.Commons
import qs.Ui
import "Glyphs.js" as Glyphs
import "controls"
import "views"

// The panel under the bar pill.
//
//   Task        course, sheet and task side by side, and the context in short
//   Context     the lecture notes and earlier tasks that go into the prompt
//   Follow-ups  canned replies for the chat, one click each
//   Setup       read in new PDFs, config files, Jev's costs, keys
//
// "Copy prompt" sits at the bottom of the first two, where the eye ends up
// once the setup is right. Keys: 1-4 or Tab switch tabs, Enter copies, Esc
// closes; each tab adds its own (see SetupView's list).
KeyboardPanel {
  id: panel

  property var service: null
  property string tab: "task"

  readonly property var tabs: [
    { key: "task", label: "Task", icon: Glyphs.tasks },
    { key: "context", label: "Context", icon: Glyphs.book },
    { key: "followups", label: "Follow-ups", icon: Glyphs.reply },
    { key: "setup", label: "Setup", icon: Glyphs.cog }
  ]

  readonly property var st: service ? service.state : null
  readonly property bool busy: !!(service && service.busy !== "")
  readonly property bool hasTask: !!(st && st.task !== null && st.task !== undefined && st.sheet)
  readonly property bool showFooter: tab === "task" || tab === "context" || tab === "prompt"

  // A focused text field needs every key, including Esc and Tab.
  readonly property bool editing: currentView !== null && currentView.editing === true
  readonly property var currentView: viewLoader.item

  signal closeRequested()

  function switchTab(direction) {
    var i = 0
    for (var k = 0; k < tabs.length; k++) if (tabs[k].key === tab) i = k
    tab = tabs[(i + direction + tabs.length) % tabs.length].key
  }

  function copyPrompt() {
    if (!service || !hasTask || busy) return
    service.request("copy_prompt", {}, function(r) {
      if (r.ok) panel.closeRequested()
    })
  }

  function openChat() {
    if (!service) return
    service.request("open_chat", {}, function(r) {
      if (r.ok) panel.closeRequested()
    })
  }

  // KeyboardPanel's default property only takes visual items, so the
  // non-visual pieces hang off properties.
  readonly property Look theme: Look { bar: panel.bar }

  focusTarget: keys
  contentWidth: panel.fittedContentWidth(Style.space(660))
  contentHeight: panel.fittedContentHeight(Style.space(800))

  onOpenChanged: {
    if (open && service) {
      service.request("state")
      service.dismissMessages()
    }
  }
  // Closing a text field must hand the keys back, or 1-4 and Esc stop working.
  onEditingChanged: if (!editing) keys.forceActiveFocus()
  onTabChanged: keys.forceActiveFocus()

  PanelKeyCatcher {
    id: keys
    anchors.fill: parent
    blocked: panel.editing
    onCloseRequested: {
      if (panel.tab === "prompt") panel.tab = "task"
      else panel.closeRequested()
    }
    onTabRequested: function(direction) { panel.switchTab(direction) }
    onMoveRequested: function(dx, dy) {
      if (panel.currentView && typeof panel.currentView.move === "function")
        panel.currentView.move(dx, dy)
    }
    onActivateRequested: {
      if (panel.currentView && typeof panel.currentView.activate === "function"
          && panel.currentView.activate())
        return
      panel.copyPrompt()
    }
    onTextKey: function(t) {
      var n = parseInt(t)
      if (n >= 1 && n <= panel.tabs.length) {
        panel.tab = panel.tabs[n - 1].key
        return
      }
      if (panel.currentView && typeof panel.currentView.key === "function")
        panel.currentView.key(t)
    }

    // ---- Tabs -------------------------------------------------------------------

    Item {
      id: header
      width: parent.width
      height: tabRow.height

      Row {
        id: tabRow
        spacing: Style.space(4)

        Repeater {
          model: panel.tabs

          Button {
            required property var modelData
            required property int index
            text: modelData.label
            iconText: modelData.icon
            selected: panel.tab === modelData.key || (modelData.key === "task" && panel.tab === "prompt")
            foreground: panel.theme.fg
            fontFamily: panel.theme.font
            tooltipText: "Key " + (index + 1)
            onClicked: panel.tab = modelData.key
          }
        }
      }

      // Where a job runs is shown where its result lands (the task list, the
      // context card); this corner says it on every tab.
      Row {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(6)

        Text {
          visible: panel.busy
          anchors.verticalCenter: parent.verticalCenter
          textFormat: Text.PlainText
          text: Glyphs.loading
          color: panel.theme.accent
          font.family: panel.theme.font
          font.pixelSize: Style.font.body
          RotationAnimation on rotation {
            running: panel.busy
            from: 0; to: 360; duration: 900
            loops: Animation.Infinite
          }
        }

        Label {
          anchors.verticalCenter: parent.verticalCenter
          width: Math.min(implicitWidth, header.width - tabRow.width - Style.space(40))
          look: panel.theme
          secondary: !panel.busy
          color: panel.busy ? panel.theme.accent : panel.theme.muted
          font.pixelSize: Style.font.caption
          text: {
            if (panel.busy) {
              if (panel.service.busy === "jev") return "Jev is picking the context"
              if (panel.service.busy === "plan") return "Jev is planning the sheet"
              return "Reading in new PDFs"
            }
            return panel.st && panel.st.course
              ? panel.st.course.name + (panel.st.semester ? "  ·  " + panel.st.semester : "") : ""
          }
        }
      }
    }

    // ---- What happened ------------------------------------------------------------

    Column {
      id: notices
      anchors.top: header.bottom
      anchors.topMargin: visible ? Style.space(10) : 0
      width: parent.width
      spacing: Style.space(6)
      // From the conditions, not the banners' `visible`: a child of an
      // invisible column reads as invisible itself, so that would never flip.
      readonly property bool any: !!(panel.service && panel.service.backendError)
        || messageBanner.message !== null
      visible: any
      height: any ? implicitHeight : 0

      Banner {
        id: errorBanner
        width: parent.width
        visible: !!(panel.service && panel.service.backendError)
        look: panel.theme
        level: "warn"
        title: "The backend is not running"
        body: panel.service ? panel.service.backendError + " Trying again …" : ""
        onDismissed: {}
      }

      Banner {
        id: messageBanner
        width: parent.width
        readonly property var message: panel.service && panel.service.messages.length
          ? panel.service.messages[panel.service.messages.length - 1] : null
        visible: message !== null && !panel.busy
        look: panel.theme
        level: message ? message.level : "info"
        title: message ? message.title : ""
        body: {
          if (!message) return ""
          var more = panel.service.messages.length - 1
          return message.body + (more > 0 ? "\n(+ " + more + " more)" : "")
        }
        onDismissed: panel.service.dismissMessages()

        Timer {
          id: fadeTimer
          interval: 9000
          onTriggered: panel.service.dismissMessages()
        }

        Connections {
          target: panel.service
          // A new message gets its full time, not what was left of the last.
          function onMessageSerialChanged() {
            fadeTimer.stop()
            Qt.callLater(function() {
              if (messageBanner.visible && messageBanner.level !== "warn") fadeTimer.restart()
            })
          }
        }
      }
    }

    // ---- The tab ------------------------------------------------------------------

    Loader {
      id: viewLoader
      anchors.top: notices.bottom
      anchors.topMargin: Style.space(10)
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: panel.showFooter ? footer.top : parent.bottom
      anchors.bottomMargin: panel.showFooter ? Style.space(10) : 0
      active: panel.service !== null && panel.visible
      sourceComponent: {
        if (panel.st && panel.st.error && panel.tab !== "setup") return panel.problemView
        if (panel.tab === "context") return panel.contextView
        if (panel.tab === "followups") return panel.followUpsView
        if (panel.tab === "setup") return panel.setupView
        if (panel.tab === "prompt") return panel.promptView
        return panel.taskView
      }
    }

    // ---- Copy ---------------------------------------------------------------------

    Item {
      id: footer
      visible: panel.showFooter
      anchors.bottom: parent.bottom
      width: parent.width
      height: visible ? footerRow.implicitHeight + Style.space(10) : 0

      PanelSeparator {
        anchors.top: parent.top
        foreground: panel.theme.fg
      }

      Row {
        id: footerRow
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        spacing: Style.space(6)

        Button {
          id: copyButton
          iconText: Glyphs.copy
          text: panel.hasTask ? "Copy prompt · task " + panel.st.task : "Copy prompt"
          selected: true
          bordered: true
          enabled: panel.hasTask && !panel.busy
          opacity: enabled ? 1 : 0.45
          foreground: panel.theme.fg
          fontFamily: panel.theme.font
          horizontalPadding: Style.space(14)
          verticalPadding: Style.space(8)
          tooltipText: "Enter · puts the prompt on the clipboard and closes the panel"
          onClicked: panel.copyPrompt()
        }

        Button {
          iconText: Glyphs.eye
          text: panel.tab === "prompt" ? "Back" : "Preview"
          bordered: true
          enabled: panel.hasTask
          opacity: enabled ? 1 : 0.45
          foreground: panel.theme.fg
          fontFamily: panel.theme.font
          verticalPadding: Style.space(8)
          tooltipText: "P · the prompt exactly as it will be copied"
          onClicked: panel.tab = panel.tab === "prompt" ? "task" : "prompt"
        }

        Button {
          iconText: Glyphs.chat
          text: "Open chat"
          bordered: true
          foreground: panel.theme.fg
          fontFamily: panel.theme.font
          verticalPadding: Style.space(8)
          tooltipText: "Opens claude.ai in a new window"
          onClicked: panel.openChat()
        }
      }

      Column {
        anchors.right: parent.right
        anchors.verticalCenter: footerRow.verticalCenter
        width: Style.space(150)
        spacing: Style.space(4)
        visible: !!(panel.st && panel.st.summary)

        readonly property var summary: panel.st ? panel.st.summary : null
        readonly property int size: panel.tab === "context" && panel.currentView && panel.currentView.liveSize !== undefined
          ? panel.currentView.liveSize : (summary ? summary.size : 0)
        readonly property int limit: panel.st ? panel.st.limit : 1

        Label {
          width: parent.width
          horizontalAlignment: Text.AlignRight
          look: panel.theme
          secondary: true
          text: (parent.size / 1000).toFixed(1) + "k of " + Math.round(parent.limit / 1000) + "k characters"
          color: parent.size > parent.limit ? panel.theme.urgent : panel.theme.muted
        }

        Meter {
          width: parent.width
          look: panel.theme
          value: parent.size
          limit: parent.limit
        }
      }
    }
  }

  // ---- Views ----------------------------------------------------------------------

  property Component taskView: Component {
    TaskView {
      service: panel.service
      look: panel.theme
      onNavigate: function(target) { panel.tab = target }
      onCopyRequested: panel.copyPrompt()
      onCloseRequested: panel.closeRequested()
    }
  }

  property Component contextView: Component {
    ContextView { service: panel.service; look: panel.theme }
  }

  property Component followUpsView: Component {
    FollowUpsView {
      service: panel.service
      look: panel.theme
      onCloseRequested: panel.closeRequested()
    }
  }

  property Component setupView: Component {
    SetupView {
      service: panel.service
      look: panel.theme
      onCloseRequested: panel.closeRequested()
    }
  }

  property Component promptView: Component {
    PromptView {
      service: panel.service
      look: panel.theme
      onBack: panel.tab = "task"
    }
  }

  property Component problemView: Component {
    Column {
      spacing: Style.space(12)
      readonly property bool editing: false

      Label {
        width: parent.width
        look: panel.theme
        text: panel.st && panel.st.error ? panel.st.error.title : ""
        font.bold: true
        font.pixelSize: Style.font.title
      }

      Label {
        width: parent.width
        look: panel.theme
        secondary: true
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
        text: panel.st && panel.st.error ? panel.st.error.body : ""
      }

      Button {
        iconText: Glyphs.pencil
        text: "Open uni.json"
        bordered: true
        foreground: panel.theme.fg
        fontFamily: panel.theme.font
        onClicked: panel.service.request("open_config", { name: "uni.json" }, function(r) {
          if (r.ok) panel.closeRequested()
        })
      }
    }
  }
}
