"""
Phase 5 — Dashboard
Flask web server yang serve dashboard prediksi BTC.
Jalan di thread terpisah dari scheduler.
"""
from flask import Flask, jsonify, render_template_string
from sqlalchemy import text
from database.connection import engine
from config import SYMBOL
import pandas as pd

app = Flask(__name__)


def query(sql, params=None):
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    return df


@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/latest")
def api_latest():
    try:
        df = query(f"""
            SELECT * FROM predictions
            WHERE symbol = '{SYMBOL}'
            ORDER BY created_at DESC LIMIT 1
        """)
        if df.empty:
            return jsonify({"error": "No predictions yet"})
        row = df.iloc[0].to_dict()
        return jsonify(row)
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/history")
def api_history():
    try:
        df = query(f"""
            SELECT ts, prediction, label, confidence,
                   regime, prob_turun, prob_sideways, prob_naik, created_at
            FROM predictions
            WHERE symbol = '{SYMBOL}'
            ORDER BY created_at DESC LIMIT 48
        """)
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/accuracy")
def api_accuracy():
    """Hitung akurasi prediksi vs harga aktual."""
    try:
        # Join predictions dengan features untuk cek label aktual
        df = query(f"""
            SELECT
                p.ts, p.label as predicted, p.confidence,
                f.label as actual
            FROM predictions p
            LEFT JOIN features f ON f.ts::text LIKE p.ts || '%'
                AND f.symbol = '{SYMBOL}'
            WHERE p.symbol = '{SYMBOL}'
            ORDER BY p.created_at DESC LIMIT 100
        """)
        if df.empty or "actual" not in df.columns:
            return jsonify({"accuracy": None, "total": 0})

        df = df.dropna(subset=["actual"])
        if df.empty:
            return jsonify({"accuracy": None, "total": 0})

        correct = (df["predicted"] == df["actual"]).sum()
        total   = len(df)
        return jsonify({
            "accuracy": round(correct / total * 100, 1),
            "correct":  int(correct),
            "total":    total,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/api/price")
def api_price():
    """Ambil harga terbaru dari mark_price_kline."""
    try:
        df = query(f"""
            SELECT open_time, close, high, low, volume
            FROM mark_price_kline
            WHERE symbol = '{SYMBOL}'
            ORDER BY open_time DESC LIMIT 48
        """)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms").astype(str)
        return jsonify(df.iloc[::-1].to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)})


