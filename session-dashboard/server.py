#!/usr/bin/env python3
"""Session Dashboard server — serves static files + API for reading Claude/Codex sessions."""
import http.server
import json
import os
import glob
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs

CLAUDE_DIR = os.path.expanduser("~/.claude/projects")
CODEX_DIR = os.path.expanduser("~/.codex/sessions")
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
REVIEW_ARTIFACTS_DIR = "/tmp/compound-engineering/ce-code-review"
ANALYTICS_CACHE_TTL = 60

PERSONA_MAP = {
    "ce-correctness-reviewer": {"displayName": "Correctness", "group": "always-on", "description": "Logic errors, edge cases, state bugs"},
    "ce-testing-reviewer": {"displayName": "Testing", "group": "always-on", "description": "Coverage gaps, weak assertions"},
    "ce-maintainability-reviewer": {"displayName": "Maintainability", "group": "always-on", "description": "Coupling, complexity, naming"},
    "ce-project-standards-reviewer": {"displayName": "Project Standards", "group": "always-on", "description": "Standards compliance"},
    "ce-agent-native-reviewer": {"displayName": "Agent-Native", "group": "ce-always-on", "description": "Agent accessibility verification"},
    "ce-learnings-researcher": {"displayName": "Learnings", "group": "ce-always-on", "description": "Past solutions search"},
    "ce-security-reviewer": {"displayName": "Security", "group": "conditional", "description": "Auth, input, permissions"},
    "ce-performance-reviewer": {"displayName": "Performance", "group": "conditional", "description": "Query perf, data transforms"},
    "ce-api-contract-reviewer": {"displayName": "API Contract", "group": "conditional", "description": "Routes, serializers, types"},
    "ce-data-migrations-reviewer": {"displayName": "Data Migrations", "group": "conditional", "description": "Migrations, schema changes"},
    "ce-reliability-reviewer": {"displayName": "Reliability", "group": "conditional", "description": "Error handling, retries"},
    "ce-adversarial-reviewer": {"displayName": "Adversarial", "group": "conditional", "description": "Abuse cases, high-risk code"},
    "ce-previous-comments-reviewer": {"displayName": "Previous Comments", "group": "conditional", "description": "Prior review threads"},
    "ce-dhh-rails-reviewer": {"displayName": "DHH Rails", "group": "stack-specific", "description": "Rails architecture"},
    "ce-kieran-rails-reviewer": {"displayName": "Kieran Rails", "group": "stack-specific", "description": "Rails application code"},
    "ce-kieran-python-reviewer": {"displayName": "Kieran Python", "group": "stack-specific", "description": "Python modules"},
    "ce-kieran-typescript-reviewer": {"displayName": "Kieran TypeScript", "group": "stack-specific", "description": "TypeScript code"},
    "ce-julik-frontend-races-reviewer": {"displayName": "Frontend Races", "group": "stack-specific", "description": "DOM/async race conditions"},
    "ce-swift-ios-reviewer": {"displayName": "Swift iOS", "group": "stack-specific", "description": "iOS/Swift files"},
    "ce-schema-drift-detector": {"displayName": "Schema Drift", "group": "ce-conditional", "description": "Schema.rb cross-reference"},
    "ce-deployment-verification-agent": {"displayName": "Deployment Verification", "group": "ce-conditional", "description": "Deployment checklist"},
}

BLIND_SPOT_EXCLUDED_GROUPS = {"stack-specific", "ce-conditional"}
ALWAYS_ON_GROUPS = {"always-on", "ce-always-on"}

