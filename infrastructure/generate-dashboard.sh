#!/bin/bash

# ANDP Dashboard Generator
# Aggregates metrics and AI insights into an HTML dashboard
# Bolt Optimized: Consolidated all subshells, `ls -t` commands, and multiple `python3` spawns
# into a single, high-performance Python process.

set -e

echo "Generating Developer Productivity Dashboard..."

python3 <<'EOF_PY'
import os
import glob
import json
import time

def get_latest_metric(prefix, metrics_dir="metrics"):
    pattern = os.path.join(metrics_dir, f"{prefix}*.json")
    files = glob.glob(pattern)
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]

def main():
    metrics_dir = "metrics"
    output_file = "dashboard.html"

    build_file = get_latest_metric("build", metrics_dir)
    test_file = get_latest_metric("test", metrics_dir)
    perf_file = get_latest_metric("perf", metrics_dir)
    ai_file = os.path.join(metrics_dir, "ai_analysis.json")

    current_time_str = time.strftime("%a %b %d %H:%M:%S %Z %Y")

    html = f"""<!DOCTYPE html>
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
    <p>Last updated: {current_time_str}</p>

    <div class="grid">
        <!-- Build Metrics -->
        <div class="card">
            <h2>Latest Build</h2>
"""

    if build_file and os.path.exists(build_file):
        try:
            with open(build_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            html += f"""            <div class="metric">{d["value"]}s</div><span class="status status-{d["status"].lower()}">{d["status"]}</span><p>{d["name"]}</p>\n"""
        except Exception as e:
            html += f"            <p>Error loading build data: {e}</p>\n"
    else:
        html += "            <p>No build data available.</p>\n"

    html += """        </div>

        <!-- Test Metrics -->
        <div class="card">
            <h2>Latest Tests</h2>
"""

    if test_file and os.path.exists(test_file):
        try:
            with open(test_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            html += f"""            <div class="metric">{d["value"]}s</div><span class="status status-{d["status"].lower()}">{d["status"]}</span><p>{d["name"]}</p>\n"""
        except Exception as e:
            html += f"            <p>Error loading test data: {e}</p>\n"
    else:
        html += "            <p>No test data available.</p>\n"

    html += """        </div>

        <!-- Performance Metrics -->
        <div class="card">
            <h2>Performance</h2>
"""

    if perf_file and os.path.exists(perf_file):
        try:
            with open(perf_file, 'r', encoding='utf-8') as f:
                d = json.load(f)['metrics']
            html += f"""            <ul class="list"><li>Startup: {d["startup_time"]}s</li><li>Memory: {d["memory_usage_mb"]}MB</li><li>CPU: {d["cpu_usage_pct"]}%</li></ul>\n"""
        except Exception as e:
            html += f"            <p>Error loading performance data: {e}</p>\n"
    else:
        html += "            <p>No performance data available.</p>\n"

    html += """        </div>
    </div>

    <div class="grid">
        <!-- AI Insights -->
        <div class="card" style="grid-column: span 2;">
            <h2>AI Quality Insights</h2>
"""

    if ai_file and os.path.exists(ai_file):
        try:
            with open(ai_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            html += '            <ul class="list">\n'
            has_issues = False
            for category, issues in data.items():
                if issues:
                    has_issues = True
                    category_title = category.replace("_", " ").title()
                    html += f'                <li><strong>{category_title}</strong>\n'
                    html += '                <ul>\n'
                    for issue in issues[:3]:  # Show top 3
                        html += f'                    <li>{issue}</li>\n'
                    html += '                </ul></li>\n'
            if not has_issues:
                html += '                <li>✅ No issues detected</li>\n'
            html += '            </ul>\n'
        except Exception as e:
            html += f"            <p>Error loading AI analysis data: {e}</p>\n"
    else:
        html += "            <p>No AI analysis data available.</p>\n"

    html += """        </div>
    </div>
</body>
</html>
"""

    with open(output_file, "w", encoding='utf-8') as f:
        f.write(html)

if __name__ == "__main__":
    main()
EOF_PY

echo "Dashboard generated: dashboard.html"