# ── HTML Dashboard ──────────────────────────────────────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BTC ML Predictor</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:      #080c10;
    --surface: #0d1117;
    --border:  #1c2333;
    --text:    #e6edf3;
    --muted:   #8b949e;
    --up:      #3fb950;
    --down:    #f85149;
    --side:    #d29922;
    --accent:  #58a6ff;
    --glow-up:   0 0 20px rgba(63,185,80,0.3);
    --glow-down: 0 0 20px rgba(248,81,73,0.3);
    --glow-side: 0 0 20px rgba(210,153,34,0.3);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Space Mono', monospace;
    min-height: 100vh;
    padding: 24px;
  }
  /* Header */
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 32px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }
  .logo {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 22px;
    letter-spacing: -0.5px;
  }
  .logo span { color: var(--accent); }
  .status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--up);
    display: inline-block;
    margin-right: 8px;
    box-shadow: 0 0 8px var(--up);
    animation: pulse 2s infinite;
  }
  @keyframes pulse {
    0%,100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
  .last-update { color: var(--muted); font-size: 12px; }

  /* Grid */
  .grid { display: grid; gap: 16px; }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-2 { grid-template-columns: 2fr 1fr; }
  @media(max-width: 900px) {
    .grid-3, .grid-2 { grid-template-columns: 1fr; }
  }

  /* Cards */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
  }
  .card-label {
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 12px;
  }

  /* Main prediction card */
  .prediction-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 32px;
    text-align: center;
    position: relative;
    overflow: hidden;
    transition: box-shadow 0.5s;
  }
  .prediction-card::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at 50% 0%, rgba(88,166,255,0.05), transparent 70%);
    pointer-events: none;
  }
  .prediction-badge {
    display: inline-block;
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 48px;
    letter-spacing: -2px;
    margin: 8px 0 16px;
    transition: color 0.5s;
  }
  .badge-up   { color: var(--up);   text-shadow: var(--glow-up); }
  .badge-down { color: var(--down); text-shadow: var(--glow-down); }
  .badge-side { color: var(--side); text-shadow: var(--glow-side); }

  .confidence-bar-wrap {
    background: var(--border);
    border-radius: 999px;
    height: 6px;
    margin: 16px auto;
    max-width: 300px;
    overflow: hidden;
  }
  .confidence-bar {
    height: 100%;
    border-radius: 999px;
    background: var(--accent);
    transition: width 1s ease;
  }
  .confidence-label {
    font-size: 13px;
    color: var(--muted);
  }
  .confidence-value {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 28px;
    color: var(--accent);
  }

  /* Probability bars */
  .prob-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }
  .prob-label { font-size: 12px; width: 70px; color: var(--muted); }
  .prob-track {
    flex: 1;
    background: var(--border);
    border-radius: 4px;
    height: 8px;
    overflow: hidden;
  }
  .prob-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 1s ease;
  }
  .fill-up   { background: var(--up); }
  .fill-down { background: var(--down); }
  .fill-side { background: var(--side); }
  .prob-pct { font-size: 12px; width: 40px; text-align: right; }

  /* Regime badge */
  .regime-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    border: 1px solid currentColor;
    margin-top: 8px;
  }

  /* Price display */
  .price-big {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 36px;
    letter-spacing: -1px;
  }
  .price-change { font-size: 13px; margin-top: 4px; }
  .pos { color: var(--up); }
  .neg { color: var(--down); }

  /* Table */
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th {
    text-align: left; padding: 8px 12px;
    color: var(--muted); font-weight: 400;
    font-size: 11px; letter-spacing: 1px;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
  }
  td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,0.02); }
  .tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
  }
  .tag-up   { background: rgba(63,185,80,0.15);  color: var(--up); }
  .tag-down { background: rgba(248,81,73,0.15);  color: var(--down); }
  .tag-side { background: rgba(210,153,34,0.15); color: var(--side); }

  /* Stats */
  .stat-value {
    font-family: 'Syne', sans-serif;
    font-size: 32px; font-weight: 800;
    letter-spacing: -1px;
  }
  .stat-sub { font-size: 12px; color: var(--muted); margin-top: 4px; }

  /* Loading */
  .loading { color: var(--muted); font-size: 13px; text-align: center; padding: 24px; }

  /* Divider */
  .mb16 { margin-bottom: 16px; }
  .mb24 { margin-bottom: 24px; }
</style>
</head>
<body>

<div class="header">
  <div class="logo">BTC<span>/ML</span> Predictor</div>
  <div>
    <span class="status-dot"></span>
    <span class="last-update" id="last-update">Loading...</span>
  </div>
</div>

