
import os
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import requests

API_KEY = os.getenv("CMM_API_KEY", "").strip()
if not API_KEY:
    raise RuntimeError("CMM_API_KEY is not set in Render.")

API_BASE = "https://ht-api.coinmarketman.com/api/external"
HL_INFO = "https://api.hyperliquid.xyz/info"
BUILDER = "0x9b451f8941240db8bedc99bff8917a2ed9550074"

COMPETITION_START = datetime(2026, 10, 2, tzinfo=timezone.utc)
COMPETITION_END = datetime(2026, 10, 9, tzinfo=timezone.utc)
PORT = int(os.getenv("PORT", "10000"))
REFRESH_SECONDS = 300
DB_FILE = "origami_competition.db"

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
    "0xec3c5055f1d402e41c9974fb8291265e087baa9c",
    "0xbe017f5edc123d52572be3743e3e136fccd4c484",
]

USERNAMES = {
    "0x28d6dda751db999b991ed169bb773e8e855c36c2": "@shamim215",
    "0x6188c0c04bd502541b77d8cd43667944437b3eda": "@puperet",
    "0xfff111cdc96472c137596a91d001fd870557501c": "@BARYSBYEK",
    "0xfcb4dbcb3dbe57f02f4a5fa603a1da948f549673": "@himel234",
    "0xbf787b37c4db340088b154e3c343f4d94508ac8c": "@tomtop",
    "0x097e0a249c065e279ec08ea021cff3dd11c32d41": "@abshamweb3",
    "0xb29b8367e3a07928d5aa788bd9137d8c416e65ae": "@madikpeju",
    "0x28a97f53f11becbb1d531ed26a953cba87d115c8": "@Edward6742",
    "0x7f2663fc903d269a9670ce5ad76d92f7a0b70e66": "@Safal818",
    "0x8a591916b925c399a4d2791d186dfae5366cc12a": "@Eleonore3663",
}

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}
session = requests.Session()
session.headers.update(HEADERS)

def utc_iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

