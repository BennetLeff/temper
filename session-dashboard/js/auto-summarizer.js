// auto-summarizer.js — Auto-generates LLM summaries when sessions complete.
import { emit } from './db.js';

const API = 'https://api.anthropic.com/v1/messages';
const MODEL = 'claude-3-5-haiku-20241022';
const MAX_TOKENS = 300;
const CONCURRENCY = 3;
const LS_COST = 'summarizer:cost';
const LS_PREFIX = 'summarizer:summary:';

const SYSTEM = `You summarize AI coding agent sessions. Output valid JSON only.

Write an 80-120 word summary paragraph that:
- Opens with a past-tense action verb describing what was accomplished
- Names key decisions made (max 3) and the outcome
- Explains why this work mattered (deeper project context)
- Never mentions agent IDs, describes tool calls, or starts with "This session..."

Respond with exactly:
{"summary":"<paragraph>","keywords":["kw1","kw2","kw3","kw4","kw5"]}`;

function skeleton(session) {
  const msgs = session.messages || [];
  const subs = session.subAgents || [];
  return {
    msgs: msgs.map(e => ({ role: e.role, content: (e.content || '').slice(0, 400) })),
    subs: subs.map(e => ({ desc: e.type || '', type: e.source || '', ts: '' })),
    tools: []
  };
}

function buildPrompt(session) {
  const sk = skeleton(session);
  const out = [`Project: ${session.project || 'unknown'}`];
  if (sk.msgs.length) {
    out.push(`\nMessages (${sk.msgs.length}):`);
    sk.msgs.slice(-15).forEach(m => out.push(`[${m.role}] ${m.content}`));
  }
  if (sk.subs.length) {
    out.push(`\nSub-agents (${sk.subs.length}):`);
    sk.subs.forEach(s => out.push(`- ${s.desc} (${s.type})`));
  }
  if (sk.tools.length) {
    out.push(`\nTool calls (${sk.tools.length}):`);
    sk.tools.slice(-25).forEach(t => out.push(`- ${t.tool}: ${t.text}`));
  }
  return out.join('\n');
}

function loadCost() {
  try { return JSON.parse(localStorage.getItem(LS_COST) || '{"tokens":0,"cost":0,"count":0}'); }
  catch { return { tokens: 0, cost: 0, count: 0 }; }
}
function saveCost(t) { localStorage.setItem(LS_COST, JSON.stringify(t)); }

function trackCost(inTok, outTok) {
  const inRate = 0.25 / 1_000_000;
  const outRate = 1.25 / 1_000_000;
  const cost = inTok * inRate + outTok * outRate;
  const t = loadCost();
  t.tokens += inTok + outTok;
  t.cost += cost;
  t.count += 1;
  saveCost(t);
  return { cost, inputTokens: inTok, outputTokens: outTok, lifetime: t };
}

function cacheSave(id, s) { localStorage.setItem(LS_PREFIX + id, JSON.stringify(s)); }
function cacheLoad(id) { try { return JSON.parse(localStorage.getItem(LS_PREFIX + id)); } catch { return null; } }

export function detectCompletion(session) {
  const now = Date.now();
  const last = session.updatedAt ? new Date(session.updatedAt).getTime()
    : session.startedAt ? new Date(session.startedAt).getTime() : 0;
  const idle = now - last;
  const subs = session.subAgents || [];
  const lastSub = subs.length ? Math.max(...subs.map(s => new Date(s.timestamp || 0).getTime())) : 0;

  if (session.processExited) return { isComplete: true, confidence: 'high', reason: 'Process exited' };
  if (idle > 30 * 60 * 1000) return { isComplete: true, confidence: 'medium', reason: 'Idle >30 minutes' };
  if (idle > 5 * 60 * 1000) {
    if (subs.length && (now - lastSub) > 2 * 60 * 1000)
      return { isComplete: true, confidence: 'medium', reason: 'Idle >5 min, sub-agents stable >2 min' };
    if (session.status === 'idle')
      return { isComplete: true, confidence: 'low', reason: 'Idle >5 min' };
  }
  return { isComplete: false, confidence: 'high', reason: 'Active or recently updated' };
}

export function activeSessionStatus(session) {
  const subs = session.subAgents || [];
  const done = subs.filter(s => s.status === 'complete').length;
  return { done, total: subs.length, text: subs.length ? `In Progress — ${done}/${subs.length} sub-agents` : 'No sub-agents' };
}

export async function autoSummarize(session, apiKey) {
  const cached = cacheLoad(session.id);
  if (cached) return cached;

  const resp = await fetch(API, {
    method: 'POST',
    headers: { 'x-api-key': apiKey, 'anthropic-version': '2023-06-01', 'content-type': 'application/json' },
    body: JSON.stringify({
      model: MODEL, max_tokens: MAX_TOKENS, system: SYSTEM,
      messages: [{ role: 'user', content: buildPrompt(session) }]
    })
  });
  if (!resp.ok) throw new Error(`API ${resp.status}: ${await resp.text().catch(() => '')}`);

  const data = await resp.json();
  const raw = data.content?.[0]?.text || '';
  const inTok = data.usage?.input_tokens || 0;
  const outTok = data.usage?.output_tokens || 0;
  const costInfo = trackCost(inTok, outTok);

  let parsed;
  try {
    const m = raw.match(/\{[\s\S]*\}/);
    parsed = m ? JSON.parse(m[0]) : {};
  } catch { parsed = {}; }

  const summary = {
    text: parsed.summary || raw,
    keywords: parsed.keywords || [],
    model: MODEL,
    cost: Math.round(costInfo.cost * 10000) / 10000,
    inputTokens: inTok,
    outputTokens: outTok,
    generatedAt: new Date().toISOString(),
    id: session.id
  };

  cacheSave(session.id, summary);
  session.summary = summary.text;
  session.summaryObj = summary;
  emit('summarizer:complete', summary);
  return summary;
}

export async function summarizeSessions(sessions, apiKey) {
  const pending = sessions.filter(s => !cacheLoad(s.id)).filter(s => detectCompletion(s).isComplete);
  if (!pending.length) return { done: 0, total: 0 };

  let done = 0;
  const total = pending.length;
  const queue = [...pending];

  const worker = async () => {
    while (queue.length) {
      const s = queue.shift();
      if (!s) break;
      try { await autoSummarize(s, apiKey); } catch (e) { console.error(`Summarize ${s.id}:`, e); }
      done++;
      emit('summarizer:progress', { done, total });
    }
  };

  await Promise.all(Array(Math.min(CONCURRENCY, total)).fill(null).map(worker));
  return { done, total };
}
