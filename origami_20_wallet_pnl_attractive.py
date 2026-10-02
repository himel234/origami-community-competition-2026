
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

API_BASE = "https://ht-api.coinmarketman.com/api/external"
API_KEY = os.environ.get("HYPERTRACKER_API_KEY", "").strip()

BUILDER = "0x9b451f8941240db8bedc99bff8917a2ed9550074"

START = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)

DB_FILE = "origami_exact_daily.sqlite3"
REFRESH_SECONDS = 300

WALLETS = [
    "0x28d6dda751db999b991ed169bb773e8e855c36c2",
    "0x6188c0c04bd502541b77d8cd43667944437b3eda",
    "0x6e5234204cd2015baf121b6934eab4d4f40a07ce",
    "0xfff111cdc96472c137596a91d001fd870557501c",
    "0x14280d8e1a1e490a3665563479e581280d32e441",
    "0xfcb4dbcb3dbe57f02f4a5fa603a1da948f549673",
    "0xbfbbb7a23d740648547f11797de7c157af81cac8",
    "0xbf787b37c4db340088b154e3c343f4d94508ac8c",
    "0x7e2df435ffaa20800713a1f1e770c1b093bacda5",
    "0xe254c53e776bb1b434f9d81bc93c246d08069bd6",
    "0x097e0a249c065e279ec08ea021cff3dd11c32d41",
    "0x8c641e56994b18b18d9bc754655c2892b80b3315",
    "0xb29b8367e3a07928d5aa788bd9137d8c416e65ae",
    "0x6f23925a69097b2ac7bf67e24b68cbb6382ca656",
    "0x28a97f53f11becbb1d531ed26a953cba87d115c8",
    "0x03a506eb9548fd844f60e65b35e56e5472f70c00",
    "0x4137bff4666989e877ade32e09ba8035cb0b1359",
    "0x88a30b45ca1fe48898675c6e4420b0090b0eba5e",
    "0x779c0a1345375b21839e4053419d9fdd6a432cce",
    "0x94aa8c596c405ac056e5caa2f08870c947a98e2a",
    "0x7f2663fc903d269a9670ce5ad76d92f7a0b70e66",
    "0x8a591916b925c399a4d2791d186dfae5366cc12a",
]

USERNAMES = {
    WALLETS[0]:"@shamim215", WALLETS[1]:"@puperet", WALLETS[2]:"",
    WALLETS[3]:"@BARYSBYEK", WALLETS[4]:"", WALLETS[5]:"@himel234",
    WALLETS[6]:"", WALLETS[7]:"@tomtop", WALLETS[8]:"", WALLETS[9]:"",
    WALLETS[10]:"@abshamweb3", WALLETS[11]:"", WALLETS[12]:"@madikpeju",
    WALLETS[13]:"", WALLETS[14]:"@Edward6742", WALLETS[15]:"",
    WALLETS[16]:"", WALLETS[17]:"", WALLETS[18]:"", WALLETS[19]:"",
    WALLETS[20]:"@Safal818", WALLETS[21]:"@Eleonore3663",
}

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "User-Agent": "Origami-Competition-Leaderboard/2.0",
})

