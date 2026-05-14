from flask import Flask, jsonify, render_template_string
from sqlalchemy import text
from database.connection import engine
from dashboard.live_price import get_live_price
from config import SYMBOL, PREDICTION_HORIZONS, SIGNAL_THRESHOLD
import pandas as pd

app = Flask(__name__)

def query(sql):
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/analytics")
def analytics_page():
    return render_template_string(ANALYTICS_HTML)

@app.route("/api/latest")
def api_latest():
    try:
        results = {}
        for h in PREDICTION_HORIZONS:
            df = query(f"""
                SELECT * FROM predictions
                WHERE symbol='{SYMBOL}' AND horizon_h={h}
                ORDER BY created_at DESC LIMIT 1
            """)
            if not df.empty:
                results[str(h)] = df.iloc[0].to_dict()
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/history")
def api_history():
    try:
        df = query(f"""
            SELECT ts, horizon_h, predicted_pct, signal, direction,
                   regime, xgb_pred, lstm_pred, created_at
            FROM predictions WHERE symbol='{SYMBOL}'
            ORDER BY created_at DESC LIMIT 96
        """)
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/analytics")
def api_analytics():
    from dashboard.analytics import get_analytics_data
    return jsonify(get_analytics_data())

@app.route("/api/price/live")
def api_price_live():
    return jsonify(get_live_price())

@app.route("/api/price")
def api_price():
    try:
        df = query(f"""
            SELECT open_time,open,high,low,close,volume
            FROM mark_price_kline WHERE symbol='{SYMBOL}'
            ORDER BY open_time DESC LIMIT 168
        """)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms").astype(str)
        return jsonify(df.iloc[::-1].to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)})

# ── NAV snippet ─────────────────────────────────────────────────────────────
NAV = lambda active: f"""
<div style="display:flex;gap:8px;margin-right:16px;">
  <a href="/" style="padding:6px 16px;border-radius:999px;font-size:12px;text-decoration:none;{'background:var(--rose);border:1px solid var(--rose);color:white' if active=='dashboard' else 'color:var(--muted);border:1px solid var(--border)'};font-family:DM Sans,sans-serif;">Dashboard</a>
  <a href="/analytics" style="padding:6px 16px;border-radius:999px;font-size:12px;text-decoration:none;{'background:var(--rose);border:1px solid var(--rose);color:white' if active=='analytics' else 'color:var(--muted);border:1px solid var(--border)'};font-family:DM Sans,sans-serif;">Analytics</a>
</div>"""

