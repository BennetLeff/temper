import { emit, on, fmtDuration, fmtTime } from './db.js';

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function badge(icon, text, cls = '') {
  const s = document.createElement('span');
  s.className = 'badge' + (cls ? ' ' + cls : '');
  s.textContent = icon ? `${icon} ${text}` : text;
  return s;
}

function sectionHeader(label) {
  const h = document.createElement('h4');
  h.textContent = `── ${label} ──`;
  h.style.cssText = 'color:var(--text-muted);font-size:0.78rem;margin-bottom:8px;';
  return h;
}

function toggle(card, summaryEl, btn, session) {
  const expanded = card.classList.toggle('expanded');
  summaryEl.classList.toggle('expanded');
  if (btn) btn.textContent = expanded ? 'Show Less ▲' : 'Show More ▼';
  if (expanded) emit('session:expanded', { session });
}

function renderBadges(session, hasSummary) {
  const row = document.createElement('div');
  row.className = 'card-badges';
  const add = (icon, text, cls) => row.appendChild(badge(icon, text, cls));
  if (session.duration != null) add('⏱', fmtDuration(session.duration));
  if (session.subAgents?.length) add('🤖', `${session.subAgents.length} agents`);
  if (session.cost != null) add('💰', `$${session.cost.toFixed(2)}`);
  if (session.model) add('', session.model);
  if (session.branch) add('', session.branch);
  if (session.date) add('', fmtTime(session.date));
  if (!hasSummary && session.summarizationStatus === 'in_progress') add('', 'Generating summary...', 'badge-stale');
  if (hasSummary) {
    const btn = document.createElement('button');
    btn.className = 'btn';
    btn.textContent = 'Show More ▼';
    btn.style.marginLeft = 'auto';
    row.appendChild(btn);
  }
  return row;
}

function renderSubAgents(agents) {
  if (!agents?.length) return null;
  const frag = document.createDocumentFragment();
  frag.appendChild(sectionHeader('Sub-agents'));
  const list = document.createElement('ul');
  list.style.cssText = 'list-style:none;padding:0;margin:0 0 12px;';
  for (const a of agents) {
    const li = document.createElement('li');
    li.style.cssText = 'padding:4px 0;border-bottom:1px solid var(--border);font-size:0.85rem;';
    li.textContent = `├─ ${a.description || a.agentType || 'Unknown agent'}`;
    const meta = document.createElement('span');
    meta.style.cssText = 'color:var(--text-muted);font-size:0.72rem;margin-left:16px;display:block;';
    if (a.agentType) {
      meta.textContent = `agentType: ${a.agentType}`;
      const extras = [];
      if (a.findings) extras.push(`${a.findings} findings`);
      if (a.sources) extras.push(`${a.sources} sources`);
      if (a.docs) extras.push(`${a.docs} docs`);
      if (extras.length) meta.textContent += ` · ${extras.join(' · ')}`;
    }
    li.appendChild(meta);
    list.appendChild(li);
  }
  frag.appendChild(list);
  return frag;
}

function renderTimeline(timeline) {
  if (!timeline?.length) return null;
  const frag = document.createDocumentFragment();
  frag.appendChild(sectionHeader('Timeline'));
  const row = document.createElement('div');
  row.style.cssText = 'display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;';
  for (const p of timeline) {
    const seg = document.createElement('span');
    seg.style.cssText = 'font-size:0.75rem;color:var(--text-muted);';
    const mins = Math.floor((p.time || 0) / 60000);
    seg.textContent = `[${String(mins).padStart(2, '0')}:00] ${p.label || ''}`;
    row.appendChild(seg);
  }
  frag.appendChild(row);
  return frag;
}

function renderArtifacts(artifacts) {
  if (!artifacts?.length) return null;
  const frag = document.createDocumentFragment();
  frag.appendChild(sectionHeader('Artifacts'));
  const div = document.createElement('div');
  div.style.marginBottom = '12px';
  for (const path of artifacts) {
    const p = document.createElement('div');
    p.style.cssText = 'font-size:0.85rem;margin-bottom:4px;';
    p.innerHTML = `&#x1F4C4; ${esc(path)}`;
    div.appendChild(p);
  }
  frag.appendChild(div);
  return frag;
}

function renderDetail(session, hasSummary) {
  const detail = document.createElement('div');
  detail.className = 'card-detail';
  if (hasSummary) {
    const sa = renderSubAgents(session.subAgents);
    if (sa) detail.appendChild(sa);
    const tl = renderTimeline(session.timeline);
    if (tl) detail.appendChild(tl);
    const ar = renderArtifacts(session.artifacts);
    if (ar) detail.appendChild(ar);
  } else {
    const notice = document.createElement('div');
    notice.style.cssText = 'color:var(--text-muted);font-size:0.85rem;';
    notice.textContent = 'No summary available yet.';
    detail.appendChild(notice);
    if (session.subAgents?.length) {
      const p = document.createElement('p');
      p.style.cssText = 'margin-top:8px;color:var(--text-muted);font-size:0.85rem;';
      p.textContent = `${session.subAgents.length} sub-agents dispatched`;
      detail.appendChild(p);
    }
    if (session.artifacts?.length) {
      const p = document.createElement('p');
      p.style.cssText = 'margin-top:4px;color:var(--text-muted);font-size:0.85rem;';
      p.textContent = `${session.artifacts.length} file artifacts`;
      detail.appendChild(p);
    }
  }
  const rawBtn = document.createElement('button');
  rawBtn.className = 'btn';
  rawBtn.textContent = 'View raw conversation';
  rawBtn.style.marginTop = '12px';
  rawBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    emit('session:view-raw', { sessionId: session.id });
  });
  detail.appendChild(rawBtn);
  return detail;
}

export function renderCard(session) {
  const hasSummary = !!(session.summary && session.summary.trim());
  const card = document.createElement('div');
  card.className = 'session-card';
  if (!hasSummary) { card.style.borderStyle = 'dashed'; card.style.opacity = '0.85'; }

  const summaryEl = document.createElement('div');
  summaryEl.className = 'card-summary';
  if (hasSummary) {
    summaryEl.textContent = session.summary;
  } else if (session.skeletonPreview) {
    summaryEl.innerHTML = `<span style="color:var(--text-muted)">${esc(session.skeletonPreview.slice(0, 120))}</span>`;
  } else {
    summaryEl.innerHTML = '<span style="color:var(--text-muted)">No summary available</span>';
  }
  card.appendChild(summaryEl);

  const badgeRow = renderBadges(session, hasSummary);
  card.appendChild(badgeRow);

  card.appendChild(renderDetail(session, hasSummary));

  const toggleBtn = badgeRow.querySelector('.btn');
  card.addEventListener('click', () => {
    if (hasSummary) toggle(card, summaryEl, toggleBtn, session);
    else card.classList.toggle('expanded');
  });
  if (toggleBtn) {
    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggle(card, summaryEl, toggleBtn, session);
    });
  }
  return card;
}

export function renderCards(sessions, container) {
  const frag = document.createDocumentFragment();
  for (const s of sessions) frag.appendChild(renderCard(s));
  container.appendChild(frag);
}
