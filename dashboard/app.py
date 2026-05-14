from flask import Flask, jsonify, render_template_string
from sqlalchemy import text
from database.connection import engine
from dashboard.live_price import get_live_price
from config import SYMBOL
import pandas as pd

app = Flask(__name__)

def query(sql):
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/latest")
def api_latest():
    try:
        df = query(f"SELECT * FROM predictions WHERE symbol='{SYMBOL}' ORDER BY created_at DESC LIMIT 1")
        return jsonify({} if df.empty else df.iloc[0].to_dict())
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/history")
def api_history():
    try:
        df = query(f"""SELECT ts,prediction,label,confidence,regime,
            prob_turun,prob_sideways,prob_naik,created_at
            FROM predictions WHERE symbol='{SYMBOL}'
            ORDER BY created_at DESC LIMIT 48""")
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/accuracy")
def api_accuracy():
    """
    Cek akurasi: prediksi dianggap benar kalau label prediksi
    cocok dengan label aktual di features table 4 jam setelah prediksi.
    """
    try:
        # Ambil semua prediksi
        preds = query(f"""
            SELECT id, created_at, label as predicted
            FROM predictions
            WHERE symbol='{SYMBOL}'
            ORDER BY created_at DESC LIMIT 200
        """)
        if preds.empty:
            return jsonify({"accuracy": None, "total": 0})

        # Ambil semua features
        feats = query(f"""
            SELECT ts, label as actual
            FROM features
            WHERE symbol='{SYMBOL}'
            ORDER BY ts ASC
        """)
        if feats.empty:
            return jsonify({"accuracy": None, "total": 0})

        feats["ts"] = pd.to_datetime(feats["ts"], utc=True)
        preds["created_at"] = pd.to_datetime(preds["created_at"], utc=True)

        correct = 0
        evaluated = 0

        for _, p in preds.iterrows():
            # Cari label aktual 4 jam setelah prediksi dibuat
            target_time = p["created_at"] + pd.Timedelta(hours=4)
            # Cari baris features yang paling dekat dengan target_time
            diff = (feats["ts"] - target_time).abs()
            closest_idx = diff.idxmin()
            if diff[closest_idx] > pd.Timedelta(hours=2):
                continue  # skip kalau terlalu jauh
            actual = feats.loc[closest_idx, "actual"]
            evaluated += 1
            if int(p["predicted"]) == int(actual):
                correct += 1

        if evaluated == 0:
            return jsonify({"accuracy": None, "total": 0,
                           "note": "Belum ada data aktual untuk dievaluasi"})

        return jsonify({
            "accuracy": round(correct / evaluated * 100, 1),
            "correct":  correct,
            "total":    evaluated,
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/price/live")
def api_price_live():
    return jsonify(get_live_price())

@app.route("/api/price")
def api_price():
    try:
        df = query(f"""SELECT open_time,open,high,low,close,volume
            FROM mark_price_kline WHERE symbol='{SYMBOL}'
            ORDER BY open_time DESC LIMIT 168""")
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms").astype(str)
        return jsonify(df.iloc[::-1].to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)})

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
:root {
  --bg:#fdf8f5;--surface:#ffffff;--border:#ede8e3;--text:#2d2420;--muted:#9e8f87;
  --rose:#c4788a;--blush:#e8a0b0;--sage:#7a9e8e;--gold:#c49a4e;--lavender:#9b8ec4;
  --up:#5a9e7a;--down:#c4788a;--side:#c49a4e;
  --shadow:0 2px 16px rgba(45,36,32,0.07);--shadow-lg:0 8px 40px rgba(45,36,32,0.12);
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;font-weight:300;min-height:100vh;padding:28px 32px;}
.header{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:28px;padding-bottom:24px;border-bottom:1px solid var(--border);}
.logo{font-family:'DM Serif Display',serif;font-size:26px;letter-spacing:-0.5px;color:var(--text);line-height:1;}
.logo em{font-style:italic;color:var(--rose);}
.logo .slash{color:var(--muted);font-weight:300;margin:0 4px;}
.header-right{display:flex;align-items:center;gap:16px;font-size:12px;color:var(--muted);}
.live-dot{width:7px;height:7px;background:var(--up);border-radius:50%;display:inline-block;margin-right:6px;box-shadow:0 0 6px var(--up);animation:breathe 2.5s ease-in-out infinite;}
@keyframes breathe{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.5;transform:scale(0.8)}}

