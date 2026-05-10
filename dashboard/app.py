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