<!-- Row 1: Main prediction + price + accuracy -->
<div class="grid grid-3 mb16">

  <!-- Prediction -->
  <div class="prediction-card" id="pred-card">
    <div class="card-label">4-Hour Prediction</div>
    <div class="prediction-badge" id="pred-badge">—</div>
    <div class="confidence-value" id="conf-value">—</div>
    <div class="confidence-label">confidence</div>
    <div class="confidence-bar-wrap">
      <div class="confidence-bar" id="conf-bar" style="width:0%"></div>
    </div>
    <div class="regime-badge" id="regime-badge" style="color:var(--muted)">—</div>
  </div>

  <!-- Probability breakdown -->
  <div class="card">
    <div class="card-label">Probability Breakdown</div>
    <div class="prob-row">
      <span class="prob-label">↑ NAIK</span>
      <div class="prob-track"><div class="prob-fill fill-up" id="p-naik" style="width:0%"></div></div>
      <span class="prob-pct" id="pct-naik">0%</span>
    </div>
    <div class="prob-row">
      <span class="prob-label">→ SIDE</span>
      <div class="prob-track"><div class="prob-fill fill-side" id="p-side" style="width:0%"></div></div>
      <span class="prob-pct" id="pct-side">0%</span>
    </div>
    <div class="prob-row">
      <span class="prob-label">↓ TURUN</span>
      <div class="prob-track"><div class="prob-fill fill-down" id="p-down" style="width:0%"></div></div>
      <span class="prob-pct" id="pct-down">0%</span>
    </div>
    <div style="margin-top:24px">
      <div class="card-label">Current Price</div>
      <div class="price-big" id="price-now">—</div>
      <div class="price-change" id="price-chg">—</div>
    </div>
  </div>

  <!-- Accuracy stats -->
  <div class="card">
    <div class="card-label">Live Accuracy</div>
    <div class="stat-value" id="acc-value" style="color:var(--accent)">—</div>
    <div class="stat-sub" id="acc-sub">vs actual price movement</div>
    <div style="margin-top: 28px">
      <div class="card-label">Model</div>
      <div style="font-size:13px; color:var(--muted); line-height:2">
        XGBoost + LSTM + HMM<br>
        Ensemble (regime-weighted)<br>
        Threshold ±0.5% · 4h horizon
      </div>
    </div>
  </div>

</div>

<!-- Row 2: History table + price chart placeholder -->
<div class="grid grid-2">

  <div class="card">
    <div class="card-label mb16">Prediction History</div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Prediction</th>
            <th>Confidence</th>
            <th>Regime</th>
          </tr>
        </thead>
        <tbody id="history-body">
          <tr><td colspan="4" class="loading">Loading...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <div class="card-label mb16">Recent Price (48h)</div>
    <canvas id="price-chart" width="400" height="260"></canvas>
  </div>

</div>

<script>
const LABEL_MAP = { 0: "TURUN ↓", 1: "SIDEWAYS →", 2: "NAIK ↑" };
const CLASS_MAP = { 0: "badge-down", 1: "badge-side", 2: "badge-up" };
const TAG_MAP   = { 0: "tag-down",  1: "tag-side",   2: "tag-up" };
const REGIME_COLOR = {
  "Bearish/Volatile": "var(--down)",
  "Sideways":         "var(--side)",
  "Bullish/Trending": "var(--up)",
};

async function fetchLatest() {
  try {
    const r = await fetch("/api/latest");
    const d = await r.json();
    if (d.error) return;

    // Badge
    const badge = document.getElementById("pred-badge");
    badge.textContent = LABEL_MAP[d.label] || d.prediction;
    badge.className = "prediction-badge " + (CLASS_MAP[d.label] || "");

    // Confidence
    document.getElementById("conf-value").textContent = d.confidence + "%";
    document.getElementById("conf-bar").style.width = d.confidence + "%";

    // Regime
    const rb = document.getElementById("regime-badge");
    rb.textContent = d.regime || "—";
    rb.style.color = REGIME_COLOR[d.regime] || "var(--muted)";

    // Probabilities
    document.getElementById("p-naik").style.width  = (d.prob_naik  || 0) + "%";
    document.getElementById("p-side").style.width  = (d.prob_sideways || 0) + "%";
    document.getElementById("p-down").style.width  = (d.prob_turun || 0) + "%";
    document.getElementById("pct-naik").textContent = (d.prob_naik  || 0) + "%";
    document.getElementById("pct-side").textContent = (d.prob_sideways || 0) + "%";
    document.getElementById("pct-down").textContent = (d.prob_turun || 0) + "%";

    // Last update
    document.getElementById("last-update").textContent =
      "Last update: " + new Date(d.created_at).toLocaleTimeString();

  } catch(e) { console.error(e); }
}