.grid-top{display:grid;grid-template-columns:1.1fr 1fr 0.9fr;gap:20px;margin-bottom:20px;}
.grid-bot{display:grid;grid-template-columns:1fr 1.2fr;gap:20px;}
@media(max-width:900px){.grid-top,.grid-bot{grid-template-columns:1fr;}}

.card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:24px;box-shadow:var(--shadow);transition:box-shadow 0.3s;}
.card:hover{box-shadow:var(--shadow-lg);}
.card-label{font-size:10px;letter-spacing:2.5px;text-transform:uppercase;color:var(--muted);margin-bottom:16px;font-weight:500;}

.pred-card{background:linear-gradient(145deg,#fff8f9,#fff);border-color:#f0e0e4;text-align:center;}
.pred-symbol{font-family:'DM Serif Display',serif;font-size:56px;line-height:1;margin:8px 0 4px;transition:color 0.6s;}
.pred-label-text{font-size:12px;letter-spacing:3px;text-transform:uppercase;color:var(--muted);margin-bottom:20px;}
.conf-wrap{background:#f7f0f2;border-radius:999px;height:4px;margin:0 auto 10px;max-width:200px;overflow:hidden;}
.conf-fill{height:100%;border-radius:999px;background:var(--rose);transition:width 1.2s cubic-bezier(.4,0,.2,1);}
.conf-num{font-family:'DM Serif Display',serif;font-size:32px;color:var(--rose);}
.conf-sub{font-size:11px;color:var(--muted);margin-bottom:16px;}
.regime-pill{display:inline-block;padding:5px 14px;border-radius:999px;font-size:10px;letter-spacing:2px;text-transform:uppercase;border:1px solid currentColor;font-weight:500;}

/* Realtime ticker */
.price-ticker{background:linear-gradient(135deg,#fff8f9,#f9f5ff);border:1px solid #ede0ea;border-radius:16px;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;gap:24px;flex-wrap:wrap;}
.price-realtime{font-family:'DM Serif Display',serif;font-size:44px;letter-spacing:-1px;line-height:1;transition:color 0.3s;}
.price-chg-rt{font-size:13px;font-weight:500;}
.price-meta{display:flex;gap:24px;flex-wrap:wrap;}
.price-meta-item{font-size:11px;color:var(--muted);}
.price-meta-item span{display:block;color:var(--text);font-weight:500;font-size:13px;margin-top:2px;}
.realtime-badge{font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--up);border:1px solid var(--up);padding:3px 8px;border-radius:999px;animation:breathe 2s infinite;white-space:nowrap;}
.flash-up{color:var(--up)!important;}
.flash-down{color:var(--down)!important;}

.prob-item{margin-bottom:16px;}
.prob-head{display:flex;justify-content:space-between;font-size:11px;margin-bottom:6px;color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;}
.prob-head span:last-child{color:var(--text);font-weight:500;}
.prob-track{background:var(--border);border-radius:999px;height:6px;overflow:hidden;}
.prob-fill{height:100%;border-radius:999px;transition:width 1.2s cubic-bezier(.4,0,.2,1);}
.fill-up{background:linear-gradient(90deg,var(--up),#8ec4a8);}
.fill-down{background:linear-gradient(90deg,var(--down),var(--blush));}
.fill-side{background:linear-gradient(90deg,var(--gold),#dbb96a);}

.stat-big{font-family:'DM Serif Display',serif;font-size:44px;color:var(--lavender);line-height:1;margin:8px 0 4px;}
.stat-sub{font-size:12px;color:var(--muted);}
.model-info{margin-top:20px;padding-top:16px;border-top:1px solid var(--border);font-size:11px;color:var(--muted);line-height:2;}

.table-wrap{overflow-x:auto;}
table{width:100%;border-collapse:collapse;}
th{text-align:left;padding:0 12px 12px;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:var(--muted);font-weight:500;border-bottom:1px solid var(--border);}
td{padding:12px;font-size:13px;border-bottom:1px solid var(--bg);}
tr:last-child td{border-bottom:none;}
tr:hover td{background:#fdf8f5;}
.tag{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:500;}
.tag-up{background:rgba(90,158,122,0.12);color:var(--up);}
.tag-down{background:rgba(196,120,138,0.12);color:var(--down);}
.tag-side{background:rgba(196,154,78,0.12);color:var(--gold);}

.chart-card{padding:24px;}
.chart-controls{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;}
.ctrl-btn{padding:5px 14px;border-radius:999px;font-size:11px;font-family:'DM Sans',sans-serif;font-weight:500;border:1px solid var(--border);background:var(--surface);color:var(--muted);cursor:pointer;transition:all 0.2s;letter-spacing:1px;}
.ctrl-btn:hover,.ctrl-btn.active{background:var(--rose);border-color:var(--rose);color:white;}
.ctrl-btn.reset-btn{margin-left:auto;}
.ctrl-btn.reset-btn:hover{background:var(--lavender);border-color:var(--lavender);color:white;}
.loading-row{text-align:center;padding:32px;color:var(--muted);font-size:13px;}
.pos{color:var(--up);}.neg{color:var(--down);}

/* Accuracy note */
.acc-note{font-size:10px;color:var(--muted);margin-top:6px;font-style:italic;}
</style>
</head>
<body>

<div class="header">
  <div>
    <div class="logo">axaphia<span class="slash">/</span><em>machine learning</em> analyst</div>
    <div style="font-size:11px;color:var(--muted);margin-top:6px;letter-spacing:1px">BTCUSDT · 4-Hour Horizon · Ensemble Model</div>
  </div>
  <div class="header-right">
    <div style="display:flex;gap:8px;margin-right:16px;">
      <a href="/" style="padding:6px 16px;border-radius:999px;font-size:12px;text-decoration:none;background:var(--rose);border:1px solid var(--rose);color:white;font-family:DM Sans,sans-serif;">Dashboard</a>
      <a href="/analytics" style="padding:6px 16px;border-radius:999px;font-size:12px;text-decoration:none;color:var(--muted);border:1px solid var(--border);font-family:DM Sans,sans-serif;">Analytics</a>
    </div>
    <div><span class="live-dot"></span>Live</div>
    <div id="last-update">—</div>
  </div>
</div>

<!-- Realtime price ticker -->
<div class="price-ticker">
  <div style="display:flex;align-items:baseline;gap:12px;">
    <div class="price-realtime" id="rt-price">—</div>
    <div>
      <div class="price-chg-rt" id="rt-chg">—</div>
      <div style="font-size:10px;color:var(--muted);margin-top:2px;">24h change</div>
    </div>
  </div>
  <div class="price-meta">
    <div class="price-meta-item">24H High<span id="rt-high">—</span></div>
    <div class="price-meta-item">24H Low<span id="rt-low">—</span></div>
    <div class="price-meta-item">Volume (24H)<span id="rt-vol">—</span></div>
  </div>
  <div class="realtime-badge">● Realtime</div>
</div>

<div class="grid-top">

  <div class="card pred-card">
    <div class="card-label">4-Hour Prediction</div>
    <div class="pred-symbol" id="pred-symbol">—</div>
    <div class="pred-label-text" id="pred-text">waiting for data</div>
    <div class="conf-num" id="conf-num">—</div>
    <div class="conf-sub">confidence</div>
    <div class="conf-wrap"><div class="conf-fill" id="conf-fill" style="width:0%"></div></div>
    <div class="regime-pill" id="regime-pill" style="color:var(--muted);margin-top:12px">—</div>
  </div>

  <div class="card">
    <div class="card-label">Probability Breakdown</div>
    <div class="prob-item">
      <div class="prob-head"><span>↑ Naik</span><span id="pct-naik">0%</span></div>
      <div class="prob-track"><div class="prob-fill fill-up" id="p-naik" style="width:0%"></div></div>
    </div>
    <div class="prob-item">
      <div class="prob-head"><span>→ Sideways</span><span id="pct-side">0%</span></div>
      <div class="prob-track"><div class="prob-fill fill-side" id="p-side" style="width:0%"></div></div>
    </div>
    <div class="prob-item">
      <div class="prob-head"><span>↓ Turun</span><span id="pct-down">0%</span></div>
      <div class="prob-track"><div class="prob-fill fill-down" id="p-down" style="width:0%"></div></div>
    </div>
  </div>

  <div class="card">
    <div class="card-label">Live Accuracy</div>
    <div class="stat-big" id="acc-val">—</div>
    <div class="stat-sub" id="acc-sub">predictions evaluated</div>
    <div class="acc-note" id="acc-note"></div>
    <div class="model-info">
      XGBoost + LSTM + HMM<br>
      Regime-weighted ensemble<br>
      Threshold ±0.5% · 4h horizon<br>
      Retrain every Sunday
    </div>
  </div>

</div>

<div class="grid-bot">

  <div class="card">
    <div class="card-label">Prediction History</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Time</th><th>Signal</th><th>Confidence</th><th>Regime</th></tr></thead>
        <tbody id="hist-body"><tr><td colspan="4" class="loading-row">Loading...</td></tr></tbody>
      </table>
    </div>
  </div>

  <div class="card chart-card">
    <div class="card-label">BTC Price — Interactive</div>
    <div class="chart-controls">
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
const LABEL={0:"TURUN ↓",1:"SIDEWAYS →",2:"NAIK ↑"};
const TAG={0:"tag-down",1:"tag-side",2:"tag-up"};
const RCOL={"Bearish/Volatile":"var(--down)","Sideways":"var(--gold)","Bullish/Trending":"var(--up)"};
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
  ce.className="price-chg-rt "+(chg>=0?"pos":"neg");
  document.getElementById("rt-high").textContent="$"+parseFloat(d.high_24h).toLocaleString("en-US",{maximumFractionDigits:0});
  document.getElementById("rt-low").textContent="$"+parseFloat(d.low_24h).toLocaleString("en-US",{maximumFractionDigits:0});
  const vol=parseFloat(d.volume_24h);
  document.getElementById("rt-vol").textContent=vol>1000?(vol/1000).toFixed(1)+"K BTC":vol.toFixed(0)+" BTC";
}

async function fetchLatest(){
  const d=await fetch("/api/latest").then(r=>r.json()).catch(()=>({}));
  if(!d||d.error)return;
  const s=document.getElementById("pred-symbol");
  s.textContent=d.label===2?"↑":d.label===0?"↓":"→";
  s.style.color=d.label===2?"var(--up)":d.label===0?"var(--down)":"var(--gold)";
  document.getElementById("pred-text").textContent=LABEL[d.label]||"—";
  document.getElementById("conf-num").textContent=(d.confidence||0)+"%";
  document.getElementById("conf-fill").style.width=(d.confidence||0)+"%";
  const rp=document.getElementById("regime-pill");
  rp.textContent=d.regime||"—";
  rp.style.color=RCOL[d.regime]||"var(--muted)";
  document.getElementById("p-naik").style.width=(d.prob_naik||0)+"%";
  document.getElementById("p-side").style.width=(d.prob_sideways||0)+"%";
  document.getElementById("p-down").style.width=(d.prob_turun||0)+"%";
  document.getElementById("pct-naik").textContent=(d.prob_naik||0)+"%";
  document.getElementById("pct-side").textContent=(d.prob_sideways||0)+"%";
  document.getElementById("pct-down").textContent=(d.prob_turun||0)+"%";
  if(d.created_at)document.getElementById("last-update").textContent=
    "Prediction: "+new Date(d.created_at).toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit"});
}

async function fetchHistory(){
  const data=await fetch("/api/history").then(r=>r.json()).catch(()=>[]);
  if(!Array.isArray(data))return;
  const tb=document.getElementById("hist-body");
  tb.innerHTML=data.length?data.map(d=>`<tr>
    <td style="color:var(--muted)">${new Date(d.created_at).toLocaleString("en-GB",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"})}</td>
    <td><span class="tag ${TAG[d.label]||''}">${LABEL[d.label]||d.prediction}</span></td>
    <td style="font-weight:500">${d.confidence}%</td>
    <td style="color:var(--muted);font-size:11px">${d.regime||"—"}</td>
  </tr>`).join(""):`<tr><td colspan="4" class="loading-row">No predictions yet — runs at :05 UTC each hour</td></tr>`;
}

async function fetchAccuracy(){
  const d=await fetch("/api/accuracy").then(r=>r.json()).catch(()=>({}));
  if(d.accuracy!=null){
    document.getElementById("acc-val").textContent=d.accuracy+"%";
    document.getElementById("acc-sub").textContent=`${d.correct} / ${d.total} correct`;
    document.getElementById("acc-note").textContent="Evaluated after 4h horizon";
  } else {
    document.getElementById("acc-val").textContent="—";
    document.getElementById("acc-sub").textContent="Not enough data yet";
    document.getElementById("acc-note").textContent=d.note||"Accuracy checked after 4h per prediction";
  }
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
    options:{
      responsive:true,
      interaction:{mode:"index",intersect:false},
      plugins:{
        legend:{display:false},
        tooltip:{backgroundColor:"#2d2420",titleColor:"#9e8f87",bodyColor:"#fdf8f5",padding:12,cornerRadius:10,callbacks:{label:c=>"$"+c.parsed.y.toLocaleString("en-US",{minimumFractionDigits:1})}},
        zoom:{pan:{enabled:true,mode:"x"},zoom:{wheel:{enabled:true},pinch:{enabled:true},mode:"x"}}
      },
      scales:{
        x:{grid:{color:"rgba(237,232,227,0.5)",drawBorder:false},ticks:{color:"#9e8f87",font:{family:"DM Sans",size:10},maxTicksLimit:8,maxRotation:0},border:{display:false}},
        y:{position:"right",grid:{color:"rgba(237,232,227,0.5)",drawBorder:false},ticks:{color:"#9e8f87",font:{family:"DM Sans",size:10},callback:v=>"$"+v.toLocaleString("en-US",{maximumFractionDigits:0})},border:{display:false}}
      }
    }
  });
}

fetchLivePrice();fetchLatest();fetchHistory();fetchAccuracy();fetchChart();
setInterval(fetchLivePrice,5000);
setInterval(()=>{fetchLatest();fetchHistory();fetchAccuracy();fetchChart();},60000);
</script>
</body>
</html>
"""

def run_dashboard(port=8080):
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ── Analytics ───────────────────────────────────────────────────────────────

@app.route("/analytics")
def analytics_page():
    return render_template_string(ANALYTICS_HTML)

@app.route("/api/analytics")
def api_analytics():
    from dashboard.analytics import get_analytics_data
    return jsonify(get_analytics_data())


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
:root{
  --bg:#fdf8f5;--surface:#fff;--border:#ede8e3;--text:#2d2420;--muted:#9e8f87;
  --rose:#c4788a;--blush:#e8a0b0;--sage:#7a9e8e;--gold:#c49a4e;--lavender:#9b8ec4;
  --up:#5a9e7a;--down:#c4788a;--side:#c49a4e;
  --shadow:0 2px 16px rgba(45,36,32,0.07);
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;font-weight:300;padding:28px 32px;}
.header{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:32px;padding-bottom:20px;border-bottom:1px solid var(--border);}
.logo{font-family:'DM Serif Display',serif;font-size:24px;letter-spacing:-0.5px;}
.logo em{font-style:italic;color:var(--rose);}
.logo .slash{color:var(--muted);margin:0 4px;}
.nav{display:flex;gap:8px;}
.nav a{padding:6px 16px;border-radius:999px;font-size:12px;text-decoration:none;color:var(--muted);border:1px solid var(--border);transition:all 0.2s;}
.nav a:hover,.nav a.active{background:var(--rose);border-color:var(--rose);color:white;}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-bottom:20px;}
.grid1{margin-bottom:20px;}
@media(max-width:900px){.grid2,.grid3{grid-template-columns:1fr;}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:24px;box-shadow:var(--shadow);}
.card-label{font-size:10px;letter-spacing:2.5px;text-transform:uppercase;color:var(--muted);margin-bottom:20px;font-weight:500;}

/* Overall stat */
.overall-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px;margin-bottom:20px;}
@media(max-width:700px){.overall-grid{grid-template-columns:1fr 1fr;}}
.stat-card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px;box-shadow:var(--shadow);text-align:center;}
.stat-num{font-family:'DM Serif Display',serif;font-size:40px;letter-spacing:-1px;line-height:1;margin-bottom:4px;}
.stat-lbl{font-size:11px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;}

/* Bar rows */
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
.fill-label-naik{background:linear-gradient(90deg,var(--up),#8ec4a8);}
.fill-label-side{background:linear-gradient(90deg,var(--gold),#dbb96a);}
.fill-label-down{background:linear-gradient(90deg,var(--down),var(--blush));}

/* Insight box */
.insight{background:linear-gradient(135deg,#fff8f9,#f9f5ff);border:1px solid #ede0ea;border-radius:16px;padding:20px;margin-bottom:20px;}
.insight-title{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:var(--rose);margin-bottom:12px;font-weight:500;}
.insight-item{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px;font-size:13px;line-height:1.6;}
.insight-item:last-child{margin-bottom:0;}
.dot{width:6px;height:6px;border-radius:50%;background:var(--rose);margin-top:7px;flex-shrink:0;}

.loading{text-align:center;padding:60px;color:var(--muted);font-size:13px;}
</style>
</head>
<body>

<div class="header">
  <div>
    <div class="logo">axaphia<span class="slash">/</span><em>machine learning</em> analyst</div>
    <div style="font-size:11px;color:var(--muted);margin-top:6px;letter-spacing:1px">Performance Analytics · BTCUSDT</div>
  </div>
  <nav class="nav">
    <a href="/">Dashboard</a>
    <a href="/analytics" class="active">Analytics</a>
  </nav>
</div>

<div id="main-content">
  <div class="loading">Loading analytics...</div>
</div>

<script>
const COLORS = {
  "Naik": "var(--up)", "Sideways": "var(--gold)", "Turun": "var(--down)",
  ">70%": "var(--up)", "50–70%": "var(--gold)", "<50%": "var(--down)",
  "Bullish/Trending": "var(--up)", "Sideways": "var(--gold)", "Bearish/Volatile": "var(--down)",
};

function colorFor(acc) {
  return acc >= 60 ? "var(--up)" : acc >= 40 ? "var(--gold)" : "var(--down)";
}

function fillFor(name) {
  if (name==="Naik") return "fill-label-naik";
  if (name==="Turun") return "fill-label-down";
  if (name===">70%"||name==="Bullish/Trending") return "fill-good";
  if (name==="50–70%"||name==="Sideways") return "fill-mid";
  return "fill-bad";
}

function barRows(items, nameKey) {
  return items.map(d => `
    <div class="bar-row">
      <div class="bar-head">
        <span class="bar-name">${d[nameKey]}</span>
        <div style="display:flex;align-items:center;gap:16px">
          <span class="bar-meta">${d.correct}/${d.total} correct</span>
          <span class="bar-acc" style="color:${colorFor(d.accuracy)}">${d.accuracy}%</span>
        </div>
      </div>
      <div class="bar-track">
        <div class="bar-fill ${fillFor(d[nameKey])}" style="width:${d.accuracy}%"></div>
      </div>
    </div>
  `).join("");
}

function generateInsights(data) {
  const insights = [];

  // Best label
  const bestLabel = [...data.by_label].sort((a,b)=>b.accuracy-a.accuracy)[0];
  if (bestLabel) insights.push(`Model paling akurat saat prediksi <strong>${bestLabel.label}</strong> — ${bestLabel.accuracy}% benar dari ${bestLabel.total} prediksi.`);

  // Confidence insight
  const high = data.by_conf.find(d=>d.range===">70%");
  const low  = data.by_conf.find(d=>d.range==="<50%");
  if (high && low) {
    if (high.accuracy > low.accuracy + 15)
      insights.push(`Prediksi dengan confidence >70% jauh lebih reliable (${high.accuracy}%) dibanding <50% (${low.accuracy}%). Fokus pada sinyal confidence tinggi.`);
    else
      insights.push(`Confidence belum jadi pembeda yang kuat. Model masih perlu lebih banyak data untuk kalibrasi confidence.`);
  }

  // Regime insight
  const bestRegime = [...data.by_regime].sort((a,b)=>b.accuracy-a.accuracy)[0];
  if (bestRegime) insights.push(`Performa terbaik di regime <strong>${bestRegime.regime}</strong> (${bestRegime.accuracy}%). Pertimbangkan untuk hanya trade saat regime ini aktif.`);

  // Overall
  if (data.overall < 40)
    insights.push(`Akurasi overall ${data.overall}% masih di bawah target. Model butuh lebih banyak data training — akan membaik setelah weekly retraining.`);
  else if (data.overall >= 55)
    insights.push(`Akurasi overall ${data.overall}% sudah di atas baseline random (33%). Model mulai menunjukkan edge yang nyata.`);

  return insights.map(i=>`<div class="insight-item"><div class="dot"></div><div>${i}</div></div>`).join("");
}

async function load() {
  const d = await fetch("/api/analytics").then(r=>r.json()).catch(()=>({}));
  const el = document.getElementById("main-content");

  if (!d || d.error || d.total === 0) {
    el.innerHTML = `<div class="loading">${d.error || "Belum ada data yang cukup untuk dianalisis."}<br><br><span style="font-size:11px">Prediksi dievaluasi 4 jam setelah dibuat. Coba lagi nanti.</span></div>`;
    return;
  }

  el.innerHTML = `
    <!-- Overall stats -->
    <div class="overall-grid">
      <div class="stat-card">
        <div class="stat-num" style="color:var(--lavender)">${d.overall}%</div>
        <div class="stat-lbl">Overall Accuracy</div>
      </div>
      <div class="stat-card">
        <div class="stat-num" style="color:var(--text)">${d.total}</div>
        <div class="stat-lbl">Predictions Evaluated</div>
      </div>
      <div class="stat-card">
        <div class="stat-num" style="color:var(--up)">${d.by_label.find(x=>x.label==="Sideways")?.accuracy||"—"}%</div>
        <div class="stat-lbl">Sideways Accuracy</div>
      </div>
      <div class="stat-card">
        <div class="stat-num" style="color:var(--rose)">${d.by_conf.find(x=>x.range===">70%")?.accuracy||"—"}%</div>
        <div class="stat-lbl">High Conf. Accuracy</div>
      </div>
    </div>

    <!-- Insights -->
    <div class="insight">
      <div class="insight-title">Key Insights</div>
      ${generateInsights(d)}
    </div>

    <!-- By label + by confidence -->
    <div class="grid2">
      <div class="card">
        <div class="card-label">Accuracy by Prediction Label</div>
        ${barRows(d.by_label, "label")}
      </div>
      <div class="card">
        <div class="card-label">Accuracy by Confidence Range</div>
        ${barRows(d.by_conf, "range")}
      </div>
    </div>

    <!-- By regime + by hour -->
    <div class="grid2">
      <div class="card">
        <div class="card-label">Accuracy by Market Regime</div>
        ${barRows(d.by_regime, "regime")}
      </div>
      <div class="card">
        <div class="card-label">Accuracy by Hour (UTC)</div>
        ${d.by_hour.length ? barRows(d.by_hour.sort((a,b)=>b.accuracy-a.accuracy).slice(0,8), "label") : '<div style="color:var(--muted);font-size:13px">Not enough data yet</div>'}
      </div>
    </div>

    <!-- Trend chart -->
    <div class="card grid1">
      <div class="card-label">Rolling Accuracy Trend (10-prediction window)</div>
      <canvas id="trend-chart" height="80"></canvas>
    </div>
  `;

  // Draw trend chart
  if (d.trend && d.trend.length > 1) {
    const ctx = document.getElementById("trend-chart").getContext("2d");
    const grad = ctx.createLinearGradient(0,0,0,160);
    grad.addColorStop(0,"rgba(155,142,196,0.2)");
    grad.addColorStop(1,"rgba(155,142,196,0)");
    new Chart(ctx, {
      type: "line",
      data: {
        labels: d.trend.map((_,i)=>i+1),
        datasets: [{
          data: d.trend.map(t=>t.y),
          borderColor: "#9b8ec4",
          borderWidth: 2,
          backgroundColor: grad,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 4,
        }, {
          data: Array(d.trend.length).fill(33.3),
          borderColor: "rgba(196,120,138,0.4)",
          borderWidth: 1,
          borderDash: [4,4],
          fill: false,
          pointRadius: 0,
          label: "Random baseline (33%)",
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: c => c.parsed.y.toFixed(1)+"%" } }
        },
        scales: {
          x: { display: false },
          y: {
            min: 0, max: 100,
            grid: { color: "rgba(237,232,227,0.5)" },
            ticks: { color: "#9e8f87", callback: v=>v+"%" },
            border: { display: false }
          }
        }
      }
    });
  }
}

load();
</script>
</body>
</html>
"""
