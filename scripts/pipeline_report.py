#!/usr/bin/env python3
"""Generate a self-contained static HTML pipeline report (R7, R8)."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


def _setup_path(repo_root: Path) -> None:
    src_path = repo_root / "packages" / "temper-placer" / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def _load_json(path: Path) -> dict | list:
    with open(path) as f:
        return json.load(f)


def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation quantile (numpy-style)."""
    n = len(sorted_values)
    idx = q * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _compute_p95(records: list[dict], stage_name: str) -> tuple[float | None, float | None]:
    """Return (p95, p99) wall_time_ms for a stage from historical records."""
    if not records:
        return None, None
    values = sorted(
        r.get("metrics", {}).get("wall_time_ms", 0)
        for r in records
        if r.get("stage_name") == stage_name or r.get("stage") == stage_name
    )
    if len(values) < 5:
        return None, None
    return _quantile(values, 0.95), _quantile(values, 0.99)


def _build_data(metrics: list[dict], execution_log: dict) -> dict:
    """Merge JSONL metrics + execution log into the embedded data payload."""
    stages: list[dict] = []
    stage_order = execution_log.get("stage_order", [])
    stage_timings = execution_log.get("stage_timings", {})
    drc_violations: list[dict] = []

    for stage in stage_order:
        duration_ms = int(stage_timings.get(stage, 0) * 1000)
        p95, p99 = _compute_p95(metrics, stage)
        color = "var(--grey)"
        if p95 is not None and duration_ms > 0:
            if duration_ms <= p95:
                color = "var(--green)"
            elif duration_ms <= p99:  # p99 may be None if < 100 records
                color = "var(--yellow)"
            elif p99 is not None:
                color = "var(--red)"

        drc_delta = None
        for r in metrics:
            if (r.get("stage_name") == stage or r.get("stage") == stage) and r.get("drc_delta") is not None:
                drc_delta = r["drc_delta"]
                break

        stages.append({
            "name": stage,
            "duration_ms": duration_ms,
            "color": color,
            "p95_ms": p95,
            "p99_ms": p99,
            "drc_delta": drc_delta,
        })

    for r in metrics:
        delta = r.get("drc_delta")
        if delta is not None:
            drc_violations.append({
                "stage": r.get("stage_name", r.get("stage", "unknown")),
                "drc_delta": delta,
            })

    has_history = any(s["p95_ms"] is not None for s in stages)

    return {
        "stages": stages,
        "drc_violations": drc_violations,
        "has_history": has_history,
        "total_duration_s": execution_log.get("total_duration_s", 0),
        "success": execution_log.get("success", False),
    }


def _render_html(data: dict) -> str:
    data_json = json.dumps(data)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Report</title>
