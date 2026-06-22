// Session Output File Browser — surfaces artifacts produced by sessions/sub-agents
import { on, emit } from './db.js';

const TYPE_PATTERNS = [
  [/^docs\/ideation\//, 'idea'],
  [/^docs\/plans\//, 'plan'],
  [/^docs\/brainstorms\//, 'req'],
  [/^docs\/solutions\//, 'soln'],
  [/^docs\/hardware\//, 'hw'],
  [/\.(py|js|c|ts|jsx|tsx|rs|go|java|cpp|h)$/, 'code'],
  [/^docs\//, 'doc'],
];

const SKIP_PREFIXES = ['tmp/', 'var/', 'node_modules/'];

function esc(s) { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; }

// --- Artifact detection ---

function detectType(path) {
  for (const [re, badge] of TYPE_PATTERNS) {
    if (re.test(path)) return badge;
  }
  return 'other';
}

function normalizePath(raw, projectRoot) {
  if (!raw) return null;
  let p = raw;
  if (p.startsWith(projectRoot)) p = p.slice(projectRoot.length);
  p = p.replace(/^\/+/, '');
  if (SKIP_PREFIXES.some(pref => p.startsWith(pref))) return null;
  return p;
}

function parseWriteEditCalls(session, projectRoot) {
  const found = [];
  const conv = session.conversation || [];
  for (const entry of conv) {
    const calls = entry.tool_calls || entry.toolUse || [];
    for (const tc of calls) {
      const type = (tc.type || tc.name || '').toLowerCase();
      if (type !== 'write' && type !== 'edit') continue;
      const args = tc.args || tc.input || {};
      const raw = args.file_path || args.filePath || args.path || '';
      const path = normalizePath(raw, projectRoot || '/');
      if (!path) continue;
      found.push({
        path,
        type: detectType(path),
        role: 'created',
        confidence: 'high',
        subAgent: null,
      });
    }
  }
  return found;
}

function timestampMatch(session) {
  if (!session.fileTimestamps || !session.fileTimestamps.length) return [];
  const start = session.startedAt || session.timestamp || 0;
  const end = session.lastTs || Date.now();
  if (!start) return [];
  return session.fileTimestamps
    .filter(f => f.mtime >= start && f.mtime <= end)
    .map(f => ({
      path: f.path,
      type: detectType(f.path),
      role: 'modified',
      confidence: 'medium',
      subAgent: null,
    }));
}

function existsOnDisk(path) {
  return true; // check delegated to caller via precomputed data
}

// --- Public API ---

export function extractArtifacts(session) {
  if (!session) return [];
  const root = session.projectRoot || '/';
  const primary = parseWriteEditCalls(session, root);
  const seen = new Set(primary.map(a => a.path));
  const secondary = timestampMatch(session).filter(a => !seen.has(a.path));

  let artifacts = [...primary, ...secondary];

  if (session.deletedFiles) {
    const deletedSet = new Set(session.deletedFiles);
    artifacts = artifacts.map(a =>
      deletedSet.has(a.path) ? { ...a, deleted: true } : a
    );
  }

  if (session.subAgents) {
    for (const sub of session.subAgents) {
      const label = sub.description || sub.type || sub.agentType || 'sub-agent';
      const subArts = extractArtifacts({ ...sub, projectRoot: root });
      artifacts.push(...subArts.map(a => ({ ...a, subAgent: label })));
    }
  }

  return artifacts;
}

export function renderArtifacts(artifacts, containerEl) {
  if (!containerEl) return;
  containerEl.innerHTML = '';

  if (!artifacts || !artifacts.length) {
    containerEl.innerHTML = '<div class="empty-state" style="padding:16px">No artifacts produced</div>';
    return;
  }

  const high = artifacts.filter(a => a.confidence === 'high');
  const med = artifacts.filter(a => a.confidence === 'medium');

  function _renderGroup(items, label) {
    if (!items.length) return '';
    const rows = items.map(a => {
      const del = a.deleted ? ' <span style="color:var(--red);font-size:0.7rem">(deleted)</span>' : '';
      const sub = a.subAgent ? ` <span style="color:var(--text-muted);font-size:0.7rem">via ${esc(a.subAgent)}</span>` : '';
      const conf = a.confidence === 'medium'
        ? ' <span style="color:var(--yellow);font-size:0.65rem" title="Timestamp correlation">&#9679;</span>'
        : '';
      return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0;font-size:0.82rem">
        <span class="badge" style="background:var(--accent-dim);color:var(--accent)">${a.type}</span>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(a.path)}</span>${sub}${del}${conf}
      </div>`;
    }).join('');
    return `<div style="margin-bottom:6px"><div style="font-size:0.7rem;color:var(--text-muted);margin-bottom:2px">${label}</div>${rows}</div>`;
  }

  containerEl.innerHTML = _renderGroup(high, 'Produced files (high confidence)')
    + _renderGroup(med, 'Produced files (medium confidence)');
}

export function renderArtifactBrowser(sessions) {
  if (!sessions || !sessions.length) {
    return '<div class="empty-state"><h2>No sessions loaded</h2></div>';
  }

  const groups = sessions.map(s => {
    const arts = extractArtifacts(s);
    if (!arts.length) return null;
    const sid = s.id || s.sessionId || '???';
    const label = s.description || s.summary || sid;
    const div = document.createElement('div');
    renderArtifacts(arts, div);
    return `<div class="session-card" style="margin-bottom:12px">
      <div style="font-weight:600;margin-bottom:8px;font-size:0.9rem">${esc(label)}</div>
      ${div.innerHTML}
    </div>`;
  }).filter(Boolean).join('');

  return groups || '<div class="empty-state"><h2>No artifacts found across sessions</h2></div>';
}

// --- Session card integration (L2 detail) ---

on('session:expanded', ({ session, detailEl }) => {
  if (!detailEl) return;
  const arts = extractArtifacts(session);
  const wrapper = document.createElement('div');
  wrapper.style.marginTop = '4px';
  renderArtifacts(arts, wrapper);
  const existing = detailEl.querySelector('.artifact-browser-section');
  if (existing) existing.remove();
  wrapper.classList.add('artifact-browser-section');
  detailEl.appendChild(wrapper);
});

on('output-browser:open', ({ sessions, containerId }) => {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = renderArtifactBrowser(sessions);
  emit('output-browser:rendered', { containerId });
});
