import QtQuick
import Quickshell.Io

// Runs collect.py on a timer and exposes its snapshot.
Item {
  id: root
  visible: false

  property bool running: true
  property int interval: 5000

  property var agents: []
  property real now: Date.now() / 1000
  property bool loaded: false
  property string error: ""

  readonly property string script: String(Qt.resolvedUrl("collect.py")).replace(/^file:\/\//, "")

  function refresh() {
    if (!proc.running) proc.running = true
  }

  function apply(text) {
    try {
      var snapshot = JSON.parse(text)
      root.agents = snapshot.agents || []
      root.now = snapshot.generatedAt || Date.now() / 1000
      root.error = ""
    } catch (e) {
      root.error = "Collector returned no data"
    }
    root.loaded = true
  }

  Process {
    id: proc
    command: ["python3", root.script]
    stdout: StdioCollector {
      onStreamFinished: root.apply(text)
    }
  }

  Timer {
    interval: root.interval
    running: root.running
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }
}
