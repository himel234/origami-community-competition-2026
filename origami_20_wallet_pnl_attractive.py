import json
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

# ============================================================
# Hyperliquid Community Trading Competition 2026
# Competition: 2026-10-02 00:00 UTC -> 2026-10-09 00:00 UTC
#
# Data source:
#   Hyperliquid public Info API
#
# Volume:
#   Exact executed fills inside each UTC competition day.
#
# PnL:
#   Hyperliquid portfolio "perpWeek" PnL history.
#   Daily PnL = PnL value at the end boundary - PnL value
#   at the start boundary.
#
# IMPORTANT:
# Hyperliquid portfolio graphs are sampled periodically. Therefore
# the PnL shown here is the Hyperliquid portfolio-graph metric, using
# the closest available samples to the UTC boundaries. It is NOT a
# fabricated rolling-24h value.
# ============================================================

API_URL = "https://api.hyperliquid.xyz/info"

START = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)

REFRESH_SECONDS = 60
REQUEST_TIMEOUT = 20

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
}

SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})

CACHE = {}
CACHE_LOCK = threading.Lock()


def api(payload):
    r = SESSION.post(API_URL, json=payload, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def now_utc():
    return datetime.now(timezone.utc)


def ms(dt):
    return int(dt.timestamp() * 1000)


def money(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def short_wallet(w):
    return w[:6] + "..." + w[-4:]


def username(wallet):
    return USERNAMES.get(wallet, "") or short_wallet(wallet)


def portfolio(wallet):
    key = ("portfolio", wallet)
    data = api({"type": "portfolio", "user": wallet})
    with CACHE_LOCK:
        CACHE[key] = data
    return data


def get_window(data, name):
    if isinstance(data, list):
        for item in data:
            if isinstance(item, list) and len(item) == 2 and item[0] == name:
                return item[1]
    return None


def get_perp_week_history(wallet):
    data = portfolio(wallet)
    obj = get_window(data, "perpWeek")
    if not obj:
        # Fallback if an account has no perpWeek data.
        obj = get_window(data, "week")
    if not obj:
        return []
    hist = obj.get("pnlHistory", [])
    out = []
    for item in hist:
        if not isinstance(item, list) or len(item) != 2:
            continue
        try:
            out.append((int(item[0]), float(item[1])))
        except Exception:
            pass
    return sorted(out)


def nearest_pnl(history, target_ms, max_distance_minutes=20):
    if not history:
        return None
    best = min(history, key=lambda x: abs(x[0] - target_ms))
    if abs(best[0] - target_ms) > max_distance_minutes * 60 * 1000:
        return None
    return best[1]


def exact_fills(wallet, start_dt, end_dt):
    """Fetch all fills in the requested period.

    Hyperliquid returns at most 2000 per response. We page backwards
    through the requested range using endTime.
    """
    start_ms = ms(start_dt)
    end_ms = ms(end_dt)

    all_fills = []
    cursor_end = end_ms
    seen = set()

    while cursor_end >= start_ms:
        payload = {
            "type": "userFillsByTime",
            "user": wallet,
            "startTime": start_ms,
            "endTime": cursor_end,
            "aggregateByTime": False,
        }
        fills = api(payload)

        if not isinstance(fills, list) or not fills:
            break

        new_count = 0
        oldest = None

        for f in fills:
            try:
                t = int(f.get("time", 0))
            except Exception:
                continue

            if t < start_ms or t > end_ms:
                continue

            tid = str(f.get("tid", "")) + ":" + str(t)
            if tid in seen:
                continue

            seen.add(tid)
            all_fills.append(f)
            new_count += 1

            if oldest is None or t < oldest:
                oldest = t

        if len(fills) < 2000:
            break

        if oldest is None or oldest <= start_ms or new_count == 0:
            break

        # Move the end before the oldest returned fill to avoid duplicates.
        cursor_end = oldest - 1

    return all_fills


def fill_volume(fills):
    total = 0.0
    for f in fills:
        try:
            total += abs(float(f["px"]) * float(f["sz"]))
        except Exception:
            pass
    return total


def build_wallet_data(wallet, current):
    # Fetch the competition-period fills once per wallet, then partition
    # them into UTC days. This avoids making 7 separate fill requests.
    end_for_volume = min(current, END)
    fills = []
    if end_for_volume > START:
        fills = exact_fills(wallet, START, end_for_volume)

    # Fetch portfolio history once per wallet and reuse it for all days.
    history = get_perp_week_history(wallet)

    days = []
    for day_index in range(7):
        day_start = START + timedelta(days=day_index)
        day_end = day_start + timedelta(days=1)

        if current < day_end:
            days.append({
                "status": "pending",
                "volume": None,
                "pnl": None,
                "fills": 0,
            })
            continue

        day_fills = [
            f for f in fills
            if ms(day_start) <= int(f.get("time", 0)) < ms(min(day_end, END))
        ]

        p0 = nearest_pnl(history, ms(day_start))
        p1 = nearest_pnl(history, ms(day_end))

        pnl = None if p0 is None or p1 is None else (p1 - p0)

        days.append({
            "status": "complete" if pnl is not None else "pnl_pending",
            "volume": fill_volume(day_fills),
            "pnl": pnl,
            "fills": len(day_fills),
        })

    weekly_volume = fill_volume(fills)

    p0 = nearest_pnl(history, ms(START))
    weekly_end = END if current >= END else current
    p1 = nearest_pnl(history, ms(weekly_end))
    weekly_pnl = None if p0 is None or p1 is None else (p1 - p0)

    if current < START:
        weekly_status = "pending"
    elif current >= END and weekly_pnl is not None:
        weekly_status = "complete"
    elif weekly_pnl is None:
        weekly_status = "pnl_pending"
    else:
        weekly_status = "running"

    return days, {
        "status": weekly_status,
        "volume": weekly_volume if end_for_volume > START else None,
        "pnl": weekly_pnl,
    }


def compute_points(rows, field, positive_only=False):
    eligible = []
    for r in rows:
        value = r.get(field)
        if value is None:
            continue
        if positive_only and value <= 0:
            continue
        eligible.append(r)

    eligible.sort(key=lambda r: r[field], reverse=True)

    points = [10, 8, 6, 4, 2]
    for i, r in enumerate(eligible[:5]):
        r[field + "_points"] = points[i]

    for r in rows:
        r.setdefault(field + "_points", 0)


PAYLOAD_CACHE = {"time": 0.0, "data": None}
PAYLOAD_CACHE_LOCK = threading.Lock()

def build_payload():
    current_time = time.time()
    with PAYLOAD_CACHE_LOCK:
        if PAYLOAD_CACHE["data"] is not None and current_time - PAYLOAD_CACHE["time"] < 45:
            return PAYLOAD_CACHE["data"]

    current = now_utc()
    wallet_rows = []

    for wallet in WALLETS:
        days, week = build_wallet_data(wallet, current)

        row = {
            "wallet": wallet,
            "name": username(wallet),
            "days": days,
            "week": week,
        }

        # Daily points for Volume and PnL.
        for i in range(7):
            row["days"][i]["volume_points"] = 0
            row["days"][i]["pnl_points"] = 0

        wallet_rows.append(row)

    # Assign daily points independently.
    for day_index in range(7):
        day_rows = []
        for r in wallet_rows:
            d = r["days"][day_index]
            day_rows.append({
                "wallet": r["wallet"],
                "name": r["name"],
                "volume": d["volume"],
                "pnl": d["pnl"],
                "days": r["days"],
            })

        compute_points(day_rows, "volume", positive_only=False)
        compute_points(day_rows, "pnl", positive_only=True)

        by_wallet = {x["wallet"]: x for x in day_rows}
        for r in wallet_rows:
            r["days"][day_index]["volume_points"] = by_wallet[r["wallet"]]["volume_points"]
            r["days"][day_index]["pnl_points"] = by_wallet[r["wallet"]]["pnl_points"]

    # Weekly points.
    week_rows = []
    for r in wallet_rows:
        week_rows.append({
            "wallet": r["wallet"],
            "name": r["name"],
            "volume": r["week"]["volume"],
            "pnl": r["week"]["pnl"],
        })

    compute_points(week_rows, "volume", positive_only=False)
    compute_points(week_rows, "pnl", positive_only=True)

    for r in wallet_rows:
        x = next(z for z in week_rows if z["wallet"] == r["wallet"])
        r["week"]["volume_points"] = x["volume_points"]
        r["week"]["pnl_points"] = x["pnl_points"]

    # Final scores.
    for r in wallet_rows:
        volume_daily = [d["volume_points"] for d in r["days"]]
        pnl_daily = [d["pnl_points"] for d in r["days"]]

        r["volume_avg_daily"] = sum(volume_daily) / 7.0
        r["pnl_avg_daily"] = sum(pnl_daily) / 7.0

        r["volume_final_score"] = (
            0.8 * r["volume_avg_daily"] + 0.2 * r["week"]["volume_points"]
        )
        r["pnl_final_score"] = (
            0.8 * r["pnl_avg_daily"] + 0.2 * r["week"]["pnl_points"]
        )

        weekly_volume = r["week"]["volume"]
        weekly_pnl = r["week"]["pnl"]

        r["pnl_qualified"] = (
            weekly_volume is not None
            and weekly_pnl is not None
            and weekly_volume >= 20000
            and weekly_pnl > 0
        )

    result = {
        "competition": {
            "start": START.isoformat(),
            "end": END.isoformat(),
            "now": current.isoformat(),
            "days": [
                (START + timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range(7)
            ],
        },
        "wallets": wallet_rows,
    }

    with PAYLOAD_CACHE_LOCK:
        PAYLOAD_CACHE["time"] = time.time()
        PAYLOAD_CACHE["data"] = result

    return result


HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hyperliquid Community Competition 2026</title>
<style>
body{margin:0;background:#07090d;color:#f3f5f7;font-family:Inter,Arial,sans-serif}
.wrap{max-width:1250px;margin:auto;padding:28px 18px 60px}
h1{margin:0 0 8px;font-size:30px}
.sub{color:#9da6b2;margin-bottom:20px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:15px 0}
button{background:#121722;color:#dfe5ec;border:1px solid #293142;border-radius:10px;padding:9px 13px;cursor:pointer}
button.active{background:#fff;color:#080a0d}
.card{background:#0d1118;border:1px solid #1f2633;border-radius:16px;padding:16px;margin-bottom:18px;overflow:auto}
table{width:100%;border-collapse:collapse;min-width:900px}
th,td{padding:12px 10px;border-bottom:1px solid #1c2330;text-align:right;white-space:nowrap}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
th{color:#8f9aaa;font-size:12px;text-transform:uppercase}
.rank{font-weight:800}
.green{color:#6ee7a1}
.red{color:#ff7b8a}
.muted{color:#737d8d}
.badge{padding:4px 7px;border-radius:7px;background:#18202d;color:#aeb8c6;font-size:11px}
.note{font-size:13px;color:#929dac;line-height:1.5}
</style>
</head>
<body>
<div class="wrap">
<h1>🏆 Hyperliquid Community Trading Competition</h1>
<div class="sub">2 Oct 2026 00:00 UTC → 9 Oct 2026 00:00 UTC · Auto-refresh every 60s</div>

<div class="tabs" id="tabs"></div>
<div id="app"></div>

<div class="card note">
<b>Scoring:</b> daily top 5 = 10 / 8 / 6 / 4 / 2 points.
Final score = 80% × average daily points + 20% × weekly points.
PnL qualification requires at least 20,000 USDC weekly volume and positive weekly PnL.
<br><br>
<b>Data:</b> Volume is calculated from Hyperliquid executed fills. PnL uses Hyperliquid's portfolio PnL history at UTC boundaries. Hyperliquid states its portfolio graphs are sampled periodically, so PnL is an account/portfolio metric and should not be treated as tick-perfect accounting.
</div>
</div>

<script>
let DATA=null;
let currentTab="volume-week";

const tabs=[
 ["volume-week","Volume — Weekly"],
 ["pnl-week","PnL — Weekly"],
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
function signedMoney(x){
 if(x===null||x===undefined)return '<span class="muted">—</span>';
 let n=Number(x);
 return '<span class="'+(n>=0?'green':'red')+'">'+(n>=0?'+':'')+money(n)+'</span>';
}
function render(){
 const [metric,scope,idx]=currentTab.split("-");
 let rows=DATA.wallets.map((r,i)=>{
   let value,pts,score,status;
   if(scope==="week"){
     value=r.week[metric];
     pts=r.week[metric+"_points"];
     score=metric==="volume"?r.volume_final_score:r.pnl_final_score;
     status=r.week.status;
   }else{
     const d=r.days[Number(idx)];
     value=d[metric];
     pts=d[metric+"_points"];
     score=pts;
     status=d.status;
   }
   return {...r,value,pts,score,status};
 });

 rows.sort((a,b)=>{
   if(scope==="week") return b.score-a.score;
   return (b.value??-Infinity)-(a.value??-Infinity);
 });

 let title=metric==="volume"?"📊 Volume":"💰 PnL";
 let subtitle=scope==="week"?"Weekly competition score":"Daily ranking";
 let html='<div class="card"><h2>'+title+' · '+subtitle+'</h2><table><thead><tr>'+
 '<th>#</th><th>Trader</th><th>'+title+'</th><th>Points</th>'+
 (scope==="week"?'<th>Avg Daily</th><th>Final Score</th>':'<th>Status</th>')+
 '</tr></thead><tbody>';

 rows.forEach((r,i)=>{
   html+='<tr>'+
    '<td class="rank">'+(i+1)+'</td>'+
    '<td><b>'+esc(r.name)+'</b><br><span class="muted">'+esc(r.wallet.slice(0,8)+'...'+r.wallet.slice(-6))+'</span></td>'+
    '<td>'+(metric==="volume"?money(r.value):signedMoney(r.value))+'</td>'+
    '<td><b>'+r.pts+'</b></td>'+
    (scope==="week"
      ? '<td>'+((metric==="volume"?r.volume_avg_daily:r.pnl_avg_daily).toFixed(2))+'</td><td><b>'+r.score.toFixed(2)+'</b></td>'
      : '<td><span class="badge">'+esc(r.status)+'</span></td>')+
   '</tr>';
 });
 html+='</tbody></table></div>';

 if(scope==="week" && metric==="pnl"){
   html+='<div class="card note"><b>PnL qualification:</b> weekly volume must be ≥ $20,000 and weekly PnL must be positive. Current qualification is shown by the underlying weekly data.</div>';
 }
 document.getElementById("app").innerHTML=html;
}

function renderTabs(){
 document.getElementById("tabs").innerHTML=tabs.map(t=>
   '<button class="'+(t[0]===currentTab?'active':'')+'" onclick="currentTab=\''+t[0]+'\';renderTabs();render()">'+t[1]+'</button>'
 ).join("");
}

async function load(){
 try{
  const r=await fetch('/data?t='+Date.now(),{cache:'no-store'});
  DATA=await r.json();
  renderTabs(); render();
 }catch(e){
  document.getElementById("app").innerHTML='<div class="card">Data temporarily unavailable. Retrying…</div>';
 }
}
load();
setInterval(load,60000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def send_text(self, status, content, content_type="text/html; charset=utf-8"):
        raw = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        try:
            if self.path.startswith("/data"):
                payload = build_payload()
                self.send_text(
                    200,
                    json.dumps(payload, separators=(",", ":")),
                    "application/json; charset=utf-8",
                )
            else:
                self.send_text(200, HTML)
        except Exception as e:
            print("ERROR:", repr(e), flush=True)
            self.send_text(
                500,
                json.dumps({"error": str(e)}),
                "application/json; charset=utf-8",
            )

    def log_message(self, fmt, *args):
        return


def main():
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("Hyperliquid competition leaderboard running on port", port, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
