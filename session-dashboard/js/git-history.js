// git-history.js — Git-log-style session history visualization
import { on, emit, fmtTime } from './db.js';

const S = document.createElement('style');
S.textContent = `
.git-log{font-family:'SF Mono','Fira Code',monospace;font-size:.82rem;line-height:1.7}
.git-log .commit{color:var(--accent)}
.git-log .branch{color:var(--green);font-weight:600}
.git-log .ref{color:var(--yellow)}
.git-log .message{color:var(--text)}
.git-log .meta{color:var(--text-muted);font-size:.75rem}
.git-log .graph-connector{color:var(--red)}
.git-entry{display:flex;gap:6px;align-items:baseline;cursor:pointer;padding:2px 4px;white-space:nowrap}
.git-entry:hover{background:var(--accent-dim);border-radius:4px}
.git-entry .graph-line{flex-shrink:0;min-width:1.2em;text-align:right}
.git-detail{display:none;padding:4px 0 12px 24px;color:var(--text-muted);font-size:.78rem;line-height:1.6;border-bottom:1px solid var(--border);margin-bottom:4px}
.git-entry.expanded+.git-detail{display:block}
#app-main[data-view="git-log"] #session-list{display:none}
#app-main[data-view="git-log"] #git-log-view{display:block}
#app-main:not([data-view="git-log"]) #git-log-view{display:none}
@media(max-width:600px){.git-log{font-size:.75rem}.git-entry{flex-wrap:wrap}.git-entry .graph-line{display:none}}
`;
document.head.appendChild(S);

// --- Utilities ---
const M = 6e4, H = 36e5, D = 864e5, W = 6048e5;

function rel(ts) {
  if (!ts) return '\u2014';
  const d = Date.now() - new Date(ts).getTime();
  if (d < M) return 'just now';
  if (d < H) return Math.floor(d / M) + 'm ago';
  if (d < D) return Math.floor(d / H) + 'h ago';
  if (d < D * 2) return 'yesterday';
  if (d < W) return Math.floor(d / D) + 'd ago';
  return fmtTime(ts);
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
}

// --- Tree builder ---
function buildTree(sessions) {
  const byId = new Map(sessions.map(s => [s.sessionId, { ...s, children: [] }]));
  const roots = [];
  for (const s of byId.values()) {
    if (s.parentSessionId && byId.has(s.parentSessionId))
      byId.get(s.parentSessionId).children.push(s);
    else roots.push(s);
  }
  return roots;
}

// --- Render one entry (recursive) ---
function renderEntry(node, depth, pref, isLast, container) {
  const el = document.createElement('div');
  el.className = 'git-entry';

  const g = document.createElement('span');
  g.className = 'graph-line graph-connector';
  g.textContent = depth > 0 ? pref + (isLast ? '\u2514\u2500' : '\u251C\u2500') : '';

  const hash = document.createElement('span');
  hash.className = 'commit';
  hash.textContent = (node.sessionId || '').slice(0, 7);

  const branch = document.createElement('span');
  branch.className = 'branch';
  branch.textContent = node.parentSessionId
    ? `(${node.branch || 'branch'})`
    : '(main)';

  const msg = document.createElement('span');
  msg.className = 'message';
  const summary = (node.summary || node.message || '').split('\n')[0].slice(0, 100);
  msg.textContent = summary;

  const meta = document.createElement('span');
  meta.className = 'meta';
  const subN = (node.children || []).length;
  meta.textContent = [
    rel(node.timestamp || node.created || node.date),
    subN ? subN + ' sub-agent' + (subN > 1 ? 's' : '') : ''
  ].filter(Boolean).join('  ');

  el.append(g, hash, ' ', branch, ' ', msg, ' ', meta);

  const det = document.createElement('div');
  det.className = 'git-detail';
  const parts = [];
  if (summary) parts.push(`<div>${esc(summary)}</div>`);
  if (node.artifacts && node.artifacts.length)
    parts.push(`<div>Artifacts: ${node.artifacts.map(esc).join(', ')}</div>`);
  if (node.children && node.children.length) {
    parts.push('<div style="margin-top:6px;font-weight:600">Sub-agent tree:</div><div>' +
      node.children.map((c, i) => {
        const pf = i === node.children.length - 1 ? '\u2514\u2500 ' : '\u251C\u2500 ';
        const h = esc((c.sessionId || '').slice(0, 7));
        const m = esc((c.summary || c.message || '').split('\n')[0].slice(0, 80));
        return pf + `<span class="commit">${h}</span> ${m}`;
      }).join('<br>') + '</div>');
  }
  det.innerHTML = parts.join('');

  el.addEventListener('click', () => el.classList.toggle('expanded'));
  container.appendChild(el);
  container.appendChild(det);

  if (node.children) node.children.forEach((c, i) => {
    const childPref = depth === 0 ? '  ' : pref + (isLast ? '   ' : '\u2502  ');
    renderEntry(c, depth + 1, childPref, i === node.children.length - 1, container);
  });
}

// --- Public API ---
export function renderGitHistory(sessions, containerEl) {
  containerEl.innerHTML = '';
  const log = document.createElement('div');
  log.className = 'git-log';
  const roots = buildTree(sessions || []);
  if (!roots.length) {
    log.innerHTML = '<div class="empty-state"><h2>No sessions</h2></div>';
    containerEl.appendChild(log);
    return;
  }
  roots.forEach((r, i) => renderEntry(r, 0, '', i === roots.length - 1, log));
  containerEl.appendChild(log);
}

// --- Toggle + init ---
export function initGitHistory() {
  const main = document.getElementById('app-main');
  if (!main) return;

  let toggle = document.getElementById('view-toggle');
  if (!toggle) {
    toggle = document.createElement('button');
    toggle.id = 'view-toggle';
    toggle.className = 'btn';
    main.before(toggle);
  }

  const _sync = () => {
    toggle.textContent = main.dataset.view === 'git-log' ? 'Timeline' : 'Git Log';
  };

  toggle.addEventListener('click', () => {
    main.dataset.view = main.dataset.view === 'git-log' ? 'timeline' : 'git-log';
    _sync();
    emit('view:toggle', main.dataset.view);
  });

  let c = document.getElementById('git-log-view');
  if (!c) { c = document.createElement('div'); c.id = 'git-log-view'; main.appendChild(c); }

  _sync();
  on('sessions:loaded', ({ sessions }) => renderGitHistory(sessions, c));
}

// Auto-init
if (document.readyState !== 'loading') initGitHistory();
else document.addEventListener('DOMContentLoaded', initGitHistory);
