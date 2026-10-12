.pragma library

// Pure formatting helpers for the collector snapshot.
function duration(seconds) {
  var s = Math.max(0, Math.round(seconds))
  if (s < 60) return s + "s"
  if (s < 3600) return Math.floor(s / 60) + "m"
  if (s < 86400) return Math.floor(s / 3600) + "h " + Math.floor(s % 3600 / 60) + "m"
  return Math.floor(s / 86400) + "d " + Math.floor(s % 86400 / 3600) + "h"
}

function ago(at, now) {
  if (!(at > 0)) return "never"
  var s = now - at
  return s < 5 ? "just now" : duration(s) + " ago"
}

function plural(n, word) {
  return n + " " + word + (n === 1 ? "" : "s")
}

function endpoint(conn) {
  var host = conn.host.indexOf(":") >= 0 ? "[" + conn.host + "]" : conn.host
  return host + ":" + conn.port
}

function connectionLine(conn) {
  var verb = conn.kind === "listen" ? "listening on " : (conn.kind === "local" ? "local " : "")
  return conn.proto + "  " + verb + endpoint(conn)
    + (conn.count > 1 ? "  ×" + conn.count : "")
    + "   (" + conn.process + ", pid " + conn.pid + ")"
}

// Every session's sockets in one list.
function connections(agent) {
  var out = []
  if (!agent) return out
  for (var i = 0; i < agent.sessions.length; i++) out = out.concat(agent.sessions[i].connections)
  return out
}

function runningCount(agents) {
  var n = 0
  for (var i = 0; i < agents.length; i++) n += agents[i].sessions.length
  return n
}

function anyUnattended(agents) {
  for (var i = 0; i < agents.length; i++) if (agents[i].unattended) return true
  return false
}

function anyBusy(agents) {
  for (var i = 0; i < agents.length; i++)
    for (var j = 0; j < agents[i].sessions.length; j++)
      if (agents[i].sessions[j].status === "busy") return true
  return false
}

// The agent whose last action is the most recent.
function latest(agents) {
  var best = null
  for (var i = 0; i < agents.length; i++) {
    var a = agents[i]
    if (a.lastAction && (!best || a.lastAction.at > best.lastAction.at)) best = a
  }
  return best
}

function agentSubtitle(agent, now) {
  if (agent.sessions.length > 0) return plural(agent.sessions.length, "session") + " running"
  return agent.lastAction ? "last active " + ago(agent.lastAction.at, now) : "installed, never used"
}

function actionText(action) {
  if (!action) return "No recorded activity"
  return action.summary !== "" ? action.summary : "Activity on disk (no detail available)"
}

function tooltip(agents, now) {
  if (agents.length === 0) return "No AI agents found"
  var n = runningCount(agents)
  var text = n > 0 ? plural(n, "agent session") + " running" : plural(agents.length, "agent") + " installed, none running"
  var last = latest(agents)
  if (last) text += "\n" + last.name + ": " + actionText(last.lastAction) + " · " + ago(last.lastAction.at, now)
  if (anyUnattended(agents)) text += "\nA session is running without permission prompts"
  return text
}
