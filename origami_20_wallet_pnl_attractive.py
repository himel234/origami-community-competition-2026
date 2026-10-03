
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

# ============================================================
# SIMPLE ORIGAMI COMPETITION LEADERBOARD
# ============================================================
# Source: CoinMarketMan HyperTracker public Origami builder data
# Builder: 0x9b451f8941240db8bedc99bff8917a2ed9550074
#
# Daily tabs:
#   - use CMM 24h data for the CURRENT competition day
#   - save that 24h data at each 00:00 UTC cutoff
#
# Weekly:
#   - use CMM 7d data directly
#
# This is intentionally kept simple, like the previous leaderboard.
# ============================================================

DATA_URL = (
    "https://dw3ji7n7thadj.cloudfront.net/aggregator/builders/"
    "0x9b451f8941240db8bedc99bff8917a2ed9550074_v2.json"
)

START = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)

REFRESH_SECONDS = 30
DB_FILE = "origami_competition.sqlite3"

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
    "0xBe017F5EDc123D52572BE3743e3E136FcCd4C484",
]

USERNAMES = {
    WALLETS[0]: "@shamim215",
    WALLETS[1]: "@puperet",
    WALLETS[2]: "",
    WALLETS[3]: "@BARYSBYEK",
    WALLETS[4]: "",
    WALLETS[5]: "@himel234",
    WALLETS[6]: "",
    WALLETS[7]: "@tomtop",
    WALLETS[8]: "",
    WALLETS[9]: "",
    WALLETS[10]: "@abshamweb3",
    WALLETS[11]: "",
    WALLETS[12]: "@madikpeju",
    WALLETS[13]: "",
    WALLETS[14]: "@Edward6742",
    WALLETS[15]: "",
    WALLETS[16]: "",
    WALLETS[17]: "",
    WALLETS[18]: "",
    WALLETS[19]: "",
    WALLETS[20]: "@Safal818",
    WALLETS[21]: "@Eleonore3663",
    WALLETS[22]: "",
    WALLETS[23]: "",
}

session = requests.Session()
session.headers.update({
    "User-Agent": "Origami-Community-Competition/1.0",
    "Accept": "application/json",
})

lock = threading.Lock()
cache = {"time": 0, "data": None}


def fetch():
    with lock:
        if cache["data"] is not None and time.time() - cache["time"] < 20:
            return cache["data"]

        last = None
        for attempt in range(4):
            try:
                r = session.get(DATA_URL, timeout=20)
                r.raise_for_status()
                data = r.json()
                cache["data"] = data
                cache["time"] = time.time()
                return data
            except Exception as e:
                last = e
                time.sleep(1 + attempt)

        raise RuntimeError(str(last))


def find_timeframe(data, timeframe):
    """
    Handles the CMM JSON structures used by the previous leaderboard.
    """
    users = data.get("users") if isinstance(data, dict) else None

    if isinstance(users, dict):
        x = users.get(timeframe)
        if x is not None:
            return x

    x = data.get(timeframe) if isinstance(data, dict) else None

    if isinstance(x, dict) and "users" in x:
        return x["users"]

    return x if x is not None else []


def wallet_map(data, timeframe):
    raw = find_timeframe(data, timeframe)
    result = {}

    if isinstance(raw, dict):
        for key, item in raw.items():
            if not isinstance(item, dict):
                continue

            address = key
            if not address.lower().startswith("0x"):
                address = item.get("address") or item.get("user") or ""

            if isinstance(address, str) and address.lower().startswith("0x"):
                result[address.lower()] = item

    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue

            address = (
                item.get("address")
                or item.get("user")
                or item.get("wallet", {}).get("address", "")
            )

            if isinstance(address, str) and address.lower().startswith("0x"):
                result[address.lower()] = item

    return result


def num(item, *keys):
    for key in keys:
        try:
            if item.get(key) is not None:
                return float(item[key])
        except Exception:
            pass
    return 0.0


def extract(data, timeframe):
    users = wallet_map(data, timeframe)
    result = {}

    for wallet in WALLETS:
        item = users.get(wallet.lower())

        if item is None:
            result[wallet] = {
                "volume": 0.0,
                "pnl": 0.0,
                "found": False,
            }
        else:
            result[wallet] = {
                "volume": num(item, "volume"),
                "pnl": num(item, "pnl"),
                "found": True,
            }

    return result


