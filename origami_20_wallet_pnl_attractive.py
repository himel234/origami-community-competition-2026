import os, json, sqlite3, threading, time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
import requests

# ============================================================
# HYPERLIQUID COMMUNITY TRADING COMPETITION
# 2 Oct 2026 00:00 UTC -> 9 Oct 2026 00:00 UTC
# ============================================================

DATA_URL = "https://dw3ji7n7thadj.cloudfront.net/aggregator/builders/0x9b451f8941240db8bedc99bff8917a2ed9550074_v2.json"
START = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
END   = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)
REFRESH_SECONDS = 30
DB_FILE = "origami_competition.sqlite3"

WALLETS = ["0x28d6dda751db999b991ed169bb773e8e855c36c2", "0x6188c0c04bd502541b77d8cd43667944437b3eda", "0x6e5234204cd2015baf121b6934eab4d4f40a07ce", "0xfff111cdc96472c137596a91d001fd870557501c", "0x14280d8e1a1e490a3665563479e581280d32e441", "0xfcb4dbcb3dbe57f02f4a5fa603a1da948f549673", "0xbfbbb7a23d740648547f11797de7c157af81cac8", "0xbf787b37c4db340088b154e3c343f4d94508ac8c", "0x7e2df435ffaa20800713a1f1e770c1b093bacda5", "0xe254c53e776bb1b434f9d81bc93c246d08069bd6", "0x097e0a249c065e279ec08ea021cff3dd11c32d41", "0x8c641e56994b18b18d9bc754655c2892b80b3315", "0xb29b8367e3a07928d5aa788bd9137d8c416e65ae", "0x6f23925a69097b2ac7bf67e24b68cbb6382ca656", "0x28a97f53f11becbb1d531ed26a953cba87d115c8", "0x03a506eb9548fd844f60e65b35e56e5472f70c00", "0x4137bff4666989e877ade32e09ba8035cb0b1359", "0x88a30b45ca1fe48898675c6e4420b0090b0eba5e", "0x779c0a1345375b21839e4053419d9fdd6a432cce", "0x94aa8c596c405ac056e5caa2f08870c947a98e2a", "0x7f2663fc903d269a9670ce5ad76d92f7a0b70e66", "0x8a591916b925c399a4d2791d186dfae5366cc12a"]
USERNAMES = {"0x28d6dda751db999b991ed169bb773e8e855c36c2": "@shamim215", "0x6188c0c04bd502541b77d8cd43667944437b3eda": "@puperet", "0x6e5234204cd2015baf121b6934eab4d4f40a07ce": "", "0xfff111cdc96472c137596a91d001fd870557501c": "@BARYSBYEK", "0x14280d8e1a1e490a3665563479e581280d32e441": "", "0xfcb4dbcb3dbe57f02f4a5fa603a1da948f549673": "@himel234", "0xbfbbb7a23d740648547f11797de7c157af81cac8": "", "0xbf787b37c4db340088b154e3c343f4d94508ac8c": "@tomtop", "0x7e2df435ffaa20800713a1f1e770c1b093bacda5": "", "0xe254c53e776bb1b434f9d81bc93c246d08069bd6": "", "0x097e0a249c065e279ec08ea021cff3dd11c32d41": "@abshamweb3", "0x8c641e56994b18b18d9bc754655c2892b80b3315": "", "0xb29b8367e3a07928d5aa788bd9137d8c416e65ae": "@madikpeju", "0x6f23925a69097b2ac7bf67e24b68cbb6382ca656": "", "0x28a97f53f11becbb1d531ed26a953cba87d115c8": "@Edward6742", "0x03a506eb9548fd844f60e65b35e56e5472f70c00": "", "0x4137bff4666989e877ade32e09ba8035cb0b1359": "", "0x88a30b45ca1fe48898675c6e4420b0090b0eba5e": "", "0x779c0a1345375b21839e4053419d9fdd6a432cce": "", "0x94aa8c596c405ac056e5caa2f08870c947a98e2a": "", "0x7f2663fc903d269a9670ce5ad76d92f7a0b70e66": "@Safal818", "0x8a591916b925c399a4d2791d186dfae5366cc12a": "@Eleonore3663"}

POINTS = [10, 8, 6, 4, 2]

# ============================================================
# DATABASE
# ============================================================