<style>
:root {{
  --bg: #1a1a2e;
  --card-bg: #161b22;
  --border: #30363d;
  --text: #e0e0e0;
  --text-muted: #8b949e;
  --green: #4caf50;
  --yellow: #ff9800;
  --red: #f44336;
  --grey: #666;
  --radius: 6px;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px;
  line-height: 1.5;
}}
h1 {{ font-size: 1.25rem; margin-bottom: 8px; }}
h2 {{ font-size: 1rem; margin: 24px 0 12px; padding-bottom: 4px; border-bottom: 1px solid var(--border); }}
.baseline-note {{
  background: var(--card-bg);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
  margin: 12px 0;
  color: var(--text-muted);
  font-size: 0.85rem;
}}
.stage-bar-container {{
  display: flex;
  align-items: center;
  margin: 6px 0;
  gap: 8px;
}}
.stage-label {{
  font-size: 0.75rem;
  min-width: 120px;
  text-align: right;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.stage-bar {{
  height: 22px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  padding: 0 8px;
  min-width: 4px;
  transition: width 0.3s;
}}
.stage-bar-text {{
  font-size: 0.7rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
table {{
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 0.85rem;
}}
th, td {{
  padding: 6px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}}
th {{ color: var(--text-muted); font-weight: 500; }}
.legend {{ display: flex; gap: 16px; margin: 8px 0; font-size: 0.75rem; color: var(--text-muted); }}
.legend-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }}
.green {{ background: var(--green); }}
.yellow {{ background: var(--yellow); }}
.red {{ background: var(--red); }}
.grey {{ background: var(--grey); }}
.empty-state {{
  text-align: center;
  padding: 24px;
  color: var(--text-muted);
  font-size: 0.85rem;
}}
</style>
</head>
<body>
<h1>Pipeline Report</h1>
<div id="dag-timeline"></div>
<h2>Stage Timing</h2>
<table id="stage-table">
  <thead><tr><th>Stage</th><th>Wall Time</th><th>vs p95</th><th>DRC Delta</th></tr></thead>
  <tbody></tbody>
</table>
<h2>DRC Summary</h2>
<div id="drc-summary"></div>
<script>
window.__PIPELINE_DATA__ = {data_json};

(function() {{
  var D = window.__PIPELINE_DATA__;
  var maxDuration = 0;
  D.stages.forEach(function(s) {{ if (s.duration_ms > maxDuration) maxDuration = s.duration_ms; }});
  if (maxDuration === 0) maxDuration = 1;

  var timeline = document.getElementById('dag-timeline');
  if (!D.has_history) {{
    var note = document.createElement('div');
    note.className = 'baseline-note';
    note.textContent = 'Baseline building — insufficient historical data for p95/p99 color coding. All stages shown in grey.';
    timeline.appendChild(note);
  }}
  var legend = document.createElement('div');
  legend.className = 'legend';
  legend.innerHTML = '<span><span class="legend-dot green"></span>&le; p95</span>' +
    '<span><span class="legend-dot yellow"></span>p95&ndash;p99</span>' +
    '<span><span class="legend-dot red"></span>&gt; p99</span>' +
    '<span><span class="legend-dot grey"></span>no baseline</span>';
  timeline.appendChild(legend);

  D.stages.forEach(function(s) {{
    var pct = Math.max((s.duration_ms / maxDuration) * 100, 1);
    var container = document.createElement('div');
    container.className = 'stage-bar-container';
    var label = document.createElement('div');
    label.className = 'stage-label';
    label.textContent = s.name;
    container.appendChild(label);
    var bar = document.createElement('div');
    bar.className = 'stage-bar';
    bar.style.width = pct + '%';
    bar.style.backgroundColor = s.color;
    bar.style.color = s.color === 'var(--yellow)' ? '#000' : '#fff';
    var text = document.createElement('span');
    text.className = 'stage-bar-text';
    text.textContent = (s.duration_ms / 1000).toFixed(1) + 's';
    bar.appendChild(text);
    container.appendChild(bar);
    timeline.appendChild(container);
  }});

  var tbody = document.querySelector('#stage-table tbody');
  D.stages.forEach(function(s) {{
    var row = document.createElement('tr');
    var p95Cell = '—';
    if (s.p95_ms != null) {{
      var pctVsP95 = ((s.duration_ms - s.p95_ms) / s.p95_ms * 100).toFixed(0);
      var sign = pctVsP95 > 0 ? '+' : '';
      p95Cell = sign + pctVsP95 + '%';
    }}
    var drcCell = s.drc_delta != null ? '' + s.drc_delta : '—';
    row.innerHTML = '<td>' + s.name + '</td>' +
      '<td>' + (s.duration_ms / 1000).toFixed(1) + 's</td>' +
      '<td>' + p95Cell + '</td>' +
      '<td>' + drcCell + '</td>';
    tbody.appendChild(row);
  }});

  var drcDiv = document.getElementById('drc-summary');
  if (!D.drc_violations.length) {{
    var empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = 'No DRC violations';
    drcDiv.appendChild(empty);
  }} else {{
    var table = document.createElement('table');
    table.innerHTML = '<thead><tr><th>Stage</th><th>DRC Delta</th></tr></thead><tbody></tbody>';
    var drcTbody = table.querySelector('tbody');
    D.drc_violations.forEach(function(v) {{
      var row = document.createElement('tr');
      row.innerHTML = '<td>' + v.stage + '</td><td>' + v.drc_delta + '</td>';
      drcTbody.appendChild(row);
    }});
    drcDiv.appendChild(table);
  }}
}})();
</script>
</body>
</html>"""


def generate_report(metrics_file: Path, execution_log: Path, output: Path) -> None:
    from temper_placer.regression.metrics_recorder import load_metrics

    metrics = load_metrics(metrics_file)
    execution = _load_json(execution_log)
    if isinstance(execution, list):
        execution = execution[0] if execution else {}
    data = _build_data(metrics, execution)
    html = _render_html(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        f.write(html)


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(prog="pipeline_report",
        description="Generate a self-contained static HTML pipeline observability report")
    p.add_argument("--metrics-file", required=True, type=Path,
                   help="Path to pipeline_metrics.jsonl")
    p.add_argument("--execution-log", required=True, type=Path,
                   help="Path to pipeline_execution.json")
    p.add_argument("--output", required=True, type=Path,
                   help="Path for output HTML file")
    args = p.parse_args()
    repo_root = _find_repo_root()
    _setup_path(repo_root)
    generate_report(args.metrics_file, args.execution_log, args.output)
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    sys.exit(main())