def init_db():
    con = sqlite3.connect(DB_FILE)
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily (
            day TEXT NOT NULL,
            wallet TEXT NOT NULL,
            volume REAL NOT NULL,
            pnl REAL NOT NULL,
            captured_at TEXT NOT NULL,
            PRIMARY KEY(day, wallet)
        )
    """)
    con.commit()
    con.close()


def save_day(day, rows):
    con = sqlite3.connect(DB_FILE)
    now = datetime.now(timezone.utc).isoformat()

    for wallet in WALLETS:
        x = rows[wallet]
        con.execute("""
            INSERT OR REPLACE INTO daily
            (day, wallet, volume, pnl, captured_at)
            VALUES (?, ?, ?, ?, ?)
        """, (day, wallet, x["volume"], x["pnl"], now))

    con.commit()
    con.close()


def read_day(day):
    con = sqlite3.connect(DB_FILE)
    rows = con.execute("""
        SELECT wallet, volume, pnl, captured_at
        FROM daily
        WHERE day=?
    """, (day,)).fetchall()
    con.close()

    return {
        wallet: {
            "volume": volume,
            "pnl": pnl,
            "captured_at": captured,
        }
        for wallet, volume, pnl, captured in rows
    }


def day_label(i):
    return (START + timedelta(days=i)).strftime("%Y-%m-%d")


def current_day_index(now):
    if now < START or now >= END:
        return None

    return (now.date() - START.date()).days


def snapshot_worker():
    """
    At every UTC cutoff:
      00:00 Oct 3 -> save Oct 2's last 24h snapshot
      00:00 Oct 4 -> save Oct 3's last 24h snapshot
      ...
    """
    while True:
        try:
            now = datetime.now(timezone.utc)

            for i in range(7):
                day_start = START + timedelta(days=i)
                day_end = day_start + timedelta(days=1)

                # Only snapshot shortly after the cutoff.
                if day_end <= now < day_end + timedelta(minutes=5):
                    day = day_start.strftime("%Y-%m-%d")

                    if len(read_day(day)) < len(WALLETS):
                        data = fetch()
                        rows = extract(data, "24h")
                        save_day(day, rows)
                        print("Saved daily snapshot:", day, flush=True)

        except Exception as e:
            print("Snapshot error:", repr(e), flush=True)

        time.sleep(15)


def display_daily(i, data):
    now = datetime.now(timezone.utc)
    day = START + timedelta(days=i)
    day_end = day + timedelta(days=1)

    saved = read_day(day.strftime("%Y-%m-%d"))

    # Current competition day:
    # show LIVE CMM 24h data.
    if day <= now < day_end:
        live = extract(data, "24h")
        return [{
            "wallet": w,
            "name": USERNAMES.get(w) or w[:6] + "..." + w[-4:],
            "volume": live[w]["volume"],
            "pnl": live[w]["pnl"],
            "status": "live 1d",
        } for w in WALLETS]

    # Completed day:
    # use the saved 24h snapshot.
    return [{
        "wallet": w,
        "name": USERNAMES.get(w) or w[:6] + "..." + w[-4:],
        "volume": saved[w]["volume"] if w in saved else None,
        "pnl": saved[w]["pnl"] if w in saved else None,
        "status": "captured" if w in saved else "waiting for cutoff",
    } for w in WALLETS]


def points(rows, field, positive=False):
    eligible = [
        r for r in rows
        if r[field] is not None and (not positive or r[field] > 0)
    ]

    eligible.sort(key=lambda r: r[field], reverse=True)

    result = {r["wallet"]: 0 for r in rows}

    for i, r in enumerate(eligible[:5]):
        result[r["wallet"]] = [10, 8, 6, 4, 2][i]

    return result


def build():
    now = datetime.now(timezone.utc)
    data = fetch()

    days = []
    for i in range(7):
        rows = display_daily(i, data)

        vp = points(rows, "volume")
        pp = points(rows, "pnl", True)

        for r in rows:
            r["volume_points"] = vp[r["wallet"]]
            r["pnl_points"] = pp[r["wallet"]]

        days.append(rows)

    # Weekly = CMM 7d directly.
    weekly_raw = extract(data, "7d")

    weekly = []
    for w in WALLETS:
        weekly.append({
            "wallet": w,
            "name": USERNAMES.get(w) or w[:6] + "..." + w[-4:],
            "volume": weekly_raw[w]["volume"],
            "pnl": weekly_raw[w]["pnl"],
            "status": "live 7d",
        })

    wvp = points(weekly, "volume")
    wpp = points(weekly, "pnl", True)

    final = []
    for w in WALLETS:
        dv = [days[i][WALLETS.index(w)]["volume_points"] for i in range(7)]
        dp = [days[i][WALLETS.index(w)]["pnl_points"] for i in range(7)]

        weekly_row = next(x for x in weekly if x["wallet"] == w)

        final.append({
            "wallet": w,
            "name": weekly_row["name"],
            "volume": weekly_row["volume"],
            "pnl": weekly_row["pnl"],
            "volume_week_points": wvp[w],
            "pnl_week_points": wpp[w],
            "volume_avg_daily": sum(dv) / 7,
            "pnl_avg_daily": sum(dp) / 7,
            "volume_final_score": 0.8 * (sum(dv) / 7) + 0.2 * wvp[w],
            "pnl_final_score": 0.8 * (sum(dp) / 7) + 0.2 * wpp[w],
            "pnl_qualified": (
                weekly_row["volume"] >= 20000
                and weekly_row["pnl"] > 0
            ),
        })

    return {
        "competition": {
            "start": START.isoformat(),
            "end": END.isoformat(),
            "now": now.isoformat(),
            "builder": "0x9b451f8941240db8bedc99bff8917a2ed9550074",
        },
        "days": days,
        "weekly": weekly,
        "final": final,
    }


HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Origami Community Trading Competition</title>
<style>
body{margin:0;background:#07090d;color:#f4f6f8;font-family:Arial,sans-serif}
.wrap{max-width:1500px;margin:auto;padding:28px 20px 60px}
h1{margin:0 0 8px;font-size:30px}
.sub{color:#9ba5b4;margin-bottom:20px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
button{background:#111722;color:#e3e8ef;border:1px solid #293345;border-radius:9px;padding:10px 14px;cursor:pointer}
button.active{background:#fff;color:#080a0d}
.card{background:#0d1118;border:1px solid #202938;border-radius:16px;padding:18px;margin-bottom:18px;overflow:auto}
table{width:100%;border-collapse:collapse;min-width:850px}
th,td{padding:12px 10px;border-bottom:1px solid #1d2531;text-align:right}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
th{font-size:12px;color:#8e9aaa;text-transform:uppercase}
.green{color:#62e39a}.red{color:#ff7788}.muted{color:#758092}
.badge{font-size:11px;background:#18202c;padding:5px 8px;border-radius:7px}
.note{font-size:13px;color:#909aaa;line-height:1.6}
</style>
</head>
<body>
<div class="wrap">
<h1>🏆 Origami Community Trading Competition</h1>
<div class="sub">2 Oct 2026 00:00 UTC → 9 Oct 2026 00:00 UTC · Origami builder-attributed data</div>
<div class="tabs" id="tabs"></div>
<div id="app"></div>
<div class="card note">
<b>Data source:</b> CoinMarketMan HyperTracker Origami builder.
Only wallets routed through the Origami builder are included.
<br>
<b>Daily:</b> CMM 1D / 24h data. The current day is live; completed days are saved at the UTC cutoff.
<br>
<b>Weekly:</b> CMM 7D data.
<br>
<b>Scoring:</b> Daily top 5 = 10 / 8 / 6 / 4 / 2. Final = 80% average daily points + 20% weekly points.
</div>
</div>

<script>
let DATA=null;
let tab="volume-week";

const tabs=[
["volume-week","📊 Volume — Weekly"],
["pnl-week","💰 PnL — Weekly"],
["volume-day-0","Volume — Oct 2"],
["volume-day-1","Volume — Oct 3"],
["volume-day-2","Volume — Oct 4"],
["volume-day-3","Volume — Oct 5"],
["volume-day-4","Volume — Oct 6"],
["volume-day-5","Volume — Oct 7"],
["volume-day-6","Volume — Oct 8"],
["pnl-day-0","PnL — Oct 2"],
["pnl-day-1","PnL — Oct 3"],
["pnl-day-2","PnL — Oct 4"],
["pnl-day-3","PnL — Oct 5"],
["pnl-day-4","PnL — Oct 6"],
["pnl-day-5","PnL — Oct 7"],
["pnl-day-6","PnL — Oct 8"]
];

function esc(x){
 return String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));
}
function money(x){
 if(x===null||x===undefined)return '<span class="muted">—</span>';
 return '$'+Number(x).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
}
function pnl(x){
 if(x===null||x===undefined)return '<span class="muted">—</span>';
 let n=Number(x);
 return '<span class="'+(n>=0?'green':'red')+'">'+(n>=0?'+':'')+money(n)+'</span>';
}
function renderTabs(){
 document.getElementById("tabs").innerHTML=tabs.map(t=>
 '<button class="'+(t[0]===tab?'active':'')+
 '" onclick="tab=\''+t[0]+'\';renderTabs();render()">'+t[1]+'</button>'
 ).join("");
}
function render(){
 let p=tab.split("-");
 let metric=p[0];
 let scope=p[1];
 let idx=p[2];

 let rows;

 if(scope==="week"){
   rows=DATA.final.map(r=>({
     ...r,
     value:r[metric],
     points:r[metric+"_week_points"],
     score:metric==="volume"?r.volume_final_score:r.pnl_final_score
   }));
   rows.sort((a,b)=>b.score-a.score);
 }else{
   rows=DATA.days[Number(idx)].map(r=>({
     ...r,
     value:r[metric],
     points:r[metric+"_points"]
   }));
   rows.sort((a,b)=>(b.value??-Infinity)-(a.value??-Infinity));
 }

 let title=metric==="volume"?"📊 Volume":"💰 PnL";

 let html='<div class="card"><h2>'+title+' · '+(scope==="week"?"Weekly":"Daily")+
 '</h2><table><thead><tr><th>#</th><th>Trader</th><th>'+title+
 '</th><th>Points</th>';

 if(scope==="week"){
   html+='<th>Avg Daily Points</th><th>Final Score</th><th>Status</th>';
 }else{
   html+='<th>Status</th>';
 }

 html+='</tr></thead><tbody>';

 rows.forEach((r,i)=>{
   html+='<tr>'+
   '<td><b>'+(i+1)+'</b></td>'+
   '<td><b>'+esc(r.name)+'</b><br><span class="muted">'+
   esc(r.wallet.slice(0,8)+'...'+r.wallet.slice(-6))+'</span></td>'+
   '<td>'+(metric==="volume"?money(r.value):pnl(r.value))+'</td>'+
   '<td><b>'+r.points+'</b></td>';

   if(scope==="week"){
     let avg=metric==="volume"?r.volume_avg_daily:r.pnl_avg_daily;
     html+='<td>'+Number(avg).toFixed(2)+'</td>'+
     '<td><b>'+Number(r.score).toFixed(2)+'</b></td>'+
     '<td><span class="badge">'+esc(r.status||"live 7d")+'</span></td>';
   }else{
     html+='<td><span class="badge">'+esc(r.status||"")+'</span></td>';
   }

   html+='</tr>';
 });

 html+='</tbody></table></div>';
 document.getElementById("app").innerHTML=html;
}

async function load(){
 try{
   const r=await fetch("/data?t="+Date.now(),{cache:"no-store"});
   DATA=await r.json();

   if(DATA.error){
     document.getElementById("app").innerHTML=
     '<div class="card">Data temporarily unavailable. Retrying…</div>';
     return;
   }

   renderTabs();
   render();
 }catch(e){
   document.getElementById("app").innerHTML=
   '<div class="card">Data temporarily unavailable. Retrying…</div>';
 }
}

load();
setInterval(load,30000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def send_text(self, status, text, content_type):
        raw=text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/data"):
            try:
                self.send_text(
                    200,
                    json.dumps(build(),separators=(",",":")),
                    "application/json; charset=utf-8"
                )
            except Exception as e:
                print("DATA ERROR:",repr(e),flush=True)
                self.send_text(
                    200,
                    json.dumps({"error":str(e)}),
                    "application/json; charset=utf-8"
                )
        else:
            self.send_text(200,HTML,"text/html; charset=utf-8")

    def log_message(self,fmt,*args):
        return


def main():
    init_db()

    threading.Thread(
        target=snapshot_worker,
        daemon=True
    ).start()

    port=int(os.environ.get("PORT","8765"))
    server=ThreadingHTTPServer(("0.0.0.0",port),Handler)

    print("Origami competition leaderboard running on",port,flush=True)
    server.serve_forever()


if __name__=="__main__":
    main()