def db():
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            day TEXT NOT NULL,
            wallet TEXT NOT NULL,
            volume REAL NOT NULL,
            pnl REAL NOT NULL,
            captured_at TEXT NOT NULL,
            locked INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(day, wallet)
        )
    """)
    # Upgrade databases made by the earlier version.
    cols = {r[1] for r in con.execute("PRAGMA table_info(daily_snapshots)").fetchall()}
    if "locked" not in cols:
        con.execute("ALTER TABLE daily_snapshots ADD COLUMN locked INTEGER NOT NULL DEFAULT 0")
    con.commit()
    return con

DB = db()

# ============================================================
# DATA HELPERS
# ============================================================

def find_users(data, tf="24h"):
    raw = None
    if isinstance(data, dict):
        if isinstance(data.get("users"), dict):
            raw = data["users"].get(tf) or data["users"].get(tf.lower())
        if raw is None and isinstance(data.get(tf), dict):
            raw = data[tf].get("users")
    if raw is None:
        def walk(x):
            if not isinstance(x, dict): return None
            for key in (tf, tf.lower()):
                if key in x and isinstance(x[key], (list, dict)): return x[key]
            for v in x.values():
                r = walk(v)
                if r is not None: return r
            return None
        raw = walk(data)
    return normalize_users(raw)

def normalize_users(raw):
    out = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict): continue
            a=item.get("address") or item.get("user") or item.get("wallet") or item.get("addr")
            if isinstance(a,str) and a.lower().startswith("0x"):
                out[a.lower()]=item
    elif isinstance(raw, dict):
        for k,v in raw.items():
            if isinstance(k,str) and k.lower().startswith("0x"):
                out[k.lower()] = v if isinstance(v,dict) else {}
            elif isinstance(v,dict):
                a=v.get("address") or v.get("user") or v.get("wallet") or v.get("addr")
                if isinstance(a,str) and a.lower().startswith("0x"):
                    out[a.lower()]=v
    return out

def num(obj, names):
    for n in names:
        if isinstance(obj,dict) and obj.get(n) is not None:
            try: return float(obj[n])
            except: pass
    return 0.0

def fetch_users(tf="24h"):
    r=requests.get(DATA_URL,timeout=30)
    r.raise_for_status()
    return find_users(r.json(),tf)

# ============================================================
# DAILY CAPTURE / LOCKING
#
# IMPORTANT: The active day's rolling 1D value is saved repeatedly
# DURING that day. At 00:00 UTC the previous day's last saved value
# is locked and can never be overwritten.
# ============================================================

def competition_day(now):
    if now < START or now >= END: return None
    return (now.date()-START.date()).days

def save_live_day(day_index, users):
    if not 0 <= day_index <= 6: return
    day=(START.date()+timedelta(days=day_index)).isoformat()
    captured=datetime.now(timezone.utc).isoformat()
    with DB:
        for w in WALLETS:
            u=users.get(w.lower(),{})
            DB.execute("""
                INSERT INTO daily_snapshots(day,wallet,volume,pnl,captured_at,locked)
                VALUES(?,?,?,?,?,0)
                ON CONFLICT(day,wallet) DO UPDATE SET
                    volume=excluded.volume,
                    pnl=excluded.pnl,
                    captured_at=excluded.captured_at
                WHERE daily_snapshots.locked=0
            """,(day,w.lower(),num(u,["volume"]),num(u,["pnl"]),captured))

def lock_finished_days():
    now=datetime.now(timezone.utc)
    with DB:
        for i in range(7):
            cutoff=START+timedelta(days=i+1)
            if now>=cutoff:
                day=(START.date()+timedelta(days=i)).isoformat()
                DB.execute("UPDATE daily_snapshots SET locked=1 WHERE day=?",(day,))

def daily_snapshot_status(day_index):
    day=(START.date()+timedelta(days=day_index)).isoformat()
    return DB.execute("SELECT COUNT(*),SUM(locked) FROM daily_snapshots WHERE day=?",(day,)).fetchone()

def snapshot_loop():
    while True:
        try:
            now=datetime.now(timezone.utc)
            i=competition_day(now)
            if i is not None:
                # Keep the active day's 1D value fresh.
                save_live_day(i,fetch_users("24h"))
            # Lock every completed day. This also handles a restart just after midnight
            # without replacing a snapshot that was captured before midnight.
            lock_finished_days()
        except Exception as e:
            print("snapshot error:",e,flush=True)
        time.sleep(30)

threading.Thread(target=snapshot_loop,daemon=True).start()

# ============================================================
# SCORING DATA
# ============================================================

def daily_rows():
    rows={}
    for i in range(7):
        day=(START.date()+timedelta(days=i)).isoformat()
        data=DB.execute("SELECT wallet,volume,pnl,captured_at,locked FROM daily_snapshots WHERE day=?",(day,)).fetchall()
        rows[day]={w:{"volume":None,"pnl":None,"captured_at":None,"locked":False} for w in WALLETS}
        for w,v,p,c,l in data:
            rows[day][w]={"volume":float(v),"pnl":float(p),"captured_at":c,"locked":bool(l)}
    return rows

# ============================================================
# SCORING
# ============================================================

def daily_rows():
    rows = {}
    for i in range(7):
        day = (START.date() + timedelta(days=i)).isoformat()
        data = DB.execute(
            "SELECT wallet, volume, pnl, captured_at FROM daily_snapshots WHERE day=?",
            (day,)
        ).fetchall()
        rows[day] = {
            w: {"volume": 0.0, "pnl": 0.0, "captured_at": None}
            for w in WALLETS
        }
        for w, volume, pnl, captured in data:
            rows[day][w] = {
                "volume": float(volume),
                "pnl": float(pnl),
                "captured_at": captured
            }
    return rows

def rank_points(values, positive_only=False):
    eligible = []
    for wallet, value in values.items():
        if positive_only and value <= 0:
            continue
        eligible.append((wallet, value))
    eligible.sort(key=lambda x: x[1], reverse=True)
    pts = {w: 0 for w in values}
    rank = 1
    for wallet, value in eligible[:5]:
        pts[wallet] = POINTS[rank-1]
        rank += 1
    return pts

def build_standings():
    days=daily_rows()
    result={w:{"wallet":w,"username":USERNAMES.get(w,""),"daily_volume_points":[],"daily_pnl_points":[],
               "volume":0.0,"pnl":0.0} for w in WALLETS}

    # Daily points come only from the locked/live 1D snapshots.
    for i in range(7):
        day=(START.date()+timedelta(days=i)).isoformat()
        vals_v={w:days[day][w]["volume"] for w in WALLETS}
        vals_p={w:days[day][w]["pnl"] for w in WALLETS}
        # Missing historical data is not treated as real zero activity.
        clean_v={w:(vals_v[w] if vals_v[w] is not None else 0.0) for w in WALLETS}
        clean_p={w:(vals_p[w] if vals_p[w] is not None else 0.0) for w in WALLETS}
        vp=rank_points(clean_v);pp=rank_points(clean_p,positive_only=True)
        for w in WALLETS:
            result[w]["daily_volume_points"].append(vp[w])
            result[w]["daily_pnl_points"].append(pp[w])

    # Weekly metrics come DIRECTLY from CMM 7D, as requested.
    weekly_users=fetch_users("7d")
    for w in WALLETS:
        u=weekly_users.get(w.lower(),{})
        result[w]["volume"]=num(u,["volume"])
        result[w]["pnl"]=num(u,["pnl"])

    weekly_volume_points=rank_points({w:result[w]["volume"] for w in WALLETS})
    weekly_pnl_points=rank_points({w:result[w]["pnl"] for w in WALLETS},positive_only=True)

    for w in WALLETS:
        dv=result[w]["daily_volume_points"];dp=result[w]["daily_pnl_points"]
        result[w]["volume_avg_daily"]=sum(dv)/7
        result[w]["pnl_avg_daily"]=sum(dp)/7
        result[w]["volume_weekly_points"]=weekly_volume_points[w]
        result[w]["pnl_weekly_points"]=weekly_pnl_points[w]
        result[w]["volume_final_score"]=.8*result[w]["volume_avg_daily"]+.2*weekly_volume_points[w]
        result[w]["pnl_final_score"]=.8*result[w]["pnl_avg_daily"]+.2*weekly_pnl_points[w]
        result[w]["pnl_qualified"]=result[w]["volume"]>=20000 and result[w]["pnl"]>0

    volume_rank=sorted(result.values(),key=lambda x:(-x["volume_final_score"],-x["volume"]))
    pnl_rank=sorted(result.values(),key=lambda x:(-(x["pnl_final_score"] if x["pnl_qualified"] else -1),-x["pnl"]))
    return days,volume_rank,pnl_rank

# ============================================================
# WEBSITE
# ============================================================


HTML = r'''<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Origami × Hyperliquid Community Competition</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#07090d;--panel:#0d1118;--panel2:#111722;--line:#202734;--text:#f4f7fb;--muted:#8993a5;--green:#36e29a;--red:#ff647c;--gold:#f5c76a;--blue:#70a7ff}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--text);background:radial-gradient(circle at 50% -10%,rgba(54,226,154,.12),transparent 35%),radial-gradient(circle at 90% 20%,rgba(91,116,255,.08),transparent 28%),var(--bg)}
.wrap{max-width:1320px;margin:auto;padding:26px 18px 55px}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:22px}
.brand{display:flex;align-items:center;gap:12px}.logo{width:42px;height:42px;border-radius:13px;display:grid;place-items:center;background:linear-gradient(135deg,#1be395,#0f8d62);color:#06100c;font-weight:900;font-size:21px}.brand h1{font-size:19px;margin:0}.brand p{margin:3px 0 0;color:var(--muted);font-size:11px}
.live{display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--line);border-radius:999px;background:rgba(13,17,24,.8);font-size:11px;color:#b8c1d0}.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 10px var(--green)}
.hero{border:1px solid var(--line);border-radius:22px;padding:25px;background:linear-gradient(145deg,rgba(18,24,34,.95),rgba(9,12,17,.96));box-shadow:0 18px 60px rgba(0,0,0,.28);margin-bottom:16px}
.kicker{font-size:11px;color:var(--green);font-weight:800;letter-spacing:1.5px;text-transform:uppercase}.hero h2{font-size:29px;margin:8px 0 5px;letter-spacing:-1px}.hero p{margin:0;color:var(--muted);font-size:13px}.dates{margin-top:17px;display:flex;gap:9px;flex-wrap:wrap}.date{border:1px solid var(--line);background:rgba(255,255,255,.025);border-radius:12px;padding:10px 12px;font-size:11px}.date b{display:block;font-size:13px}.date span{color:var(--muted)}
.stats{display:flex;gap:9px;flex-wrap:wrap;margin-top:18px}.stat{min-width:125px;padding:12px 14px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.02)}.stat b{display:block;font-size:17px}.stat span{display:block;color:var(--muted);font-size:10px;margin-top:3px;text-transform:uppercase;letter-spacing:.7px}
.streams{display:flex;gap:8px;margin:17px 0 12px}.stream{border:1px solid var(--line);background:var(--panel);color:var(--muted);padding:10px 18px;border-radius:11px;cursor:pointer;font-weight:850;font-size:12px}.stream.active{background:#eafcf5;color:#07110d}
.daytabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:15px}.day{border:1px solid var(--line);background:transparent;color:var(--muted);padding:8px 11px;border-radius:9px;cursor:pointer;font-weight:800;font-size:10px}.day.active{border-color:#354052;color:var(--text);background:#151b25}
.panel{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:rgba(13,17,24,.92)}.panelHead{padding:17px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px;align-items:center}.panelHead h3{margin:0;font-size:14px}.panelHead span{color:var(--muted);font-size:10px}
table{width:100%;border-collapse:collapse}th{background:#0a0e14;color:#687385;font-size:9px;letter-spacing:1px;text-transform:uppercase;font-weight:800}th,td{padding:13px 11px;border-bottom:1px solid #191f29;text-align:right}tr:last-child td{border-bottom:0}tbody tr:hover{background:rgba(255,255,255,.025)}th:first-child,td:first-child{text-align:center;width:55px}th:nth-child(2),td:nth-child(2){text-align:left}.rank{font-weight:900;color:#9da8b8}.rank.top{color:var(--gold)}.trader{display:flex;align-items:center;gap:9px}.avatar{width:31px;height:31px;border-radius:9px;display:grid;place-items:center;background:#161d28;border:1px solid #27303e;font-size:10px;font-weight:900}.name{font-weight:750;font-size:12px}.wallet{font:9px ui-monospace,SFMono-Regular,Menlo,monospace;color:#697487;margin-top:3px}.num{font-variant-numeric:tabular-nums;font-weight:700;font-size:11px}.score{font-size:13px;font-weight:900;color:var(--green)}.pnl{font-size:12px;font-weight:900}.pos{color:var(--green)}.neg{color:var(--red)}.qual{font-size:9px;font-weight:900;padding:4px 7px;border-radius:7px}.yes{background:rgba(54,226,154,.1);color:var(--green)}.no{background:rgba(255,100,124,.1);color:var(--red)}
.note{margin-top:12px;color:#697487;font-size:10px;line-height:1.6}.err{padding:16px;border:1px solid rgba(255,100,124,.25);background:rgba(255,100,124,.07);color:#ff9aaa;border-radius:13px}
.footer{display:flex;justify-content:space-between;color:#566172;font-size:10px;margin-top:14px;padding:0 3px}
@media(max-width:850px){.topbar{align-items:flex-start}.hero h2{font-size:24px}.panel{overflow-x:auto}table{min-width:980px}}
</style>
</head>
<body>
<div class="wrap">
<div class="topbar">
  <div class="brand"><div class="logo">O</div><div><h1>Origami × Hyperliquid</h1><p>Community Trading Competition</p></div></div>
  <div class="live"><span class="dot"></span> LIVE DATA</div>
</div>

<section class="hero">
  <div class="kicker">Competition</div>
  <h2>7-Day Community Trading Competition</h2>
  <p>Two independent streams · Volume & PnL · Final score based on daily + weekly points</p>
  <div class="dates">
    <div class="date"><b>02 Oct 2026 · 00:00 UTC</b><span>Start</span></div>
    <div class="date"><b>09 Oct 2026 · 00:00 UTC</b><span>Finish</span></div>
    <div class="date"><b>$1,500 USDC</b><span>Total prizes</span></div>
  </div>
  <div class="stats">
    <div class="stat"><b>22</b><span>Traders</span></div>
    <div class="stat"><b id="clock">—</b><span>UTC time</span></div>
    <div class="stat"><b id="daysDone">0 / 7</b><span>Days recorded</span></div>
  </div>
</section>

<div class="streams">
  <button class="stream active" id="volBtn" onclick="setStream('volume')">📊 VOLUME · 1,000 USDC</button>
  <button class="stream" id="pnlBtn" onclick="setStream('pnl')">💰 PnL · 500 USDC</button>
</div>

<div class="daytabs" id="days"></div>
<div id="out"></div>

<div class="footer"><span>Origami builder · 22 selected wallets</span><span>Auto-refresh: 30 seconds</span></div>
</div>

<script>
const START=new Date("2026-10-02T00:00:00Z"), END=new Date("2026-10-09T00:00:00Z");
let STREAM="volume", DAY="overall", STATE=null;

const money=x=>Number(x||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const safe=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const short=a=>a.slice(0,6)+"..."+a.slice(-4);
const avatar=(n,a)=>safe((n&&n!=="—"?n:a.slice(2,4)).slice(0,2).toUpperCase());

function setStream(s){STREAM=s;document.getElementById("volBtn").classList.toggle("active",s==="volume");document.getElementById("pnlBtn").classList.toggle("active",s==="pnl");render();}
function setDay(d){DAY=d;document.querySelectorAll(".day").forEach(x=>x.classList.toggle("active",x.dataset.day===d));render();}

function renderDays(){
  const el=document.getElementById("days");
  let h='<button class="day active" data-day="overall" onclick="setDay(\'overall\')">OVERALL</button>';
  for(let i=0;i<7;i++){
    const d=new Date(START.getTime()+i*86400000);
    const key=d.toISOString().slice(0,10);
    h+=`<button class="day" data-day="${key}" onclick="setDay('${key}')">DAY ${i+1}<br>${d.toLocaleDateString(undefined,{month:"short",day:"numeric",timeZone:"UTC"})}</button>`;
  }
  el.innerHTML=h;
}

function render(){
  if(!STATE)return;
  document.getElementById("clock").textContent=new Date().toISOString().slice(11,19);
  document.getElementById("daysDone").textContent=STATE.days_done+" / 7";

  c