def parse_iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def db_connect():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily (
            day TEXT NOT NULL,
            wallet TEXT NOT NULL,
            volume REAL NOT NULL DEFAULT 0,
            realized REAL NOT NULL DEFAULT 0,
            fees REAL NOT NULL DEFAULT 0,
            funding REAL NOT NULL DEFAULT 0,
            unrealized REAL NOT NULL DEFAULT 0,
            pnl REAL NOT NULL DEFAULT 0,
            updated TEXT,
            PRIMARY KEY(day, wallet)
        )
    """)
    conn.commit()
    return conn


def api_get(path, params, timeout=60):
    response = session.get(API_BASE + path, params=params, timeout=timeout)
    if response.status_code == 429:
        raise RuntimeError("HyperTracker API rate limit reached.")
    response.raise_for_status()
    return response.json()

def normalize_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("fills", "results", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return []

def fetch_builder_fills(start, end):
    # HyperTracker fills supports multiple address parameters and max 24h windows.
    # 24 wallets are therefore fetched in 3 CMM requests: 10 + 10 + 4.
    results=[]
    if end <= start:
        return results
    for offset in range(0,len(WALLETS),10):
        batch=WALLETS[offset:offset+10]
        params=[("start",utc_iso(start)),("end",utc_iso(end)),
                ("fillType","perp"),("limit","500")]
        for wallet in batch:
            params.append(("address",wallet))
        cursor=None
        while True:
            q=list(params)
            if cursor:
                q.append(("nextCursor",cursor))
            data=api_get(f"/builders/{BUILDER}/fills",q)
            fills=normalize_list(data)
            results.extend(fills)
            cursor=data.get("nextCursor") if isinstance(data,dict) else None
            if not cursor or not fills:
                break
    return results

def fetch_hl_funding(wallet,start,end):
    body={"type":"userFunding","user":wallet,
          "startTime":int(start.timestamp()*1000),
          "endTime":int(end.timestamp()*1000)}
    r=requests.post(HL_INFO,json=body,timeout=30)
    r.raise_for_status()
    data=r.json()
    total=0.0
    for item in data if isinstance(data,list) else []:
        try:
            total += float(item.get("delta",{}).get("usdc",0) or 0)
        except Exception:
            pass
    return total

_price_cache={}
def historical_price_proxy(coin,cutoff):
    key=(coin,int(cutoff.timestamp())//60)
    if key in _price_cache:
        return _price_cache[key]
    ms=int(cutoff.timestamp()*1000)
    body={"type":"candleSnapshot","req":{"coin":coin,"interval":"1m",
          "startTime":ms-120000,"endTime":ms+60000}}
    r=requests.post(HL_INFO,json=body,timeout=30)
    r.raise_for_status()
    candles=r.json()
    if not candles:
        return None
    candles.sort(key=lambda x:abs(int(x["T"])-ms))
    value=float(candles[0]["c"])
    _price_cache[key]=value
    return value

def reconstruct_positions(fills,cutoff):
    positions={}
    for fill in sorted(fills,key=lambda x:int(x.get("time",0) or 0)):
        try:
            dt=datetime.fromtimestamp(int(fill["time"])/1000,tz=timezone.utc)
        except Exception:
            continue
        if dt>=cutoff:
            continue
        coin=fill.get("coin")
        if not coin: continue
        try:
            size=float(fill.get("sz",0) or 0); price=float(fill.get("px",0) or 0)
        except Exception:
            continue
        if size==0: continue
        d=str(fill.get("dir",""))
        if "Open Long" in d: signed=size
        elif "Close Long" in d: signed=-size
        elif "Open Short" in d: signed=-size
        elif "Close Short" in d: signed=size
        else: signed=size if fill.get("side")=="B" else -size

        p=positions.setdefault(coin,{"qty":0.0,"avg":0.0})
        old=p["qty"]; new=old+signed
        if old==0:
            p["qty"]=new; p["avg"]=price
        elif old*signed>0:
            p["avg"]=(abs(old)*p["avg"]+abs(signed)*price)/abs(new)
            p["qty"]=new
        else:
            p["qty"]=new
            if abs(new)<1e-12:
                p["qty"]=0.0; p["avg"]=0.0
            elif old*new<0:
                p["avg"]=price
    return positions

def calculate_unrealized(wallet_fills,cutoff):
    total=0.0
    for coin,p in reconstruct_positions(wallet_fills,cutoff).items():
        if abs(p["qty"])<1e-12: continue
        mark=historical_price_proxy(coin,cutoff)
        if mark is not None:
            total += (mark-p["avg"])*p["qty"]
    return total

def calculate_day(day_start,day_end,fills):
    by_wallet={w:[] for w in WALLETS}
    for fill in fills:
        address=str(fill.get("address") or fill.get("user") or "").lower()
        if address in by_wallet:
            by_wallet[address].append(fill)

    conn=db_connect()
    updated=utc_iso(datetime.now(timezone.utc))
    for wallet in WALLETS:
        wf=by_wallet[wallet]
        volume=sum(float(f.get("px",0) or 0)*float(f.get("sz",0) or 0) for f in wf)
        realized=sum(float(f.get("closedPnl",0) or 0) for f in wf)
        fees=sum(float(f.get("fee",0) or 0) for f in wf)
        funding=0.0
        if wf:
            try: funding=fetch_hl_funding(wallet,day_start,day_end)
            except Exception as e: print("Funding lookup failed:",wallet,repr(e))
        cutoff=min(day_end,datetime.now(timezone.utc))
        unrealized=0.0
        if wf:
            try: unrealized=calculate_unrealized(wf,cutoff)
            except Exception as e: print("Unrealized calculation failed:",wallet,repr(e))
        pnl=realized-fees+funding+unrealized
        conn.execute("""INSERT OR REPLACE INTO daily
            (day,wallet,volume,realized,fees,funding,unrealized,pnl,updated)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (day_start.date().isoformat(),wallet,volume,realized,fees,funding,unrealized,pnl,updated))
    conn.commit(); conn.close()

POINTS = [10, 8, 6, 4, 2]

def ranking_points(values, positive_only=False):
    ordered = sorted(values, key=lambda w: values[w], reverse=True)
    if positive_only:
        ordered = [w for w in ordered if values[w] > 0]
    result = {wallet: 0 for wallet in WALLETS}
    for i, wallet in enumerate(ordered[:5]):
        result[wallet] = POINTS[i]
    return result

