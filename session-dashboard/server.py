#!/usr/bin/env python3
"""Session Dashboard server — serves static files + API for reading Claude/Codex sessions."""
import http.server
import json
import os
import glob
from datetime import datetime, timezone

CLAUDE_DIR = os.path.expanduser("~/.claude/projects")
CODEX_DIR = os.path.expanduser("~/.codex/sessions")
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))

# In-memory cache
_cache = {"sessions": None, "ts": 0}
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
            sessions.sort(key=lambda s: s.get("startedAt") or "", reverse=True)
            _cache["sessions"] = sessions
            _cache["ts"] = now
        total = len(sessions)
        page = sessions[offset:offset + limit]
        return {"sessions": page, "count": len(page), "total": total, "offset": offset, "limit": limit}

    def _scan_subagents(self, proj_path, proj_dir):
        """Find sub-agent sessions within a project, each treated as a discrete session."""
        subs = []
        sub_dir = os.path.join(proj_path, "subagents")
        if not os.path.isdir(sub_dir):
            # Check within session UUID dirs
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
                "agentType": agent_type, "filename": jsonl_path,
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
        duration = (last_ts - started_at) if (started_at and last_ts) else None
        sid = session.get("id") or session.get("sessionId") or os.path.splitext(os.path.basename(filepath))[0]
        return {
            "id": str(sid), "platform": "codex", "project": session.get("project") or session.get("cwd") or "unknown",
            "branch": session.get("branch"), "cwd": session.get("cwd"),
            "startedAt": datetime.fromtimestamp(started_at / 1000, tz=timezone.utc).isoformat() if started_at else None,
            "duration": duration, "subAgentCount": 0,
            "status": "completed" if duration else "unknown",
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
