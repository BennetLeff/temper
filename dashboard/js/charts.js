// Chart.js configuration per metric type
// Exposes createChart(canvasId, chartType, labels, datasets, options)

function createChart(canvasId, chartType, labels, datasets, options) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;

  const defaultOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#8b949e',
          boxWidth: 12,
          padding: 12,
          font: { size: 11 },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: '#8b949e', maxTicksLimit: 12, font: { size: 10 } },
        grid: { color: '#21262d' },
      },
      y: {
        ticks: { color: '#8b949e', font: { size: 10 } },
        grid: { color: '#21262d' },
        beginAtZero: false,
      },
    },
    ...options,
  };

  return new Chart(ctx, {
    type: chartType,
    data: { labels, datasets },
    options: defaultOptions,
  });
}
