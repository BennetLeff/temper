/**
 * Temper Placer Live Visualization Viewer
 * 
 * Connects to the WebSocket server and displays real-time placement updates.
 */

// ============================================================================
// Configuration
// ============================================================================

const CONFIG = {
    // WebSocket
    wsPort: 8765,
    reconnectDelay: 2000,  // ms
    maxReconnectAttempts: 10,

    // UI
    updateThrottle: 50,  // ms between UI updates

    // Chart colors
    colors: {
        primary: '#3b82f6',
        secondary: '#8b5cf6',
        success: '#4ade80',
        warning: '#fbbf24',
        danger: '#f87171',
        background: '#0f0f1a',
        grid: '#333',
        text: '#888',
    },

    // Component colors by type
    componentColors: {
        ic: '#3b82f6',
        connector: '#8b5cf6',
        resistor: '#4ade80',
        capacitor: '#fbbf24',
        inductor: '#f97316',
        diode: '#ec4899',
        transistor: '#14b8a6',
        default: '#6b7280',
    },

    // Zone colors
    zoneColors: {
        keepout: 'rgba(248, 113, 113, 0.3)',
        high_voltage: 'rgba(251, 191, 36, 0.3)',
        low_voltage: 'rgba(74, 222, 128, 0.3)',
        thermal: 'rgba(239, 68, 68, 0.3)',
        default: 'rgba(107, 114, 128, 0.2)',
    }
};

// ============================================================================
// State
// ============================================================================

let state = {
    ws: null,
    connected: false,
    training: false,
    paused: false,
    reconnectAttempts: 0,
    lastUpdate: 0,
    currentState: null,
};

// ============================================================================
// WebSocket Connection
// ============================================================================

function getWebSocketUrl() {
    // Get the WebSocket URL from the current page location
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname || 'localhost';
    const port = CONFIG.wsPort;
    return `${protocol}//${host}:${port}`;
}

function connect() {
    if (state.ws && state.ws.readyState === WebSocket.CONNECTING) {
        return;
    }

    const url = getWebSocketUrl();
    console.log(`Connecting to ${url}...`);

    try {
        state.ws = new WebSocket(url);
        
        state.ws.onopen = handleOpen;
        state.ws.onclose = handleClose;
        state.ws.onerror = handleError;
        state.ws.onmessage = handleMessage;
    } catch (e) {
        console.error('Failed to create WebSocket:', e);
        scheduleReconnect();
    }
}

function handleOpen() {
    console.log('WebSocket connected');
    state.connected = true;
    state.reconnectAttempts = 0;
    
    updateConnectionStatus('connected');
    hideOverlay();

    // Request current state
    send({ type: 'get_state' });
}

function handleClose(event) {
    console.log('WebSocket closed:', event.code, event.reason);
    state.connected = false;
    state.ws = null;
    
    updateConnectionStatus('disconnected');
    scheduleReconnect();
}

function handleError(error) {
    console.error('WebSocket error:', error);
}

function handleMessage(event) {
    try {
        const message = JSON.parse(event.data);
        processMessage(message);
    } catch (e) {
        console.error('Failed to parse message:', e);
    }
}

function send(message) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(message));
    }
}

function scheduleReconnect() {
    if (state.reconnectAttempts >= CONFIG.maxReconnectAttempts) {
        console.log('Max reconnection attempts reached');
        showOverlay('Connection Failed', 'Unable to connect to server after multiple attempts.');
        return;
    }

    state.reconnectAttempts++;
    console.log(`Reconnecting in ${CONFIG.reconnectDelay}ms (attempt ${state.reconnectAttempts}/${CONFIG.maxReconnectAttempts})`);
    
    setTimeout(connect, CONFIG.reconnectDelay);
}

function reconnect() {
    state.reconnectAttempts = 0;
    connect();
}

// ============================================================================
// Message Processing
// ============================================================================

function processMessage(message) {
    const { type, data } = message;

    switch (type) {
        case 'state_update':
            handleStateUpdate(data);
            break;
        case 'training_started':
            handleTrainingStarted();
            break;
        case 'training_stopped':
            handleTrainingStopped();
            break;
        case 'training_complete':
            handleTrainingComplete(data);
            break;
        case 'error':
            handleServerError(data);
            break;
        default:
            console.warn('Unknown message type:', type);
    }
}