_cache = {"sessions": None, "ts": 0, "analytics": None, "analytics_ts": 0}
CACHE_TTL = 30


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        path = self.path.split("?")[0]
        qs = {}
        if "?" in self.path:
            qs = {k: v[0] for k, v in parse_qs(self.path.split("?")[1]).items()}

        if path == "/api/discover" or path == "/api/sessions":
            limit = int(qs.get("limit", 50))
            offset = int(qs.get("offset", 0))
            self._json(self._discover(limit, offset))
        elif path.startswith("/api/session/"):
            sid = path.split("/api/session/")[1]
            self._json(self._session_detail(sid))
        elif path == "/api/analytics/reviewers":
            self._json(self._analytics_reviewers(
                project=qs.get("project"),
                days=int(qs["days"]) if qs.get("days") else None,
            ))
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

    # ── Persona analytics ──────────────────────────────────────────────

    def _analytics_reviewers(self, project=None, days=None):
        now = datetime.now().timestamp()
        if _cache.get("analytics") and (now - _cache.get("analytics_ts", 0)) < ANALYTICS_CACHE_TTL:
            resp = _cache["analytics"]
        else:
            resp = self._build_analytics()
            _cache["analytics"] = resp
            _cache["analytics_ts"] = now

        if project or days:
            resp = self._filter_analytics(resp, project, days)
        return resp

    def _build_analytics(self):
        all_sessions = self._discover(limit=999999)["sessions"]
        artifacts = self._discover_review_artifacts(all_sessions)

        agent_to_persona = {}
        for key in PERSONA_MAP:
            agent_to_persona[f"compound-engineering:{key}"] = key

        persona_artifact_map = {}
        for a in artifacts:
            at = a["agentType"]
            base_key = agent_to_persona.get(at)
            if not base_key:
                base_key = at.replace("compound-engineering:", "")
            if base_key not in persona_artifact_map:
                persona_artifact_map[base_key] = []
            persona_artifact_map[base_key].append(a)

        session_ids_seen = set()
        sessions_out = []
        for a in artifacts:
            sid = a.get("sessionId")
            if sid and sid not in session_ids_seen:
                session_ids_seen.add(sid)
                sessions_out.append({
                    "sessionId": sid,
                    "startedAt": a.get("startedAt"),
                    "project": a.get("project"),
                })
        sessions_out.sort(key=lambda s: s.get("startedAt") or "", reverse=True)

        persona_keys = sorted(PERSONA_MAP.keys(), key=lambda k: (
            {"always-on": 0, "ce-always-on": 1, "conditional": 2, "stack-specific": 3, "ce-conditional": 4}.get(PERSONA_MAP[k]["group"], 5),
            PERSONA_MAP[k]["displayName"],
        ))

        matrix = {}
        max_cell = 0
        persona_stats = {}

        for pk in persona_keys:
            pinfo = PERSONA_MAP[pk]
            full_at = f"compound-engineering:{pk}"
            arts = persona_artifact_map.get(pk, [])

            total_findings = 0
            high_severity = 0
            all_findings = []
            session_counts = {}
            last_dispatched = None

            for a in arts:
                sid = a.get("sessionId")
                if not sid:
                    continue
                findings = a.get("findings", []) or []
                session_counts[sid] = len(findings)
                total_findings += len(findings)
                for f in findings:
                    sev = (f.get("severity") or "P2").upper()
                    if sev in ("P0", "P1"):
                        high_severity += 1
                    all_findings.append(f)
                ts = a.get("startedAt")
                if ts and (not last_dispatched or ts > last_dispatched):
                    last_dispatched = ts

            matrix[pk] = {}
            for s in sessions_out:
                sid = s["sessionId"]
                if sid in session_counts:
                    count = session_counts[sid]
                    matrix[pk][sid] = count
                    if count > max_cell:
                        max_cell = count

            persona_stats[pk] = {
                "totalFindings": total_findings,
                "highSeverityCount": high_severity,
                "lastDispatchedAt": last_dispatched,
                "allFindings": all_findings,
                "sessionCount": len(arts),
                "sessionIds": list(session_counts.keys()),
            }

        acceptance_rates = self._compute_acceptance_rates(persona_stats, all_sessions)

        personas_out = []
        for pk in persona_keys:
            pinfo = PERSONA_MAP[pk]
            stats = persona_stats[pk]
            personas_out.append({
                "agentType": f"compound-engineering:{pk}",
                "displayName": pinfo["displayName"],
                "group": pinfo["group"],
                "description": pinfo["description"],
                "totalFindings": stats["totalFindings"],
                "highSeverityCount": stats["highSeverityCount"],
                "acceptanceRate": acceptance_rates.get(pk),
                "lastDispatchedAt": stats["lastDispatchedAt"],
            })

        trends = {}
        for pk in persona_keys:
            arts = sorted(persona_artifact_map.get(pk, []), key=lambda a: a.get("startedAt") or "")
            trend_data = []
            for a in arts:
                sid = a.get("sessionId")
                ts = a.get("startedAt")
                findings = a.get("findings", []) or []
                hs = sum(1 for f in findings if (f.get("severity") or "P2").upper() in ("P0", "P1"))
                trend_data.append({
                    "sessionId": sid,
                    "startedAt": ts,
                    "findingCount": len(findings),
                    "highSeverityCount": hs,
                })
            trends[pk] = trend_data

        blind_spots = self._detect_blind_spots(persona_keys, persona_stats, sessions_out)

        return {
            "personas": personas_out,
            "sessions": sessions_out,
            "matrix": matrix,
            "trends": trends,
            "blindSpots": blind_spots,
        }

    def _discover_review_artifacts(self, all_sessions):
        agent_session_map = {}
        for s in all_sessions:
            at = s.get("agentType", "")
            if at.startswith("compound-engineering:ce-") and s.get("isSubagent"):
                agent_session_map[at] = {
                    "sessionId": s["id"],
                    "startedAt": s.get("startedAt"),
                    "project": s.get("project"),
                }

        results = []
        if not os.path.isdir(REVIEW_ARTIFACTS_DIR):
            return results

        for run_id in sorted(os.listdir(REVIEW_ARTIFACTS_DIR)):
            run_dir = os.path.join(REVIEW_ARTIFACTS_DIR, run_id)
            if not os.path.isdir(run_dir):
                continue
            summary_path = os.path.join(run_dir, "summary.json")
            if not os.path.isfile(summary_path):
                continue

            for fname in os.listdir(run_dir):
                if fname == "summary.json" or not fname.endswith(".json"):
                    continue
                reviewer_name = fname[:-5]
                filepath = os.path.join(run_dir, fname)
                try:
                    with open(filepath) as f:
                        artifact = json.load(f)
                except Exception:
                    continue

                findings = artifact.get("findings") or []
                agent_type = f"compound-engineering:{reviewer_name}"

                session_info = agent_session_map.get(agent_type)

                if not session_info:
                    try:
                        mtime = os.path.getmtime(filepath)
                    except Exception:
                        mtime = None
                    if mtime:
                        for s in all_sessions:
                            started_at = s.get("startedAt")
                            if started_at:
                                try:
                                    t = datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
                                    if abs(mtime - t) < 300:
                                        session_info = {
                                            "sessionId": s["id"],
                                            "startedAt": started_at,
                                            "project": s.get("project"),
                                        }
                                        break
                                except Exception:
                                    pass

                results.append({
                    "reviewer": reviewer_name,
                    "agentType": agent_type,
                    "findings": findings,
                    "residual_risks": artifact.get("residual_risks", []),
                    "testing_gaps": artifact.get("testing_gaps", []),
                    "runId": run_id,
                    "sessionId": session_info["sessionId"] if session_info else None,
                    "startedAt": session_info["startedAt"] if session_info else None,
                    "project": session_info["project"] if session_info else None,
                })

        return results

    def _compute_acceptance_rates(self, persona_stats, all_sessions):
        rates = {}
        session_edits_cache = {}

        def get_session_edits(sid):
            if sid in session_edits_cache:
                return session_edits_cache[sid]
            edits = set()
            for base in [CLAUDE_DIR, CODEX_DIR]:
                if not os.path.isdir(base):
                    continue
                for fp in glob.glob(os.path.join(base, "**/*"), recursive=True):
                    if os.path.splitext(os.path.basename(fp))[0] == sid and fp.endswith((".jsonl", ".json")):
                        try:
                            with open(fp) as f:
                                for line in f:
                                    line = line.strip()
                                    if not line:
                                        continue
                                    try:
                                        msg = json.loads(line)
                                    except Exception:
                                        continue
                                    wrapper = msg.get("message", msg)
                                    content = wrapper.get("content") if isinstance(wrapper, dict) else None
                                    if not content or not isinstance(content, list):
                                        continue
                                    for block in content:
                                        if isinstance(block, dict) and block.get("type") == "tool_use":
                                            inp = block.get("input", {}) or {}
                                            for val in [inp.get("file_path"), inp.get("file"), inp.get("path")]:
                                                if val and isinstance(val, str):
                                                    edits.add(val)
                                            text = json.dumps(inp)
                                            m = re.search(r'[\\\/](\w[\w.\-/]*\.\w+)', text)
                                            if m:
                                                edits.add(m.group(1))
                        except Exception:
                            pass
                        break
            session_edits_cache[sid] = edits
            return edits

        def touched_by_later_session(finding_file, finding_line, later_session_ids):
            for lsid in later_session_ids:
                edits = get_session_edits(lsid)
                for edit_path in edits:
                    if finding_file and (edit_path.endswith(finding_file) or finding_file.endswith(edit_path) or finding_file in edit_path or edit_path in finding_file):
                        return True
            return False

        for pk, stats in persona_stats.items():
            if stats["sessionCount"] < 2:
                rates[pk] = None
                continue
            findings = [f for f in stats["allFindings"] if (f.get("confidence") or 0) >= 50]
            if not findings:
                rates[pk] = 0.0
                continue

            review_session_ids = stats["sessionIds"]
            review_times = set()
            for s in all_sessions:
                if s["id"] in review_session_ids:
                    sat = s.get("startedAt")
                    if sat:
                        try:
                            review_times.add((s["id"], datetime.fromisoformat(sat.replace("Z", "+00:00"))))
                        except Exception:
                            pass

            later_ids = []
            for s in all_sessions:
                sid = s["id"]
                if sid in review_session_ids:
                    continue
                sat = s.get("startedAt")
                if not sat:
                    continue
                try:
                    st = datetime.fromisoformat(sat.replace("Z", "+00:00"))
                except Exception:
                    continue
                for rid, rtime in review_times:
                    if st > rtime:
                        later_ids.append(sid)
                        break

            if not later_ids:
                rates[pk] = None
                continue

            accepted = 0
            for f in findings:
                ffile = f.get("file") or ""
                fline = f.get("line") or 0
                if not ffile:
                    continue
                if touched_by_later_session(ffile, fline, later_ids):
                    accepted += 1

            rates[pk] = round(accepted / len(findings), 4) if findings else 0.0

        return rates

    def _detect_blind_spots(self, persona_keys, persona_stats, sessions_out):
        total_session_count = len(sessions_out)
        blind_spots = []
        session_positions = {}
        for i, s in enumerate(sessions_out):
            session_positions[s["sessionId"]] = i

        for pk in persona_keys:
            pinfo = PERSONA_MAP[pk]
            group = pinfo["group"]

            if group in BLIND_SPOT_EXCLUDED_GROUPS:
                continue

            stats = persona_stats[pk]
            last_ts = stats.get("lastDispatchedAt")

            if not last_ts or not stats["sessionIds"]:
                if group in ALWAYS_ON_GROUPS:
                    blind_spots.append({
                        "agentType": f"compound-engineering:{pk}",
                        "displayName": pinfo["displayName"],
                        "reason": f"{pinfo['displayName']} reviewer has never been dispatched",
                        "sessionsSinceLastDispatch": total_session_count,
                    })
                continue

            last_sid = max(stats["sessionIds"], key=lambda sid: session_positions.get(sid, -1))
            last_pos = session_positions.get(last_sid, -1)
            sessions_since = total_session_count - last_pos - 1

            if group in ALWAYS_ON_GROUPS and sessions_since > 3:
                blind_spots.append({
                    "agentType": f"compound-engineering:{pk}",
                    "displayName": pinfo["displayName"],
                    "reason": f"{pinfo['displayName']} reviewer hasn't been dispatched in {sessions_since} sessions (last: {stats['lastDispatchedAt'][:10]})",
                    "sessionsSinceLastDispatch": sessions_since,
                })
            elif group == "conditional" and sessions_since > 5:
                blind_spots.append({
                    "agentType": f"compound-engineering:{pk}",
                    "displayName": pinfo["displayName"],
                    "reason": f"{pinfo['displayName']} reviewer hasn't been dispatched in {sessions_since} sessions (last: {stats['lastDispatchedAt'][:10]})",
                    "sessionsSinceLastDispatch": sessions_since,
                })

        return blind_spots

    def _filter_analytics(self, resp, project, days):
        if not project and not days:
            return resp

        filtered = dict(resp)
        now = datetime.now().timestamp()

        sessions = resp.get("sessions", [])
        if project:
            sessions = [s for s in sessions if s.get("project") == project]
        if days:
            cutoff = now - days * 86400
            sessions = [s for s in sessions if s.get("startedAt") and _parse_iso(s["startedAt"]) > cutoff]

        filtered_sids = {s["sessionId"] for s in sessions}
        filtered["sessions"] = sessions

        matrix = {}
        for pk, row in resp.get("matrix", {}).items():
            matrix[pk] = {sid: v for sid, v in row.items() if sid in filtered_sids}
        filtered["matrix"] = matrix

        personas = []
        for p in resp.get("personas", []):
            pk = p["agentType"].replace("compound-engineering:", "")
            pf = dict(p)
            pf["totalFindings"] = sum(v for sid, v in matrix.get(pk, {}).items() if isinstance(v, int) and v >= 0)
            pf["highSeverityCount"] = 0
            pf["lastDispatchedAt"] = None
            for sid, v in matrix.get(pk, {}).items():
                if v >= 0:
                    ts = next((s["startedAt"] for s in sessions if s["sessionId"] == sid), None)
                    if ts and (not pf["lastDispatchedAt"] or ts > pf["lastDispatchedAt"]):
                        pf["lastDispatchedAt"] = ts
            personas.append(pf)
        filtered["personas"] = personas

        trends = {}
        for pk, trend in resp.get("trends", {}).items():
            trends[pk] = [t for t in trend if t.get("sessionId") in filtered_sids]
        filtered["trends"] = trends

        filtered["blindSpots"] = resp.get("blindSpots", [])

        return filtered


def _parse_iso(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


if __name__ == "__main__":
    port = 8765
    print(f"Session Dashboard on http://localhost:{port}")
    print(f"Reading: {CLAUDE_DIR}")
    http.server.HTTPServer(("", port), Handler).serve_forever()
