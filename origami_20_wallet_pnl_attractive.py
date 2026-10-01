from pathlib import Path

code = r'''import os
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

# ============================================================
# HYPERLIQUID COMMUNITY TRADING COMPETITION
# 2 Oct 2026 00:00 UTC -> 9 Oct 2026 00:00 UTC
# ============================================================

DATA_URL = (
    "https://dw3ji7n7thadj.cloudfront.net/aggregator/builders/"
    "0x9b451f8941240db8bedc99bff8917a2ed9550074_v2.json"
)

START = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)

REFRESH_SECONDS = 30
DB_FILE = "origami_competition.sqlite3"
POINTS = [10, 8, 6, 4, 2]

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
    "0x28d6dda751db999b991ed169bb773e8e855c36c2": "@shamim215",
    "0x6188c0c04bd502541b77d8cd43667944437b3eda": "@puperet",
    "0x6e5234204cd2015baf121b6934eab4d4f40a07ce": "",
    "0xfff111cdc96472c137596a91d001fd870557501c": "@BARYSBYEK",
    "0x14280d8e1a1e490a3665563479e581280d32e441": "",
    "0xfcb4dbcb3dbe57f02f4a5fa603a1da948f549673": "@himel234",
    "0xbfbbb7a23d740648547f11797de7c157af81cac8": "",
    "0xbf787b37c4db340088b154e3c343f4d94508ac8c": "@tomtop",
    "0x7e2df435ffaa20800713a1f1e770c1b093bacda5": "",
    "0xe254c53e776bb1b434f9d81bc93c246d08069bd6": "",
    "0x097e0a249c065e279ec08ea021cff3dd11c32d41": "@abshamweb3",
    "0x8c641e56994b18b18d9bc754655c2892b80b3315": "",
    "0xb29b8367e3a07928d5aa788bd9137d8c416e65ae": "@madikpeju",
    "0x6f23925a69097b2ac7bf67e24b68cbb6382ca656": "",
    "0x28a97f53f11becbb1d531ed26a953cba87d115c8": "@Edward6742",
    "0x03a506eb9548fd844f60e65b35e56e5472f70c00": "",
    "0x4137bff4666989e877ade32e09ba8035cb0b1359": "",
    "0x88a30b45ca1fe48898675c6e4420b0090b0eba5e": "",
    "0x779c0a1345375b21839e4053419d9fdd6a432cce": "",
    "0x94aa8c596c405ac056e5caa2f08870c947a98e2a": "",
    "0x7f2663fc903d269a9670ce5ad76d92f7a0b70e66": "@Safal818",
    "0x8a591916b925c399a4d2791d186dfae5366cc12a": "@Eleonore3663",
}

# ============================================================
# DATABASE
# ============================================================

DB = sqlite3.connect(DB_FILE, check_same_thread=False)
DB.execute("""
CREATE TABLE IF NOT EXISTS daily_snapshots (
    day TEXT NOT NULL,
    wallet TEXT NOT NULL,
    volume REAL NOT NULL,
    pnl REAL NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(day, wallet)
)
""")
DB.commit()
DB_LOCK = threading.Lock()


def num(obj, names):
    for name in names:
        if isinstance(obj, dict) and obj.get(name) is not None:
            try:
                return float(obj[name])
            except (TypeError, ValueError):
                pass
    return 0.0


def normalize_users(raw):
    out = {}

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            address = (
                item.get("address")
                or item.get("user")
                or item.get("wallet")
                or item.get("addr")
            )
            if isinstance(address, str) and len(address) == 42:
                out[address.lower()] = item

    elif isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(key, str) and len(key) == 42 and key.startswith("0x"):
                out[key.lower()] = value if isinstance(value, dict) else {}
            elif isinstance(value, dict):
                address = (
                    value.get("address")
                    or value.get("user")
                    or value.get("wallet")
                    or value.get("addr")
                )
                if isinstance(address, str) and len(address) == 42:
                    out[address.lower()] = value

    return out


def find_users(data):
    if isinstance(data, dict):
        users = data.get("users")

        if isinstance(users, dict):
            raw = users.get("24h")
            if raw is not None:
                return normalize_users(raw)

        raw = data.get("24h")
        if isinstance(raw, dict):
            if isinstance(raw.get("users"), (dict, list)):
                return normalize_users(raw["users"])
            return normalize_users(raw)

    return {}


def fetch_24h():
    response = requests.get(DATA_URL, timeout=30)
    response.raise_for_status()
    return find_users(response.json())


def save_snapshot(day_index, users):
    day = (START.date() + timedelta(days=day_index)).isoformat()
    captured = datetime.now(timezone.utc).isoformat()

    with DB_LOCK:
        for wallet in WALLETS:
            user = users.get(wallet, {})
            volume = num(user, ["volume"])
            pnl = num(user, ["pnl"])

            DB.execute(
                """
                INSERT OR REPLACE INTO daily_snapshots
                (day, wallet, volume, pnl, captured_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (day, wallet, volume, pnl, captured),
            )
        DB.commit()


def capture_finished_days(users):
    now = datetime.now(timezone.utc)

    for i in range(7):
        cutoff = START + timedelta(days=i + 1)

        if now < cutoff:
            continue

        day = (START.date() + timedelta(days=i)).isoformat()

        with DB_LOCK:
            exists = DB.execute(
                "SELECT 1 FROM daily_snapshots WHERE day=? LIMIT 1",
                (day,),
            ).fetchone()

        if not exists:
            save_snapshot(i, users)
            print(f"Saved snapshot for {day}")


def data_loop():
    while True:
        try:
            users = fetch_24h()
            if users:
                capture_finished_days(users)
        except Exception as exc:
            print("Data update error:", exc)

        time.sleep(REFRESH_SECONDS)


threading.Thread(target=data_loop, daemon=True).start()

# ============================================================
# SCORING
# ============================================================

def get_daily_data():
    result = {}

    with DB_LOCK:
        for i in range(7):
            day = (START.date() + timedelta(days=i)).isoformat()

            result[day] = {
                wallet: {
                    "volume": 0.0,
                    "pnl": 0.0,
                    "captured_at": None,
                }
                for wallet in WALLETS
            }

            rows = DB.execute(
                """
                SELECT wallet, volume, pnl, captured_at
                FROM daily_snapshots
                WHERE day=?
                """,
                (day,),
            ).fetchall()

            for wallet, volume, pnl, captured_at in rows:
                if wallet in result[day]:
                    result[day][wallet] = {
                        "volume": float(volume),
                        "pnl": float(pnl),
                        "captured_at": captured_at,
                    }

    return result


def rank_points(values, positive_only=False):
    eligible = []

    for wallet, value in values.items():
        if positive_only and value <= 0:
            continue
        eligible.append((wallet, value))

    eligible.sort(key=lambda item: item[1], reverse=True)

    points = {wallet: 0 for wallet in values}

    for index, (wallet, _) in enumerate(eligible[:5]):
        points[wallet] = POINTS[index]

    return points


def build_standings():
    days = get_daily_data()

    result = {
        wallet: {
            "wallet": wallet,
            "username": USERNAMES.get(wallet, ""),
            "daily_volume_points": [],
            "daily_pnl_points": [],
            "volume": 0.0,
            "pnl": 0.0,
        }
        for wallet in WALLETS
    }

    for i in range(7):
        day = (START.date() + timedelta(days=i)).isoformat()

        volume_values = {
            wallet: days[day][wallet]["volume"]
            for wallet in WALLETS
        }

        pnl_values = {
            wallet: days[day][wallet]["pnl"]
            for wallet in WALLETS
        }

        volume_points = rank_points(volume_values)
        pnl_points = rank_points(pnl_values, positive_only=True)

        for wallet in WALLETS:
            result[wallet]["daily_volume_points"].append(volume_points[wallet])
            result[wallet]["daily_pnl_points"].append(pnl_points[wallet])
            result[wallet]["volume"] += volume_values[wallet]
            result[wallet]["pnl"] += pnl_values[wallet]

    weekly_volume_points = rank_points(
        {w: result[w]["volume"] for w in WALLETS}
    )

    weekly_pnl_points = rank_points(
        {w: result[w]["pnl"] for w in WALLETS},
        positive_only=True,
    )

    for wallet in WALLETS:
        dv = result[wallet]["daily_volume_points"]
        dp = result[wallet]["daily_pnl_points"]

        result[wallet]["volume_avg_daily"] = sum(dv) / 7
        result[wallet]["pnl_avg_daily"] = sum(dp) / 7

        result[wallet]["volume_weekly_points"] = weekly_volume_points[wallet]
        result[wallet]["pnl_weekly_points"] = weekly_pnl_points[wallet]

        result[wallet]["volume_final_score"] = (
            0.8 * result[wallet]["volume_avg_daily"]
            + 0.2 * weekly_volume_points[wallet]
        )

        result[wallet]["pnl_final_score"] = (
            0.8 * result[wallet]["pnl_avg_daily"]
            + 0.2 * weekly_pnl_points[wallet]
        )

        result[wallet]["pnl_qualified"] = (
            result[wallet]["volume"] >= 20000
            and result[wallet]["pnl"] > 0
        )

    volume_rank = sorted(
        result.values(),
        key=lambda x: (-x["volume_final_score"], -x["volume"]),
    )

    # Qualified PnL participants are ranked first.
    # Unqualified participants remain visible below them.
    pnl_rank = sorted(
        result.values(),
        key=lambda x: (
            0 if x["pnl_qualified"] else 1,
            -x["pnl_final_score"],
            -x["pnl"],
        ),
    )

    return days, volume_rank, pnl_rank

# ============================================================
# WEBSITE
# ============================================================

HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Origami × Hyperliquid Community Competition</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#07090d;--panel:#0d1118;--line:#202734;--text:#f4f7fb;--muted:#8993a5;--green:#36e29a;--red:#ff647c;--gold:#f5c76a}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,sans-serif;color:var(--text);background:radial-gradient(circle at 50% -10%,rgba(54,226,154,.12),transparent 35%),var(--bg)}
.wrap{max-width:1320px;margin:auto;padding:26px 18px 55px}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}
.brand{display:flex;align-items:center;gap:12px}.logo{width:42px;height:42px;border-radius:13px;display:grid;place-items:center;background:linear-gradient(135deg,#1be395,#0f8d62);color:#06100c;font-weight:900;font-size:21px}.brand h1{font-size:19px;margin:0}.brand p{margin:3px 0 0;color:var(--muted);font-size:11px}
.live{display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--line);border-radius:999px;font-size:11px;color:#b8c1d0}.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 10px var(--green)}
.hero{border:1px solid var(--line);border-radius:22px;padding:25px;background:linear-gradient(145deg,#121822,#090c11);margin-bottom:16px}
.kicker{font-size:11px;color:var(--green);font-weight:800;letter-spacing:1.5px;text-transform:uppercase}.hero h2{font-size:29px;margin:8px 0 5px}.hero p{margin:0;color:var(--muted);font-size:13px}
.dates{margin-top:17px;display:flex;gap:9px;flex-wrap:wrap}.date{border:1px solid var(--line);border-radius:12px;padding:10px 12px;font-size:11px}.date b{display:block;font-size:13px}.date span{color:var(--muted)}
.stats{display:flex;gap:9px;flex-wrap:wrap;margin-top:18px}.stat{min-width:125px;padding:12px 14px;border:1px solid var(--line);border-radius:14px}.stat b{display:block;font-size:17px}.stat span{display:block;color:var(--muted);font-size:10px;margin-top:3px;text-transform:uppercase}
.streams{display:flex;gap:8px;margin:17px 0 12px}.stream{border:1px solid var(--line);background:var(--panel);color:var(--muted);padding:10px 18px;border-radius:11px;cursor:pointer;font-weight:850;font-size:12px}.stream.active{background:#eafcf5;color:#07110d}
.daytabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:15px}.day{border:1px solid var(--line);background:transparent;color:var(--muted);padding:8px 11px;border-radius:9px;cursor:pointer;font-weight:800;font-size:10px}.day.active{color:var(--text);background:#151b25}
.panel{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:rgba(13,17,24,.92)}.panelHead{padding:17px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between}.panelHead h3{margin:0;font-size:14px}.panelHead span{color:var(--muted);font-size:10px}
table{width:100%;border-collapse:collapse}th{background:#0a0e14;color:#687385;font-size:9px;letter-spacing:1px;text-transform:uppercase}th,td{padding:13px 11px;border-bottom:1px solid #191f29;text-align:right}th:first-child,td:first-child{text-align:center}th:nth-child(2),td:nth-child(2){text-align:left}
.rank{font-weight:900;color:#9da8b8}.rank.top{color:var(--gold)}.trader{display:flex;align-items:center;gap:9px}.avatar{width:31px;height:31px;border-radius:9px;display:grid;place-items:center;background:#161d28;border:1px solid #27303e;font-size:10px;font-weight:900}.name{font-weight:750;font-size:12px}.wallet{font:9px monospace;color:#697487;margin-top:3px}.num{font-variant-numeric:tabular-nums;font-weight:700;font-size:11px}.score{font-size:13px;font-weight:900;color:var(--green)}.pos{color:var(--green);font-weight:900}.neg{color:var(--red);font-weight:900}.qual{font-size:9px;font-weight:900;padding:4px 7px;border-radius:7px}.yes{background:rgba(54,226,154,.1);color:var(--green)}.no{background:rgba(255,100,124,.1);color:var(--red)}
.note{margin-top:12px;color:#697487;font-size:10px;line-height:1.6}.err{padding:16px;border:1px solid rgba(255,100,124,.25);background:rgba(255,100,124,.07);color:#ff9aaa;border-radius:13px}.footer{display:flex;justify-content:space-between;color:#566172;font-size:10px;margin-top:14px}
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
const START=new Date("2026-10-02T00:00:00Z");
let STREAM="volume",DAY="overall",STATE=null;

const money=x=>Number(x||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const safe=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const short=a=>a.slice(0,6)+"..."+a.slice(-4);
const avatar=(n,a)=>safe((n||a.slice(2,4)).slice(0,2).toUpperCase());

function setStream(s){
STREAM=s;
document.getElementById("volBtn").classList.toggle("active",s==="volume");
document.getElementById("pnlBtn").classList.toggle("active",s==="pnl");
render();
}

function setDay(d){
DAY=d;
document.querySelectorAll(".day").forEach(x=>x.classList.toggle("active",x.dataset.day===d));
render();
}

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

let rows=STREAM==="volume"?STATE.volume:STATE.pnl;

if(DAY!=="overall"){
const d=STATE.days[DAY]||{};
rows=rows.map(x=>{
const q=d[x.wallet]||{volume:0,pnl:0,volume_points:0,pnl_points:0};
const dayPoints=STREAM==="volume"?q.volume_points:q.pnl_points;
return {...x,metric:STREAM==="volume"?q.volume:q.pnl,dayPoints};
}).sort((a,b)=>b.metric-a.metric);
}

const title=STREAM==="volume"?"Volume Leaderboard":"PnL Leaderboard";
const metric=STREAM==="volume"?"Executed Volume":"Net PnL";

let head=DAY==="overall"
?`<th>Daily Avg</th><th>Weekly Pts</th><th>Final Score</th><th>${metric}</th>${STREAM==="pnl"?"<th>Qualification</th>":""}`
:`<th>Points</th><th>${metric}</th><th>Daily Rank</th>`;

let body=rows.map((x,i)=>{
const value=DAY==="overall"?(STREAM==="volume"?x.volume:x.pnl):x.metric;
const score=DAY==="overall"?x.final_score:x.dayPoints;
const positive=value>=0;

return `<tr>
<td><span class="rank ${i<3?"top":""}">${i<3?["🥇","🥈","🥉"][i]:i+1}</span></td>
<td><div class="trader"><div class="avatar">${avatar(x.username,x.wallet)}</div><div><div class="name">${safe(x.username||"Anonymous Trader")}</div><div class="wallet">${short(x.wallet)}</div></div></div></td>
${DAY==="overall"
?`<td class="num">${money(x.avg_daily)}</td>
<td class="num">${x.weekly_points}</td>
<td class="score">${score.toFixed(2)}</td>
<td class="${STREAM==="pnl"?(positive?"pos":"neg"):"num"}">${STREAM==="pnl"?(positive?"+":"-")+"$"+money(Math.abs(value)):"$"+money(value)}</td>
${STREAM==="pnl"?`<td><span class="qual ${x.qualified?"yes":"no"}">${x.qualified?"QUALIFIED":"NOT QUALIFIED"}</span></td>`:""}`
:`<td class="score">${score}</td>
<td class="${STREAM==="pnl"?(positive?"pos":"neg"):"num"}">${STREAM==="pnl"?(positive?"+":"-")+"$"+money(Math.abs(value)):"$"+money(value)}</td>
<td class="num">#${i+1}</td>`}
</tr>`;
}).join("");

document.getElementById("out").innerHTML=`
<section class="panel">
<div class="panelHead">
<h3>${title} · ${DAY==="overall"?"FINAL SCORING":"DAY "+(Object.keys(STATE.days).indexOf(DAY)+1)}</h3>
<span>${DAY==="overall"?"80% daily average + 20% weekly points":"10 / 8 / 6 / 4 / 2 points"}</span>
</div>
<table><thead><tr><th>Rank</th><th>Trader</th>${head}</tr></thead><tbody>${body}</tbody></table>
</section>
<div class="note">
${STREAM==="volume"
?"Volume stream: both opening and closing trades count. Profitability does not affect eligibility."
:"PnL stream: only positive daily PnL earns daily points. PnL prize qualification requires at least $20,000 weekly volume and positive weekly net PnL."}
</div>`;
}

async function load(){
try{
const r=await fetch("/state?x="+Date.now());
if(!r.ok)throw new Error("Leaderboard data request failed.");
STATE=await r.json();
render();
}catch(e){
document.getElementById("out").innerHTML=`<div class="err">${safe(e.message)}</div>`;
}
}

renderDays();
load();
setInterval(load,30000);
</script>
</body>
</html>
"""

# ============================================================
# HTTP SERVER
# ============================================================

def pack(rows, stream):
    result = []

    for row in rows:
        result.append({
            "wallet": row["wallet"],
            "username": row["username"],
            "volume": row["volume"],
            "pnl": row["pnl"],
            "avg_daily": (
                row["volume_avg_daily"]
                if stream == "volume"
                else row["pnl_avg_daily"]
            ),
            "weekly_points": (
                row["volume_weekly_points"]
                if stream == "volume"
                else row["pnl_weekly_points"]
            ),
            "final_score": (
                row["volume_final_score"]
                if stream == "volume"
                else row["pnl_final_score"]
            ),
            "qualified": (
                True if stream == "volume"
                else row["pnl_qualified"]
            ),
        })

    return result


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/state"):
            try:
                days, volume_rank, pnl_rank = build_standings()

                out_days = {}
                days_done = 0

                for i in range(7):
                    day = (START.date() + timedelta(days=i)).isoformat()

                    if any(
                        item["captured_at"]
                        for item in days[day].values()
                    ):
                        days_done += 1

                    volume_values = {
                        w: days[day][w]["volume"]
                        for w in WALLETS
                    }

                    pnl_values = {
                        w: days[day][w]["pnl"]
                        for w in WALLETS
                    }

                    volume_points = rank_points(volume_values)
                    pnl_points = rank_points(
                        pnl_values,
                        positive_only=True,
                    )

                    out_days[day] = {}

                    for wallet in WALLETS:
                        out_days[day][wallet] = {
                            "volume": volume_values[wallet],
                            "pnl": pnl_values[wallet],
                            "volume_points": volume_points[wallet],
                            "pnl_points": pnl_points[wallet],
                        }

                payload = {
                    "now": datetime.now(timezone.utc).isoformat(),
                    "days_done": days_done,
                    "volume": pack(volume_rank, "volume"),
                    "pnl": pack(pnl_rank, "pnl"),
                    "days": out_days,
                }

                raw = json.dumps(payload).encode()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(raw)

            except Exception as exc:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(str(exc).encode())

        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())

    def log_message(self, format, *args):
        return


HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8765"))

server = HTTPServer((HOST, PORT), Handler)

print(
    f"Starting Origami competition leaderboard on "
    f"{HOST}:{PORT}"
)
print("Competition: 2 Oct 2026 00:00 UTC -> 9 Oct 2026 00:00 UTC")
print("Refresh: 30 seconds")

try:
    server.serve_forever()
except KeyboardInterrupt:
    server.server_close()
'''

path = Path("/mnt/data/origami_20_wallet_pnl_attractive.py")
path.write_text(code, encoding="utf-8")

# Syntax check
compile(code, str(path), "exec")

print("Corrected code created and syntax-checked successfully.")
print(f"File: {path}")