function handleStateUpdate(data) {
    // Throttle updates
    const now = Date.now();
    if (now - state.lastUpdate < CONFIG.updateThrottle) {
        return;
    }
    state.lastUpdate = now;

    state.currentState = data;
    updateUI(data);
}

function handleTrainingStarted() {
    state.training = true;
    state.paused = false;
    updateConnectionStatus('training');
    updatePauseButton();
}

function handleTrainingStopped() {
    state.paused = true;
    updateConnectionStatus('paused');
    updatePauseButton();
}

function handleTrainingComplete(data) {
    state.training = false;
    state.paused = false;
    updateConnectionStatus('complete');
    updatePauseButton();

    if (data) {
        state.currentState = data;
        updateUI(data);
    }
}

function handleServerError(data) {
    console.error('Server error:', data);
}

// ============================================================================
// UI Updates
// ============================================================================

function updateUI(data) {
    updateMetrics(data);
    updateBoardView(data.board);
    updateLossCurves(data.loss_history);
    updateLossBreakdown(data.loss_history);
    updateConstraintIndicators(data.constraints);
}

function updateMetrics(data) {
    document.getElementById('epoch-value').textContent = data.epoch || 0;
    
    const lossValue = document.getElementById('loss-value');
    if (data.loss_history && data.loss_history.total_losses && data.loss_history.total_losses.length > 0) {
        const loss = data.loss_history.total_losses[data.loss_history.total_losses.length - 1];
        lossValue.textContent = loss.toFixed(4);
        lossValue.className = 'metric-value ' + getLossClass(loss);
    } else {
        lossValue.textContent = '-';
        lossValue.className = 'metric-value';
    }

    const elapsed = data.elapsed_seconds || 0;
    const minutes = Math.floor(elapsed / 60);
    const seconds = Math.floor(elapsed % 60);
    document.getElementById('elapsed-value').textContent = 
        `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function getLossClass(loss) {
    if (loss < 0.1) return 'good';
    if (loss < 1.0) return 'warning';
    return 'bad';
}

function updateConnectionStatus(status) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');

    dot.className = 'status-dot';
    
    switch (status) {
        case 'connected':
            dot.classList.add('connected');
            text.textContent = 'Connected';
            break;
        case 'training':
            dot.classList.add('training');
            text.textContent = 'Training...';
            break;
        case 'paused':
            dot.classList.add('paused');
            text.textContent = 'Paused';
            break;
        case 'complete':
            dot.classList.add('complete');
            text.textContent = 'Complete';
            break;
        default:
            text.textContent = 'Disconnected';
    }
}

function updatePauseButton() {
    const btn = document.getElementById('btn-pause');
    if (state.paused) {
        btn.textContent = 'Resume';
        btn.className = 'btn-success';
    } else {
        btn.textContent = 'Pause';
        btn.className = 'btn-warning';
    }
}

// ============================================================================
// Board Visualization
// ============================================================================

function updateBoardView(board) {
    if (!board) return;

    const traces = [];

    // Draw zones first (background)
    if (board.zones) {
        for (const zone of board.zones) {
            traces.push(createZoneTrace(zone));
        }
    }

    // Draw components
    if (board.components) {
        for (const comp of board.components) {
            traces.push(createComponentTrace(comp));
        }
    }

    // Board outline
    traces.push({
        type: 'scatter',
        x: [0, board.width, board.width, 0, 0],
        y: [0, 0, board.height, board.height, 0],
        mode: 'lines',
        line: { color: CONFIG.colors.grid, width: 2 },
        name: 'Board',
        hoverinfo: 'none',
    });

    const layout = {
        xaxis: {
            range: [-5, board.width + 5],
            scaleanchor: 'y',
            scaleratio: 1,
            showgrid: true,
            gridcolor: CONFIG.colors.grid,
            zeroline: false,
            title: 'X (mm)',
            titlefont: { color: CONFIG.colors.text },
            tickfont: { color: CONFIG.colors.text },
        },
        yaxis: {
            range: [-5, board.height + 5],
            showgrid: true,
            gridcolor: CONFIG.colors.grid,
            zeroline: false,
            title: 'Y (mm)',
            titlefont: { color: CONFIG.colors.text },
            tickfont: { color: CONFIG.colors.text },
        },
        paper_bgcolor: CONFIG.colors.background,
        plot_bgcolor: CONFIG.colors.background,
        margin: { l: 50, r: 20, t: 20, b: 50 },
        showlegend: false,
        hovermode: 'closest',
    };

    Plotly.react('board-view', traces, layout, { responsive: true });
}

function createComponentTrace(comp) {
    const { ref, position, rotation, width, height } = comp;
    const color = getComponentColor(comp.component_type || 'default');
    
    // Calculate rotated rectangle corners
    const corners = getRotatedRectCorners(
        position.x, position.y, width, height, rotation || 0
    );

    return {
        type: 'scatter',
        x: [...corners.map(c => c.x), corners[0].x],
        y: [...corners.map(c => c.y), corners[0].y],
        fill: 'toself',
        fillcolor: color + '80',  // Add transparency
        line: { color: color, width: 1 },
        name: ref,
        text: ref,
        hovertemplate: `<b>${ref}</b><br>Position: (${position.x.toFixed(1)}, ${position.y.toFixed(1)})<br>Size: ${width}×${height}mm<extra></extra>`,
    };
}

function createZoneTrace(zone) {
    const { zone_type, bounds } = zone;
    const color = CONFIG.zoneColors[zone_type] || CONFIG.zoneColors.default;

    return {
        type: 'scatter',
        x: [bounds.x, bounds.x + bounds.width, bounds.x + bounds.width, bounds.x, bounds.x],
        y: [bounds.y, bounds.y, bounds.y + bounds.height, bounds.y + bounds.height, bounds.y],
        fill: 'toself',
        fillcolor: color,
        line: { color: color, width: 1, dash: 'dot' },
        name: zone.name || zone_type,
        hovertemplate: `<b>${zone.name || zone_type}</b><extra></extra>`,
    };
}

function getRotatedRectCorners(cx, cy, w, h, angleDeg) {
    const angle = angleDeg * Math.PI / 180;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const hw = w / 2;
    const hh = h / 2;

    const corners = [
        { x: -hw, y: -hh },
        { x: hw, y: -hh },
        { x: hw, y: hh },
        { x: -hw, y: hh },
    ];

    return corners.map(c => ({
        x: cx + c.x * cos - c.y * sin,
        y: cy + c.x * sin + c.y * cos,
    }));
}

function getComponentColor(type) {
    return CONFIG.componentColors[type] || CONFIG.componentColors.default;
}

// ============================================================================
// Loss Curves
// ============================================================================

function updateLossCurves(lossHistory) {
    if (!lossHistory || !lossHistory.epochs || lossHistory.epochs.length === 0) {
        return;
    }

    const traces = [{
        type: 'scatter',
        x: lossHistory.epochs,
        y: lossHistory.total_losses,
        mode: 'lines',
        name: 'Total Loss',
        line: { color: CONFIG.colors.primary, width: 2 },
    }];

    const layout = {
        xaxis: {
            title: 'Epoch',
            titlefont: { color: CONFIG.colors.text },
            tickfont: { color: CONFIG.colors.text },
            gridcolor: CONFIG.colors.grid,
            zeroline: false,
        },
        yaxis: {
            title: 'Loss',
            type: 'log',
            titlefont: { color: CONFIG.colors.text },
            tickfont: { color: CONFIG.colors.text },
            gridcolor: CONFIG.colors.grid,
            zeroline: false,
        },
        paper_bgcolor: CONFIG.colors.background,
        plot_bgcolor: CONFIG.colors.background,
        margin: { l: 50, r: 20, t: 10, b: 40 },
        showlegend: false,
    };

    Plotly.react('loss-curves', traces, layout, { responsive: true });
}

function updateLossBreakdown(lossHistory) {
    if (!lossHistory || !lossHistory.breakdown_names || lossHistory.breakdown_names.length === 0) {
        return;
    }

    // Get the latest breakdown
    const latestBreakdown = lossHistory.latest_breakdown || {};
    const names = lossHistory.breakdown_names || Object.keys(latestBreakdown);
    const values = names.map(name => latestBreakdown[name] || 0);

    // Sort by value descending
    const sorted = names.map((name, i) => ({ name, value: values[i] }))
        .sort((a, b) => b.value - a.value);

    const traces = [{
        type: 'bar',
        x: sorted.map(s => s.value),
        y: sorted.map(s => s.name),
        orientation: 'h',
        marker: {
            color: sorted.map((_, i) => 
                `hsl(${210 + i * 30}, 70%, 50%)`
            ),
        },
        hovertemplate: '%{y}: %{x:.4f}<extra></extra>',
    }];

    const layout = {
        xaxis: {
            title: 'Loss Value',
            titlefont: { color: CONFIG.colors.text },
            tickfont: { color: CONFIG.colors.text },
            gridcolor: CONFIG.colors.grid,
            zeroline: false,
        },
        yaxis: {
            tickfont: { color: CONFIG.colors.text },
            automargin: true,
        },
        paper_bgcolor: CONFIG.colors.background,
        plot_bgcolor: CONFIG.colors.background,
        margin: { l: 100, r: 20, t: 10, b: 40 },
        showlegend: false,
    };

    Plotly.react('loss-breakdown', traces, layout, { responsive: true });
}

// ============================================================================
// Constraint Indicators
// ============================================================================

function updateConstraintIndicators(constraints) {
    if (!constraints) return;

    const container = document.getElementById('constraint-indicators');
    container.innerHTML = '';

    const indicators = [
        { name: 'Overlaps', count: constraints.overlap_count || 0 },
        { name: 'Boundary', count: constraints.boundary_count || 0 },
        { name: 'Clearance', count: constraints.clearance_count || 0 },
        { name: 'Zone', count: constraints.zone_count || 0 },
    ];

    for (const ind of indicators) {
        const badge = document.createElement('span');
        badge.className = 'constraint-badge ' + (ind.count === 0 ? 'ok' : 'violation');
        badge.textContent = `${ind.name}: ${ind.count}`;
        container.appendChild(badge);
    }
}

// ============================================================================
// Controls
// ============================================================================

function togglePause() {
    if (state.paused) {
        send({ type: 'resume' });
    } else {
        send({ type: 'pause' });
    }
}

function stepIterations() {
    const count = parseInt(document.getElementById('step-count').value) || 10;
    send({ type: 'step', steps: count });
}

function exportState() {
    send({ type: 'export' });
    
    // Also download current state as JSON
    if (state.currentState) {
        const blob = new Blob([JSON.stringify(state.currentState, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `placement_state_epoch_${state.currentState.epoch || 0}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }
}

