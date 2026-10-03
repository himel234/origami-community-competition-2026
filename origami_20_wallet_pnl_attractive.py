
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
    "0x9701d4d5b1910462354368bb0f7bc31dac0e601a",
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
    response.raise_for_status()
    return response.json()

def fetch_builder_fills(start, end):
    results = []
    for offset in range(0, len(WALLETS), 10):
        batch = WALLETS[offset:offset + 10]
        base_params = [
            ("start", utc_iso(start)),
            ("end", utc_iso(end)),
            ("fillType", "perp"),
            ("limit", "500"),
        ]
        base_params += [("address[]", wallet) for wallet in batch]
        cursor = None
        while True:
            params = list(base_params)
            if cursor:
                params.append(("cursor", cursor))
            data = api_get(f"/builders/{BUILDER}/fills", params)
            fills = data.get("fills", [])
            results.extend(fills)
            cursor = data.get("nextCursor")
            if not cursor or not fills:
                break
    return results

def fetch_closed_trades(wallet, start, end):
    data = api_get("/closed-trades", {
        "address": wallet,
        "startTime": int(start.timestamp() * 1000),
        "endTime": int(end.timestamp() * 1000),
        "limit": 500,
    })
    return data.get("trades", [])

def estimate_origami_funding(wallet_fills, closed_trades, day_start, day_end):
    total = 0.0
    for trade in closed_trades:
        close_time = trade.get("closeTime")
        if not close_time:
            continue
        try:
            close_dt = parse_iso(close_time)
        except Exception:
            continue
        if not (day_start <= close_dt < day_end):
            continue
        coin = trade.get("coin")
        total_size = float(trade.get("totalSize", 0) or 0)
        if not coin or total_size <= 0:
            continue
        candidates = []
        for fill in wallet_fills:
            if fill.get("coin") != coin:
                continue
            try:
                fill_dt = parse_iso(fill["time"])
            except Exception:
                continue
            if abs((fill_dt - close_dt).total_seconds()) <= 6 * 3600:
                candidates.append(fill)
        candidate_size = sum(float(f.get("sz", 0) or 0) for f in candidates)
        if candidates and abs(candidate_size - total_size) / total_size <= 0.02:
            total += float(trade.get("fundingUsd", 0) or 0)
    return total

def reconstruct_positions(fills, cutoff):
    positions = {}
    for fill in sorted(fills, key=lambda x: x.get("time", "")):
        try:
            fill_time = parse_iso(fill["time"])
        except Exception:
            continue
        if fill_time >= cutoff:
            continue
        coin = fill.get("coin") or fill.get("fullCoinName")
        if not coin:
            continue
        size = float(fill.get("sz", 0) or 0)
        price = float(fill.get("px", 0) or 0)
        direction = str(fill.get("dir", ""))
        if "Open Long" in direction:
            signed = size
        elif "Close Long" in direction:
            signed = -size
        elif "Open Short" in direction:
            signed = -size
        elif "Close Short" in direction:
            signed = size
        else:
            signed = size if fill.get("side") == "B" else -size
        p = positions.setdefault(coin, {"qty": 0.0, "cost": 0.0})
        old = p["qty"]
        new = old + signed
        if old == 0 or old * signed > 0:
            p["cost"] += signed * price
            p["qty"] = new
        else:
            close_qty = min(abs(old), abs(signed))
            if old != 0:
                p["cost"] *= max(0.0, (abs(old) - close_qty) / abs(old))
            p["qty"] = new
            if old * new < 0:
                residual = abs(new)
                p["cost"] = residual * price if new > 0 else -residual * price
        if abs(p["qty"]) < 1e-12:
            p["qty"] = 0.0
            p["cost"] = 0.0
    return positions

def historical_price_proxy(coin, cutoff):
    cutoff_ms = int(cutoff.timestamp() * 1000)
    body = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": "1m",
            "startTime": cutoff_ms - 120000,
            "endTime": cutoff_ms + 60000,
        },
    }
    response = requests.post(HL_INFO, json=body, timeout=30)
    response.raise_for_status()
    candles = response.json()
    if not candles:
        return None
    candles.sort(key=lambda x: abs(int(x["T"]) - cutoff_ms))
    return float(candles[0]["c"])

