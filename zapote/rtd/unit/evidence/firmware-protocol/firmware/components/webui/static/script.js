document.addEventListener('DOMContentLoaded', () => {
    const currTempEl = document.getElementById('curr-temp');
    const targetTempEl = document.getElementById('target-temp');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const intensitySlider = document.getElementById('intensity');
    const intensityVal = document.getElementById('intensity-val');

    function updateStatus() {
        fetch('/api/status')
            .then(res => res.json())
            .then(data => {
                currTempEl.textContent = data.temp.toFixed(1);
                targetTempEl.textContent = data.target.toFixed(1);
                statusDot.classList.add('connected');
                statusText.textContent = 'CONNECTED';
            })
            .catch(err => {
                console.error('Fetch error:', err);
                statusDot.classList.remove('connected');
                statusText.textContent = 'DISCONNECTED';
            });
    }

    intensitySlider.addEventListener('input', (e) => {
        intensityVal.textContent = e.target.value;
    });

    document.getElementById('btn-start').addEventListener('click', () => {
        fetch('/api/start', { method: 'POST' });
    });

    document.getElementById('btn-stop').addEventListener('click', () => {
        fetch('/api/stop', { method: 'POST' });
    });

    // Poll for status every 2 seconds
    setInterval(updateStatus, 2000);
    updateStatus();
});
