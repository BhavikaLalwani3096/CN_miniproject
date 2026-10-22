#!/usr/bin/env python3
"""
Flask Web Dashboard for Live Queue Telemetry
"""
import subprocess, threading, time, re
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

metrics = {
    "q0_packets": 0, "q0_bytes": 0, "q0_throughput": 0.0,
    "q1_packets": 0, "q1_bytes": 0, "q1_throughput": 0.0,
    "current_latency": 10.0, "latency_history": [], "status": "Ready"
}

def poll_metrics():
    prev_q0_bytes = 0
    prev_q1_bytes = 0
    prev_time = time.time()

    while True:
        try:
            res = subprocess.run(["sudo", "ovs-ofctl", "-O", "OpenFlow13", "queue-stats", "s1", "3"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            curr_time = time.time()
            dt = max(curr_time - prev_time, 1.0)
            
            q0_bytes, q1_bytes = metrics["q0_bytes"], metrics["q1_bytes"]

            for line in res.stdout.splitlines():
                if 'queue 0:' in line:
                    parts = line.split(',')
                    q0_bytes = int(parts[0].split('=')[1].strip())
                    metrics["q0_packets"] = int(parts[1].split('=')[1].strip())
                elif 'queue 1:' in line:
                    parts = line.split(',')
                    q1_bytes = int(parts[0].split('=')[1].strip())
                    metrics["q1_packets"] = int(parts[1].split('=')[1].strip())

            if prev_q0_bytes > 0 and q0_bytes >= prev_q0_bytes:
                metrics["q0_throughput"] = round(((q0_bytes - prev_q0_bytes) * 8.0) / (dt * 1e6), 2)
            if prev_q1_bytes > 0 and q1_bytes >= prev_q1_bytes:
                metrics["q1_throughput"] = round(((q1_bytes - prev_q1_bytes) * 8.0) / (dt * 1e6), 2)

            metrics["q0_bytes"], metrics["q1_bytes"] = q0_bytes, q1_bytes
            prev_q0_bytes, prev_q1_bytes = q0_bytes, q1_bytes
            prev_time = curr_time

            h1_pid = subprocess.getoutput("pgrep -f 'mininet:h1' | head -n1").strip()
            if h1_pid:
                ping_res = subprocess.getoutput(f"sudo mnexec -a {h1_pid} ping -c 1 -W 1 10.0.0.3")
                match = re.search(r'time=([\d\.]+)\s*ms', ping_res)
                if match:
                    rtt = float(match.group(1))
                    metrics["latency_history"].append(rtt)
                    if len(metrics["latency_history"]) > 30: metrics["latency_history"].pop(0)
        except Exception: pass
        time.sleep(1.0)

@app.route('/api/stats')
def get_stats(): return jsonify(metrics)

@app.route('/api/run_test/<test_type>', methods=['POST'])
def run_test(test_type):
    def task():
        h1_pid = subprocess.getoutput("pgrep -f 'mininet:h1' | head -n1").strip()
        h2_pid = subprocess.getoutput("pgrep -f 'mininet:h2' | head -n1").strip()
        h3_pid = subprocess.getoutput("pgrep -f 'mininet:h3' | head -n1").strip()

        if not (h1_pid and h2_pid and h3_pid):
            metrics["status"] = "Error: Mininet nodes not running!"
            return

        subprocess.run(f"sudo mnexec -a {h3_pid} pkill -f iperf", shell=True)
        subprocess.run(f"sudo mnexec -a {h3_pid} iperf -s -p 5001 &", shell=True)
        subprocess.run(f"sudo mnexec -a {h3_pid} iperf -s -u -p 5002 &", shell=True)
        time.sleep(0.5)

        if test_type == "contention":
            metrics["status"] = "Running Contention: TCP Bulk Download on Queue 1..."
            subprocess.run(f"sudo mnexec -a {h2_pid} iperf -c 10.0.0.3 -p 5001 -t 12", shell=True)
            metrics["status"] = "Contention Test Completed."
        elif test_type == "starvation":
            metrics["status"] = "Running Anti-Starvation: Q0 UDP Flood + Q1 TCP Bulk..."
            subprocess.Popen(f"sudo mnexec -a {h1_pid} iperf -c 10.0.0.3 -u -p 5002 -b 12M -t 12", shell=True)
            time.sleep(1)
            subprocess.run(f"sudo mnexec -a {h2_pid} iperf -c 10.0.0.3 -p 5001 -t 10", shell=True)
            metrics["status"] = "Anti-Starvation Test Completed."

    threading.Thread(target=task).start()
    return jsonify({"result": "started"})

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Adaptive SDN Traffic Slicing & Anti-Starvation Monitor</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; background: #0b1329; color: #f1f5f9; margin: 0; padding: 24px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .status-badge { background: #1e293b; padding: 8px 16px; border-radius: 20px; border: 1px solid #38bdf8; font-size: 14px; font-weight: 600; }
        .btn-group { display: flex; gap: 12px; margin-bottom: 24px; }
        button { background: #2563eb; color: white; border: none; padding: 12px 24px; border-radius: 8px; cursor: pointer; font-weight: 600; font-size: 14px; }
        button:hover { background: #1d4ed8; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }
        .card { background: #152238; border-radius: 12px; padding: 20px; border: 1px solid #1e293b; }
        .card h3 { margin: 0 0 8px 0; color: #94a3b8; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; }
        .val { font-size: 32px; font-weight: 700; }
        .throughput-tag { font-size: 20px; font-weight: bold; margin-top: 6px; }
        .sub { color: #64748b; font-size: 14px; margin-top: 4px; }
        .chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    </style>
</head>
<body>
    <div class="header">
        <h2>Adaptive SDN Traffic Slicing & Anti-Starvation Monitor</h2>
        <div class="status-badge" id="status">Status: Ready</div>
    </div>
    <div class="btn-group">
        <button onclick="triggerTest('contention')">Trigger Contention Test (Bulk TCP -> Q1)</button>
        <button onclick="triggerTest('starvation')">Trigger Anti-Starvation (Q0 Flood + Q1 TCP)</button>
    </div>
    <div class="grid">
        <div class="card">
            <h3>Queue 0 (Interactive: ICMP / UDP)</h3>
            <div class="val" id="q0_pkts" style="color: #10b981;">0 pkts</div>
            <div class="throughput-tag" style="color: #34d399;">Rate: <span id="q0_rate">0.00</span> Mbps</div>
            <div class="sub" id="q0_bytes">0.00 MB processed</div>
        </div>
        <div class="card">
            <h3>Queue 1 (Bulk: TCP Downloads)</h3>
            <div class="val" id="q1_pkts" style="color: #60a5fa;">0 pkts</div>
            <div class="throughput-tag" style="color: #93c5fd;">Rate: <span id="q1_rate">0.00</span> Mbps</div>
            <div class="sub" id="q1_bytes">0.00 MB processed</div>
        </div>
    </div>
    <div class="chart-grid">
        <div class="card">
            <h3>Live Queue Packet Distribution</h3>
            <canvas id="barChart" height="150"></canvas>
        </div>
        <div class="card">
            <h3>Interactive Round-Trip Latency (ms)</h3>
            <canvas id="lineChart" height="150"></canvas>
        </div>
    </div>
    <script>
        const barCtx = document.getElementById('barChart').getContext('2d');
        const lineCtx = document.getElementById('lineChart').getContext('2d');
        const barChart = new Chart(barCtx, { type: 'bar', data: { labels: ['Queue 0 (Interactive)', 'Queue 1 (Bulk)'], datasets: [{ data: [0, 0], backgroundColor: ['#10b981', '#60a5fa'], borderRadius: 6 }] }, options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } } });
        const lineChart = new Chart(lineCtx, { type: 'line', data: { labels: Array.from({length: 30}, (_, i) => i + 1), datasets: [{ label: 'RTT (ms)', data: [], borderColor: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.1)', tension: 0.3, fill: true }] }, options: { responsive: true, scales: { y: { min: 0, max: 80 } } } });
        async function refresh() {
            try {
                const res = await fetch('/api/stats'); const d = await res.json();
                document.getElementById('q0_pkts').innerText = d.q0_packets.toLocaleString() + ' pkts';
                document.getElementById('q0_bytes').innerText = (d.q0_bytes / (1024*1024)).toFixed(2) + ' MB processed';
                document.getElementById('q0_rate').innerText = d.q0_throughput.toFixed(2);
                document.getElementById('q1_pkts').innerText = d.q1_packets.toLocaleString() + ' pkts';
                document.getElementById('q1_bytes').innerText = (d.q1_bytes / (1024*1024)).toFixed(2) + ' MB processed';
                document.getElementById('q1_rate').innerText = d.q1_throughput.toFixed(2);
                document.getElementById('status').innerText = 'Status: ' + d.status;
                barChart.data.datasets[0].data = [d.q0_packets, d.q1_packets]; barChart.update();
                lineChart.data.datasets[0].data = d.latency_history; lineChart.update();
            } catch(e) {}
        }
        setInterval(refresh, 1000);
        async function triggerTest(name) { await fetch('/api/run_test/' + name, { method: 'POST' }); }
    </script>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_PAGE)

if __name__ == '__main__':
    t = threading.Thread(target=poll_metrics, daemon=True)
    t.start()
    app.run(host='0.0.0.0', port=8080)