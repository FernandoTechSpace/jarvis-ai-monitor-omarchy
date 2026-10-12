import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// Agent list on the left, the selected agent's detail on the right.
Panel {
  id: root
  moduleName: "fernando.jarvis-ai-monitor"
  ipcTarget: "fernando.jarvis-ai-monitor"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property var collector: null
  readonly property var barIdentity: hostWidget || root

  readonly property var agents: collector ? collector.agents : []
  readonly property real now: collector ? collector.now : 0

  readonly property color fg: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(fg, 1.4)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  property int sel: 0
  readonly property var agent: agents.length > 0 ? agents[Math.min(sel, agents.length - 1)] : null
  readonly property var connections: Model.connections(agent)

  function tint(alpha) { return Qt.rgba(fg.r, fg.g, fg.b, alpha) }

  function open() {
    detailScroll.contentY = 0
    root.controller.show()
  }
  function close() { root.controller.hide() }
  function toggle() { root.opened ? root.close() : root.open() }

  function select(index) {
    if (agents.length === 0) return
    root.sel = Math.max(0, Math.min(agents.length - 1, index))
    detailScroll.contentY = 0
  }

  function scroll(direction) {
    var max = Math.max(0, detailScroll.contentHeight - detailScroll.height)
    detailScroll.contentY = Math.max(0, Math.min(max, detailScroll.contentY + direction * 80))
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(820))
    contentHeight: panel.fittedContentHeight(Style.space(590))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onMoveRequested: function(dx, dy) {
        if (dy !== 0) root.select(root.sel + dy)
        if (dx !== 0) root.scroll(dx)
      }
      onActivateRequested: { if (root.collector) root.collector.refresh() }
      onCloseRequested: root.close()
      onTabRequested: function(direction) { if (root.bar) root.bar.switchPanelFrom(root.barIdentity, direction) }
      onTextKey: function(t) {
        if (t === "r" || t === "R") { if (root.collector) root.collector.refresh() }
        else if (t >= "1" && t <= "9") root.select(Number(t) - 1)
      }

      Item {
        id: header
        width: parent.width
        height: headerTitle.implicitHeight + Style.space(14)

        JarvisIcon {
          id: headerIcon
          anchors.verticalCenter: headerTitle.verticalCenter
          iconSize: Style.font.display
          color: root.fg
          spinning: root.hostWidget ? root.hostWidget.busy === true : false
        }

        Text {
          id: headerTitle
          anchors.left: headerIcon.right
          anchors.leftMargin: Style.space(10)
          text: "Jarvis AI Monitor"
          textFormat: Text.PlainText
          color: root.fg
          font.family: root.fontFamily
          font.pixelSize: Style.font.display
          font.bold: true
        }

        Text {
          anchors.right: parent.right
          anchors.verticalCenter: headerTitle.verticalCenter
          text: Model.plural(root.agents.length, "agent") + "  ·  "
            + Model.plural(Model.runningCount(root.agents), "session") + " running"
          textFormat: Text.PlainText
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
        }

        PanelSeparator {
          anchors.bottom: parent.bottom
          width: parent.width
          foreground: root.fg
        }
      }

      Text {
        anchors.centerIn: parent
        visible: root.agents.length === 0
        text: !root.collector || !root.collector.loaded ? "Looking for agents…"
          : (root.collector.error !== "" ? root.collector.error : "No AI agents found on this machine.")
        textFormat: Text.PlainText
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
      }

      Column {
        id: sidebar
        visible: root.agents.length > 0
        width: Style.space(230)
        anchors.top: header.bottom
        anchors.topMargin: Style.space(12)
        anchors.bottom: hint.top
        anchors.bottomMargin: Style.space(8)
        spacing: Style.space(6)

        Repeater {
          model: root.agents

          Rectangle {
            id: entry
            required property int index
            required property var modelData
            readonly property bool selected: root.sel === index
            readonly property bool live: modelData.sessions.length > 0

            width: sidebar.width
            height: entryColumn.implicitHeight + Style.space(14)
            color: selected ? root.tint(0.08) : "transparent"
            border.width: 1
            border.color: selected ? Color.accent : root.tint(0.18)

            Column {
              id: entryColumn
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.margins: Style.space(10)
              spacing: Style.space(2)

              Text {
                width: parent.width
                text: (entry.live ? "● " : "○ ") + entry.modelData.name
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: entry.modelData.unattended ? Color.urgent : (entry.live ? root.fg : root.dim)
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: true
              }

              Text {
                width: parent.width
                text: Model.agentSubtitle(entry.modelData, root.now)
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
              }
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.select(entry.index)
            }
          }
        }
      }

      Flickable {
        id: detailScroll
        visible: root.agent !== null
        anchors.left: sidebar.right
        anchors.leftMargin: Style.space(16)
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.topMargin: Style.space(12)
        anchors.bottom: hint.top
        anchors.bottomMargin: Style.space(8)
        contentWidth: width
        contentHeight: detail.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height

        Column {
          id: detail
          width: detailScroll.width
          spacing: Style.space(6)

          Text {
            text: root.agent ? root.agent.name : ""
            textFormat: Text.PlainText
            color: root.fg
            font.family: root.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
          }

          Note { text: root.agent ? root.agent.path : "" }
          Note {
            visible: root.agent && root.agent.error !== undefined
            text: root.agent && root.agent.error ? "Could not read this agent's config: " + root.agent.error : ""
            color: Color.urgent
          }

          SectionTitle { text: "LAST ACTION" }
          Line {
            label: root.agent && root.agent.lastAction ? Model.ago(root.agent.lastAction.at, root.now) : "never"
            value: Model.actionText(root.agent ? root.agent.lastAction : null)
              + (root.agent && root.agent.lastAction && root.agent.lastAction.cwd ? "\nin " + root.agent.lastAction.cwd : "")
          }

          SectionTitle { text: "SESSIONS" }
          Note { visible: root.agent && root.agent.sessions.length === 0; text: "Not running." }
          Repeater {
            model: root.agent ? root.agent.sessions : []

            Line {
              required property var modelData
              label: "pid " + modelData.pid
              valueColor: modelData.unattended ? Color.urgent : root.fg
              value: (modelData.name ? modelData.name + "  ·  " : "")
                + (modelData.status ? modelData.status + "  ·  " : "")
                + "up " + Model.duration(root.now - modelData.startedAt)
                + (modelData.version ? "  ·  v" + modelData.version : "")
                + "\n" + modelData.cwd
                + "\nmode: " + (modelData.mode || "default")
                + (modelData.lastAction ? "\n" + Model.actionText(modelData.lastAction)
                  + "  ·  " + Model.ago(modelData.lastAction.at, root.now) : "")
            }
          }

          SectionTitle { text: "NETWORK CONNECTIONS" }
          Note {
            visible: root.connections.length === 0
            text: root.agent && root.agent.sessions.length > 0 ? "No open sockets right now." : "Only shown while the agent runs."
          }
          Repeater {
            model: root.connections

            Note {
              required property var modelData
              text: Model.connectionLine(modelData)
              color: root.fg
            }
          }

          SectionTitle { text: "MCP SERVERS AND CONNECTORS" }
          Note { visible: root.agent && root.agent.mcp.length === 0; text: "None configured." }
          Repeater {
            model: root.agent ? root.agent.mcp : []

            Line {
              required property var modelData
              label: modelData.type
              valueColor: modelData.enabled ? root.fg : root.dim
              value: modelData.name + (modelData.enabled ? "" : "  (disabled)")
                + "\n" + modelData.target + "  ·  " + modelData.scope
            }
          }

          SectionTitle { text: "PERMISSIONS" }
          Line {
            visible: root.agent && root.agent.defaultMode !== ""
            label: "default mode"
            value: root.agent ? root.agent.defaultMode : ""
          }
          Repeater {
            model: root.agent ? root.agent.facts : []

            Line {
              required property var modelData
              label: modelData.label.toLowerCase()
              value: modelData.value
            }
          }
          Note {
            visible: root.agent && root.agent.rules.length === 0
            text: "No explicit allow or deny rules: the agent asks according to its mode."
          }
          Repeater {
            model: root.agent ? root.agent.rules : []

            Line {
              required property var modelData
              label: modelData.effect
              valueColor: modelData.effect === "deny" ? Color.urgent : root.fg
              value: modelData.rule + "   (" + modelData.scope + ")"
            }
          }
        }
      }

      Text {
        id: hint
        anchors.bottom: parent.bottom
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: "↑ ↓  agent   ·   ← →  scroll   ·   r / Enter  refresh   ·   Esc  close"
        textFormat: Text.PlainText
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
      }
    }
  }

  component SectionTitle: Column {
    property alias text: header.text
    width: detail.width
    topPadding: Style.space(8)

    PanelSectionHeader {
      id: header
      foreground: root.fg
      fontFamily: root.fontFamily
      fontSize: Style.font.body
    }
  }

  component Note: Text {
    width: detail.width
    textFormat: Text.PlainText
    wrapMode: Text.WrapAnywhere
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  component Line: Item {
    property string label: ""
    property string value: ""
    property color valueColor: root.fg

    width: detail.width
    height: Math.max(labelText.implicitHeight, valueText.implicitHeight)

    Text {
      id: labelText
      width: Style.space(110)
      text: parent.label
      textFormat: Text.PlainText
      elide: Text.ElideRight
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
    }

    Text {
      id: valueText
      anchors.left: labelText.right
      anchors.leftMargin: Style.space(10)
      anchors.right: parent.right
      text: parent.value
      textFormat: Text.PlainText
      wrapMode: Text.Wrap
      color: parent.valueColor
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
    }
  }
}
