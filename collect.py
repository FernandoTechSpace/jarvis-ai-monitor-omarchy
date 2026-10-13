#!/usr/bin/python3
"""Print one JSON snapshot of the AI coding agents on this machine.

Read-only: it looks at /proc, `ss`, and each agent's own config and session
files. Nothing is written and no agent is contacted.
"""

import calendar
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

HOME = os.path.expanduser("~")
TAIL_BYTES = 512 * 1024
MAX_TEXT = 160


def home(*parts):
    return os.path.join(HOME, *parts)


# Each agent: the binary names it runs as, plus where it keeps its state.
# `state` paths only feed the "last activity" fallback (newest mtime).
AGENTS = [
    {"id": "claude", "name": "Claude Code", "bins": ["claude"],
     "state": [home(".claude", "projects"), home(".claude", "history.jsonl")]},
    {"id": "codex", "name": "Codex", "bins": ["codex"],
     "state": [home(".codex", "sessions"), home(".codex", "history.jsonl")]},
    {"id": "opencode", "name": "opencode", "bins": ["opencode"],
     "state": [home(".local", "share", "opencode", "storage"), home(".local", "share", "opencode", "log")]},
    {"id": "gemini", "name": "Gemini CLI", "bins": ["gemini"],
     "state": [home(".gemini", "tmp"), home(".gemini", "history")]},
    {"id": "antigravity", "name": "Antigravity CLI", "bins": ["agy"],
     "state": [home(".gemini", "antigravity-cli", "conversations"),
               home(".gemini", "antigravity-cli", "history.jsonl")]},
    {"id": "cursor-agent", "name": "Cursor Agent", "bins": ["cursor-agent"],
     "state": [home(".cursor", "chats"), home(".cursor", "projects")]},
    {"id": "crush", "name": "Crush", "bins": ["crush"],
     "state": [home(".local", "share", "crush"), home(".config", "crush")]},
    {"id": "copilot", "name": "GitHub Copilot CLI", "bins": ["copilot"],
     "state": [home(".copilot", "session-state"), home(".copilot", "logs")]},
]

INTERPRETERS = {"node", "bun", "deno", "python", "python3"}


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read_toml(path):
    if tomllib is None:
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (OSError, ValueError):
        return {}


def clip(text, limit=MAX_TEXT):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def short_path(path):
    path = str(path or "")
    return "~" + path[len(HOME):] if path == HOME or path.startswith(HOME + "/") else path


def tail_lines(path, size=TAIL_BYTES):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            f.seek(max(0, end - size))
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", "replace").splitlines()
    return lines[1:] if end > size else lines


def newest_mtime(paths):
    best = 0.0
    for root in paths:
        try:
            if os.path.isfile(root):
                best = max(best, os.path.getmtime(root))
                continue
            for dirpath, _dirs, files in os.walk(root):
                for name in files:
                    try:
                        best = max(best, os.path.getmtime(os.path.join(dirpath, name)))
                    except OSError:
                        pass
        except OSError:
            pass
    return best


# ---------------------------------------------------------------- processes

def boot_time():
    try:
        with open("/proc/stat") as f:
            for line in f:
                if line.startswith("btime "):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def scan_processes():
    """pid -> {ppid, argv, cwd, started} for every process we may read."""
    procs = {}
    btime = boot_time()
    hz = os.sysconf("SC_CLK_TCK")
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        base = "/proc/" + entry
        try:
            with open(base + "/cmdline", "rb") as f:
                argv = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
            with open(base + "/stat") as f:
                stat = f.read()
        except OSError:
            continue
        if not argv:
            continue
        # comm may contain spaces and parens, so split after the last ")".
        fields = stat[stat.rfind(")") + 2:].split()
        try:
            cwd = os.readlink(base + "/cwd")
        except OSError:
            cwd = ""
        procs[int(entry)] = {
            "ppid": int(fields[1]),
            "argv": argv,
            "cwd": cwd,
            "started": btime + int(fields[19]) / hz,
        }
    return procs