// ============================================================================
// Overlay
// ============================================================================

function showOverlay(title, message) {
    const overlay = document.getElementById('connection-overlay');
    overlay.classList.remove('hidden');
    overlay.querySelector('h2').textContent = title || 'Connecting...';
    overlay.querySelector('p').textContent = message || 'Waiting for WebSocket connection to server';
}

function hideOverlay() {
    document.getElementById('connection-overlay').classList.add('hidden');
}

// ============================================================================
// Initialize
// ============================================================================

function init() {
    console.log('Initializing Temper Placer Viewer...');
    
    // Initialize empty charts
    initEmptyCharts();
    
    // Connect to WebSocket
    connect();
    
    // Handle window resize
    window.addEventListener('resize', () => {
        Plotly.Plots.resize('board-view');
        Plotly.Plots.resize('loss-curves');
        Plotly.Plots.resize('loss-breakdown');
    });
}

function initEmptyCharts() {
    const emptyLayout = {
        paper_bgcolor: CONFIG.colors.background,
        plot_bgcolor: CONFIG.colors.background,
        xaxis: { 
            showgrid: true, 
            gridcolor: CONFIG.colors.grid,
            zeroline: false,
            tickfont: { color: CONFIG.colors.text },
        },
        yaxis: { 
            showgrid: true, 
            gridcolor: CONFIG.colors.grid,
            zeroline: false,
            tickfont: { color: CONFIG.colors.text },
        },
        margin: { l: 50, r: 20, t: 20, b: 40 },
    };

    Plotly.newPlot('board-view', [], emptyLayout, { responsive: true });
    Plotly.newPlot('loss-curves', [], emptyLayout, { responsive: true });
    Plotly.newPlot('loss-breakdown', [], emptyLayout, { responsive: true });
}

// Start on page load
document.addEventListener('DOMContentLoaded', init);
