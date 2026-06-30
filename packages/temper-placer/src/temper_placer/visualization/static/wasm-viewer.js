import init, {
    load_board as wasmLoadBoard,
    on_wheel as wasmOnWheel,
    on_mouse_down as wasmOnMouseDown,
    on_mouse_move as wasmOnMouseMove,
    on_mouse_up as wasmOnMouseUp,
    on_click as wasmOnClick,
    search as wasmSearch,
    set_viewport as wasmSetViewport,
    get_board_summary as wasmGetBoardSummary,
} from './wasm/temper_viewer.js';

let wasm = null;
let ws = null;
let reconnectAttempt = 0;
const maxReconnectDelay = 30000;
let isPaused = false;
let currentState = null;

const STAGES = ['input', 'semantic', 'topological', 'preflight', 'geometric', 'routing', 'refinement', 'output'];

async function initViewer() {
    try {
        wasm = await init();
        console.log('WASM viewer initialized');
        if (window.location.search.includes('connect')) connectToServer();
    } catch (e) {
        console.error('Failed to initialize WASM module:', e);
        document.getElementById('landing-overlay').querySelector('.landing-content').innerHTML = `
            <h1>Temper Board Viewer</h1>
            <p class="error-msg">Failed to load WASM renderer. Check browser console for details.</p>
        `;
    }
}

window.connectToServer = function() {
    const host = window.location.hostname || 'localhost';
    const port = 8765;
    const url = `ws://${host}:${port}/ws`;

    ws = new WebSocket(url);

    ws.onopen = () => {
        console.log('WebSocket connected');
        document.getElementById('landing-overlay').classList.add('hidden');
        document.getElementById('connection-error').classList.add('hidden');
        document.getElementById('main-content').classList.remove('hidden');
        document.getElementById('toolbar').classList.remove('hidden');
        document.getElementById('animation-controls').classList.remove('hidden');
        reconnectAttempt = 0;
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        } catch (e) {
            console.error('Skipping malformed message:', e);
        }
    };

    ws.onclose = () => { console.log('WebSocket disconnected'); attemptReconnect(); };
    ws.onerror = (e) => { console.error('WebSocket error:', e); };

    setTimeout(() => {
        if (ws.readyState !== WebSocket.OPEN) {
            const err = document.getElementById('connection-error');
            err.classList.remove('hidden');
            err.textContent = `Cannot connect to server on port ${port}. Ensure temper-placer run --watch is active.`;
        }
    }, 3000);
};

function attemptReconnect() {
    if (reconnectAttempt > 10) return;
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), maxReconnectDelay);
    reconnectAttempt++;
    const banner = document.getElementById('reconnect-banner');
    banner.classList.remove('hidden');
    setTimeout(() => { banner.classList.add('hidden'); connectToServer(); }, delay);
}

function handleMessage(msg) {
    switch (msg.type) {
        case 'STATE_UPDATE':
            currentState = msg.data;
            if (wasm && msg.data.board) {
                try {
                    wasmLoadBoard(JSON.stringify(msg.data.board));
                } catch (e) { console.error('WASM render error:', e); }
            }
            updateSidebar(msg.data);
            break;
        case 'STAGE_CHANGE':
            updatePipelineProgress(msg.data);
            break;
    }
}

function updateSidebar(data) {
    const losses = data.loss_history?.total_loss;
    if (losses?.length) {
        const latest = losses[losses.length - 1];
        document.getElementById('loss-total').textContent = `Total Loss: ${latest.toFixed(4)}`;
        if (losses.length >= 2) {
            const prev = losses[losses.length - 2];
            const trend = latest < prev ? '↓' : latest > prev ? '↑' : '→';
            document.getElementById('loss-trend').textContent = `Trend: ${trend}`;
        }
    }

    const board = data.board;
    if (board) {
        const stats = [`Components: ${board.components?.length || 0}`];
        const traceCounts = {};
        (board.traces || []).forEach(t => {
            traceCounts[t.layer] = (traceCounts[t.layer] || 0) + 1;
        });
        Object.entries(traceCounts).forEach(([layer, count]) => stats.push(`Traces(${layer}): ${count}`));
        document.getElementById('board-stats').textContent = stats.join(', ');
    }
}

function updatePipelineProgress(stageData) {
    const container = document.getElementById('pipeline-stages');
    container.innerHTML = STAGES.map(s => {
        const cls = s === stageData.stage ? 'active' :
                    STAGES.indexOf(s) < STAGES.indexOf(stageData.stage) ? 'completed' : 'pending';
        return `<span class="stage ${cls}">${s}</span>`;
    }).join(' → ');
}

window.toggleSection = function(name) {
    document.getElementById(`section-${name}`).classList.toggle('collapsed');
};

window.togglePause = function() {
    isPaused = !isPaused;
    document.getElementById('btn-pause').textContent = isPaused ? 'Resume' : 'Pause';
};

window.updateAnimationMode = function() {
    const mode = document.getElementById('animation-mode').value;
    console.log('Animation mode:', mode);
};

