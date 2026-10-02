
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

# ============================================================
# ORIGAMI COMMUNITY TRADING COMPETITION
# ============================================================
# DATA SOURCE:
# CoinMarketMan / HyperTracker public Origami builder dataset.
#
# Origami builder:
# 0x9b451f8941240db8bedc99bff8917a2ed9550074
#
# The CMM dataset contains:
#   users["24h"] -> current rolling 24-hour builder-attributed data
#   users["7d"]  -> current rolling 7-day builder-attributed data
#
# Daily snapshots are taken at exactly the UTC cutoff:
#   Oct 3 00:00 UTC -> captures Oct 2
#   Oct 4 00:00 UTC -> captures Oct 3
#   ...
#   Oct 9 00:00 UTC -> captures Oct 8
#
# Weekly snapshot:
#   Oct 9 00:00 UTC -> CMM 7d value covers the competition window.
#
# IMPORTANT:
# A rolling 24h value cannot reconstruct a missed historical cutoff.
# Therefore the service must be running/awake at the UTC cutoffs.
# ============================================================

DATA_URL = (
    "https://dw3ji7n7thadj.cloudfront.net/aggregator/builders/"
    "0x9b451f8941240db8bedc99bff8917a2ed9550074_v2.json"
)

START = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)

REFRESH_SECONDS = 60
SNAPSHOT_CHECK_SECONDS = 30
DB_FILE = "origami_competition_cmm.sqlite3"

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

# ------------------------------------------------------------
# OPTIONAL MANUAL OVERRIDE
# ------------------------------------------------------------
# Oct 2's exact 24h cutoff may already have passed before this
# service was deployed. If you have the Oct 2 CMM 24h numbers,
# put them here later. Format:
#
# "0xwallet": {"volume": 123.45, "pnl": 6.78}
#
# Leave empty for now.
MANUAL_DAILY = {
    # "0x28d6...": {"volume": 12345.67, "pnl": 12.34},
}

session = requests.Session()
session.headers.update({
    "User-Agent": "Origami-Competition-Leaderboard/1.0",
    "Accept": "application/json",
})

FETCH_LOCK = threading.Lock()
LAST_FETCH = {"time": 0.0, "data": None, "error": None}

DB_LOCK = threading.Lock()


def db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            day TEXT NOT NULL,
            wallet TEXT NOT NULL,
            volume REAL NOT NULL,
            pnl REAL NOT NULL,
            captured_at TEXT NOT NULL,
            PRIMARY KEY(day, wallet)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS weekly_snapshot (
            id INTEGER PRIMARY KEY CHECK(id=1),
            volume REAL NOT NULL,
            pnl REAL NOT NULL,
            captured_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def fetch_cmm(force=False):
    now = time.time()

    with FETCH_LOCK:
        if (
            not force
            and LAST_FETCH["data"] is not None
            and now - LAST_FETCH["time"] < 45
        ):
            return LAST_FETCH["data"]

        last_error = None

        for attempt in range(4):
            try:
                r = session.get(DATA_URL, timeout=20)
                r.raise_for_status()
                data = r.json()

                LAST_FETCH["time"] = time.time()
                LAST_FETCH["data"] = data
                LAST_FETCH["error"] = None
                return data

            except Exception as e:
                last_error = e
                time.sleep(1.5 * (attempt + 1))

        LAST_FETCH["error"] = str(last_error)
        raise RuntimeError(
            "CoinMarketMan data request failed: " + str(last_error)
        )


def normalize_users(data, timeframe):
    """
    Supports the known CMM structure:
        {"users": {"24h": [...], "7d": [...], ...}}

    Also supports timeframe-first variants.
    """
    raw = None

    if isinstance(data, dict):
        users = data.get("users")
        if isinstance(users, dict):
            raw = users.get(timeframe)

        if raw is None:
            block = data.get(timeframe)
            if isinstance(block, dict):
                raw = block.get("users")
            elif isinstance(block, list):
                raw = block

    if raw is None:
        return {}

    result = {}

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue

            address = (
                item.get("address")
                or item.get("user")
                or item.get("wallet", {}).get("address")
            )

            if isinstance(address, str) and address.lower().startswith("0x"):
                result[address.lower()] = item

    elif isinstance(raw, dict):
        for key, item in raw.items():
            if not isinstance(item, dict):
                continue

            address = (
                key
                if isinstance(key, str) and key.lower().startswith("0x")
                else item.get("address")
                or item.get("user")
            )

            if isinstance(address, str) and address.lower().startswith("0x"):
                result[address.lower()] = item

    return result


def number(obj, *names):
    for name in names:
        try:
            value = obj.get(name)
            if value is not None:
                return float(value)
        except Exception:
            pass
    return 0.0


def extract_wallets(data, timeframe):
    users = normalize_users(data, timeframe)

    result = {}

    for wallet in WALLETS:
        item = users.get(wallet.lower())

        if item is None:
            result[wallet] = {
                "volume": 0.0,
                "pnl": 0.0,
                "closedPnl": 0.0,
                "builderFee": 0.0,
                "found": False,
            }
        else:
            result[wallet] = {
                "volume": number(item, "volume"),
                "pnl": number(item, "pnl"),
                "closedPnl": number(item, "closedPnl", "closed_pnl"),
                "builderFee": number(item, "builderFee", "builder_fee"),
                "found": True,
            }

    return result


def snapshot_exists(day):
    conn = db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM daily_snapshots WHERE day=?",
            (day,),
        ).fetchone()
        return row[0] == len(WALLETS)
    finally:
        conn.close()


