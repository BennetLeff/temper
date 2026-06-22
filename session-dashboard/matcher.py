"""Heuristic artifact matcher — 3-signal weighted scoring for session-dashboard."""

import os
import re
from datetime import datetime, timezone

DEFAULT_STOPWORDS = {
    "a","an","the","is","are","was","were","in","on","at","of","for","to",
    "with","by","and","or","not","this","that","from","as","be","has","have",
    "do","does","did","will","would","can","could","may","might","shall",
    "should","about","into","through","during","before","after","above",
    "below","between","out","off","over","under","again","further","then",
    "once","here","there","when","where","why","how","all","each","every",
    "both","few","more","most","other","some","such","no","nor","only",
    "own","same","so","than","too","very","just","also","now",
}

_AGENT_DIR_MAP = {
    "ce-plan": "plans",
    "ce-brainstorm": "brainstorms",
    "ce-ideate": "brainstorms",
    "ce-product-pulse": "brainstorms",
    "ce-strategy": "brainstorms",
    "ce-code-review": "reviews",
    "ce-compound": "solutions",
    "ce-debug": "fixes",
    "ce-doc-review": "reviews",
    "ce-proof": "reviews",
    "ce-resolve-pr-feedback": "reviews",
    "ce-plan-design": "designs",
    "ce-frontend-design": "designs",
    "ce-demo-reel": "reports",
    "ce-polish-beta": "polish",
    "ce-work": "work",
    "ce-work-beta": "work",
}


def _get_stopwords():
    raw = os.environ.get("MATCHER_STOPWORDS")
    if raw:
        return {w.strip().lower() for w in raw.split(",") if w.strip()}
    return DEFAULT_STOPWORDS


def _extract_keywords(text):
    if not text:
        return []
    words = re.split(r"\W+", text.lower())
    stopwords = _get_stopwords()
    seen = set()
    result = []
    for w in words:
        if w and w not in stopwords and w not in seen:
            seen.add(w)
            result.append(w)
    result.sort(key=len, reverse=True)
    return result[:15]


def _parse_frontmatter_title(content):
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    fm = content[3:end]
    for line in fm.split("\n"):
        line = line.strip()
        if line.startswith("title:"):
            val = line[len("title:"):].strip().strip("\"'")
            return val
    return None


def _read_file_head(filepath, max_bytes=1024):
    try:
        with open(filepath, "rb") as f:
            raw = f.read(max_bytes)
            return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def scan_project_docs(project_root):
    docs_dir = os.path.join(project_root, "docs")
    if not os.path.isdir(docs_dir):
        return []
    artifacts = []
    for root, dirs, files in os.walk(docs_dir):
        for fn in files:
            if fn.startswith("."):
                continue
            fp = os.path.join(root, fn)
            try:
                st = os.stat(fp)
            except OSError:
                continue
            artifacts.append({
                "path": os.path.relpath(fp, project_root),
                "mtime": st.st_mtime,
                "exists": True,
            })
    return artifacts


def score_artifact(artifact_path, mtime, session_meta):
    scores = {}
    reasons = []

    session_start_str = session_meta.get("startedAt")
    session_duration = session_meta.get("duration")
    session_summary = session_meta.get("summary") or session_meta.get("description") or ""
    agent_type = session_meta.get("agentType") or ""

    ts_score = 0.0
    if session_start_str:
        try:
            t = datetime.fromisoformat(str(session_start_str).replace("Z", "+00:00"))
            session_start_ts = t.timestamp()
        except (ValueError, TypeError):
            session_start_ts = None
        if session_start_ts is not None:
            window_start = session_start_ts - 300
            if session_duration:
                window_end = session_start_ts + (session_duration / 1000) + 300
            else:
                window_end = session_start_ts + 300
            if window_start <= mtime <= window_end:
                ts_score = 1.0
                reasons.append("timestamp")
            else:
                dist = min(abs(mtime - window_start), abs(mtime - window_end))
                ts_score = max(0.0, 1.0 - (dist / 600.0))
                if ts_score > 0:
                    reasons.append("timestamp")
    scores["timestamp"] = 0.5 * ts_score

    kw_score = 0.0
    keywords = _extract_keywords(session_summary)
    if keywords:
        fname = os.path.basename(artifact_path).lower()
        match_text = fname
        head = _read_file_head(artifact_path)
        if head:
            title = _parse_frontmatter_title(head)
            if title:
                match_text += " " + title.lower()
            match_text += " " + head.lower()
        hits = sum(1 for kw in keywords if kw in match_text)
        kw_score = hits / len(keywords)
        if kw_score > 0:
            reasons.append("keywords")
    scores["keywords"] = 0.3 * kw_score

    at_score = 0.0
    if agent_type:
        artifact_dir = artifact_path.split("/")
        for ad in artifact_dir:
            expected = _AGENT_DIR_MAP.get(agent_type.split(":")[0])
            if expected and expected in ad:
                at_score = 1.0
                reasons.append("agentType")
                break
        if at_score == 0.0:
            for key, expected in _AGENT_DIR_MAP.items():
                if key in agent_type or agent_type in key:
                    at_score = 0.5
                    reasons.append("agentType")
                    break
    scores["agentType"] = 0.2 * at_score

    combined = sum(scores.values())
    if combined >= 0.5:
        confidence = "high"
    elif combined >= 0.25:
        confidence = "medium"
    elif combined >= 0.1:
        confidence = "low"
    else:
        return None

    return {
        "path": artifact_path,
        "confidence": confidence,
        "score": round(combined, 3),
        "match_method": "+".join(sorted(reasons)) if reasons else "none",
        "mtime": mtime,
        "exists": os.path.isfile(artifact_path),
    }


def _find_project_root(cwd):
    if cwd:
        resolved = os.path.realpath(cwd)
        while True:
            if os.path.isdir(os.path.join(resolved, ".git")):
                return resolved
            parent = os.path.dirname(resolved)
            if parent == resolved:
                break
            resolved = parent
    return os.path.realpath(os.environ.get("PROJECT_ROOT", os.getcwd()))


def match_session(session, project_root=None):
    if project_root is None:
        project_root = _find_project_root(session.get("cwd"))
    session_meta = dict(session)

    sub_agents = session_meta.pop("subAgents", session_meta.pop("sub_agents", None))
    if sub_agents and isinstance(sub_agents, list):
        all_results = []
        seen = set()
        for sa in sub_agents:
            sa_meta = dict(session_meta)
            sa_meta.update(sa)
            for r in match_session(sa_meta, project_root):
                if r["path"] not in seen:
                    seen.add(r["path"])
                    all_results.append(r)
        # Also run for parent
        for r in match_session(session_meta, project_root):
            if r["path"] not in seen:
                seen.add(r["path"])
                all_results.append(r)
        return all_results

    artifacts = scan_project_docs(project_root)
    results = []
    for a in artifacts:
        result = score_artifact(a["path"], a["mtime"], session_meta)
        if result:
            results.append(result)
    results.sort(key=lambda x: ({"high": 0, "medium": 1, "low": 2}[x["confidence"]], -x["mtime"]))
    return results
