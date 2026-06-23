#!/usr/bin/env python3
"""Session Dashboard server — serves static files + API for reading Claude/Codex sessions."""
import http.server
import json
import os
import glob
import hashlib
from datetime import datetime, timezone

CLAUDE_DIR = os.path.expanduser("~/.claude/projects")
CODEX_DIR = os.path.expanduser("~/.codex/sessions")
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

PHASE_MAP = {
    "ce-ideate": "ideation",
    "ce-brainstorm": "brainstorm",
    "ce-plan": "plan",
    "ce-work": "work",
    "ce-code-review": "review",
    "ce-resolve-pr-feedback": "review",
}
PHASES = ["ideation", "brainstorm", "plan", "work", "review"]

def phase_from_type(agent_type):
    if not agent_type:
        return "unknown"
    for prefix, phase in PHASE_MAP.items():
        if agent_type.startswith(prefix):
            return phase
    return "unknown"

# In-memory cache
_cache = {"sessions": None, "chains": None, "ts": 0}
CACHE_TTL = 30  # seconds

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        path = self.path.split("?")[0]
        qs = {}
        if "?" in self.path:
            from urllib.parse import parse_qs
            qs = {k: v[0] for k, v in parse_qs(self.path.split("?")[1]).items()}

        if path == "/api/discover" or path == "/api/sessions":
            limit = int(qs.get("limit", 50))
            offset = int(qs.get("offset", 0))
            self._json(self._discover(limit, offset))
        elif path == "/api/chains":
            self._json(self._chains())
        elif path.startswith("/api/session/"):
            sid = path.split("/api/session/")[1]
            self._json(self._session_detail(sid))
        else:
            super().do_GET()

    def _json(self, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _chains(self):
        self._discover(limit=1, offset=0)
        chains_data = _cache.get("chains")
        if chains_data is None:
            return {"chains": [], "count": 0, "generatedAt": datetime.now(timezone.utc).isoformat()}
        return chains_data

    def _discover(self, limit=50, offset=0):
        now = datetime.now().timestamp()
        if _cache["sessions"] is not None and (now - _cache["ts"]) < CACHE_TTL:
            sessions = _cache["sessions"]
        else:
            sessions = []
            if os.path.isdir(CLAUDE_DIR):
                for proj_dir in sorted(os.listdir(CLAUDE_DIR)):
                    proj_path = os.path.join(CLAUDE_DIR, proj_dir)
                    if not os.path.isdir(proj_path):
                        continue
                    index_path = os.path.join(proj_path, "sessions-index.json")
                    if os.path.isfile(index_path):
                        try:
                            with open(index_path) as f:
                                idx = json.load(f)
                            entries = idx.get("entries", [])
                            if isinstance(idx, dict) and "entries" in idx:
                                entries = idx["entries"]
                            for e in entries:
                                s = self._from_index_entry(e, proj_dir)
                                if s: sessions.append(s)
                            continue
                        except Exception:
                            pass
                    for fp in glob.glob(os.path.join(proj_path, "**/*.jsonl"), recursive=True):
                        if "/subagents/" in fp:
                            continue
                        s = self._parse_jsonl(fp)
                        if s: sessions.append(s)
                    subs = self._scan_subagents(proj_path, proj_dir)
                    sessions.extend(subs)
            if os.path.isdir(CODEX_DIR):
                for fp in glob.glob(os.path.join(CODEX_DIR, "*.json")):
                    s = self._parse_codex_json(fp)
                    if s: sessions.append(s)

            chain_data = self.detect_chains(sessions)
            chain_map = {}
            for chain in chain_data["chains"]:
                for phase_name, ps in chain["phases"].items():
                    if ps.get("sessionId"):
                        chain_map[ps["sessionId"]] = chain["id"]
            for s in sessions:
                s["chainId"] = chain_map.get(s.get("id"))

            sessions.sort(key=lambda s: s.get("startedAt") or "", reverse=True)
            _cache["sessions"] = sessions
            _cache["chains"] = chain_data
            _cache["ts"] = now
        total = len(sessions)
        page = sessions[offset:offset + limit]
        return {"sessions": page, "count": len(page), "total": total, "offset": offset, "limit": limit}

    def _scan_subagents(self, proj_path, proj_dir):
        subs = []
        sub_dir = os.path.join(proj_path, "subagents")
        if not os.path.isdir(sub_dir):
            for item in os.listdir(proj_path):
                item_path = os.path.join(proj_path, item)
                if os.path.isdir(item_path):
                    sdir = os.path.join(item_path, "subagents")
                    if os.path.isdir(sdir):
                        subs.extend(self._parse_subagent_dir(sdir, proj_dir))
            return subs
        return self._parse_subagent_dir(sub_dir, proj_dir)

    def _parse_subagent_dir(self, sub_dir, proj_dir):
        subs = []
        for meta_file in glob.glob(os.path.join(sub_dir, "*.meta.json")):
            try:
                with open(meta_file) as f:
                    meta = json.load(f)
            except Exception:
                continue
            agent_id = os.path.splitext(os.path.basename(meta_file))[0].replace(".meta", "")
            agent_type = meta.get("agentType", "unknown")
            description = meta.get("description", "")
            jsonl_path = os.path.join(sub_dir, f"{agent_id}.jsonl")
            started_at = None
            duration = None
            msg_count = 0
            if os.path.isfile(jsonl_path):
                lines = []
                try:
                    with open(jsonl_path) as f:
                        lines = [l.strip() for l in f if l.strip()]
                    msg_count = len(lines)
                except Exception:
                    pass
                for line in lines:
                    try:
                        o = json.loads(line)
                        ts = o.get("timestamp")
                        if ts:
                            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            ts_ms = t.timestamp() * 1000
                            if not started_at or ts_ms < started_at:
                                started_at = ts_ms
                            if not duration:
                                duration = 0
                            duration = max(duration, ts_ms - started_at)
                    except Exception:
                        pass
            project = os.path.basename(proj_dir.replace("-", "/").lstrip("/").split("/")[-1] or "unknown")
            summary = description or f"{agent_type} sub-agent"
            subs.append({
                "id": agent_id, "platform": "opencode", "project": project,
                "branch": "", "cwd": proj_dir,
                "startedAt": datetime.fromtimestamp(started_at / 1000, tz=timezone.utc).isoformat() if started_at else None,
                "duration": duration, "subAgentCount": 0, "messageCount": msg_count,
                "status": "completed", "sourceType": "jsonl",
                "summary": summary, "isSubagent": True,
                "agentType": agent_type, "chainId": None, "filename": jsonl_path,
            })
        return subs

    def _parse_jsonl(self, filepath):
        lines = []
        try:
            with open(filepath) as f:
                lines = [l.strip() for l in f if l.strip()]
        except Exception:
            return None
        if len(lines) < 2:
            return None
        started_at = None
        last_ts = None
        agent_count = 0
        branch = None
        cwd = None
        agent_type = None
        for line in lines:
            try:
                o = json.loads(line)
                ts = o.get("timestamp")
                if ts:
                    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    ts_ms = t.timestamp() * 1000
                    if not started_at or ts_ms < started_at:
                        started_at = ts_ms
                    if not last_ts or ts_ms > last_ts:
                        last_ts = ts_ms
                if o.get("type") == "tool_use" and o.get("name") in ("Task",):
                    agent_count += 1
                if not branch:
                    branch = o.get("gitBranch") or o.get("branch")
                if not cwd:
                    cwd = o.get("cwd")
                if not agent_type:
                    agent_type = o.get("agentType")
            except Exception:
                pass
        duration = (last_ts - started_at) if (started_at and last_ts) else None
        sid = os.path.splitext(os.path.basename(filepath))[0]
        if cwd:
            project = os.path.basename(cwd.rstrip("/")) or os.path.basename(os.path.dirname(cwd.rstrip("/")))
        else:
            rel = os.path.relpath(filepath, CLAUDE_DIR)
            parts = rel.split(os.sep)
            encoded = parts[0] if parts else ""
            project = encoded.replace("-", "/").lstrip("/").split("/")[-1] or encoded
        return {
            "id": sid, "platform": "opencode", "project": project,
            "branch": branch, "cwd": cwd,
            "startedAt": datetime.fromtimestamp(started_at / 1000, tz=timezone.utc).isoformat() if started_at else None,
            "duration": duration, "subAgentCount": agent_count,
            "status": "completed" if duration else "unknown",
            "chainId": None,
            "agentType": agent_type,
            "filename": os.path.relpath(filepath, CLAUDE_DIR), "sourceType": "jsonl",
            "summary": self._make_summary(project, branch, duration, agent_count, "claude"),
        }

    def _parse_codex_json(self, filepath):
        try:
            with open(filepath) as f:
                data = json.load(f)
        except Exception:
            return None
        session = data.get("session", data)
        events = data.get("items", data.get("events", []))
        started_at = None
        last_ts = None
        agent_type = None
        for ev in events:
            ts = ev.get("timestamp")
            if ts:
                try:
                    t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    ts_ms = t.timestamp() * 1000
                    if not started_at or ts_ms < started_at:
                        started_at = ts_ms
                    if not last_ts or ts_ms > last_ts:
                        last_ts = ts_ms
                except Exception:
                    pass
            if not agent_type:
                agent_type = ev.get("agentType") or (ev.get("metadata") or {}).get("agentType")
        duration = (last_ts - started_at) if (started_at and last_ts) else None
        sid = session.get("id") or session.get("sessionId") or os.path.splitext(os.path.basename(filepath))[0]
        return {
            "id": str(sid), "platform": "codex", "project": session.get("project") or session.get("cwd") or "unknown",
            "branch": session.get("branch"), "cwd": session.get("cwd"),
            "startedAt": datetime.fromtimestamp(started_at / 1000, tz=timezone.utc).isoformat() if started_at else None,
            "duration": duration, "subAgentCount": 0,
            "status": "completed" if duration else "unknown",
            "chainId": None,
            "agentType": agent_type,
            "filename": filepath, "sourceType": "json",
            "summary": self._make_summary(session.get("project") or session.get("cwd") or "unknown", session.get("branch"), duration, 0, "codex"),
        }

    def _from_index_entry(self, entry, encoded_dir):
        sid = entry.get("sessionId") or ""
        summary = entry.get("summary") or ""
        branch = entry.get("gitBranch") or ""
        project_path = entry.get("projectPath") or ""
        project = os.path.basename(project_path.rstrip("/")) or "unknown"
        created = entry.get("created") or ""
        modified = entry.get("modified") or ""
        msg_count = entry.get("messageCount", 0)
        started_at = None
        duration = None
        if created:
            try:
                t = datetime.fromisoformat(created.replace("Z", "+00:00"))
                started_at = t.timestamp() * 1000
            except Exception:
                pass
        if started_at and modified:
            try:
                t2 = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                duration = t2.timestamp() * 1000 - started_at
            except Exception:
                pass
        return {
            "id": sid, "platform": "opencode", "project": project,
            "branch": branch, "cwd": project_path,
            "startedAt": created, "duration": duration,
            "subAgentCount": 0, "messageCount": msg_count,
            "status": "completed",
            "chainId": None,
            "agentType": None,
            "filename": entry.get("fullPath", ""), "sourceType": "jsonl",
            "summary": summary or self._make_summary(project, branch, duration, 0, "claude"),
        }

    def _make_summary(self, project, branch, duration_ms, agent_count, platform):
        parts = []
        if branch:
            parts.append(f"on branch {branch}")
        if agent_count:
            parts.append(f"dispatched {agent_count} sub-agent{'s' if agent_count > 1 else ''}")
        if duration_ms:
            mins = int(duration_ms / 60000)
            if mins >= 60:
                parts.append(f"ran for {mins // 60}h {mins % 60}m")
            else:
                parts.append(f"ran for {mins}m")
        if not parts:
            parts.append("session")
        summary = f"{platform.title()} session in {project}"
        if parts:
            summary += " — " + ", ".join(parts)
        return summary

    def detect_chains(self, sessions):
        if not sessions:
            return {"chains": [], "count": 0, "generatedAt": datetime.now(timezone.utc).isoformat()}

        n = len(sessions)
        adj = [[] for _ in range(n)]

        for i in range(n):
            for j in range(i + 1, n):
                a, b = sessions[i], sessions[j]
                if a.get("project") != b.get("project"):
                    continue
                signals = 1
                if self._signal_temporal_consecutive(a, b):
                    signals += 1
                if self._signal_discovered_from(a, b, sessions):
                    signals += 1
                if signals >= 2:
                    adj[i].append(j)
                    adj[j].append(i)

        visited = [False] * n
        chains = []
        session_to_chain = {}

        for i in range(n):
            if not visited[i]:
                stack = [i]
                component = []
                while stack:
                    v = stack.pop()
                    if not visited[v]:
                        visited[v] = True
                        component.append(v)
                        for u in adj[v]:
                            if not visited[u]:
                                stack.append(u)
                chain_sessions = [sessions[idx] for idx in component]
                chain = self._build_chain(chain_sessions)
                chains.append(chain)
                for idx in component:
                    session_to_chain[sessions[idx].get("id")] = chain["id"]

        chains.sort(key=lambda c: c.get("lastActivity", ""), reverse=True)

        return {"chains": chains, "count": len(chains), "generatedAt": datetime.now(timezone.utc).isoformat()}

    def _chain_id(self, sessions):
        sorted_ids = sorted(s.get("id", "") for s in sessions)
        raw = "|".join(sorted_ids)
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def _signal_temporal_consecutive(self, a, b):
        phase_a = phase_from_type(a.get("agentType"))
        phase_b = phase_from_type(b.get("agentType"))
        if phase_a == "unknown" or phase_b == "unknown":
            return False
        if phase_a not in PHASES or phase_b not in PHASES:
            return False
        idx_a = PHASES.index(phase_a)
        idx_b = PHASES.index(phase_b)
        if abs(idx_a - idx_b) != 1:
            return False
        ts_a = a.get("startedAt")
        ts_b = b.get("startedAt")
        if not ts_a or not ts_b:
            return False
        try:
            t_a = datetime.fromisoformat(ts_a.replace("Z", "+00:00"))
            t_b = datetime.fromisoformat(ts_b.replace("Z", "+00:00"))
            return abs((t_a - t_b).total_seconds()) <= 86400
        except Exception:
            return False

    def _signal_discovered_from(self, a, b, all_sessions):
        a_id = a.get("id", "")
        b_id = b.get("id", "")
        a_summary = a.get("summary", "") or ""
        b_summary = b.get("summary", "") or ""
        if a_id and b_id:
            if a_id in b_summary or b_id in a_summary:
                return True
            if "discovered-from" in a_summary.lower() or "discovered-from" in b_summary.lower():
                if b_id in a_summary or a_id in b_summary:
                    return True
        return False

    def _build_chain(self, sessions):
        chain_id = self._chain_id(sessions)
        project = sessions[0].get("project", "unknown")
        label = (sessions[0].get("summary") or "")[:100]

        phases = {}
        for p in PHASES:
            phases[p] = {"status": "pending", "sessionId": None, "duration": None, "startedAt": None}

        for s in sessions:
            p = phase_from_type(s.get("agentType"))
            if p == "unknown" or p not in phases:
                continue
            existing = phases[p]
            if existing["startedAt"] is None or (s.get("startedAt") and s["startedAt"] > existing["startedAt"]):
                phases[p] = {
                    "status": "completed",
                    "sessionId": s.get("id"),
                    "duration": s.get("duration"),
                    "startedAt": s.get("startedAt"),
                }

        sorted_sessions = sorted(sessions, key=lambda s: s.get("startedAt") or "", reverse=True)
        now = datetime.now(timezone.utc)

        for s in sorted_sessions:
            p = phase_from_type(s.get("agentType"))
            if p == "unknown" or p not in phases:
                continue
            ps = phases[p]
            if ps["status"] == "completed":
                if s.get("duration") is None:
                    ps["status"] = "active"
                elif s.get("startedAt"):
                    try:
                        t = datetime.fromisoformat(s["startedAt"].replace("Z", "+00:00"))
                        if (now - t).total_seconds() <= 300:
                            ps["status"] = "active"
                    except Exception:
                        pass
            break

        active_or_completed = [i for i, p in enumerate(PHASES) if phases[p]["status"] in ("completed", "active")]
        for i, p in enumerate(PHASES):
            if phases[p]["status"] == "pending" and any(j > i for j in active_or_completed):
                phases[p]["status"] = "skipped"

        last_activity = ""
        for s in sorted_sessions:
            if s.get("startedAt"):
                last_activity = s["startedAt"]
                break

        health = []

        if last_activity:
            try:
                t = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                hours_since = (now - t).total_seconds() / 3600
                if hours_since > 48:
                    last_phase = None
                    for p in reversed(PHASES):
                        if phases[p]["status"] in ("completed", "active"):
                            last_phase = p
                            break
                    if last_phase and last_phase != "review":
                        health.append({
                            "type": "stalled",
                            "message": f"Stalled — {int(hours_since)}h since last phase"
                        })
            except Exception:
                pass

        for i, p in enumerate(PHASES):
            if phases[p]["status"] == "completed":
                if i + 1 < len(PHASES):
                    next_p = PHASES[i + 1]
                    if phases[next_p]["status"] == "pending":
                        later_has = any(
                            phases[PHASES[j]]["status"] in ("completed", "active")
                            for j in range(i + 2, len(PHASES))
                        )
                        if not later_has:
                            first_s = min(sessions, key=lambda s: s.get("startedAt") or "")
                            if first_s.get("startedAt"):
                                try:
                                    t = datetime.fromisoformat(first_s["startedAt"].replace("Z", "+00:00"))
                                    if (now - t).total_seconds() > 86400:
                                        health.append({
                                            "type": "broken",
                                            "message": f"Broken chain — {p.capitalize()} completed but no {next_p.capitalize()}"
                                        })
                                except Exception:
                                    pass

        health.sort(key=lambda h: 0 if h["type"] == "broken" else 1)

        return {
            "id": chain_id,
            "project": project,
            "label": label,
            "phases": phases,
            "lastActivity": last_activity,
            "health": health,
        }

    def _session_detail(self, sid):
        for base in [CLAUDE_DIR, CODEX_DIR]:
            if not os.path.isdir(base):
                continue
            for fp in glob.glob(os.path.join(base, "**/*"), recursive=True):
                if os.path.splitext(os.path.basename(fp))[0] == sid and fp.endswith((".jsonl", ".json")):
                    s = self._parse_jsonl(fp) if fp.endswith(".jsonl") else self._parse_codex_json(fp)
                    if s:
                        if fp.endswith(".jsonl"):
                            msgs = []
                            try:
                                with open(fp) as f:
                                    for l in f:
                                        l = l.strip()
                                        if l:
                                            try: msgs.append(json.loads(l))
                                            except Exception: pass
                            except Exception: pass
                            s["messages"] = msgs[:500]
                        return s
        return None

if __name__ == "__main__":
    port = 8765
    print(f"Session Dashboard on http://localhost:{port}")
    print(f"Reading: {CLAUDE_DIR}")
    http.server.HTTPServer(("", port), Handler).serve_forever()