def save_daily_snapshot(day, rows):
    conn = db()
    try:
        captured = datetime.now(timezone.utc).isoformat()

        for wallet in WALLETS:
            x = rows[wallet]
            conn.execute("""
                INSERT OR REPLACE INTO daily_snapshots
                (day, wallet, volume, pnl, captured_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                day,
                wallet,
                x["volume"],
                x["pnl"],
                captured,
            ))

        conn.commit()
    finally:
        conn.close()


def save_weekly_snapshot(rows):
    conn = db()
    try:
        captured = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT OR REPLACE INTO weekly_snapshot
            (id, volume, pnl, captured_at)
            VALUES (1, ?, ?, ?)
        """, (
            rows["volume"],
            rows["pnl"],
            captured,
        ))
        conn.commit()
    finally:
        conn.close()


def read_daily(day):
    conn = db()
    try:
        rows = conn.execute("""
            SELECT wallet, volume, pnl, captured_at
            FROM daily_snapshots
            WHERE day=?
        """, (day,)).fetchall()

        return {
            wallet: {
                "volume": volume,
                "pnl": pnl,
                "captured_at": captured,
            }
            for wallet, volume, pnl, captured in rows
        }
    finally:
        conn.close()


def read_weekly():
    conn = db()
    try:
        row = conn.execute("""
            SELECT volume, pnl, captured_at
            FROM weekly_snapshot
            WHERE id=1
        """).fetchone()

        if not row:
            return None

        return {
            "volume": row[0],
            "pnl": row[1],
            "captured_at": row[2],
        }
    finally:
        conn.close()


def utc_day_label(i):
    return (START + timedelta(days=i)).strftime("%Y-%m-%d")


def snapshot_worker():
    print("CMM snapshot worker started.", flush=True)

    while True:
        try:
            now = datetime.now(timezone.utc)

            # At each cutoff, the current CMM 24h window represents
            # the preceding UTC day.
            for i in range(7):
                day_start = START + timedelta(days=i)
                day_end = day_start + timedelta(days=1)

                if now >= day_end and day_start >= START:
                    day = day_start.strftime("%Y-%m-%d")

                    if snapshot_exists(day):
                        continue

                    # Optional exact manual override.
                    if i == 0 and MANUAL_DAILY:
                        override_rows = {}
                        for wallet in WALLETS:
                            if wallet in MANUAL_DAILY:
                                override_rows[wallet] = {
                                    "volume": float(MANUAL_DAILY[wallet]["volume"]),
                                    "pnl": float(MANUAL_DAILY[wallet]["pnl"]),
                                }
                            else:
                                override_rows = {}
                                break

                        if override_rows:
                            save_daily_snapshot(day, override_rows)
                            print("Saved manual Oct 2 snapshot.", flush=True)
                            continue

                    data = fetch_cmm(force=True)
                    rows = extract_wallets(data, "24h")

                    save_daily_snapshot(day, rows)

                    print(
                        "Saved CMM 24h snapshot for",
                        day,
                        "at",
                        now.isoformat(),
                        flush=True,
                    )

            # At Oct 9 00:00 UTC, CMM's 7d view represents
            # Oct 2 00:00 -> Oct 9 00:00.
            if now >= END and read_weekly() is None:
                data = fetch_cmm(force=True)
                rows = extract_wallets(data, "7d")

                total_volume = sum(x["volume"] for x in rows.values())
                total_pnl = sum(x["pnl"] for x in rows.values())

                save_weekly_snapshot({
                    "volume": total_volume,
                    "pnl": total_pnl,
                })

                print(
                    "Saved final CMM 7d weekly snapshot.",
                    flush=True,
                )

        except Exception as e:
            print("SNAPSHOT WORKER ERROR:", repr(e), flush=True)

        time.sleep(SNAPSHOT_CHECK_SECONDS)