# ── Dashboard HTML ──────────────────────────────────────────────────────────
DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>axaphia / ML Analyst</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/hammer.js/2.0.8/hammer.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-zoom/2.0.1/chartjs-plugin-zoom.min.js"></script>
<style>
:root{
  --bg:#fdf8f5;--surface:#fff;--border:#ede8e3;--text:#2d2420;--muted:#9e8f87;
  --rose:#c4788a;--blush:#e8a0b0;--gold:#c49a4e;--lavender:#9b8ec4;
  --up:#5a9e7a;--down:#c4788a;--side:#c49a4e;
  --shadow:0 2px 16px rgba(45,36,32,0.07);--shadow-lg:0 8px 40px rgba(45,36,32,0.12);
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;font-weight:300;min-height:100vh;padding:28px 32px;}
.header{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid var(--border);}
.logo{font-family:'DM Serif Display',serif;font-size:26px;letter-spacing:-0.5px;}
.logo em{font-style:italic;color:var(--rose);}
.logo .slash{color:var(--muted);margin:0 4px;}
.header-right{display:flex;align-items:center;gap:16px;font-size:12px;color:var(--muted);}
.live-dot{width:7px;height:7px;background:var(--up);border-radius:50%;display:inline-block;margin-right:6px;box-shadow:0 0 6px var(--up);animation:breathe 2.5s ease-in-out infinite;}
@keyframes breathe{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.5;transform:scale(0.8)}}
.grid-top{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-bottom:20px;}
.grid-bot{display:grid;grid-template-columns:1fr 1.2fr;gap:20px;}
@media(max-width:900px){.grid-top,.grid-bot{grid-template-columns:1fr;}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:24px;box-shadow:var(--shadow);transition:box-shadow 0.3s;}
.card:hover{box-shadow:var(--shadow-lg);}
.card-label{font-size:10px;letter-spacing:2.5px;text-transform:uppercase;color:var(--muted);margin-bottom:16px;font-weight:500;}
/* Ticker */
.ticker{background:linear-gradient(135deg,#fff8f9,#f9f5ff);border:1px solid #ede0ea;border-radius:16px;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;gap:24px;flex-wrap:wrap;}
.price-big{font-family:'DM Serif Display',serif;font-size:44px;letter-spacing:-1px;line-height:1;transition:color 0.3s;}
.price-chg{font-size:13px;font-weight:500;}
.meta-item{font-size:11px;color:var(--muted);}
.meta-item span{display:block;color:var(--text);font-weight:500;font-size:13px;margin-top:2px;}
.rt-badge{font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--up);border:1px solid var(--up);padding:3px 8px;border-radius:999px;animation:breathe 2s infinite;white-space:nowrap;}
.flash-up{color:var(--up)!important;}.flash-down{color:var(--down)!important;}
/* Horizon cards */
.horizon-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.h-card{background:linear-gradient(145deg,#fff8f9,#fff);border:1px solid #f0e0e4;border-radius:16px;padding:20px;text-align:center;}
.h-label{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);margin-bottom:8px;}
.h-pct{font-family:'DM Serif Display',serif;font-size:40px;letter-spacing:-1px;line-height:1;margin-bottom:4px;}
.h-signal{font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px;}
.regime-pill{display:inline-block;padding:4px 12px;border-radius:999px;font-size:10px;letter-spacing:2px;text-transform:uppercase;border:1px solid currentColor;}
/* Model detail */
.model-row{display:flex;justify-content:space-between;font-size:12px;padding:8px 0;border-bottom:1px solid var(--border);}
.model-row:last-child{border-bottom:none;}
.model-row span:last-child{font-weight:500;}
/* Table */
.table-wrap{overflow-x:auto;}
table{width:100%;border-collapse:collapse;}
th{text-align:left;padding:0 12px 12px;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);font-weight:500;border-bottom:1px solid var(--border);}
td{padding:10px 12px;font-size:13px;border-bottom:1px solid var(--bg);}
tr:last-child td{border-bottom:none;}
tr:hover td{background:#fdf8f5;}
.tag{display:inline-flex;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:500;}
.tag-up{background:rgba(90,158,122,0.12);color:var(--up);}
.tag-down{background:rgba(196,120,138,0.12);color:var(--down);}
.tag-side{background:rgba(196,154,78,0.12);color:var(--gold);}
.tag-8h{background:rgba(155,142,196,0.12);color:var(--lavender);}
/* Chart */
.ctrl-btn{padding:5px 14px;border-radius:999px;font-size:11px;font-family:'DM Sans',sans-serif;font-weight:500;border:1px solid var(--border);background:var(--surface);color:var(--muted);cursor:pointer;transition:all 0.2s;letter-spacing:1px;}
.ctrl-btn:hover,.ctrl-btn.active{background:var(--rose);border-color:var(--rose);color:white;}
.ctrl-btn.reset-btn{margin-left:auto;}
.ctrl-btn.reset-btn:hover{background:var(--lavender);border-color:var(--lavender);color:white;}
.pos{color:var(--up);}.neg{color:var(--down);}
.loading-row{text-align:center;padding:32px;color:var(--muted);font-size:13px;}
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="logo">axaphia<span class="slash">/</span><em>machine learning</em> analyst</div>
    <div style="font-size:11px;color:var(--muted);margin-top:6px;letter-spacing:1px">BTCUSDT · Regression · 8h & 24h Horizon</div>
  </div>
  <div class="header-right">
    <div style="display:flex;gap:8px;margin-right:8px;">
      <a href="/" style="padding:6px 16px;border-radius:999px;font-size:12px;text-decoration:none;background:var(--rose);border:1px solid var(--rose);color:white;font-family:'DM Sans',sans-serif;">Dashboard</a>
      <a href="/analytics" style="padding:6px 16px;border-radius:999px;font-size:12px;text-decoration:none;color:var(--muted);border:1px solid var(--border);font-family:'DM Sans',sans-serif;">Analytics</a>
    </div>
    <div><span class="live-dot"></span>Live</div>
    <div id="last-update">—</div>
  </div>
</div>

<!-- Realtime ticker -->
<div class="ticker">
  <div style="display:flex;align-items:baseline;gap:12px;">
    <div class="price-big" id="rt-price">—</div>
    <div>
      <div class="price-chg" id="rt-chg">—</div>
      <div style="font-size:10px;color:var(--muted);margin-top:2px;">24h change</div>
    </div>
  </div>
  <div style="display:flex;gap:24px;flex-wrap:wrap;">
    <div class="meta-item">24H High<span id="rt-high">—</span></div>
    <div class="meta-item">24H Low<span id="rt-low">—</span></div>
    <div class="meta-item">Volume<span id="rt-vol">—</span></div>
  </div>
  <div class="rt-badge">● Realtime</div>
</div>

<div class="grid-top">
  <!-- Dual horizon prediction -->
  <div class="card" style="grid-column:span 2">
    <div class="card-label">Prediction</div>
    <div class="horizon-grid" id="horizon-cards">
      <div class="h-card"><div class="h-label">8H Horizon</div><div class="h-pct" style="color:var(--muted)">—</div><div class="h-signal" style="color:var(--muted)">loading</div></div>
      <div class="h-card"><div class="h-label">24H Horizon</div><div class="h-pct" style="color:var(--muted)">—</div><div class="h-signal" style="color:var(--muted)">loading</div></div>
    </div>
    <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border);display:flex;align-items:center;gap:12px;">
      <span style="font-size:11px;color:var(--muted);">Market Regime:</span>
      <div class="regime-pill" id="regime-pill" style="color:var(--muted);">—</div>
      <span style="margin-left:auto;font-size:11px;color:var(--muted);">Signal threshold: ±1.5%</span>
    </div>
  </div>

  <!-- Model info -->
  <div class="card">
    <div class="card-label">Model Detail</div>
    <div class="model-row"><span style="color:var(--muted)">Architecture</span><span>XGBoost + LSTM + HMM</span></div>
    <div class="model-row"><span style="color:var(--muted)">Type</span><span>Regression</span></div>
    <div class="model-row"><span style="color:var(--muted)">Horizons</span><span>8h & 24h</span></div>
    <div class="model-row"><span style="color:var(--muted)">Signal threshold</span><span>±1.5%</span></div>
    <div class="model-row"><span style="color:var(--muted)">Retrain</span><span>Every Sunday</span></div>
    <div class="model-row" id="xgb-weights"><span style="color:var(--muted)">XGB weight</span><span>—</span></div>
    <div class="model-row" id="lstm-weights"><span style="color:var(--muted)">LSTM weight</span><span>—</span></div>
  </div>
</div>

<div class="grid-bot">
  <!-- History -->
  <div class="card">
    <div class="card-label">Prediction History</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Time</th><th>Horizon</th><th>Signal</th><th>Predicted</th><th>Regime</th></tr></thead>
        <tbody id="hist-body"><tr><td colspan="5" class="loading-row">Loading...</td></tr></tbody>
      </table>
    </div>
  </div>

  <!-- Chart -->
  <div class="card">
    <div class="card-label">BTC Price — Interactive</div>
    <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;">
      <button class="ctrl-btn active" onclick="setRange(24,this)">24H</button>
      <button class="ctrl-btn" onclick="setRange(48,this)">48H</button>
      <button class="ctrl-btn" onclick="setRange(96,this)">4D</button>
      <button class="ctrl-btn" onclick="setRange(168,this)">7D</button>
      <button class="ctrl-btn reset-btn" onclick="resetZoom()">↺ Reset</button>
    </div>
    <canvas id="btc-chart"></canvas>
    <div style="font-size:10px;color:var(--muted);margin-top:8px;text-align:center;">Scroll to zoom · drag to pan</div>
  </div>
</div>

<script>
const RCOL={"Bearish/Volatile":"var(--down)","Sideways":"var(--gold)","Bullish/Trending":"var(--up)"};
const TAG={"up":"tag-up","down":"tag-down","side":"tag-side"};
let chart,allData=[],activeRange=24,lastPrice=0;

async function fetchLivePrice(){
  const d=await fetch("/api/price/live").then(r=>r.json()).catch(()=>({}));
  if(!d||d.error)return;
  const el=document.getElementById("rt-price");
  const price=d.price;
  if(lastPrice&&price!==lastPrice){
    el.classList.remove("flash-up","flash-down");
    void el.offsetWidth;
    el.classList.add(price>lastPrice?"flash-up":"flash-down");
    setTimeout(()=>el.classList.remove("flash-up","flash-down"),600);
  }
  lastPrice=price;
  el.textContent="$"+price.toLocaleString("en-US",{minimumFractionDigits:1,maximumFractionDigits:1});
  const chg=d.change_pct;
  const ce=document.getElementById("rt-chg");
  ce.textContent=(chg>=0?"+":"")+chg.toFixed(2)+"%";
  ce.className="price-chg "+(chg>=0?"pos":"neg");
  document.getElementById("rt-high").textContent="$"+parseFloat(d.high_24h).toLocaleString("en-US",{maximumFractionDigits:0});
  document.getElementById("rt-low").textContent="$"+parseFloat(d.low_24h).toLocaleString("en-US",{maximumFractionDigits:0});
  const vol=parseFloat(d.volume_24h);
  document.getElementById("rt-vol").textContent=vol>1000?(vol/1000).toFixed(1)+"K BTC":vol.toFixed(0)+" BTC";
}

async function fetchLatest(){
  const d=await fetch("/api/latest").then(r=>r.json()).catch(()=>({}));
  if(!d||d.error)return;
  const cards=document.getElementById("horizon-cards");
  let regime="—", xgb_w="—", lstm_w="—", lastTs="";
  cards.innerHTML=["8","24"].map(h=>{
    const r=d[h];
    if(!r)return`<div class="h-card"><div class="h-label">${h}H Horizon</div><div class="h-pct" style="color:var(--muted)">—</div><div class="h-signal" style="color:var(--muted)">no data</div></div>`;
    const pct=parseFloat(r.predicted_pct||0);
    const col=r.direction==="up"?"var(--up)":r.direction==="down"?"var(--down)":"var(--gold)";
    regime=r.regime||regime;
    xgb_w=r.xgb_pred!==undefined?parseFloat(r.xgb_pred).toFixed(3)+"%":xgb_w;
    lstm_w=r.lstm_pred!==undefined?parseFloat(r.lstm_pred).toFixed(3)+"%":lstm_w;
    lastTs=r.created_at||lastTs;
    return`<div class="h-card">
      <div class="h-label">${h}H Horizon</div>
      <div class="h-pct" style="color:${col}">${pct>=0?"+":""}${pct.toFixed(2)}%</div>
      <div class="h-signal" style="color:${col}">${r.signal||"—"}</div>
      <div style="font-size:10px;color:var(--muted);margin-top:4px;">XGB: ${parseFloat(r.xgb_pred||0).toFixed(2)}% · LSTM: ${parseFloat(r.lstm_pred||0).toFixed(2)}%</div>
    </div>`;
  }).join("");
  const rp=document.getElementById("regime-pill");
  rp.textContent=regime;rp.style.color=RCOL[regime]||"var(--muted)";
  if(lastTs)document.getElementById("last-update").textContent="Updated "+new Date(lastTs).toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit"});
}

async function fetchHistory(){
  const data=await fetch("/api/history").then(r=>r.json()).catch(()=>[]);
  if(!Array.isArray(data))return;
  const tb=document.getElementById("hist-body");
  tb.innerHTML=data.length?data.map(d=>{
    const pct=parseFloat(d.predicted_pct||0);
    const col=d.direction==="up"?"var(--up)":d.direction==="down"?"var(--down)":"var(--gold)";
    return`<tr>
      <td style="color:var(--muted)">${new Date(d.created_at).toLocaleString("en-GB",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"})}</td>
      <td><span class="tag tag-8h">${d.horizon_h}H</span></td>
      <td><span class="tag ${TAG[d.direction]||''}">${d.signal}</span></td>
      <td style="color:${col};font-weight:500;">${pct>=0?"+":""}${pct.toFixed(2)}%</td>
      <td style="color:var(--muted);font-size:11px;">${d.regime||"—"}</td>
    </tr>`;
  }).join(""):`<tr><td colspan="5" class="loading-row">No predictions yet — runs at :05 UTC each hour</td></tr>`;
}

async function fetchChart(){
  const data=await fetch("/api/price").then(r=>r.json()).catch(()=>[]);
  if(!Array.isArray(data)||!data.length)return;
  allData=data;
  drawChart(data.slice(-activeRange));
}

function setRange(n,btn){
  activeRange=n;
  document.querySelectorAll(".ctrl-btn:not(.reset-btn)").forEach(b=>b.classList.remove("active"));
  btn.classList.add("active");
  if(allData.length)drawChart(allData.slice(-n));
}
function resetZoom(){if(chart)chart.resetZoom();}

function drawChart(data){
  const labels=data.map(d=>new Date(d.open_time).toLocaleString("en-GB",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}));
  const prices=data.map(d=>parseFloat(d.close));
  if(chart)chart.destroy();
  const ctx=document.getElementById("btc-chart").getContext("2d");
  const grad=ctx.createLinearGradient(0,0,0,280);
  grad.addColorStop(0,"rgba(196,120,138,0.2)");
  grad.addColorStop(1,"rgba(196,120,138,0)");
  chart=new Chart(ctx,{
    type:"line",
    data:{labels,datasets:[{data:prices,borderColor:"#c4788a",borderWidth:2,backgroundColor:grad,fill:true,tension:0.4,pointRadius:0,pointHoverRadius:5,pointHoverBackgroundColor:"#c4788a",pointHoverBorderColor:"#fff",pointHoverBorderWidth:2}]},
    options:{responsive:true,interaction:{mode:"index",intersect:false},
      plugins:{legend:{display:false},
        tooltip:{backgroundColor:"#2d2420",titleColor:"#9e8f87",bodyColor:"#fdf8f5",padding:12,cornerRadius:10,callbacks:{label:c=>"$"+c.parsed.y.toLocaleString("en-US",{minimumFractionDigits:1})}},
        zoom:{pan:{enabled:true,mode:"x"},zoom:{wheel:{enabled:true},pinch:{enabled:true},mode:"x"}}},
      scales:{
        x:{grid:{color:"rgba(237,232,227,0.5)"},ticks:{color:"#9e8f87",font:{family:"DM Sans",size:10},maxTicksLimit:8,maxRotation:0},border:{display:false}},
        y:{position:"right",grid:{color:"rgba(237,232,227,0.5)"},ticks:{color:"#9e8f87",font:{family:"DM Sans",size:10},callback:v=>"$"+v.toLocaleString("en-US",{maximumFractionDigits:0})},border:{display:false}}
      }
    }
  });
}

