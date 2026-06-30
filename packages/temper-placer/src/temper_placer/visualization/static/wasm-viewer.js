import init, { load_board as wasmLoadBoard } from './wasm/temper_viewer.js';

let wasm = null;
let ws = null;
let reconnectAttempt = 0;
let maxReconnectDelay = 30000;
let isPaused = false;
let currentState = null;
let animationMode = 'smooth';

const STAGES = ['input', 'semantic', 'topological', 'preflight', 'geometric', 'routing', 'refinement', 'output'];

async function initViewer() {
    try {
        wasm = await init();
        console.log('WASM viewer initialized');

        // Auto-connect if ?connect query param is present
        if (window.location.search.includes('connect')) {
            connectToServer();
        }
    } catch (e) {
        console.error('Failed to initialize WASM module:', e);
        const overlay = document.getElementById('landing-overlay');
        overlay.querySelector('.landing-content').innerHTML = `
            <h1>Temper Board Viewer</h1>
            <p class="error-msg">Failed to load WASM renderer. Check browser console for details.</p>
            <p>Try Chrome 113+, Firefox 116+, or Safari 17+.</p>
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

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        attemptReconnect();
    };

    ws.onerror = (e) => {
        console.error('WebSocket error:', e);
    };

    // Initial connection failure
    setTimeout(() => {
        if (ws.readyState !== WebSocket.OPEN) {
            document.getElementById('connection-error').classList.remove('hidden');
            document.getElementById('connection-error').textContent =
                `Cannot connect to server on port ${port}. Ensure temper-placer run --watch is active.`;
        }
    }, 3000);
};

function attemptReconnect() {
    if (reconnectAttempt > 10) return;
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), maxReconnectDelay);
    reconnectAttempt++;
    document.getElementById('reconnect-banner').classList.remove('hidden');

    setTimeout(() => {
        document.getElementById('reconnect-banner').classList.add('hidden');
        connectToServer();
    }, delay);
}

function handleMessage(msg) {
    switch (msg.type) {
        case 'STATE_UPDATE':
            currentState = msg.data;
            if (wasm && msg.data.board) {
                try {
                    wasmLoadBoard(JSON.stringify(msg.data.board));
                } catch (e) {
                    console.error('WASM render error:', e);
                }
            }
            updateSidebar(msg.data);
            break;
        case 'STAGE_CHANGE':
            updatePipelineProgress(msg.data);
            break;
        default:
            break;
    }
}

function updateSidebar(data) {
    if (data.loss_history && data.loss_history.total_loss) {
        const losses = data.loss_history.total_loss;
        const latest = losses[losses.length - 1];
        document.getElementById('loss-total').textContent = `Total Loss: ${latest.toFixed(4)}`;
    }

    if (data.board) {
        const stats = [];
        stats.push(`Components: ${data.board.components?.length || 0}`);
        const traceCounts = {};
        (data.board.traces || []).forEach(t => {
            traceCounts[t.layer] = (traceCounts[t.layer] || 0) + 1;
        });
        Object.entries(traceCounts).forEach(([layer, count]) => {
            stats.push(`Traces (${layer}): ${count}`);
        });
        document.getElementById('board-stats').textContent = stats.join(', ');
    }
}

function updatePipelineProgress(stageData) {
    const container = document.getElementById('pipeline-stages');
    container.innerHTML = STAGES.map(s => {
        const cls = s === stageData.stage ? 'active' : 'pending';
        return `<span class="stage ${cls}">${s}</span>`;
    }).join(' → ');
}

window.toggleSection = function(name) {
    const section = document.getElementById(`section-${name}`);
    section.classList.toggle('collapsed');
};

window.updateVisibility = function() {
    // Will call WASM visibility functions when render pipeline is built
    console.log('Visibility toggles updated');
};

window.togglePause = function() {
    isPaused = !isPaused;
    document.getElementById('btn-pause').textContent = isPaused ? 'Resume' : 'Pause';
};

window.updateAnimationMode = function() {
    animationMode = document.getElementById('animation-mode').value;
};

// File drop handler
const dropZone = document.getElementById('drop-zone');
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
});
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
        if (wasm && data.board) {
            wasmLoadBoard(JSON.stringify(data.board));
        }
        updateSidebar(data);
        document.getElementById('landing-overlay').classList.add('hidden');
        document.getElementById('main-content').classList.remove('hidden');
        document.getElementById('toolbar').classList.remove('hidden');
    } catch (e) {
        document.getElementById('connection-error').classList.remove('hidden');
        document.getElementById('connection-error').textContent = `Failed to parse file: ${e.message}`;
    }
});

initViewer();