def daily_rows(day_index):
    day = utc_day_label(day_index)
    saved = read_daily(day)

    result = []

    for wallet in WALLETS:
        x = saved.get(wallet)

        if x:
            result.append({
                "wallet": wallet,
                "name": USERNAMES.get(wallet, "") or wallet[:6] + "..." + wallet[-4:],
                "volume": x["volume"],
                "pnl": x["pnl"],
                "status": "captured",
                "captured_at": x["captured_at"],
            })
        else:
            result.append({
                "wallet": wallet,
                "name": USERNAMES.get(wallet, "") or wallet[:6] + "..." + wallet[-4:],
                "volume": None,
                "pnl": None,
                "status": "not captured",
                "captured_at": None,
            })

    return result


def weekly_rows():
    weekly = read_weekly()

    # Before final weekly snapshot, calculate a live CMM 7d view only
    # for display. It is NOT treated as final competition data until
    # Oct 9 00:00 UTC.
    if weekly is None:
        try:
            data = fetch_cmm()
            rows = extract_wallets(data, "7d")

            return [{
                "wallet": wallet,
                "name": USERNAMES.get(wallet, "") or wallet[:6] + "..." + wallet[-4:],
                "volume": rows[wallet]["volume"],
                "pnl": rows[wallet]["pnl"],
                "status": "live 7d",
            } for wallet in WALLETS]
        except Exception:
            return [{
                "wallet": wallet,
                "name": USERNAMES.get(wallet, "") or wallet[:6] + "..." + wallet[-4:],
                "volume": None,
                "pnl": None,
                "status": "unavailable",
            } for wallet in WALLETS]

    # Final weekly snapshot is a total across all selected wallets.
    # For leaderboard scoring we need each wallet's 7d value, so fetch
    # the same CMM 7d user list for the final display.
    try:
        data = fetch_cmm()
        rows = extract_wallets(data, "7d")
        return [{
            "wallet": wallet,
            "name": USERNAMES.get(wallet, "") or wallet[:6] + "..." + wallet[-4:],
            "volume": rows[wallet]["volume"],
            "pnl": rows[wallet]["pnl"],
            "status": "final 7d",
        } for wallet in WALLETS]
    except Exception:
        return [{
            "wallet": wallet,
            "name": USERNAMES.get(wallet, "") or wallet[:6] + "..." + wallet[-4:],
            "volume": None,
            "pnl": None,
            "status": "unavailable",
        } for wallet in WALLETS]


def points(rows, field, positive_only=False):
    eligible = [
        r for r in rows
        if r[field] is not None
        and (not positive_only or r[field] > 0)
    ]

    eligible.sort(key=lambda r: r[field], reverse=True)

    score = [10, 8, 6, 4, 2]
    result = {r["wallet"]: 0 for r in rows}

    for i, r in enumerate(eligible[:5]):
        result[r["wallet"]] = score[i]

    return result


def build_data():
    current = datetime.now(timezone.utc)

    days = [daily_rows(i) for i in range(7)]

    for i in range(7):
        vp = points(days[i], "volume")
        pp = points(days[i], "pnl", positive_only=True)

        for r in days[i]:
            r["volume_points"] = vp[r["wallet"]]
            r["pnl_points"] = pp[r["wallet"]]

    # Weekly live/final CMM 7d values.
    week = weekly_rows()
    wpv = points(week, "volume")
    wpp = points(week, "pnl", positive_only=True)

    week_by_wallet = {r["wallet"]: r for r in week}

    # Combine daily and weekly scores.
    final = []

    for wallet in WALLETS:
        name = USERNAMES.get(wallet, "") or wallet[:6] + "..." + wallet[-4:]

        daily_v = [
            days[i][WALLETS.index(wallet)]["volume_points"]
            for i in range(7)
        ]
        daily_p = [
            days[i][WALLETS.index(wallet)]["pnl_points"]
            for i in range(7)
        ]

        w = week_by_wallet[wallet]

        avg_v = sum(daily_v) / 7.0
        avg_p = sum(daily_p) / 7.0

        final.append({
            "wallet": wallet,
            "name": name,
            "volume": w["volume"],
            "pnl": w["pnl"],
            "volume_week_points": wpv[wallet],
            "pnl_week_points": wpp[wallet],
            "volume_avg_daily": avg_v,
            "pnl_avg_daily": avg_p,
            "volume_final_score": 0.8 * avg_v + 0.2 * wpv[wallet],
            "pnl_final_score": 0.8 * avg_p + 0.2 * wpp[wallet],
            "pnl_qualified": (
                w["volume"] is not None
                and w["pnl"] is not None
                and w["volume"] >= 20000
                and w["pnl"] > 0
            ),
            "week_status": w["status"],
        })

    return {
        "competition": {
            "start": START.isoformat(),
            "end": END.isoformat(),
            "now": current.isoformat(),
            "builder": "0x9b451f8941240db8bedc99bff8917a2ed9550074",
        },
        "days": days,
        "week": week,
        "final": final,
        "data_source": DATA_URL,
    }