// Canvas mouse events → WASM
let dragging = false;
let lastMouseX = 0, lastMouseY = 0;
const canvas = document.getElementById('board-canvas');
canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    if (wasm) wasmOnWheel(e.deltaY, e.offsetX, e.offsetY);
}, { passive: false });
canvas.addEventListener('mousedown', (e) => {
    dragging = true;
    lastMouseX = e.offsetX; lastMouseY = e.offsetY;
    if (wasm) wasmOnMouseDown(e.offsetX, e.offsetY);
});
canvas.addEventListener('mousemove', (e) => {
    if (dragging && wasm) {
        const dx = e.offsetX - lastMouseX;
        const dy = e.offsetY - lastMouseY;
        lastMouseX = e.offsetX; lastMouseY = e.offsetY;
        wasmOnMouseMove(dx, dy, true);
    } else if (wasm) {
        wasmOnMouseMove(e.offsetX, e.offsetY, false).then(result => {
            const tooltip = document.getElementById('tooltip');
            if (!result || result === 'clear') {
                tooltip.classList.add('hidden');
            } else if (result.startsWith('component:')) {
                const parts = result.split(':');
                tooltip.textContent = `${parts[1]} — ${parts[2]}`;
                tooltip.style.left = (e.clientX + 12) + 'px';
                tooltip.style.top = (e.clientY - 28) + 'px';
                tooltip.classList.remove('hidden');
            } else if (result.startsWith('trace:')) {
                const parts = result.split(':');
                tooltip.textContent = `${parts[1]} — ${parts[2]}`;
                tooltip.style.left = (e.clientX + 12) + 'px';
                tooltip.style.top = (e.clientY - 28) + 'px';
                tooltip.classList.remove('hidden');
            }
        });
    }
});
canvas.addEventListener('mouseup', () => { dragging = false; if (wasm) wasmOnMouseUp(); });
canvas.addEventListener('mouseleave', () => { dragging = false; if (wasm) wasmOnMouseUp(); });
canvas.addEventListener('click', (e) => {
    if (!wasm) return;
    wasmOnClick(e.offsetX, e.offsetY).then(result => {
        const inspector = document.getElementById('inspector-content');
        if (result === 'none' || result === 'deselected') {
            inspector.textContent = 'Select a component to inspect.';
        } else {
            try {
                const data = JSON.parse(result);
                inspector.innerHTML = `
                    <div><strong>${data.ref}</strong> (${data.footprint || '?'})</div>
                    <div>Value: ${data.value || 'N/A'}</div>
                    <div>Position: (${data.position.x.toFixed(2)}, ${data.position.y.toFixed(2)}) mm</div>
                    <div>Rotation: ${data.rotation}°</div>
                    <div>Zone: ${data.zone || 'none'}</div>
                    <div>Loss: ${data.loss_contribution?.toFixed(4) || 'N/A'}</div>
                    ${data.last_movement_reason ? `<div>Reason: ${data.last_movement_reason}</div>` : ''}
                    <div>Neighbors: ${data.neighbors.join(', ') || 'none'}</div>
                `;
            } catch { inspector.textContent = 'Error displaying component data.'; }
        }
    });
});

// Search bar
document.getElementById('search-input').addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || !wasm) return;
    const query = e.target.value.trim();
    if (!query) return;
    wasmSearch(query).then(result => {
        if (!result || result === 'not_found') {
            const searchInput = document.getElementById('search-input');
            searchInput.style.borderColor = '#f66';
            setTimeout(() => searchInput.style.borderColor = '', 2000);
            // Show inline "no results" indicator
            const msg = document.getElementById('search-no-results') || createNoResultsEl();
            msg.textContent = `No component found matching "${query}"`;
            msg.classList.remove('hidden');
            setTimeout(() => msg.classList.add('hidden'), 3000);
        }
    });
});

function createNoResultsEl() {
    const el = document.createElement('span');
    el.id = 'search-no-results';
    el.className = 'hidden';
    el.style.cssText = 'color:#c00;font-size:0.85em;margin-left:8px;';
    document.getElementById('toolbar').appendChild(el);
    return el;
}

// File drop handler
const dropZone = document.getElementById('drop-zone');
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', async (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (!file) return;
    try {
        const text = await file.text();
        const data = JSON.parse(text);
        currentState = data;
        if (wasm && data.board) wasmLoadBoard(JSON.stringify(data.board));
        updateSidebar(data);
        document.getElementById('landing-overlay').classList.add('hidden');
        document.getElementById('main-content').classList.remove('hidden');
        document.getElementById('toolbar').classList.remove('hidden');
    } catch (e) {
        const err = document.getElementById('connection-error');
        err.classList.remove('hidden');
        err.textContent = `Failed to parse file: ${e.message}`;
    }
});

// Keyboard: Escape = deselect
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.getElementById('inspector-content').textContent = 'Select a component to inspect.';
        if (wasm) wasmOnClick(-1, -1);
    }
});

// Resize handler
window.addEventListener('resize', () => {
    const canvasEl = document.getElementById('board-canvas');
    if (wasm && canvasEl) {
        wasmSetViewport(canvasEl.clientWidth, canvasEl.clientHeight);
    }
});

// Resizable sidebar
let sidebarResizing = false;
document.getElementById('sidebar-resize-handle').addEventListener('mousedown', (e) => {
    sidebarResizing = true;
    e.preventDefault();
});
document.addEventListener('mousemove', (e) => {
    if (!sidebarResizing) return;
    const sidebar = document.getElementById('sidebar');
    sidebar.style.width = Math.max(200, Math.min(500, window.innerWidth - e.clientX)) + 'px';
});
document.addEventListener('mouseup', () => { sidebarResizing = false; });

// Expose connect globally for the button onclick
window.connectToServer = window.connectToServer || connectToServer;

initViewer();