async function fetchHistory() {
  try {
    const r = await fetch("/api/history");
    const data = await r.json();
    if (!Array.isArray(data)) return;

    const tbody = document.getElementById("history-body");
    tbody.innerHTML = data.map(d => `
      <tr>
        <td style="color:var(--muted)">${new Date(d.created_at).toLocaleString('en-GB',{hour:'2-digit',minute:'2-digit',day:'2-digit',month:'short'})}</td>
        <td><span class="tag ${TAG_MAP[d.label] || ''}">${LABEL_MAP[d.label] || d.prediction}</span></td>
        <td>${d.confidence}%</td>
        <td style="color:var(--muted);font-size:12px">${d.regime || '—'}</td>
      </tr>
    `).join("") || '<tr><td colspan="4" class="loading">No predictions yet</td></tr>';
  } catch(e) { console.error(e); }
}

async function fetchAccuracy() {
  try {
    const r = await fetch("/api/accuracy");
    const d = await r.json();
    const el = document.getElementById("acc-value");
    if (d.accuracy !== null && d.accuracy !== undefined) {
      el.textContent = d.accuracy + "%";
      document.getElementById("acc-sub").textContent =
        `${d.correct}/${d.total} correct predictions`;
    } else {
      el.textContent = "—";
    }
  } catch(e) { console.error(e); }
}

async function fetchPrice() {
  try {
    const r = await fetch("/api/price");
    const data = await r.json();
    if (!Array.isArray(data) || !data.length) return;

    const latest = data[data.length - 1];
    const prev   = data[data.length - 2];
    const price  = parseFloat(latest.close);
    const change = prev ? ((price - parseFloat(prev.close)) / parseFloat(prev.close) * 100) : 0;

    document.getElementById("price-now").textContent =
      "$" + price.toLocaleString("en-US", {minimumFractionDigits: 0});
    const chgEl = document.getElementById("price-chg");
    chgEl.textContent = (change >= 0 ? "+" : "") + change.toFixed(2) + "% (1h)";
    chgEl.className = "price-change " + (change >= 0 ? "pos" : "neg");

    // Draw mini chart
    drawChart(data);
  } catch(e) { console.error(e); }
}

function drawChart(data) {
  const canvas = document.getElementById("price-chart");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const prices = data.map(d => parseFloat(d.close));
  const min = Math.min(...prices), max = Math.max(...prices);
  const pad = { top: 20, bottom: 30, left: 10, right: 10 };
  const w = W - pad.left - pad.right;
  const h = H - pad.top - pad.bottom;

  ctx.clearRect(0, 0, W, H);

  // Grid lines
  ctx.strokeStyle = "rgba(28,35,51,0.8)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (h / 4) * i;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y);
    ctx.stroke();
  }

  // Price line
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0, "rgba(88,166,255,0.3)");
  grad.addColorStop(1, "rgba(88,166,255,0)");

  ctx.beginPath();
  prices.forEach((p, i) => {
    const x = pad.left + (i / (prices.length - 1)) * w;
    const y = pad.top + h - ((p - min) / (max - min || 1)) * h;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#58a6ff";
  ctx.lineWidth = 2;
  ctx.stroke();

  // Fill area
  const lastX = pad.left + w, firstX = pad.left;
  ctx.lineTo(lastX, pad.top + h);
  ctx.lineTo(firstX, pad.top + h);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Price labels
  ctx.fillStyle = "rgba(139,148,158,0.8)";
  ctx.font = "10px Space Mono, monospace";
  ctx.fillText("$" + max.toLocaleString(), pad.left + 4, pad.top + 12);
  ctx.fillText("$" + min.toLocaleString(), pad.left + 4, pad.top + h - 4);
}

// Initial load
fetchLatest();
fetchHistory();
fetchAccuracy();
fetchPrice();

// Auto-refresh tiap 60 detik
setInterval(() => {
  fetchLatest();
  fetchHistory();
  fetchAccuracy();
  fetchPrice();
}, 60000);
</script>
</body>
</html>
"""


def run_dashboard(port=8080):
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