HTML = r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Origami Community Trading Competition</title>
<style>
body{margin:0;background:#07090d;color:#f3f5f7;font-family:Arial,sans-serif}
.wrap{max-width:1300px;margin:auto;padding:28px 18px 60px}
h1{margin:0 0 8px;font-size:30px}
.sub{color:#9da6b2;margin-bottom:18px}
.tabs{display:flex;gap:7px;flex-wrap:wrap;margin:15px 0}
button{background:#121722;color:#dfe5ec;border:1px solid #293142;border-radius:9px;padding:9px 12px;cursor:pointer}
button.active{background:#fff;color:#080a0d}
.card{background:#0d1118;border:1px solid #1f2633;border-radius:16px;padding:16px;margin-bottom:18px;overflow:auto}
table{width:100%;border-collapse:collapse;min-width:900px}
th,td{padding:11px 9px;border-bottom:1px solid #1c2330;text-align:right;white-space:nowrap}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
th{color:#8f9aaa;font-size:11px;text-transform:uppercase}
.green{color:#6ee7a1}.red{color:#ff7b8a}.muted{color:#737d8d}
.badge{padding:4px 7px;border-radius:7px;background:#18202d;color:#aeb8c6;font-size:11px}
.note{font-size:13px;color:#929dac;line-height:1.55}
</style>
</head>
<body>
<div class="wrap">
<h1>🏆 Origami Community Trading Competition</h1>
<div class="sub">2 Oct 2026 00:00 UTC → 9 Oct 2026 00:00 UTC · Origami builder-attributed data</div>
<div class="tabs" id="tabs"></div>
<div id="app"></div>
<div class="card note">
<b>Data source:</b> CoinMarketMan / HyperTracker Origami builder data.
Only activity attributed to the Origami builder is used.
<br><br>
<b>Daily:</b> CMM 24h data is captured at each 00:00 UTC cutoff and stored.
<b>Weekly:</b> CMM 7d data is used for the final weekly view.
<br><br>
<b>Scoring:</b> daily top 5 = 10 / 8 / 6 / 4 / 2. Final score = 80% average daily points + 20% weekly points.
PnL qualification requires ≥ $20,000 weekly volume and positive weekly PnL.
<br><br>
<b>Important:</b> a rolling 24h feed cannot recreate a missed historical cutoff. The server therefore needs to be awake at the UTC cutoffs for exact daily snapshots.
</div>
</div>
<script>
let DATA=null,currentTab="volume-week";
const tabs=[
["volume-week","Volume — Weekly"],["pnl-week","PnL — Weekly"],
["volume-day-0","Volume — Oct 2"],["volume-day-1","Volume — Oct 3"],
["volume-day-2","Volume — Oct 4"],["volume-day-3","Volume — Oct 5"],
["volume-day-4","Volume — Oct 6"],["volume-day-5","Volume — Oct 7"],
["volume-day-6","Volume — Oct 8"],
["pnl-day-0","PnL — Oct 2"],["pnl-day-1","PnL — Oct 3"],
["pnl-day-2","PnL — Oct 4"],["pnl-day-3","PnL — Oct 5"],
["pnl-day-4","PnL — Oct 6"],["pnl-day-5","PnL — Oct 7"],
["pnl-day-6","PnL — Oct 8"]
];
function esc(x){return String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]));}
function money(x){if(x===null||x===undefined)return '<span class="muted">—</span>';return '$'+Number(x).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});}
function pnl(x){if(x===null||x===undefined)return '<span class="muted">—</span>';let n=Number(x);return '<span class="'+(n>=0?'green':'red')+'">'+(n>=0?'+':'')+money(n)+'</span>';}
function render(){
 const p=currentTab.split("-");
 const metric=p[0],scope=p[1],idx=p[2];
 let rows;
 if(scope==="week"){
   rows=DATA.final.map(r=>({...r,value:r[metric],points:r[metric+"_week_points"],score:metric==="volume"?r.volume_final_score:r.pnl_final_score,status:r.week_status}));
   rows.sort((a,b)=>(b.score??-Infinity)-(a.score??-Infinity));
 }else{
   rows=DATA.days[Number(idx)].map(r=>({...r,value:r[metric],points:r[metric+"_points"],score:r[metric+"_points"]}));
   rows.sort((a,b)=>(b.value??-Infinity)-(a.value??-Infinity));
 }
 const title=metric==="volume"?"📊 Volume":"💰 PnL";
 let html='<div class="card"><h2>'+title+' · '+(scope==="week"?"Weekly":"Daily")+'</h2><table><thead><tr><th>#</th><th>Trader</th><th>'+title+'</th><th>Points</th>';
 if(scope==="week")html+='<th>Avg Daily</th><th>Final Score</th><th>Status</th>';
 else html+='<th>Status</th>';
 html+='</tr></thead><tbody>';
 rows.forEach((r,i)=>{
   html+='<tr><td><b>'+(i+1)+'</b></td><td><b>'+esc(r.name)+'</b><br><span class="muted">'+esc(r.wallet.slice(0,8)+'...'+r.wallet.slice(-6))+'</span></td><td>'+(metric==="volume"?money(r.value):pnl(r.value))+'</td><td><b>'+r.points+'</b></td>';
   if(scope==="week"){
     const avg=metric==="volume"?r.volume_avg_daily:r.pnl_avg_daily;
     html+='<td>'+Number(avg).toFixed(2)+'</td><td><b>'+Number(r.score).toFixed(2)+'</b></td><td><span class="badge">'+esc(r.status||"")+'</span></td>';
   }else{
     html+='<td><span class="badge">'+esc(r.status||"")+'</span></td>';
   }
   html+='</tr>';
 });
 html+='</tbody></table></div>';
 document.getElementById("app").innerHTML=html;
}
function renderTabs(){
 document.getElementById("tabs").innerHTML=tabs.map(t=>'<button class="'+(t[0]===currentTab?'active':'')+'" onclick="currentTab=\''+t[0]+'\';renderTabs();render()">'+t[1]+'</button>').join("");
}
async function load(){
 try{
  const r=await fetch("/data?t="+Date.now(),{cache:"no-store"});
  if(!r.ok)throw new Error("Data request failed: HTTP "+r.status);
  DATA=await r.json();
  renderTabs();render();
 }catch(e){
  document.getElementById("app").innerHTML='<div class="card">Data temporarily unavailable. Retrying…</div>';
 }
}
load();setInterval(load,60000);
</script>
</body>
</html>
"""


PAYLOAD_CACHE = {"time": 0.0, "data": None}
PAYLOAD_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def send_text(self, status, text, content_type):
        raw = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/data"):
            try:
                now = time.time()

                with PAYLOAD_LOCK:
                    if (
                        PAYLOAD_CACHE["data"] is not None
                        and now - PAYLOAD_CACHE["time"] < 45
                    ):
                        payload = PAYLOAD_CACHE["data"]
                    else:
                        payload = build_data()
                        PAYLOAD_CACHE["data"] = payload
                        PAYLOAD_CACHE["time"] = now

                self.send_text(
                    200,
                    json.dumps(payload, separators=(",", ":")),
                    "application/json; charset=utf-8",
                )
            except Exception as e:
                print("DATA ERROR:", repr(e), flush=True)
                self.send_text(
                    200,
                    json.dumps({
                        "error": "CMM data unavailable",
                        "details": str(e),
                    }),
                    "application/json; charset=utf-8",
                )
        else:
            self.send_text(200, HTML, "text/html; charset=utf-8")

    def log_message(self, fmt, *args):
        return


def main():
    db()

    worker = threading.Thread(target=snapshot_worker, daemon=True)
    worker.start()

    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)

    print("Origami CMM competition leaderboard running on port", port, flush=True)
    print("Competition:", START.isoformat(), "->", END.isoformat(), flush=True)
    print("Builder:", "0x9b451f8941240db8bedc99bff8917a2ed9550074", flush=True)

    server.serve_forever()


if __name__ == "__main__":
    main()
