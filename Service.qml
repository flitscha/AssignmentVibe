import QtQuick
import Quickshell
import Quickshell.Io

// The link to the Python side. Runs `assignmentvibe serve` for as long as the
// shell does and talks JSON lines with it (assignmentvibe/api.py): every
// answer carries the whole `state`, which is all the bar pill and the panel
// draw from.
//
// The backend is found in this plugin's own folder - the repository is the
// plugin, bin/assignmentvibe beside this file - so panel and backend are
// always the same version. Failing that, `assignmentvibe` on PATH.
//
// Also the IPC target `assignmentvibe`, for keybindings:
//   qs ipc -p $OMARCHY_PATH/shell call assignmentvibe toggle
//   ... call assignmentvibe open context
//   ... call assignmentvibe copy
Item {
  id: root

  property var shell: null
  property var manifest: null

  // What the backend last said; null until it has started.
  property var state: null
  // The context editor's data, only fetched while that tab is open.
  property var context: null
  // The last response's messages, for the panel's banner.
  property var messages: []
  property int messageSerial: 0
  // "jev", "plan" or "ingest" while one runs, else "".
  property string busy: ""
  property real busySince: 0
  property string backendError: ""
  readonly property bool ready: state !== null

  signal openRequested(string tab)
  signal closeRequested()
  signal contextReloaded()

  readonly property string pluginDir: {
    var url = Qt.resolvedUrl(".").toString()
    return decodeURIComponent(url.replace(/^file:\/\//, "")).replace(/\/$/, "")
  }

  readonly property string contextFile: {
    var base = Quickshell.env("XDG_STATE_HOME") || (Quickshell.env("HOME") + "/.local/state")
    return base + "/assignmentvibe/context.json"
  }

  // ---- Requests -----------------------------------------------------------------

  property int nextId: 1
  property var pending: ({})

  readonly property var slowCommands: ({ jev: true, plan: true, ingest: true })

  function request(cmd, args, callback) {
    if (!backend.running) {
      if (callback) callback({ ok: false, messages: [] })
      return
    }
    if (slowCommands[cmd]) {
      if (busy !== "") return
      busy = cmd
      busySince = Date.now()
    }
    var id = nextId++
    if (callback || slowCommands[cmd]) {
      var p = pending
      p[id] = { cmd: cmd, callback: callback || null }
      pending = p
    }
    backend.write(JSON.stringify({ id: id, cmd: cmd, args: args || {} }) + "\n")
  }

  function receive(line) {
    var response
    try {
      response = JSON.parse(line)
    } catch (e) {
      console.warn("assignmentvibe: not JSON from the backend:", line)
      return
    }
    if (response.state) root.state = response.state
    if (response.context !== undefined && response.context !== null) {
      root.context = response.context
      root.contextReloaded()
    }
    if (response.messages && response.messages.length) {
      root.messages = response.messages
      root.messageSerial++
    }
    if (slowCommands[response.cmd] && busy === response.cmd) busy = ""
    backendError = ""
    var entry = pending[response.id]
    if (entry) {
      var p = pending
      delete p[response.id]
      pending = p
      if (entry.callback) entry.callback(response)
    }
  }

  function dismissMessages() {
    messages = []
  }

  // ---- The backend process ------------------------------------------------------

  property int restarts: 0

  Process {
    id: backend
    stdinEnabled: true
    command: ["sh", "-c",
      "dir=$(readlink -f \"$1\"); bin=\"$dir/bin/assignmentvibe\"; "
      + "[ -x \"$bin\" ] || bin=$(command -v assignmentvibe) || { echo 'assignmentvibe not found' >&2; exit 127; }; "
      + "exec \"$bin\" serve",
      "sh", root.pluginDir]

    stdout: SplitParser {
      onRead: function(data) { root.receive(data) }
    }
    stderr: SplitParser {
      onRead: function(data) {
        console.warn("assignmentvibe backend:", data)
        root.lastStderr = data
      }
    }

    onExited: function(code) {
      root.busy = ""
      root.pending = ({})
      root.backendError = code === 127
        ? "The assignmentvibe command was not found."
        : "The backend stopped" + (root.lastStderr ? ": " + root.lastStderr : ".")
      restartTimer.interval = Math.min(30000, 1000 * Math.pow(2, root.restarts))
      root.restarts++
      restartTimer.start()
    }
    onStarted: stableTimer.restart()
  }

  property string lastStderr: ""

  Timer {
    id: restartTimer
    onTriggered: backend.running = true
  }

  // A backend that stays up for a minute is healthy again.
  Timer {
    id: stableTimer
    interval: 60000
    onTriggered: root.restarts = 0
  }

  Component.onCompleted: backend.running = true
  Component.onDestruction: backend.running = false

  // ---- Changes made elsewhere ---------------------------------------------------

  // `assignmentvibe jev` in a terminal, or a second panel: the context file is
  // what they all write, so a change there means the state moved.
  FileView {
    path: root.contextFile
    watchChanges: true
    printErrors: false
    onFileChanged: refreshTimer.restart()
  }

  Timer {
    id: refreshTimer
    interval: 150
    onTriggered: if (root.busy === "") root.request("state")
  }

  // ---- IPC ------------------------------------------------------------------------

  IpcHandler {
    target: "assignmentvibe"

    function toggle(): void { root.openRequested("toggle") }
    function open(tab: string): void { root.openRequested(tab || "task") }
    function close(): void { root.closeRequested() }
    function copy(): void { root.request("copy_prompt") }
  }
}
