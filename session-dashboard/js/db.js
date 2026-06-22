// Shared database layer — DuckDB initialization and query utilities
// Each feature module imports from this single source of truth.

let _db = null;
let _ready = false;
const _listeners = [];

export function onReady(fn) {
  if (_ready) { fn(_db); return; }
  _listeners.push(fn);
}

export function getDB() { return _db; }
export function isReady() { return _ready; }

export async function initDB() {
  return _ready ? _db : null;
}

export function setDBReady(db) {
  _db = db;
  _ready = true;
  _listeners.forEach(fn => fn(_db));
  _listeners.length = 0;
}

// Event bus for cross-module communication
const _events = {};

export function emit(event, data) {
  (_events[event] || []).forEach(fn => fn(data));
}

export function on(event, fn) {
  (_events[event] = _events[event] || []).push(fn);
  return () => { _events[event] = _events[event].filter(f => f !== fn); };
}

// Shared utility: format duration from ms
export function fmtDuration(ms) {
  if (ms == null || ms < 0) return '—';
  if (ms < 60000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3600000) return `${Math.round(ms / 60000)}m`;
  return `${(ms / 3600000).toFixed(1)}h`;
}

// Shared utility: format timestamp
export function fmtTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  const now = new Date();
  const diff = now - d;
  if (diff < 86400000) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (diff < 604800000) return d.toLocaleDateString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}
