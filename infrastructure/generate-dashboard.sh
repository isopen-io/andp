#!/bin/bash

# ANDP Dashboard Generator
# Aggregates metrics and AI insights into an HTML dashboard

set -e

OUTPUT_FILE="dashboard.html"
METRICS_DIR="metrics"

echo "Generating Developer Productivity Dashboard..."

# Function to extract latest metrics from JSON files
get_latest_metric() {
    local type=$1
    ls -t "$METRICS_DIR/${type}"*.json 2>/dev/null | head -n 1
}

BUILD_METRIC=$(get_latest_metric "build")
TEST_METRIC=$(get_latest_metric "test")
PERF_METRIC=$(get_latest_metric "perf")
AI_METRIC="$METRICS_DIR/ai_analysis.json"

# Create HTML
cat <<EOF > "$OUTPUT_FILE"
<!DOCTYPE html>
<html>
<head>
    <title>ANDP Developer Productivity Dashboard</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background-color: #f5f5f7; }
        h1 { color: #1d1d1f; border-bottom: 1px solid #d2d2d7; padding-bottom: 10px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 20px; }
        .card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .card h2 { margin-top: 0; font-size: 1.2rem; color: #0071e3; }
        .metric { font-size: 2rem; font-weight: bold; margin: 10px 0; }
        .status { padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }
        .status-success { background: #e2f5e9; color: #15803d; }
        .status-failed { background: #fee2e2; color: #b91c1c; }
        .list { list-style: none; padding: 0; }
        .list li { margin-bottom: 8px; border-bottom: 1px solid #f2f2f2; padding-bottom: 4px; font-size: 0.9rem; }
    </style>
</head>
<body>
    <h1>ANDP Productivity Dashboard</h1>
    <p>Last updated: $(date)</p>

    <div class="grid">
        <!-- Build Metrics -->
        <div class="card">
            <h2>Latest Build</h2>
EOF

if [ -f "$BUILD_METRIC" ]; then
    python3 -c "import json; d=json.load(open('$BUILD_METRIC')); print(f'<div class=\"metric\">{d[\"value\"]}s</div><span class=\"status status-{d[\"status\"].lower()}\">{d[\"status\"]}</span><p>{d[\"name\"]}</p>')" >> "$OUTPUT_FILE"
else
    echo "<p>No build data available.</p>" >> "$OUTPUT_FILE"
fi

cat <<EOF >> "$OUTPUT_FILE"
        </div>

        <!-- Test Metrics -->
        <div class="card">
            <h2>Latest Tests</h2>
EOF

if [ -f "$TEST_METRIC" ]; then
    python3 -c "import json; d=json.load(open('$TEST_METRIC')); print(f'<div class=\"metric\">{d[\"value\"]}s</div><span class=\"status status-{d[\"status\"].lower()}\">{d[\"status\"]}</span><p>{d[\"name\"]}</p>')" >> "$OUTPUT_FILE"
else
    echo "<p>No test data available.</p>" >> "$OUTPUT_FILE"
fi

cat <<EOF >> "$OUTPUT_FILE"
        </div>

        <!-- Performance Metrics -->
        <div class="card">
            <h2>Performance</h2>
EOF

if [ -f "$PERF_METRIC" ]; then
    python3 -c "import json; d=json.load(open('$PERF_METRIC'))['metrics']; print(f'<ul class=\"list\"><li>Startup: {d[\"startup_time\"]}s</li><li>Memory: {d[\"memory_usage_mb\"]}MB</li><li>CPU: {d[\"cpu_usage_pct\"]}%</li></ul>')" >> "$OUTPUT_FILE"
else
    echo "<p>No performance data available.</p>" >> "$OUTPUT_FILE"
fi

cat <<EOF >> "$OUTPUT_FILE"
        </div>
    </div>

    <div class="grid">
        <!-- AI Insights -->
        <div class="card" style="grid-column: span 2;">
            <h2>AI Quality Insights</h2>
EOF

if [ -f "$AI_METRIC" ]; then
    python3 <<EOF_PY >> "$OUTPUT_FILE"
import json
with open('$AI_METRIC') as f:
    data = json.load(f)
    print('<ul class="list">')
    for category, issues in data.items():
        if issues:
            print(f'<li><strong>{category.replace("_", " ").title()}</strong>')
            print('<ul>')
            for issue in issues[:3]: # Show top 3
                print(f'<li>{issue}</li>')
            print('</ul></li>')
    if not any(data.values()):
        print('<li>✅ No issues detected</li>')
    print('</ul>')
EOF_PY
else
    echo "<p>No AI analysis data available.</p>" >> "$OUTPUT_FILE"
fi

cat <<EOF >> "$OUTPUT_FILE"
        </div>
    </div>
</body>
</html>
EOF

echo "Dashboard generated: $OUTPUT_FILE"
