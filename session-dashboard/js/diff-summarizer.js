import { emit } from './db.js';

const API_URL = 'https://api.anthropic.com/v1/messages';
const MODEL = 'claude-3-5-haiku-20241022';
const MAX_TOKENS = 500;
const MAX_BASELINES = 2;
const CACHE_PFX = 'diff-summary:';
const h = s => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };

function cacheKey(sid, bids) { return CACHE_PFX + sid + '|' + [...bids].sort().join(','); }
function getCached(sid, bids) {
  try { const r = localStorage.getItem(cacheKey(sid, bids)); return r ? JSON.parse(r) : null; } catch { return null; }
}
function setCache(sid, bids, data) {
  try { localStorage.setItem(cacheKey(sid, bids), JSON.stringify(data)); } catch { /* quota */ }
}

function jaccard(a, b) {
  if (!a || !b || !a.length || !b.length) return 0;
  const sa = new Set(a.map(k => k.toLowerCase())), sb = new Set(b.map(k => k.toLowerCase()));
  return [...sa].filter(k => sb.has(k)).length / new Set([...sa, ...sb]).size;
}

function hasDepLink(a, b) {
  const da = a.deps || [], db = b.deps || [];
  return da.some(d => d.includes(b.id)) || db.some(d => d.includes(a.id))
    || (a.parent && a.parent === b.id) || (b.parent && b.parent === a.id);
}

function matchOutputDirs(a, b) {
  const dirs = paths => (paths || []).map(p => p.split('/').slice(0, -1).join('/')).filter(Boolean);
  return dirs(a).some(d => dirs(b).includes(d));
}

function scoreSession(session, candidate) {
  if (hasDepLink(session, candidate))
    return { score: 100, reason: 'discovered-from ' + candidate.id, confidence: 95 };

  const kw = jaccard(session.keywords, candidate.keywords);
  const sameSkill = session.skillType && session.skillType === candidate.skillType;
  const sameProject = session.cwd && candidate.cwd && session.cwd === candidate.cwd;
  const hoursDiff = Math.abs(new Date(session.ts || 0) - new Date(candidate.ts || 0)) / 3600000;

  let score = 0, reason = '', confidence = 0;
  if (sameSkill && kw > 0.5) { score = 80; reason = 'same skill + topic'; confidence = 80; }
  else if (sameProject && kw > 0.3 && hoursDiff < 24) { score = 60 + Math.round(20 * (1 - hoursDiff / 24)); reason = 'same project + recent'; confidence = 60; }
  else if (sameProject && kw > 0.3) { score = 30; reason = 'same project'; confidence = 40; }
  else if (kw > 0.3) { score = 40; reason = 'topic overlap'; confidence = 35; }
  else if (sameSkill) { score = 20; reason = 'same skill type'; confidence = 25; }

  if (matchOutputDirs(session.outputPaths, candidate.outputPaths)) {
    score += 5; reason += ' + output dir'; confidence = Math.min(confidence + 5, 90);
  }
  return { score, reason, confidence };
}

export function findSimilarSessions(session, allSessions) {
  if (!session || !allSessions) return [];
  const scored = allSessions.filter(s => s.id !== session.id)
    .map(c => ({ ...c, ...scoreSession(session, c) }));
  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, MAX_BASELINES).filter(s => s.score > 0);
}

function fmtSkeleton(s, label) {
  const p = [`${label}: ${s.id || 'unknown'}`];
  if (s.description) p.push('Description: ' + s.description);
  if (s.skillType) p.push('Skill: ' + s.skillType);
  if (s.subAgentTypes) p.push('Sub-agents: ' + s.subAgentTypes.join(', '));
  if (s.toolCalls) p.push('Tool calls: ' + s.toolCalls.join(', '));
  if (s.outputPaths) p.push('Output files: ' + s.outputPaths.join(', '));
  if (s.summary) p.push('Summary: ' + s.summary);
  return p.join('\n');
}

