// Session data layer — calls local API server (server.py)
import { emit } from './db.js';

let _sessions = [];
let _dbReady = false;

function setStatus(msg, err) {
  const s = document.getElementById('status-bar');
  if (s) { s.textContent = msg; if (err) s.style.color = '#f85149'; }
}

export async function discoverSessions() {
  setStatus('Scanning sessions...');
  try {
    const res = await fetch('/api/discover');
    const data = await res.json();
    _sessions = data.sessions || [];
    _dbReady = true;
    emit('store:discovered', { count: _sessions.length });
    emit('sessions:loaded', { sessions: _sessions });
    setStatus(`${_sessions.length} sessions loaded`);
    return _sessions.length;
  } catch (e) {
    setStatus('Scan error: ' + e.message, true);
    emit('store:error', { error: e.message });
    return 0;
  }
}

export async function autoDiscover() {
  return discoverSessions();
}

export async function listSessions(filters = {}) {
  if (!_dbReady) await discoverSessions();
  let sessions = [..._sessions];
  if (filters.project) sessions = sessions.filter(s => s.project === filters.project);
  if (filters.platform) sessions = sessions.filter(s => s.platform === filters.platform);
  sessions.sort((a, b) => {
    const ta = a.startedAt ? new Date(a.startedAt).getTime() : 0;
    const tb = b.startedAt ? new Date(b.startedAt).getTime() : 0;
    return tb - ta;
  });
  return sessions;
}

export async function getSessionDetail(sessionId) {
  try {
    const res = await fetch(`/api/session/${sessionId}`);
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}

export async function getSessionsByProject(project) {
  const sessions = _sessions.filter(s => s.project === project);
  return { project, count: sessions.length, sessions };
}

// Auto-init on import
setStatus('Initializing...');
autoDiscover().then(() => {
  emit('store:ready', {});
}).catch(() => {
  setStatus('Server not reachable — is server.py running?', true);
});
