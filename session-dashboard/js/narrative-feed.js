import { on, fmtTime } from './db.js';
import { renderCard } from './session-card.js';
import { discoverSessions, listSessions } from './session-store.js';

let _sessions = [];
let _filters = { project: '', status: 'all', dateRange: 'all' };

const _CSS = `
.feed-timeline { position: relative; padding-left: 88px; }
.feed-timeline::before { content: ''; position: absolute; left: 68px; top: 0; bottom: 0; width: 2px; background: var(--border); }
.feed-entry { position: relative; margin-bottom: 20px; }
.feed-dot { position: absolute; left: -24px; top: 18px; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); border: 2px solid var(--bg); z-index: 1; }
.feed-dot.active { background: var(--green); }
.feed-time { position: absolute; left: -84px; top: 16px; width: 56px; text-align: right; font-size: 0.72rem; color: var(--text-muted); white-space: nowrap; }
.feed-date-header { font-size: 0.8rem; color: var(--text-muted); padding: 8px 0 8px 0; margin-bottom: 4px; border-bottom: 1px solid var(--border); }
`;

const _style = document.createElement('style');
_style.textContent = _CSS;
document.head.appendChild(_style);

function _dateLabel(ts) {
  const d = new Date(ts);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  if (target.getTime() === today.getTime()) return 'Today';
  if (target.getTime() === yesterday.getTime()) return 'Yesterday';
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function _groupByDate(sessions) {
  const map = new Map();
  for (const s of sessions) {
    const key = _dateLabel(s.timestamp || s.date);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(s);
  }
  return map;
}

function _filtered() {
  return _sessions.filter(s => {
    if (_filters.project && s.project !== _filters.project) return false;
    if (_filters.status === 'completed' && s.status !== 'completed') return false;
    if (_filters.dateRange !== 'all') {
      const cutoff = Date.now() - parseInt(_filters.dateRange, 10) * 86400000;
      const ts = s.timestamp || s.date;
      if (ts < cutoff) return false;
    }
    return true;
  });
}

function _renderFilterBar() {
  let bar = document.getElementById('filter-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'filter-bar';
    bar.style.cssText = 'display:flex;gap:8px;align-items:center;padding:8px 0;margin-bottom:16px;flex-wrap:wrap;';
    const main = document.getElementById('app-main');
    main.insertBefore(bar, main.firstChild);
  }

  const projects = [...new Set(_sessions.map(s => s.project).filter(Boolean))].sort();

  bar.innerHTML = [
    `<select class="btn" id="ff-project">
      <option value="">All Projects</option>
      ${projects.map(p => `<option value="${p}" ${_filters.project === p ? 'selected' : ''}>${p}</option>`).join('')}
    </select>`,
    `<select class="btn" id="ff-status">
      <option value="all" ${_filters.status === 'all' ? 'selected' : ''}>All</option>
      <option value="active" ${_filters.status === 'active' ? 'selected' : ''}>Active</option>
      <option value="completed" ${_filters.status === 'completed' ? 'selected' : ''}>Completed</option>
    </select>`,
    `<select class="btn" id="ff-date">
      <option value="all" ${_filters.dateRange === 'all' ? 'selected' : ''}>All Time</option>
      <option value="7" ${_filters.dateRange === '7' ? 'selected' : ''}>Last 7 Days</option>
      <option value="30" ${_filters.dateRange === '30' ? 'selected' : ''}>Last 30 Days</option>
      <option value="90" ${_filters.dateRange === '90' ? 'selected' : ''}>Last 90 Days</option>
    </select>`,
    '<button class="btn btn-primary" id="ff-discover">Discover Sessions</button>',
  ].join('');

  document.getElementById('ff-project').onchange = e => { _filters.project = e.target.value; _renderFeed(); };
  document.getElementById('ff-status').onchange = e => { _filters.status = e.target.value; _renderFeed(); };
  document.getElementById('ff-date').onchange = e => { _filters.dateRange = e.target.value; _renderFeed(); };
  document.getElementById('ff-discover').onclick = async () => {
    const btn = document.getElementById('ff-discover');
    btn.textContent = 'Discovering...';
    btn.disabled = true;
    try { await discoverSessions(); } catch (e) { console.error('Discover failed:', e); }
    btn.textContent = 'Discover Sessions';
    btn.disabled = false;
  };
}

function _renderFeed() {
  const list = document.getElementById('session-list');
  const filtered = _filtered();

  if (!filtered.length) {
    list.className = 'empty-state';
    list.innerHTML = '<h2>No sessions found.</h2><p>Click \'Discover\' to scan for sessions.</p>';
    return;
  }

  list.className = 'feed-timeline';
  list.innerHTML = '';

  const groups = _groupByDate(filtered);
  for (const [label, sessions] of groups) {
    const header = document.createElement('div');
    header.className = 'feed-date-header';
    header.textContent = label;
    list.appendChild(header);

    for (const s of sessions) {
      const entry = document.createElement('div');
      entry.className = 'feed-entry';

      const time = document.createElement('div');
      time.className = 'feed-time';
      time.textContent = fmtTime(s.timestamp || s.date);
      entry.appendChild(time);

      const dot = document.createElement('div');
      dot.className = s.status === 'active' ? 'feed-dot active' : 'feed-dot';
      entry.appendChild(dot);

      entry.appendChild(renderCard(s));
      list.appendChild(entry);
    }
  }
}

export function renderFeed(sessions) {
  _sessions = sessions || [];
  _renderFilterBar();
  _renderFeed();
}

// Proactive init — store may already be ready before we registered listeners
listSessions().then(s => { if (s.length) renderFeed(s); }).catch(() => {});

let _bound = false;
function _bind() {
  if (_bound) return;
  _bound = true;
  on('store:discovered', async () => { try { const sessions = await listSessions(); emit('sessions:loaded', { sessions }); renderFeed(sessions); } catch {} });
  on('store:ready', async () => { try { const sessions = await listSessions(); emit('sessions:loaded', { sessions }); renderFeed(sessions); } catch {} });
}

_bind();