def get_daily_data():
    conn = db_connect()
    rows = conn.execute(
        "SELECT day,wallet,volume,pnl FROM daily ORDER BY day,wallet"
    ).fetchall()
    conn.close()
    data = {}
    for day, wallet, volume, pnl in rows:
        data.setdefault(day, {})[wallet] = {
            "volume": volume or 0.0,
            "pnl": pnl or 0.0,
        }
    return data

def build_weekly():
    daily = get_daily_data()
    metrics = {
        wallet: {
            "volume": 0.0,
            "pnl": 0.0,
            "daily_volume_points": 0.0,
            "daily_pnl_points": 0.0,
            "days": 0,
        }
        for wallet in WALLETS
    }

    for day in sorted(daily):
        day_data = daily[day]
        volumes = {
            w: day_data.get(w, {}).get("volume", 0.0)
            for w in WALLETS
        }
        pnls = {
            w: day_data.get(w, {}).get("pnl", 0.0)
            for w in WALLETS
        }
        vp = ranking_points(volumes)
        pp = ranking_points(pnls, positive_only=True)

        for wallet in WALLETS:
            metrics[wallet]["volume"] += volumes[wallet]
            metrics[wallet]["pnl"] += pnls[wallet]
            metrics[wallet]["daily_volume_points"] += vp[wallet]
            metrics[wallet]["daily_pnl_points"] += pp[wallet]
            metrics[wallet]["days"] += 1

    weekly_volume_points = ranking_points(
        {w: metrics[w]["volume"] for w in WALLETS}
    )
    weekly_pnl_points = ranking_points(
        {w: metrics[w]["pnl"] for w in WALLETS},
        positive_only=True,
    )

    result = []
    for wallet in WALLETS:
        days = max(1, metrics[wallet]["days"])
        avg_vol = metrics[wallet]["daily_volume_points"] / days
        avg_pnl = metrics[wallet]["daily_pnl_points"] / days

        # PnL prize eligibility requires at least $20,000 volume
        # and positive weekly net PnL.
        pnl_eligible = (
            metrics[wallet]["volume"] >= 20000
            and metrics[wallet]["pnl"] > 0
        )

        result.append({
            "wallet": wallet,
            "username": USERNAMES.get(wallet, ""),
            "volume": metrics[wallet]["volume"],
            "pnl": metrics[wallet]["pnl"],
            "volume_final": 0.8 * avg_vol + 0.2 * weekly_volume_points[wallet],
            "pnl_final": (
                0.8 * avg_pnl + 0.2 * weekly_pnl_points[wallet]
                if pnl_eligible else 0.0
            ),
            "weekly_volume_points": weekly_volume_points[wallet],
            "weekly_pnl_points": weekly_pnl_points[wallet],
            "pnl_eligible": pnl_eligible,
        })
    return result


def build_daily(day, stream):
    daily=get_daily_data()
    source=daily.get(day,{})
    volumes={w:source.get(w,{}).get("volume",0.0) for w in WALLETS}
    pnls={w:source.get(w,{}).get("pnl",0.0) for w in WALLETS}
    if stream=="volume":
        points=ranking_points(volumes)
        rows=[{"wallet":w,"username":USERNAMES.get(w,""),
               "volume":volumes[w],"pnl":pnls[w],
               "daily_points":points[w],"weekly_points":0,
               "final_score":points[w]} for w in WALLETS]
        rows.sort(key=lambda x:x["volume"],reverse=True)
        return rows
    points=ranking_points(pnls,positive_only=True)
    rows=[{"wallet":w,"username":USERNAMES.get(w,""),
           "volume":volumes[w],"pnl":pnls[w],
           "daily_points":points[w],"weekly_points":0,
           "final_score":points[w]} for w in WALLETS]
    rows.sort(key=lambda x:x["pnl"],reverse=True)
    return rows

