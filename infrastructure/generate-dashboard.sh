#!/bin/bash

# ANDP Dashboard Generator (Bolt Optimized)
# Aggregates metrics and AI insights into an HTML dashboard in a single-pass Python execution

set -e

OUTPUT_FILE="dashboard.html"
METRICS_DIR="metrics"

echo "Generating Developer Productivity Dashboard..."

python3 <<'EOF_PY'
import os
import json
import time

metrics_dir = "metrics"
output_file = "dashboard.html"

def get_latest_metric(metric_type):
    if not os.path.isdir(metrics_dir):
        return None
    files = [os.path.join(metrics_dir, f) for f in os.listdir(metrics_dir) if f.startswith(metric_type) and f.endswith(".json")]
    if not files:
        return None
    # Sort files by modification time descending
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

build_metric_path = get_latest_metric("build")
test_metric_path = get_latest_metric("test")
perf_metric_path = get_latest_metric("perf")
ai_metric_path = os.path.join(metrics_dir, "ai_analysis.json")

# Build metric content
build_html = "<p>No build data available.</p>"
if build_metric_path and os.path.exists(build_metric_path):
    try:
        with open(build_metric_path, "r") as f:
            d = json.load(f)
            build_html = f'<div class="metric">{d["value"]}s</div><span class="status status-{d["status"].lower()}">{d["status"]}</span><p>{d["name"]}</p>'
    except Exception:
        pass

# Test metric content
test_html = "<p>No test data available.</p>"
if test_metric_path and os.path.exists(test_metric_path):
    try:
        with open(test_metric_path, "r") as f:
            d = json.load(f)
            test_html = f'<div class="metric">{d["value"]}s</div><span class="status status-{d["status"].lower()}">{d["status"]}</span><p>{d["name"]}</p>'
    except Exception:
        pass

# Performance metric content
perf_html = "<p>No performance data available.</p>"
if perf_metric_path and os.path.exists(perf_metric_path):
    try:
        with open(perf_metric_path, "r") as f:
            d = json.load(f)['metrics']
            perf_html = f'<ul class="list"><li>Startup: {d["startup_time"]}s</li><li>Memory: {d["memory_usage_mb"]}MB</li><li>CPU: {d["cpu_usage_pct"]}%</li></ul>'
    except Exception:
        pass

# AI insights content
ai_html = "<p>No AI analysis data available.</p>"
if ai_metric_path and os.path.exists(ai_metric_path):
    try:
        with open(ai_metric_path, "r") as f:
            data = json.load(f)
            ai_list = []
            ai_list.append('<ul class="list">')
            for category, issues in data.items():
                if issues:
                    cat_title = category.replace("_", " ").title()
                    ai_list.append(f'<li><strong>{cat_title}</strong>')
                    ai_list.append('<ul>')
                    for issue in issues[:3]:
                        ai_list.append(f'<li>{issue}</li>')
                    ai_list.append('</ul></li>')
            if not any(data.values()):
                ai_list.append('<li>✅ No issues detected</li>')
            ai_list.append('</ul>')
            ai_html = "\n".join(ai_list)
    except Exception:
        pass

current_time = time.strftime("%a %b %d %H:%M:%S %Z %Y")

html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>ANDP Developer Productivity Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f5f7; }}
        h1 {{ color: #1d1d1f; border-bottom: 1px solid #d2d2d7; padding-bottom: 10px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 20px; }}
        .card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .card h2 {{ margin-top: 0; font-size: 1.2rem; color: #0071e3; }}
        .metric {{ font-size: 2rem; font-weight: bold; margin: 10px 0; }}
        .status {{ padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }}
        .status-success {{ background: #e2f5e9; color: #15803d; }}
        .status-failed {{ background: #fee2e2; color: #b91c1c; }}
        .list {{ list-style: none; padding: 0; }}
        .list li {{ margin-bottom: 8px; border-bottom: 1px solid #f2f2f2; padding-bottom: 4px; font-size: 0.9rem; }}
    </style>
</head>
<body>
    <h1>ANDP Productivity Dashboard</h1>
    <p>Last updated: {current_time}</p>

    <div class="grid">
        <!-- Build Metrics -->
        <div class="card">
            <h2>Latest Build</h2>
            {build_html}
        </div>

        <!-- Test Metrics -->
        <div class="card">
            <h2>Latest Tests</h2>
            {test_html}
        </div>

        <!-- Performance Metrics -->
        <div class="card">
            <h2>Performance</h2>
            {perf_html}
        </div>
    </div>

    <div class="grid">
        <!-- AI Insights -->
        <div class="card" style="grid-column: span 2;">
            <h2>AI Quality Insights</h2>
            {ai_html}
        </div>
    </div>
</body>
</html>"""

with open(output_file, "w") as f:
    f.write(html_content)
EOF_PY

echo "Dashboard generated: $OUTPUT_FILE"