def calculate_unrealized(wallet_fills, cutoff):
    positions = reconstruct_positions(wallet_fills, cutoff)
    total = 0.0
    for coin, position in positions.items():
        qty = position["qty"]
        if abs(qty) < 1e-12:
            continue
        mark = historical_price_proxy(coin, cutoff)
        if mark is None:
            continue
        avg_entry = position["cost"] / qty
        total += (mark - avg_entry) * qty
    return total

def calculate_day(day_start, day_end, fills):
    by_wallet = {wallet: [] for wallet in WALLETS}
    for fill in fills:
        address = str(fill.get("address", "")).lower()
        if address in by_wallet:
            by_wallet[address].append(fill)

    conn = db_connect()
    updated = utc_iso(datetime.now(timezone.utc))

    for wallet in WALLETS:
        wallet_fills = by_wallet[wallet]
        volume = sum(
            float(f.get("px", 0) or 0) * float(f.get("sz", 0) or 0)
            for f in wallet_fills
        )
        realized = sum(float(f.get("closedPnl", 0) or 0) for f in wallet_fills)
        fees = sum(float(f.get("fee", 0) or 0) for f in wallet_fills)

        funding = 0.0
        try:
            trades = fetch_closed_trades(wallet, day_start, day_end)
            funding = estimate_origami_funding(
                wallet_fills, trades, day_start, day_end
            )
        except Exception as error:
            print("Funding lookup failed:", wallet, repr(error))

        cutoff = min(day_end, datetime.now(timezone.utc))
        try:
            unrealized = calculate_unrealized(wallet_fills, cutoff)
        except Exception as error:
            print("Unrealized calculation failed:", wallet, repr(error))
            unrealized = 0.0

        pnl = realized - fees + funding + unrealized

        conn.execute("""
            INSERT OR REPLACE INTO daily
            (day,wallet,volume,realized,fees,funding,unrealized,pnl,updated)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            day_start.date().isoformat(),
            wallet,
            volume,
            realized,
            fees,
            funding,
            unrealized,
            pnl,
            updated,
        ))

    conn.commit()
    conn.close()

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
        days = 7
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

def build_daily(day):
    daily = get_daily_data()
    source = daily.get(day, {})

    volumes = {w: source.get(w, {}).get("volume", 0.0) for w in WALLETS}
    pnls = {w: source.get(w, {}).get("pnl", 0.0) for w in WALLETS}

    vp = ranking_points(volumes)
    pp = ranking_points(pnls, positive_only=True)

    rows = []
    for wallet in WALLETS:
        rows.append({
            "wallet": wallet,
            "username": USERNAMES.get(wallet, ""),
            "volume": volumes[wallet],
            "pnl": pnls[wallet],
            "volume_points": vp[wallet],
            "pnl_points": pp[wallet],
        })
    return rows

def refresh_worker():
    print("Origami competition worker running:", len(WALLETS), "wallets")
    while True:
        try:
            now = datetime.now(timezone.utc)
            if now >= COMPETITION_START:
                day = COMPETITION_START
                while day < COMPETITION_END and day < now:
                    end = day + timedelta(days=1)
                    query_end = min(end, now)

                    # Completed days are stored once; the current day is
                    # refreshed on every cycle.
                    conn = db_connect()
                    existing = conn.execute(
                        "SELECT COUNT(*) FROM daily WHERE day=?",
                        (day.date().isoformat(),),
                    ).fetchone()[0]
                    conn.close()

                    if end <= now and existing == len(WALLETS):
                        day += timedelta(days=1)
                        continue

                    print(
                        "Fetching",
                        day.date(),
                        "->",
                        utc_iso(query_end),
                    )

                    fills = fetch_builder_fills(day, query_end)
                    calculate_day(day, end, fills)
                    day += timedelta(days=1)

        except Exception as error:
            print("REFRESH ERROR:", repr(error))

        time.sleep(REFRESH_SECONDS)

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
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0 10px}
.daytabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px}
.streamtabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}
button{border:1px solid #222a36;background:#111720;color:#dce2eb;border-radius:10px;padding:10px 14px;cursor:pointer}
button.active{background:#f0f3f7;color:#080b10}
.card{background:#0e131b;border:1px solid #222a36;border-radius:16px;overflow:hidden}
.notice{margin:18px 0;padding:14px;border:1px solid #222a36;border-radius:12px;color:#aab3c1;font-size:13px;line-height:1.6}
.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:850px}
th,td{padding:13px 12px;border-bottom:1px solid #222a36;text-align:left}
th{font-size:12px;color:#8993a5;text-transform:uppercase}.right{text-align:right}
.pos{color:#39e29a}.neg{color:#ff657d}.wallet{font-size:11px;color:#697487;margin-top:3px}
.titlebar{margin:8px 0 14px;font-size:18px;font-weight:700}
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
<b>Two independent streams:</b> Volume and PnL.<br>
<b>Volume:</b> all Origami-builder perp fills count by executed notional (price × size), including opening and closing trades.<br>
<b>PnL:</b> net profit includes trading fees, matched funding and the historical unrealized-PnL proxy.<br>
<b>Scoring:</b> each day top 5 earn 10 / 8 / 6 / 4 / 2 points. Weekly totals are ranked separately. Final score = 80% × average daily points + 20% × weekly points. All seven days count, including zero-point days.<br>
<b>PnL qualification:</b> at least $20,000 weekly volume and positive weekly net PnL are required for the PnL prize.
</div>

<div class="tabs" id="weeklyTabs"></div>
<div class="daytabs" id="dayTabs"></div>
<div class="streamtabs" id="streamTabs"></div>
<div class="titlebar" id="leaderTitle"></div>

<div class="card"><div class="table-wrap"><table>
<thead id="thead"></thead>
<tbody id="body"></tbody>
</table></div></div>
</div>

<script>
let selectedDay="2026-10-02";
let stream="volume";
let mode="volume-weekly";

const days=[
["2026-10-02","Oct 2"],["2026-10-03","Oct 3"],["2026-10-04","Oct 4"],
["2026-10-05","Oct 5"],["2026-10-06","Oct 6"],["2026-10-07","Oct 7"],
["2026-10-08","Oct 8"]
];

function button(label,id,active,onclick){
 const b=document.createElement("button");
 b.textContent=label;
 if(active)b.className="active";
 b.onclick=onclick;
 return b;
}

const wt=document.getElementById("weeklyTabs");
wt.appendChild(button("🏆 Volume Weekly","volume-weekly",true,()=>selectWeekly("volume")));
wt.appendChild(button("💰 PnL Weekly","pnl-weekly",false,()=>selectWeekly("pnl")));

const dt=document.getElementById("dayTabs");
for(const [d,label] of days){
 dt.appendChild(button(label,d,d===selectedDay,()=>selectDay(d)));
}

function selectWeekly(s){
 stream=s; mode=s+"-weekly";
 document.querySelectorAll("#weeklyTabs button").forEach((b,i)=>b.classList.toggle("active",i===(s==="volume"?0:1)));
 document.querySelectorAll("#dayTabs button").forEach(b=>b.classList.remove("active"));
 document.getElementById("streamTabs").innerHTML="";
 load();
}

function selectDay(d){
 selectedDay=d;
 mode="day-"+d+"-"+stream;
 document.querySelectorAll("#dayTabs button").forEach(b=>b.classList.toggle("active",b.textContent===days.find(x=>x[0]===d)[1]));
 document.querySelectorAll("#weeklyTabs button").forEach(b=>b.classList.remove("active"));
 renderStreamTabs();
 load();
}

function renderStreamTabs(){
 const st=document.getElementById("streamTabs");
 st.innerHTML="";
 st.appendChild(button("📊 Volume", "volume", stream==="volume",()=>{stream="volume";mode="day-"+selectedDay+"-volume";renderStreamTabs();load();}));
 st.appendChild(button("💰 PnL", "pnl", stream==="pnl",()=>{stream="pnl";mode="day-"+selectedDay+"-pnl";renderStreamTabs();load();}));
}

renderStreamTabs();

function money(x){return Number(x||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});}
function short(x){return x.slice(0,6)+"…"+x.slice(-4)}
function esc(x){return String(x||"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");}

function renderTable(rows,isPnl){
 const thead=document.getElementById("thead");
 const title=document.getElementById("leaderTitle");
 if(isPnl){
   title.textContent="💰 PnL Leaderboard";
   thead.innerHTML=`<tr><th>Rank</th><th>Trader</th><th>Username</th><th class="right">PnL</th><th class="right">Daily Pts</th><th class="right">Weekly Pts</th><th class="right">Final Score</th></tr>`;
 }else{
   title.textContent="📊 Volume Leaderboard";
   thead.innerHTML=`<tr><th>Rank</th><th>Trader</th><th>Username</th><th class="right">Volume</th><th class="right">Daily Pts</th><th class="right">Weekly Pts</th><th class="right">Final Score</th></tr>`;
 }
 document.getElementById("body").innerHTML=rows.map((x,i)=>{
   const score=Number(x.final_score||0), pnl=Number(x.pnl||0), volume=Number(x.volume||0);
   const main=isPnl?pnl:volume;
   return `<tr>
   <td><b>${i+1}</b></td>
   <td><b>${esc(x.username||"Anonymous Trader")}</b><div class="wallet">${short(x.wallet)}</div></td>
   <td>${esc(x.username||"—")}</td>
   <td class="right ${isPnl?(pnl>=0?"pos":"neg"):""}">${isPnl?(pnl>=0?"+":"-")+"$"+money(Math.abs(main)):"$"+money(main)}</td>
   <td class="right">${x.daily_points??0}</td>
   <td class="right">${x.weekly_points??0}</td>
   <td class="right"><b>${money(score)}</b></td>
   </tr>`;
 }).join("");
}

async function load(){
 try{
  const r=await fetch("/data?mode="+encodeURIComponent(mode)+"&x="+Date.now());
  const d=await r.json();
  document.getElementById("status").textContent="Updated "+new Date().toLocaleTimeString();
  renderTable(d.rows,stream==="pnl");
 }catch(e){
  document.getElementById("body").innerHTML="<tr><td colspan='7'>"+esc(e.message)+"</td></tr>";
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
                weekly = build_weekly()
                rows = []
                is_pnl = mode == "pnl-weekly"
                for row in weekly:
                    rows.append({
                        "wallet": row["wallet"],
                        "username": row["username"],
                        "volume": row["volume"],
                        "pnl": row["pnl"],
                        "daily_points": 0,
                        "weekly_points": row["weekly_pnl_points"] if is_pnl else row["weekly_volume_points"],
                        "final_score": row["pnl_final"] if is_pnl else row["volume_final"],
                        "pnl_eligible": row.get("pnl_eligible", False),
                    })
                rows.sort(key=lambda x: x["final_score"], reverse=True)

            elif mode.startswith("day-"):
                parts = mode.split("-")
                # mode is day-YYYY-MM-DD-volume or day-YYYY-MM-DD-pnl
                day = "-".join(parts[1:4])
                is_pnl = parts[4] == "pnl"
                stream_rows = build_daily(day)
                rows = []
                for row in stream_rows:
                    rows.append({
                        "wallet": row["wallet"],
                        "username": row["username"],
                        "volume": row["volume"],
                        "pnl": row["pnl"],
                        "daily_points": row["pnl_points"] if is_pnl else row["volume_points"],
                        "weekly_points": 0,
                        "final_score": row["pnl_points"] if is_pnl else row["volume_points"],
                    })
                rows.sort(key=lambda x: (x["pnl"] if is_pnl else x["volume"]), reverse=True)

            else:
                rows = []

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