def refresh_worker():
    print("Origami competition worker running:",len(WALLETS),"wallets")
    last_current_fetch=None
    while True:
        try:
            now=datetime.now(timezone.utc)
            if now<COMPETITION_START:
                time.sleep(60); continue

            day=COMPETITION_START
            while day<min(now,COMPETITION_END):
                end=day+timedelta(days=1)
                conn=db_connect()
                existing=conn.execute("SELECT COUNT(*) FROM daily WHERE day=?",
                                      (day.date().isoformat(),)).fetchone()[0]
                conn.close()
                if existing==len(WALLETS):
                    day+=timedelta(days=1); continue

                query_end=min(end,now)
                print("FETCHING DAY",day.date(),"->",utc_iso(query_end),
                      "(3 CMM batches max)")
                fills=fetch_builder_fills(day,query_end)
                print("Builder fills received:",len(fills))
                calculate_day(day,end,fills)
                day+=timedelta(days=1)

            current=COMPETITION_START+timedelta(
                days=(now.date()-COMPETITION_START.date()).days)
            if (COMPETITION_START<=current<COMPETITION_END and
                (last_current_fetch is None or
                 (now-last_current_fetch).total_seconds()>=3600)):
                print("REFRESHING CURRENT DAY:",current.date())
                fills=fetch_builder_fills(current,now)
                print("Current-day builder fills received:",len(fills))
                calculate_day(current,current+timedelta(days=1),fills)
                last_current_fetch=now
        except Exception as e:
            print("REFRESH ERROR:",repr(e))
        time.sleep(60)

HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Origami Community Trading Competition 2026</title>
<style>
body{margin:0;background:#07090d;color:#f5f7fb;font-family:Inter,system-ui,sans-serif}
.wrap{max-width:1250px;margin:auto;padding:28px 18px 60px}
.hero{display:flex;justify-content:space-between;gap:20px;align-items:end}
h1{margin:0 0 8px;font-size:30px}.muted{color:#8993a5}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}
button{border:1px solid #222a36;background:#111720;color:#dce2eb;border-radius:10px;padding:10px 14px;cursor:pointer}
button.active{background:#f0f3f7;color:#080b10}
.card{background:#0e131b;border:1px solid #222a36;border-radius:16px;overflow:hidden}
.notice{margin:18px 0;padding:12px 14px;border:1px solid #222a36;border-radius:12px;color:#aab3c1;font-size:13px}
.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:1050px}
th,td{padding:13px 12px;border-bottom:1px solid #222a36;text-align:left}
th{font-size:12px;color:#8993a5;text-transform:uppercase}.right{text-align:right}
.pos{color:#39e29a}.neg{color:#ff657d}.wallet{font-size:11px;color:#697487;margin-top:3px}
.stream{font-weight:700;color:#f5f7fb;margin-bottom:6px}
</style>
</head>
<body>
<div class="wrap">
<div class="hero">
<div>
<h1>Origami Community Trading Competition</h1>
<div class="muted">2 Oct 2026 00:00 UTC → 9 Oct 2026 00:00 UTC · 24 wallets</div>
</div>
<div id="status" class="muted">Loading…</div>
</div>

<div class="notice">
<b>Volume:</b> every Origami-builder perp fill counts by executed notional
(price × size), including both opening and closing trades.
&nbsp;&nbsp;|&nbsp;&nbsp;
<b>PnL:</b> Origami-builder fills, fees, matched funding and historical
unrealized-PnL proxy are used.
<br><br>
Final score for each stream = 80% × average daily points + 20% × weekly points.
PnL qualification requires at least $20,000 weekly volume and positive weekly net PnL.
</div>

<div class="tabs" id="tabs"></div>

<div class="card"><div class="table-wrap"><table>
<thead><tr>
<th>Rank</th><th>Trader</th><th>Username</th>
<th class="right">Volume</th><th class="right">PnL</th>
<th class="right">Daily Pts</th><th class="right">Weekly Pts</th>
<th class="right">Final Score</th>
</tr></thead>
<tbody id="body"></tbody>
</table></div></div>
</div>

<script>
let mode="volume-weekly";

const tabs=[
["volume-weekly","🏆 Volume Weekly"],
["pnl-weekly","💰 PnL Weekly"],
["volume-day-2026-10-02","Oct 2 · Volume"],
["pnl-day-2026-10-02","Oct 2 · PnL"],
["volume-day-2026-10-03","Oct 3 · Volume"],
["pnl-day-2026-10-03","Oct 3 · PnL"],
["volume-day-2026-10-04","Oct 4 · Volume"],
["pnl-day-2026-10-04","Oct 4 · PnL"],
["volume-day-2026-10-05","Oct 5 · Volume"],
["pnl-day-2026-10-05","Oct 5 · PnL"],
["volume-day-2026-10-06","Oct 6 · Volume"],
["pnl-day-2026-10-06","Oct 6 · PnL"],
["volume-day-2026-10-07","Oct 7 · Volume"],
["pnl-day-2026-10-07","Oct 7 · PnL"],
["volume-day-2026-10-08","Oct 8 · Volume"],
["pnl-day-2026-10-08","Oct 8 · PnL"]
];

for(const [id,label] of tabs){
 const b=document.createElement("button");
 b.textContent=label;
 b.onclick=()=>{
   mode=id;
   document.querySelectorAll("#tabs button").forEach(x=>x.classList.remove("active"));
   b.classList.add("active");
   load();
 };
 if(id===mode)b.className="active";
 document.getElementById("tabs").appendChild(b);
}

function money(x){
 return Number(x||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
}
function short(x){return x.slice(0,6)+"…"+x.slice(-4)}
function esc(x){
 return String(x||"").replaceAll("&","&amp;").replaceAll("<","&lt;")
   .replaceAll(">","&gt;").replaceAll('"',"&quot;");
}

async function load(){
 try{
  const r=await fetch("/data?mode="+encodeURIComponent(mode)+"&x="+Date.now());
  const d=await r.json();

  document.getElementById("status").textContent=
    "Updated "+new Date().toLocaleTimeString();

  document.getElementById("body").innerHTML=d.rows.map((x,i)=>{
    const score = Number(x.final_score||0);
    const pnl = Number(x.pnl||0);
    const volume = Number(x.volume||0);

    return `
    <tr>
      <td><b>${i+1}</b></td>
      <td>
        <b>${esc(x.username||"Anonymous Trader")}</b>
        <div class="wallet">${short(x.wallet)}</div>
      </td>
      <td>${esc(x.username||"—")}</td>
      <td class="right">$${money(volume)}</td>
      <td class="right ${pnl>=0?"pos":"neg"}">
        ${pnl>=0?"+":"-"}$${money(Math.abs(pnl))}
      </td>
      <td class="right">${x.daily_points??0}</td>
      <td class="right">${x.weekly_points??0}</td>
      <td class="right"><b>${money(score)}</b></td>
    </tr>`;
  }).join("");

 }catch(e){
  document.getElementById("body").innerHTML=
    "<tr><td colspan='8'>"+esc(e.message)+"</td></tr>";
 }
}

load();
setInterval(load,60000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            payload = HTML.encode("utf-8")
            content_type = "text/html; charset=utf-8"

        elif path == "/data":
            mode = parse_qs(urlparse(self.path).query).get("mode", ["weekly"])[0]


            if mode in ("volume-weekly", "pnl-weekly"):
                weekly=build_weekly()
                rows=[]
                for row in weekly:
                    if mode=="volume-weekly":
                        rows.append({"wallet":row["wallet"],"username":row["username"],
                                     "volume":row["volume"],"pnl":row["pnl"],
                                     "daily_points":row["daily_volume_points"],
                                     "weekly_points":row["weekly_volume_points"],
                                     "final_score":row["volume_final"]})
                    else:
                        rows.append({"wallet":row["wallet"],"username":row["username"],
                                     "volume":row["volume"],"pnl":row["pnl"],
                                     "daily_points":row["daily_pnl_points"],
                                     "weekly_points":row["weekly_pnl_points"],
                                     "final_score":row["pnl_final"]})
                rows.sort(key=lambda x:x["final_score"],reverse=True)

            elif mode.startswith("volume-day-"):
                rows=build_daily(mode[len("volume-day-"):],"volume")
            elif mode.startswith("pnl-day-"):
                rows=build_daily(mode[len("pnl-day-"):],"pnl")
            else:
                rows=[]

            payload = json.dumps({"rows": rows}).encode("utf-8")
            content_type = "application/json"

        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return

if __name__ == "__main__":
    db_connect().close()

    threading.Thread(
        target=refresh_worker,
        daemon=True,
    ).start()

    print("Origami competition leaderboard running on", PORT)
    print("Wallet count:", len(WALLETS))
    print("Builder:", BUILDER)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