def agent_of(argv, by_bin):
    name = os.path.basename(argv[0])
    if name in by_bin:
        return by_bin[name]
    if name in INTERPRETERS:
        for arg in argv[1:3]:
            if not arg.startswith("-"):
                return by_bin.get(os.path.splitext(os.path.basename(arg))[0])
    return None


def descendants(procs, roots):
    """pid -> root pid, for each root and everything it spawned."""
    children = {}
    for pid, info in procs.items():
        children.setdefault(info["ppid"], []).append(pid)
    owner = {}
    for root in roots:
        stack = [root]
        while stack:
            pid = stack.pop()
            if pid in owner:
                continue
            owner[pid] = root
            stack.extend(children.get(pid, []))
    return owner


# -------------------------------------------------------------- connections

def scan_sockets():
    """Every TCP/UDP socket `ss` can attribute to a process of this user."""
    if not shutil.which("ss"):
        return []
    try:
        out = subprocess.run(["ss", "-Htunap"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    sockets = []
    for line in out.splitlines():
        f = line.split()
        if len(f) < 7:
            continue
        for proc, pid in re.findall(r'\("([^"]*)",pid=(\d+)', line):
            sockets.append({"proto": f[0], "state": f[1], "local": f[4], "peer": f[5],
                            "process": proc, "pid": int(pid)})
    return sockets


def split_endpoint(endpoint):
    host, _, port = endpoint.rpartition(":")
    return host.strip("[]"), port


def summarize_sockets(sockets):
    """Collapse per-fd sockets into one row per remote endpoint or listener."""
    rows = {}
    for s in sockets:
        listening = s["state"] in ("LISTEN", "UNCONN")
        host, port = split_endpoint(s["local"] if listening else s["peer"])
        if not listening and host in ("127.0.0.1", "::1"):
            kind = "local"
        else:
            kind = "listen" if listening else "remote"
        key = (kind, s["proto"], host, port, s["process"])
        row = rows.setdefault(key, {"kind": kind, "proto": s["proto"], "host": host, "port": port,
                                    "process": s["process"], "pid": s["pid"], "count": 0})
        row["count"] += 1
    order = {"remote": 0, "listen": 1, "local": 2}
    return sorted(rows.values(), key=lambda r: (order[r["kind"]], r["host"], r["port"]))


def mcp_rows(servers, scope):
    rows = []
    if not isinstance(servers, dict):
        return rows
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        command = cfg.get("command")
        if isinstance(command, list):
            command = " ".join(map(str, command))
        elif command and isinstance(cfg.get("args"), list):
            command = " ".join([str(command)] + [str(a) for a in cfg["args"]])
        target = cfg.get("url") or cfg.get("httpUrl") or command or ""
        kind = cfg.get("type") or cfg.get("transport") or ("http" if cfg.get("url") else "stdio")
        rows.append({"name": str(name), "type": str(kind), "target": clip(target, 100), "scope": scope,
                     "enabled": cfg.get("enabled", True) is not False and cfg.get("disabled") is not True})
    return rows


# ------------------------------------------------------------------- claude

def claude_tool_summary(block):
    name = block.get("name", "tool")
    args = block.get("input") or {}
    for key in ("description", "command", "file_path", "path", "pattern", "url", "query", "skill", "prompt"):
        if args.get(key):
            return name + ": " + clip(short_path(args[key]) if key.endswith("path") else args[key])
    return name


def claude_last_action(transcript):
    """Last tool call (or reply) plus the current permission mode."""
    action, mode = None, ""
    for line in reversed(tail_lines(transcript)):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        kind = entry.get("type")
        if kind == "permission-mode" and not mode:
            mode = entry.get("permissionMode", "")
        if action is None and kind == "assistant" and not entry.get("isSidechain"):
            content = (entry.get("message") or {}).get("content") or []
            tools = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if tools:
                summary = claude_tool_summary(tools[-1])
            elif any(texts):
                summary = "Reply: " + clip(" ".join(texts))
            else:
                continue
            action = {"summary": summary, "at": parse_iso(entry.get("timestamp")), "cwd": short_path(entry.get("cwd"))}
        if action and mode:
            break
    return action, mode


def parse_iso(value):
    try:
        return calendar.timegm(time.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return 0


def claude_rules(settings, scope):
    perms = settings.get("permissions") if isinstance(settings.get("permissions"), dict) else {}
    rows = []
    for key in ("allow", "ask", "deny"):
        for rule in perms.get(key) or []:
            rows.append({"effect": key, "rule": str(rule), "scope": scope})
    for directory in perms.get("additionalDirectories") or []:
        rows.append({"effect": "allow", "rule": "dir " + short_path(directory), "scope": scope})
    return rows, perms.get("defaultMode", "")


def collect_claude(agent, sessions):
    base = os.environ.get("CLAUDE_CONFIG_DIR") or home(".claude")
    state = read_json(home(".claude.json")) or read_json(os.path.join(base, ".claude.json"))
    projects = state.get("projects") if isinstance(state.get("projects"), dict) else {}

    live = {}
    for path in glob.glob(os.path.join(base, "sessions", "*.json")):
        info = read_json(path)
        if info.get("pid"):
            live[int(info["pid"])] = info

    rules, default_mode = [], ""
    for path, scope in (("/etc/claude-code/managed-settings.json", "managed"),
                        (os.path.join(base, "settings.json"), "user")):
        found, mode = claude_rules(read_json(path), scope)
        rules += found
        default_mode = default_mode or mode
    mcp = mcp_rows(state.get("mcpServers"), "user")

    seen_dirs = set()
    for session in sessions:
        info = live.get(session["pid"], {})
        cwd = info.get("cwd") or session["cwd"]
        session["name"] = info.get("name", "")
        session["status"] = info.get("status", "")
        session["version"] = info.get("version", "")
        mode = ""
        matches = glob.glob(os.path.join(base, "projects", "*", str(info.get("sessionId", "")) + ".jsonl"))
        if info.get("sessionId") and matches:
            session["lastAction"], mode = claude_last_action(matches[0])
        if "--dangerously-skip-permissions" in session["argv"]:
            mode = "bypassPermissions"
        session["mode"] = mode or default_mode or "default"

        if cwd in seen_dirs:
            continue
        seen_dirs.add(cwd)
        label = "project " + short_path(cwd)
        for name in ("settings.json", "settings.local.json"):
            found, _ = claude_rules(read_json(os.path.join(cwd, ".claude", name)), label)
            rules += found
        project = projects.get(cwd) or {}
        for tool in project.get("allowedTools") or []:
            rules.append({"effect": "allow", "rule": str(tool), "scope": label})
        mcp += mcp_rows(project.get("mcpServers"), label)
        mcp += mcp_rows(read_json(os.path.join(cwd, ".mcp.json")).get("mcpServers"), label)

    needs_auth = read_json(os.path.join(base, "mcp-needs-auth-cache.json"))
    connectors = set(state.get("claudeAiMcpEverConnected") or []) | set(needs_auth)
    for name in sorted(connectors):
        mcp.append({"name": name, "type": "connector", "scope": "claude.ai", "enabled": True,
                    "target": "needs sign-in" if name in needs_auth else "connected before"})

    last = None
    transcripts = glob.glob(os.path.join(base, "projects", "*", "*.jsonl"))
    if transcripts:
        last, _ = claude_last_action(max(transcripts, key=os.path.getmtime))

    agent["mcp"] = mcp
    agent["rules"] = rules
    agent["defaultMode"] = default_mode or "default"
    agent["facts"] = [{"label": "Trusted folders",
                       "value": str(sum(1 for p in projects.values() if p.get("hasTrustDialogAccepted")))}]
    return last


# -------------------------------------------------------------------- codex

def collect_codex(agent, sessions):
    base = os.environ.get("CODEX_HOME") or home(".codex")
    cfg = read_toml(os.path.join(base, "config.toml"))
    agent["mcp"] = mcp_rows(cfg.get("mcp_servers"), "user")
    agent["defaultMode"] = "approval " + str(cfg.get("approval_policy", "default")) \
        + " · sandbox " + str(cfg.get("sandbox_mode", "default"))
    rules = []
    for path, project in (cfg.get("projects") or {}).items():
        if isinstance(project, dict) and project.get("trust_level"):
            rules.append({"effect": "allow", "rule": "trust " + str(project["trust_level"]),
                          "scope": "project " + short_path(path)})
    agent["rules"] = rules
    for session in sessions:
        argv = session["argv"]
        if "--dangerously-bypass-approvals-and-sandbox" in argv or "--yolo" in argv:
            session["mode"] = "danger-full-access"
        elif "--full-auto" in argv:
            session["mode"] = "full-auto"
        else:
            session["mode"] = agent["defaultMode"]

    try:
        db = sqlite3.connect("file:" + os.path.join(base, "state_5.sqlite") + "?mode=ro", uri=True, timeout=1)
        row = db.execute("select title, cwd, updated_at, rollout_path from threads "
                         "order by updated_at desc limit 1").fetchone()
        db.close()
    except sqlite3.Error:
        row = None
    if not row:
        return None
    title, cwd, updated, rollout = row
    summary = "Thread: " + clip(title or "untitled")
    for line in reversed(tail_lines(rollout)):
        try:
            payload = json.loads(line).get("payload") or {}
        except ValueError:
            continue
        if payload.get("type") in ("function_call", "local_shell_call", "custom_tool_call"):
            detail = payload.get("arguments") or payload.get("input") or payload.get("action") or ""
            summary = str(payload.get("name") or "shell") + ": " + clip(detail if isinstance(detail, str) else json.dumps(detail))
            break
    # updated_at moved from seconds to milliseconds across Codex versions.
    return {"summary": summary, "at": updated / 1000 if updated > 1e11 else updated, "cwd": short_path(cwd)}


# ----------------------------------------------------- config-only agents

def collect_opencode(agent, sessions):
    cfg = read_json(home(".config", "opencode", "opencode.json"))
    agent["mcp"] = mcp_rows(cfg.get("mcp"), "user")
    perm = cfg.get("permission")
    if isinstance(perm, dict):
        agent["rules"] = [{"effect": v if isinstance(v, str) else "custom", "rule": k, "scope": "user"}
                          for k, v in perm.items()]
    elif isinstance(perm, str):
        agent["defaultMode"] = perm


def collect_gemini(agent, sessions):
    cfg = read_json(home(".gemini", "settings.json"))
    agent["mcp"] = mcp_rows(cfg.get("mcpServers"), "user")
    tools = cfg.get("tools") if isinstance(cfg.get("tools"), dict) else {}
    agent["rules"] = [{"effect": "allow", "rule": str(t), "scope": "user"} for t in tools.get("allowed") or []] \
        + [{"effect": "deny", "rule": str(t), "scope": "user"} for t in tools.get("exclude") or []]
    for session in sessions:
        if "--yolo" in session["argv"] or "-y" in session["argv"]:
            session["mode"] = "yolo"


def collect_antigravity(agent, sessions):
    base = home(".gemini", "antigravity-cli")
    cfg = read_json(os.path.join(base, "settings.json"))
    agent["mcp"] = mcp_rows(read_json(home(".gemini", "config", "mcp_config.json")).get("mcpServers"), "user")
    agent["rules"] = [{"effect": "allow", "rule": "trust folder", "scope": "project " + short_path(p)}
                      for p in cfg.get("trustedWorkspaces") or []]
    if cfg.get("model"):
        agent["facts"] = [{"label": "Model", "value": str(cfg["model"])}]
    for session in sessions:
        argv = session["argv"]
        if "--dangerously-skip-permissions" in argv:
            session["mode"] = "skip-permissions"
        elif "--mode" in argv[:-1]:
            session["mode"] = argv[argv.index("--mode") + 1]

    for line in reversed(tail_lines(os.path.join(base, "history.jsonl"))):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("display") and entry.get("timestamp"):
            return {"summary": "Prompt: " + clip(entry["display"]), "at": entry["timestamp"] / 1000,
                    "cwd": short_path(entry.get("workspace"))}
    return None


def collect_cursor(agent, sessions):
    cfg = read_json(home(".cursor", "cli-config.json"))
    agent["mcp"] = mcp_rows(read_json(home(".cursor", "mcp.json")).get("mcpServers"), "user")
    agent["rules"], _ = claude_rules(cfg, "user")
    for session in sessions:
        if "--force" in session["argv"] or "-f" in session["argv"]:
            session["mode"] = "force"


def collect_crush(agent, sessions):
    cfg = read_json(home(".config", "crush", "crush.json"))
    agent["mcp"] = mcp_rows(cfg.get("mcp"), "user")
    perms = cfg.get("permissions") if isinstance(cfg.get("permissions"), dict) else {}
    agent["rules"] = [{"effect": "allow", "rule": str(t), "scope": "user"} for t in perms.get("allowed_tools") or []]
    for session in sessions:
        if "--yolo" in session["argv"] or "-y" in session["argv"]:
            session["mode"] = "yolo"


def collect_copilot(agent, sessions):
    cfg = read_json(home(".copilot", "config.json"))
    agent["mcp"] = mcp_rows(read_json(home(".copilot", "mcp-config.json")).get("mcpServers"), "user")
    agent["rules"] = [{"effect": "allow", "rule": "trust folder", "scope": "project " + short_path(p)}
                      for p in cfg.get("trusted_folders") or []]
    for session in sessions:
        if "--allow-all-tools" in session["argv"] or "--yolo" in session["argv"]:
            session["mode"] = "allow-all-tools"


COLLECTORS = {
    "claude": collect_claude, "codex": collect_codex, "opencode": collect_opencode,
    "gemini": collect_gemini, "antigravity": collect_antigravity, "cursor-agent": collect_cursor, "crush": collect_crush,
    "copilot": collect_copilot,
}

# Modes where the agent acts without asking first.
UNATTENDED = ("bypassPermissions", "danger-full-access", "yolo", "force", "allow-all-tools", "full-auto",
              "skip-permissions")


def main():
    now = time.time()
    by_bin = {b: a["id"] for a in AGENTS for b in a["bins"]}
    procs = scan_processes()

    # A session is the topmost process of an agent; its own helpers are not sessions.
    tagged = {pid: agent_of(info["argv"], by_bin) for pid, info in procs.items()}
    roots = {}
    for pid, agent_id in tagged.items():
        if agent_id and tagged.get(procs[pid]["ppid"]) != agent_id:
            roots.setdefault(agent_id, []).append(pid)

    owner = descendants(procs, [pid for pids in roots.values() for pid in pids])
    sockets = scan_sockets()

    agents = []
    for spec in AGENTS:
        path = next((p for p in (shutil.which(b) for b in spec["bins"]) if p), "")
        pids = sorted(roots.get(spec["id"], []))
        if not path and not pids:
            continue
        sessions = [{"pid": pid, "argv": procs[pid]["argv"], "cwd": procs[pid]["cwd"],
                     "startedAt": procs[pid]["started"], "name": "", "status": "", "version": "",
                     "mode": "", "lastAction": None} for pid in pids]
        agent = {"id": spec["id"], "name": spec["name"], "path": short_path(path),
                 "mcp": [], "rules": [], "facts": [], "defaultMode": ""}
        try:
            last = COLLECTORS[spec["id"]](agent, sessions)
        except Exception as error:  # one broken config must not hide the others
            last = None
            agent["error"] = clip(repr(error))
        if not last:
            mtime = newest_mtime(spec["state"])
            last = {"summary": "", "at": mtime, "cwd": ""} if mtime else None
        for session in sessions:
            session["connections"] = summarize_sockets(
                [s for s in sockets if owner.get(s["pid"]) == session["pid"]])
            session["cwd"] = short_path(session["cwd"])
            session["unattended"] = session["mode"] in UNATTENDED
            del session["argv"]
        agent["sessions"] = sessions
        agent["lastAction"] = last
        agent["unattended"] = any(s["unattended"] for s in sessions)
        agents.append(agent)

    json.dump({"generatedAt": now, "agents": agents}, sys.stdout)


if __name__ == "__main__":
    main()