function buildPrompt(current, baselines) {
  const bt = baselines.map((b, i) => fmtSkeleton(b, 'BASELINE ' + (i + 1))).join('\n\n');
  return `Compare CURRENT vs BASELINE sessions. List semantic differences in exactly four sections:

${fmtSkeleton(current, 'CURRENT')}

${bt}

NEW:
- <one-line>
REFINED:
- <one-line>
DROPPED:
- <one-line>
UNCHANGED:
- <one-line>

Max 3 items/section, under 80 chars each. Use "—" if empty.`;
}

function parseDiff(text) {
  const keys = ['new', 'refined', 'dropped', 'unchanged'];
  const s = { new: [], refined: [], dropped: [], unchanged: [] };
  for (const k of keys) {
    const re = new RegExp(k.toUpperCase() + ':\\s*([\\s\\S]*?)(?=\n(?:'
      + keys.filter(x => x !== k).map(x => x.toUpperCase()).join('|') + '):|$)', 'i');
    const m = text.match(re);
    if (m) s[k] = m[1].split('\n').map(l => l.replace(/^-\s*/, '').trim()).filter(l => l && l !== '—');
  }
  return s;
}

export async function generateDiffSummary(currentSession, baselineSessions, apiKey) {
  if (!baselineSessions || !baselineSessions.length)
    return { new: [], refined: [], dropped: [], unchanged: [], baselineInfo: null };

  const bids = baselineSessions.map(b => b.id);
  const cached = getCached(currentSession.id, bids);
  if (cached) return cached;

  let diff;
  try {
    const resp = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({ model: MODEL, max_tokens: MAX_TOKENS,
        messages: [{ role: 'user', content: buildPrompt(currentSession, baselineSessions) }] }),
    });
    if (!resp.ok) throw new Error('API error ' + resp.status);
    diff = parseDiff((await resp.json()).content?.[0]?.text || '');
  } catch (e) {
    console.warn('Diff generation failed:', e);
    diff = { new: [], refined: [], dropped: [], unchanged: [] };
  }

  const baselineInfo = baselineSessions.map(b => ({
    id: b.id, summary: b.description || b.id || '',
    confidence: b.confidence || 0, reason: b.reason || '',
  }));

  const result = { ...diff, baselineInfo };
  setCache(currentSession.id, bids, result);
  emit('diff:generated', { sessionId: currentSession.id, result });
  return result;
}

export function renderDiffSummary(diff, containerEl) {
  if (!containerEl) return;
  if (!diff || !diff.baselineInfo || !diff.baselineInfo.length) {
    containerEl.innerHTML = '<div class="diff-fallback">No prior similar sessions &mdash; full summary only</div>';
    return;
  }

  let html = '<div class="diff-summary"><div class="diff-baselines">Compared to: '
    + diff.baselineInfo.map(b =>
      '<span class="diff-baseline">' + h(b.summary) + ' <em>(confidence: ' + b.confidence + '%)</em></span>'
    ).join(', ')
    + '</div>';

  const sections = [
    ['new', 'New this session:', 'diff-new', '+ '],
    ['refined', 'Refined from baseline:', 'diff-refined', '~ '],
    ['dropped', 'Dropped:', 'diff-dropped', '− '],
  ];
  for (const [key, title, cls, prefix] of sections) {
    if (diff[key] && diff[key].length) {
      html += '<div class="diff-section ' + cls + '"><h4>' + title + '</h4><ul>'
        + diff[key].map(item => '<li>' + prefix + h(item) + '</li>').join('')
        + '</ul></div>';
    }
  }

  if (diff.unchanged && diff.unchanged.length) {
    html += '<details class="diff-section diff-unchanged"><summary>Unchanged ('
      + diff.unchanged.length + ')</summary><ul>'
      + diff.unchanged.map(item => '<li>' + h(item) + '</li>').join('')
      + '</ul></details>';
  }

  containerEl.innerHTML = html + '</div>';
}