fetchLivePrice();fetchLatest();fetchHistory();fetchChart();
setInterval(fetchLivePrice,5000);
setInterval(()=>{fetchLatest();fetchHistory();fetchChart();},60000);
</script>
</body>
</html>
"""

# ── Analytics HTML ──────────────────────────────────────────────────────────
ANALYTICS_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>axaphia / Analytics</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#fdf8f5;--surface:#fff;--border:#ede8e3;--text:#2d2420;--muted:#9e8f87;--rose:#c4788a;--blush:#e8a0b0;--gold:#c49a4e;--lavender:#9b8ec4;--up:#5a9e7a;--down:#c4788a;--side:#c49a4e;--shadow:0 2px 16px rgba(45,36,32,0.07);}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;font-weight:300;padding:28px 32px;}
.header{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:32px;padding-bottom:20px;border-bottom:1px solid var(--border);}
.logo{font-family:'DM Serif Display',serif;font-size:24px;letter-spacing:-0.5px;}
.logo em{font-style:italic;color:var(--rose);}
.logo .slash{color:var(--muted);margin:0 4px;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;}
.grid1{margin-bottom:20px;}
@media(max-width:900px){.grid2{grid-template-columns:1fr;}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:24px;box-shadow:var(--shadow);}
.card-label{font-size:10px;letter-spacing:2.5px;text-transform:uppercase;color:var(--muted);margin-bottom:20px;font-weight:500;}
.overall-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-bottom:20px;}
@media(max-width:700px){.overall-grid{grid-template-columns:1fr 1fr;}}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px;box-shadow:var(--shadow);text-align:center;}
.stat-num{font-family:'DM Serif Display',serif;font-size:40px;letter-spacing:-1px;line-height:1;margin-bottom:4px;}
.stat-lbl{font-size:11px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;}
.bar-row{margin-bottom:18px;}
.bar-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;}
.bar-name{font-size:13px;}
.bar-meta{font-size:11px;color:var(--muted);}
.bar-track{background:var(--border);border-radius:999px;height:10px;overflow:hidden;}
.bar-fill{height:100%;border-radius:999px;transition:width 1s cubic-bezier(.4,0,.2,1);}
.bar-acc{font-family:'DM Serif Display',serif;font-size:20px;margin-left:12px;min-width:52px;text-align:right;}
.fill-good{background:linear-gradient(90deg,var(--up),#8ec4a8);}
.fill-mid{background:linear-gradient(90deg,var(--gold),#dbb96a);}
.fill-bad{background:linear-gradient(90deg,var(--down),var(--blush));}
.insight{background:linear-gradient(135deg,#fff8f9,#f9f5ff);border:1px solid #ede0ea;border-radius:16px;padding:20px;margin-bottom:20px;}
.insight-title{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--rose);margin-bottom:12px;font-weight:500;}
.insight-item{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px;font-size:13px;line-height:1.6;}
.insight-item:last-child{margin-bottom:0;}
.dot{width:6px;height:6px;border-radius:50%;background:var(--rose);margin-top:7px;flex-shrink:0;}
.table-wrap{overflow-x:auto;}
table{width:100%;border-collapse:collapse;}
th{text-align:left;padding:0 10px 12px;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);font-weight:500;border-bottom:1px solid var(--border);}
td{padding:10px;font-size:12px;border-bottom:1px solid var(--bg);}
tr:last-child td{border-bottom:none;}
tr:hover td{background:#fdf8f5;}
.tag{display:inline-flex;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:500;}
.tag-up{background:rgba(90,158,122,0.12);color:var(--up);}
.tag-down{background:rgba(196,120,138,0.12);color:var(--down);}
.tag-side{background:rgba(196,154,78,0.12);color:var(--gold);}
.loading{text-align:center;padding:60px;color:var(--muted);font-size:13px;}
.pos{color:var(--up);}.neg{color:var(--down);}
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="logo">axaphia<span class="slash">/</span><em>machine learning</em> analyst</div>
    <div style="font-size:11px;color:var(--muted);margin-top:6px;letter-spacing:1px">Performance Analytics · BTCUSDT</div>
  </div>
  <div style="display:flex;gap:8px;">
    <a href="/" style="padding:6px 16px;border-radius:999px;font-size:12px;text-decoration:none;color:var(--muted);border:1px solid var(--border);font-family:'DM Sans',sans-serif;">Dashboard</a>
    <a href="/analytics" style="padding:6px 16px;border-radius:999px;font-size:12px;text-decoration:none;background:var(--rose);border:1px solid var(--rose);color:white;font-family:'DM Sans',sans-serif;">Analytics</a>
  </div>
</div>

<div id="main-content"><div class="loading">Loading analytics...</div></div>

<script>
function colorFor(acc){return acc>=60?"var(--up)":acc>=40?"var(--gold)":"var(--down)";}
function fillFor(name){
  if(["Naik",">2%","Bullish/Trending"].includes(name))return"fill-good";
  if(["Sideways","1.5–2%"].includes(name))return"fill-mid";
  return"fill-bad";
}
function barRows(items,nameKey,extra=""){
  return items.map(d=>`
    <div class="bar-row">
      <div class="bar-head">
        <span class="bar-name">${d[nameKey]}</span>
        <div style="display:flex;align-items:center;gap:12px">
          <span class="bar-meta">${d.correct}/${d.total} correct${extra&&d.mae?" · MAE:"+d.mae+"%":""}</span>
          <span class="bar-acc" style="color:${colorFor(d.accuracy)}">${d.accuracy}%</span>
        </div>
      </div>
      <div class="bar-track"><div class="bar-fill ${fillFor(d[nameKey])}" style="width:${d.accuracy}%"></div></div>
    </div>`).join("");
}

function generateInsights(d){
  const ins=[];
  const bestSig=[...d.by_signal].sort((a,b)=>b.accuracy-a.accuracy)[0];
  if(bestSig)ins.push(`Model paling akurat saat prediksi <strong>${bestSig.label}</strong> — ${bestSig.accuracy}% benar dari ${bestSig.total} prediksi.`);
  const bigMag=d.by_magnitude.find(x=>x.range===">2%");
  if(bigMag&&bigMag.total>3)ins.push(`Sinyal kuat (>2%) akurasinya ${bigMag.accuracy}% dari ${bigMag.total} kasus — ${bigMag.accuracy>=50?"lebih reliable dari sinyal kecil.":"masih perlu lebih banyak data untuk dinilai."}`);
  const bestR=[...d.by_regime].sort((a,b)=>b.accuracy-a.accuracy)[0];
  if(bestR)ins.push(`Performa terbaik di regime <strong>${bestR.regime}</strong> (${bestR.accuracy}%). Prioritaskan sinyal saat regime ini aktif.`);
  const h8=d.by_horizon.find(x=>x.horizon==="8h");
  const h24=d.by_horizon.find(x=>x.horizon==="24h");
  if(h8&&h24)ins.push(`8h horizon akurasi ${h8.accuracy}% (MAE ${h8.mae}%) vs 24h ${h24.accuracy}% (MAE ${h24.mae}%). ${h8.accuracy>h24.accuracy?"8h lebih reliable untuk saat ini.":"24h lebih reliable untuk saat ini."}`);
  if(d.overall<40)ins.push(`Akurasi overall ${d.overall}% masih berkembang. Akan membaik setelah data dan retraining mingguan bertambah.`);
  return ins.map(i=>`<div class="insight-item"><div class="dot"></div><div>${i}</div></div>`).join("");
}

async function load(){
  const d=await fetch("/api/analytics").then(r=>r.json()).catch(()=>({}));
  const el=document.getElementById("main-content");
  if(!d||d.error||d.total===0){
    el.innerHTML=`<div class="loading">${d.error||"Belum ada data yang cukup."}<br><br><span style="font-size:11px">Prediksi dievaluasi setelah horizon berlalu. Coba lagi nanti.</span></div>`;
    return;
  }

  const h8=d.by_horizon.find(x=>x.horizon==="8h");
  const h24=d.by_horizon.find(x=>x.horizon==="24h");

  el.innerHTML=`
    <div class="overall-grid">
      <div class="stat-card"><div class="stat-num" style="color:var(--lavender)">${d.overall}%</div><div class="stat-lbl">Overall Accuracy</div></div>
      <div class="stat-card"><div class="stat-num">${d.total}</div><div class="stat-lbl">Evaluated</div></div>
      <div class="stat-card"><div class="stat-num" style="color:var(--up)">${h8?h8.accuracy+"%" : "—"}</div><div class="stat-lbl">8H Accuracy</div></div>
      <div class="stat-card"><div class="stat-num" style="color:var(--rose)">${h24?h24.accuracy+"%" : "—"}</div><div class="stat-lbl">24H Accuracy</div></div>
    </div>

    <div class="insight"><div class="insight-title">Key Insights</div>${generateInsights(d)}</div>

    <div class="grid2">
      <div class="card">
        <div class="card-label">Accuracy by Horizon</div>
        ${barRows(d.by_horizon,"horizon","mae")}
        <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border)">
          <div class="card-label">Accuracy by Signal</div>
          ${barRows(d.by_signal,"label")}
        </div>
      </div>
      <div class="card">
        <div class="card-label">Accuracy by Prediction Magnitude</div>
        ${barRows(d.by_magnitude,"range")}
        <div style="margin-top:16px;padding-top:16px;border-top:1px solid var(--border)">
          <div class="card-label">Accuracy by Market Regime</div>
          ${barRows(d.by_regime,"regime")}
        </div>
      </div>
    </div>

    <div class="card grid1">
      <div class="card-label">Rolling Accuracy Trend (10-prediction window)</div>
      <canvas id="trend-chart" height="70"></canvas>
    </div>

    <div class="card grid1">
      <div class="card-label">Recent Predictions</div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Time</th><th>H</th><th>Predicted</th><th>Actual</th><th>Signal</th><th>✓</th><th>Regime</th></tr></thead>
          <tbody>${d.recent.map(r=>{
            const pp=parseFloat(r.predicted_pct||0);
            const ap=parseFloat(r.actual_pct||0);
            const tc=r.pred_signal==="Naik"?"tag-up":r.pred_signal==="Turun"?"tag-down":"tag-side";
            return`<tr>
              <td style="color:var(--muted)">${new Date(r.created_at).toLocaleString("en-GB",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"})}</td>
              <td style="color:var(--lavender);font-size:11px">${r.horizon}H</td>
              <td class="${pp>=0?"pos":"neg"}">${pp>=0?"+":""}${pp.toFixed(2)}%</td>
              <td class="${ap>=0?"pos":"neg"}">${ap>=0?"+":""}${ap.toFixed(2)}%</td>
              <td><span class="tag ${tc}">${r.pred_signal}</span></td>
              <td>${r.correct?"✓":"✗"}</td>
              <td style="color:var(--muted);font-size:11px">${r.regime||"—"}</td>
            </tr>`;
          }).join("")}</tbody>
        </table>
      </div>
    </div>
  `;

  if(d.trend&&d.trend.length>1){
    const ctx=document.getElementById("trend-chart").getContext("2d");
    const grad=ctx.createLinearGradient(0,0,0,140);
    grad.addColorStop(0,"rgba(155,142,196,0.2)");
    grad.addColorStop(1,"rgba(155,142,196,0)");
    new Chart(ctx,{
      type:"line",
      data:{labels:d.trend.map((_,i)=>i+1),datasets:[
        {data:d.trend.map(t=>t.y),borderColor:"#9b8ec4",borderWidth:2,backgroundColor:grad,fill:true,tension:0.4,pointRadius:0,pointHoverRadius:4},
        {data:Array(d.trend.length).fill(33.3),borderColor:"rgba(196,120,138,0.4)",borderWidth:1,borderDash:[4,4],fill:false,pointRadius:0}
      ]},
      options:{responsive:true,plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>c.parsed.y.toFixed(1)+"%"}}},
        scales:{x:{display:false},y:{min:0,max:100,grid:{color:"rgba(237,232,227,0.5)"},ticks:{color:"#9e8f87",callback:v=>v+"%"},border:{display:false}}}}
    });
  }
}
load();
</script>
</body>
</html>
"""

def run_dashboard(port=8080):
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