DB_LOCK = threading.Lock()
CACHE = {"time": 0, "data": None}
CACHE_LOCK = threading.Lock()


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def init_db():
    with sqlite3.connect(DB_FILE) as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS daily (
            day TEXT NOT NULL,
            wallet TEXT NOT NULL,
            volume REAL NOT NULL,
            pnl REAL NOT NULL,
            fills INTEGER NOT NULL,
            captured_at TEXT NOT NULL,
            PRIMARY KEY(day,wallet)
        )
        """)
        c.commit()


def api_get(path, params):
    if not API_KEY:
        raise RuntimeError("HYPERTRACKER_API_KEY is missing in Render Environment.")

    for attempt in range(5):
        try:
            r = session.get(API_BASE + path, params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(2 + attempt * 2)
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == 4:
                raise
            time.sleep(1.5 * (attempt + 1))


def extract_items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("fills", "data", "items", "results"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def next_cursor(data):
    if isinstance(data, dict):
        return data.get("nextCursor") or data.get("next_cursor") or data.get("cursor")
    return None


def wallet_of(fill):
    for k in ("address", "user", "wallet", "userAddress"):
        v = fill.get(k)
        if isinstance(v, str) and v.lower().startswith("0x"):
            return v.lower()
    return ""


def fill_volume(fill):
    for key in ("volumeUsd", "volume_usd", "notional", "notionalUsd"):
        try:
            if fill.get(key) is not None:
                return abs(float(fill[key]))
        except Exception:
            pass

    try:
        return abs(float(fill.get("px", fill.get("price", 0))) *
                   float(fill.get("sz", fill.get("size", 0))))
    except Exception:
        return 0.0


def fill_pnl(fill):
    # HyperTracker/Hyperliquid fill payloads normally expose closedPnl.
    for key in ("closedPnl", "closed_pnl", "pnl", "realizedPnl", "realized_pnl"):
        try:
            if fill.get(key) is not None:
                return float(fill[key])
        except Exception:
            pass
    return 0.0


def get_builder_day(day_start):
    day_end = day_start + timedelta(days=1)
    totals = {w: {"volume": 0.0, "pnl": 0.0, "fills": 0} for w in WALLETS}
    cursor = None

    while True:
        params = {
            "start": iso(day_start),
            "end": iso(day_end - timedelta(milliseconds=1)),
            "limit": 500,
            "fillType": "perp",
        }
        if cursor:
            params["cursor"] = cursor

        data = api_get(f"/builders/{BUILDER}/fills", params)
        items = extract_items(data)

        for f in items:
            w = wallet_of(f)
            if w not in totals:
                continue
            totals[w]["volume"] += fill_volume(f)
            totals[w]["pnl"] += fill_pnl(f)
            totals[w]["fills"] += 1

        cursor = next_cursor(data)
        if not cursor or not items:
            break

    return totals


def save_day(day, totals):
    with DB_LOCK:
        with sqlite3.connect(DB_FILE) as c:
            captured = datetime.now(timezone.utc).isoformat()
            for w in WALLETS:
                x = totals[w]
                c.execute("""
                INSERT OR REPLACE INTO daily
                (day,wallet,volume,pnl,fills,captured_at)
                VALUES (?,?,?,?,?,?)
                """, (day, w, x["volume"], x["pnl"], x["fills"], captured))
            c.commit()


def has_day(day):
    with sqlite3.connect(DB_FILE) as c:
        n = c.execute("SELECT COUNT(*) FROM daily WHERE day=?", (day,)).fetchone()[0]
        return n == len(WALLETS)


def load_day(day):
    with sqlite3.connect(DB_FILE) as c:
        rows = c.execute("""
        SELECT wallet,volume,pnl,fills,captured_at
        FROM daily WHERE day=?
        """, (day,)).fetchall()
    return {
        r[0]: {"volume": r[1], "pnl": r[2], "fills": r[3], "captured_at": r[4]}
        for r in rows
    }


def snapshot_missing_days():
    now = datetime.now(timezone.utc)
    for i in range(7):
        ds = START + timedelta(days=i)
        de = ds + timedelta(days=1)
        day = ds.strftime("%Y-%m-%d")

        if now < de:
            continue
        if has_day(day):
            continue

        print("Fetching exact Origami builder fills:", day, flush=True)
        totals = get_builder_day(ds)
        save_day(day, totals)
        print("Saved:", day, flush=True)


def daily_points(rows, field, positive=False):
    candidates = [r for r in rows if r[field] is not None and (not positive or r[field] > 0)]
    candidates.sort(key=lambda r: r[field], reverse=True)
    pts = {w: 0 for w in WALLETS}
    for i, r in enumerate(candidates[:5]):
        pts[r["wallet"]] = [10,8,6,4,2][i]
    return pts


def build_payload():
    snapshot_missing_days()

    days = []
    for i in range(7):
        label = (START + timedelta(days=i)).strftime("%Y-%m-%d")
        saved = load_day(label)
        rows = []
        for w in WALLETS:
            x = saved.get(w)
            rows.append({
                "wallet": w,
                "name": USERNAMES.get(w) or w[:6]+"..."+w[-4:],
                "volume": None if x is None else x["volume"],
                "pnl": None if x is None else x["pnl"],
                "fills": 0 if x is None else x["fills"],
                "status": "captured" if x else "not available",
            })
        vp = daily_points(rows, "volume")
        pp = daily_points(rows, "pnl", True)
        for r in rows:
            r["volume_points"] = vp[r["wallet"]]
            r["pnl_points"] = pp[r["wallet"]]
        days.append(rows)

    weekly_totals = {}
    for w in WALLETS:
        wallet_days = [next(r for r in d if r["wallet"] == w) for d in days]
        weekly_totals[w] = {
            "volume": sum(r["volume"] or 0 for r in wallet_days),
            "pnl": sum(r["pnl"] or 0 for r in wallet_days),
            "volume_avg_daily": sum(r["volume_points"] for r in wallet_days) / 7,
            "pnl_avg_daily": sum(r["pnl_points"] for r in wallet_days) / 7,
        }

    v_sorted = sorted(
        weekly_totals.items(), key=lambda kv: kv[1]["volume"], reverse=True
    )
    p_sorted = sorted(
        [(w, x) for w, x in weekly_totals.items() if x["pnl"] > 0],
        key=lambda kv: kv[1]["pnl"], reverse=True
    )
    vpw = {w: [10,8,6,4,2][i] for i,(w,_) in enumerate(v_sorted[:5])}
    ppw = {w: [10,8,6,4,2][i] for i,(w,_) in enumerate(p_sorted[:5])}

    final = []
    for w in WALLETS:
        x = weekly_totals[w]
        vweek = x["volume"]
        pweek = x["pnl"]
        vavg = x["volume_avg_daily"]
        pavg = x["pnl_avg_daily"]

        final.append({
            "wallet": w,
            "name": USERNAMES.get(w) or w[:6]+"..."+w[-4:],
            "volume": vweek,
            "pnl": pweek,
            "volume_week_points": vpw.get(w,0),
            "pnl_week_points": ppw.get(w,0),
            "volume_avg_daily": vavg,
            "pnl_avg_daily": pavg,
            "volume_final_score": .8*vavg + .2*vpw.get(w,0),
            "pnl_final_score": .8*pavg + .2*ppw.get(w,0),
            "pnl_qualified": vweek >= 20000 and pweek > 0,
        })

    return {
        "competition": {
            "start": START.isoformat(),
            "end": END.isoformat(),
            "builder": BUILDER,
            "now": datetime.now(timezone.utc).isoformat(),
        },
        "days": days,
        "final": final,
    }


HTML = r"""
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Origami Community Trading Competition</title>
<style>
body{margin:0;background:#07090d;color:#f3f5f7;font-family:Arial,sans-serif}
.wrap{max-width:1450px;margin:auto;padding:28px 18px 60px}h1{margin:0 0 8px;font-size:30px}
.sub{color:#9da6b2;margin-bottom:18px}.tabs{display:flex;gap:7px;flex-wrap:wrap;margin:15px 0}
button{background:#121722;color:#dfe5ec;border:1px solid #293142;border-radius:9px;padding:9px 12px;cursor:pointer}
button.active{background:#fff;color:#080a0d}.card{background:#0d1118;border:1px solid #1f2633;border-radius:16px;padding:16px;margin-bottom:18px;overflow:auto}
table{width:100%;border-collapse:collapse;min-width:900px}th,td{padding:11px 9px;border-bottom:1px solid #1c2330;text-align:right;white-space:nowrap}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}th{color:#8f9aaa;font-size:11px;text-transform:uppercase}
.green{color:#6ee7a1}.red{color:#ff7b8a}.muted{color:#737d8d}.badge{padding:4px 7px;border-radius:7px;background:#18202d;color:#aeb8c6;font-size:11px}
.note{font-size:13px;color:#929dac;line-height:1.55}
</style></head><body><div class="wrap">
<h1>🏆 Origami Community Trading Competition</h1>
<div class="sub">2 Oct 2026 00:00 UTC → 9 Oct 2026 00:00 UTC · Origami builder-attributed data</div>
<div class="tabs" id="tabs"></div><div id="app"></div>
<div class="card note"><b>Data:</b> exact historical fills from HyperTracker's Origami builder endpoint. Only fills carrying the Origami builder code are counted. Volume is fill notional; PnL is the sum of fill-level closed/realized PnL supplied by HyperTracker.<br><br>
<b>Scoring:</b> daily top 5 = 10 / 8 / 6 / 4 / 2. Final score = 80% average daily points + 20% weekly points. PnL qualification requires ≥ $20,000 weekly volume and positive weekly PnL.</div>
</div><script>
let DATA=null,currentTab="volume-week";
const tabs=[["volume-week","Volume — Weekly"],["pnl-week","PnL — Weekly"],
["volume-day-0","Volume — Oct 2"],["volume-day-1","Volume — Oct 3"],["volume-day-2","Volume — Oct 4"],["volume-day-3","Volume — Oct 5"],["volume-day-4","Volume — Oct 6"],["volume-day-5","Volume — Oct 7"],["volume-day-6","Volume — Oct 8"],
["pnl-day-0","PnL — Oct 2"],["pnl-day-1","PnL — Oct 3"],["pnl-day-2","PnL — Oct 4"],["pnl-day-3","PnL — Oct 5"],["pnl-day-4","PnL — Oct 6"],["pnl-day-5","PnL — Oct 7"],["pnl-day-6","PnL — Oct 8"]];
function esc(x){return String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));}
function money(x){if(x===null||x===undefined)return '<span class="muted">—</span>';return '$'+Number(x).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});}
function pnl(x){if(x===null||x===undefined)return '<span class="muted">—</span>';let n=Number(x);return '<span class="'+(n>=0?'green':'red')+'">'+(n>=0?'+':'')+money(n)+'</span>';}
function render(){let p=currentTab.split("-"),metric=p[0],scope=p[1],idx=p[2],rows;
if(scope==="week"){rows=DATA.final.map(r=>({...r,value:r[metric],points:r[metric+"_week_points"],score:metric==="volume"?r.volume_final_score:r.pnl_final_score,status:r.pnl_qualified===false&&metric==="pnl"?"not qualified":"calculated"}));rows.sort((a,b)=>(b.score??-Infinity)-(a.score??-Infinity));}
else{rows=DATA.days[Number(idx)].map(r=>({...r,value:r[metric],points:r[metric+"_points"]}));rows.sort((a,b)=>(b.value??-Infinity)-(a.value??-Infinity));}
let html='<div class="card"><h2>'+(metric==="volume"?"📊 Volume":"💰 PnL")+' · '+(scope==="week"?"Weekly":"Daily")+'</h2><table><thead><tr><th>#</th><th>Trader</th><th>'+(metric==="volume"?"📊 Volume":"💰 PnL")+'</th><th>Points</th>';
if(scope==="week")html+='<th>Avg Daily Points</th><th>Final Score</th><th>Status</th>';else html+='<th>Fills</th><th>Status</th>';
html+='</tr></thead><tbody>';
rows.forEach((r,i)=>{html+='<tr><td><b>'+(i+1)+'</b></td><td><b>'+esc(r.name)+'</b><br><span class="muted">'+esc(r.wallet.slice(0,8)+"..."+r.wallet.slice(-6))+'</span></td><td>'+(metric==="volume"?money(r.value):pnl(r.value))+'</td><td><b>'+r.points+'</b></td>';
if(scope==="week")html+='<td>'+Number(metric==="volume"?r.volume_avg_daily:r.pnl_avg_daily).toFixed(2)+'</td><td><b>'+Number(r.score).toFixed(2)+'</b></td><td><span class="badge">'+esc(r.status)+'</span></td>';
else html+='<td>'+r.fills+'</td><td><span class="badge">'+esc(r.status)+'</span></td>';
html+='</tr>';});html+='</tbody></table></div>';document.getElementById("app").innerHTML=html;}
function renderTabs(){document.getElementById("tabs").innerHTML=tabs.map(t=>'<button class="'+(t[0]===currentTab?'active':'')+'" onclick="currentTab=\''+t[0]+'\';renderTabs();render()">'+t[1]+'</button>').join("");}
async function load(){try{let r=await fetch("/data?t="+Date.now(),{cache:"no-store"});DATA=await r.json();if(DATA.error)throw new Error(DATA.error+" "+(DATA.details||""));renderTabs();render();}catch(e){document.getElementById("app").innerHTML='<div class="card">Data temporarily unavailable. Retrying…<br><span class="muted">'+esc(e.message)+'</span></div>';}}
load();setInterval(load,300000);
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def send_text(self, status, text, typ):
        b=text.encode()
        self.send_response(status);self.send_header("Content-Type",typ)
        self.send_header("Content-Length",str(len(b)));self.send_header("Cache-Control","no-store")
        self.end_headers();self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/data"):
            try:
                now=time.time()
                with CACHE_LOCK:
                    if CACHE["data"] is None or now-CACHE["time"]>REFRESH_SECONDS:
                        CACHE["data"]=build_payload();CACHE["time"]=now
                    payload=CACHE["data"]
                self.send_text(200,json.dumps(payload,separators=(",",":")),"application/json; charset=utf-8")
            except Exception as e:
                print("DATA ERROR:",repr(e),flush=True)
                self.send_text(200,json.dumps({"error":"HyperTracker error","details":str(e)}),"application/json; charset=utf-8")
        else:
            self.send_text(200,HTML,"text/html; charset=utf-8")
    def log_message(self,*args): pass


def main():
    init_db()
    if not API_KEY:
        print("WARNING: HYPERTRACKER_API_KEY is missing.",flush=True)
    port=int(os.environ.get("PORT","8765"))
    print("Starting Origami exact historical leaderboard on",port,flush=True)
    print("Builder:",BUILDER,flush=True)
    ThreadingHTTPServer(("0.0.0.0",port),Handler).serve_forever()


if __name__=="__main__":
    main()
