// App initialization
import { on } from './db.js';

const status = document.getElementById('status-bar');
on('store:ready', () => { status.textContent = 'Ready'; });

// Fallback: if store already ready before we registered, check directly
import('./session-store.js').then(m => {
  m.listSessions().then(() => {
    if (!status.textContent.includes('Ready')) status.textContent = 'Ready';
  }).catch(() => {});
});
