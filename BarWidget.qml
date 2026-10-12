import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

// Bar icon and host for the detail panel.
BarWidget {
  id: root
  moduleName: "fernando.jarvis-ai-monitor"

  readonly property alias collector: collector

  readonly property int sessionCount: Model.runningCount(collector.agents)
  readonly property bool unattended: Model.anyUnattended(collector.agents)
  readonly property bool busy: Model.anyBusy(collector.agents)

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function togglePanel() { if (panelLoader.item) panelLoader.item.toggle() }

  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
    if ("collector" in target) target.collector = collector
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  Collector {
    id: collector
    // The panel shows live sockets and "ago" times, so sample faster while it is open.
    interval: root.opened ? 2000 : Number(root.setting("interval", 5000))
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  IpcHandler {
    target: "fernando.jarvis-ai-monitor"

    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.togglePanel() }
    function refresh(): void { collector.refresh() }
  }

  // Our own HUD mark, painted in the bar's foreground so it follows the theme
  // like the glyph icons next to it: dimmed while no agent runs, the theme's
  // urgent color while a session runs without permission prompts, and the
  // outer ring turns while an agent is working.
  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    iconComponent: Component {
      Item {
        JarvisIcon {
          anchors.centerIn: parent
          iconSize: button.opticalSize * 1.1
          color: button.active ? button.activeColor : button.foreground
          spinning: root.busy
        }
      }
    }
    dimmed: root.sessionCount === 0
    active: root.unattended
    tooltipText: Model.tooltip(collector.agents, collector.now)
    onPressed: function(b) {
      if (b === Qt.MiddleButton) collector.refresh()
      else root.togglePanel()
    }
  }
}
