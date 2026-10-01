import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import requests


# ============================================================
# SETTINGS
# ============================================================

DATA_URL = "https://dw3ji7n7thadj.cloudfront.net/aggregator/builders/0x9b451f8941240db8bedc99bff8917a2ed9550074_v2.json"


# ============================================================
# USERNAMES
#
# THIS IS THE ONLY PART YOU NEED TO EDIT FOR USERNAMES.
#
# Example:
#     "0xfcb4...": "Sami",
#
# Leave "" if you don't want a username yet.
# ============================================================

USERNAMES = {
    "0x28d6dda751db999b991ed169bb773e8e855c36c2": "",
    "0x6188c0c04bd502541b77d8cd43667944437b3eda": "",
    "0x6e5234204cd2015baf121b6934eab4d4f40a07ce": "",
    "0xfff111cdc96472c137596a91d001fd870557501c": "",
    "0x14280d8e1a1e490a3665563479e581280d32e441": "",
    "0xfcb4dbcb3dbe57f02f4a5fa603a1da948f549673": "",
    "0xbfbbb7a23d740648547f11797de7c157af81cac8": "",
    "0xbf787b37c4db340088b154e3c343f4d94508ac8c": "",
    "0x7e2df435ffaa20800713a1f1e770c1b093bacda5": "",
    "0xe254c53e776bb1b434f9d81bc93c246d08069bd6": "",
    "0x097e0a249c065e279ec08ea021cff3dd11c32d41": "",
    "0x8c641e56994b18b18d9bc754655c2892b80b3315": "",
    "0xb29b8367e3a07928d5aa788bd9137d8c416e65ae": "",
    "0x6f23925a69097b2ac7bf67e24b68cbb6382ca656": "",
    "0x28a97f53f11becbb1d531ed26a953cba87d115c8": "",
    "0x03a506eb9548fd844f60e65b35e56e5472f70c00": "",
    "0x4137bff4666989e877ade32e09ba8035cb0b1359": "",
    "0x88a30b45ca1fe48898675c6e4420b0090b0eba5e": "",
    "0x779c0a1345375b21839e4053419d9fdd6a432cce": "",
    "0x94aa8c596c405ac056e5caa2f08870c947a98e2a": "",
}


# ============================================================
# WALLETS
# ============================================================

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
]


# ============================================================
# WEBSITE
# ============================================================

WALLETS_JSON = json.dumps(WALLETS)
USERNAMES_JSON = json.dumps(USERNAMES)

HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Origami Trading Leaderboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{
  --bg:#07090d;
  --panel:#0d1118;
  --panel2:#111722;
  --line:#202734;
  --text:#f4f7fb;
  --muted:#8993a5;
  --green:#36e29a;
  --red:#ff647c;
  --gold:#f5c76a;
}
*{box-sizing:border-box}
body{
  margin:0;
  font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  color:var(--text);
  background:
    radial-gradient(circle at 50% -10%,rgba(54,226,154,.12),transparent 35%),
    radial-gradient(circle at 90% 20%,rgba(91,116,255,.08),transparent 28%),
    var(--bg);
}
.wrap{max-width:1280px;margin:auto;padding:28px 20px 50px}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:28px}
.brand{display:flex;align-items:center;gap:12px}
.logo{
  width:42px;height:42px;border-radius:13px;display:grid;place-items:center;
  background:linear-gradient(135deg,#1be395,#0f8d62);
  color:#06100c;font-weight:900;font-size:21px;
  box-shadow:0 0 30px rgba(54,226,154,.18)
}
.brand h1{font-size:20px;margin:0;letter-spacing:-.4px}
.brand p{margin:3px 0 0;color:var(--muted);font-size:12px}
.live{
  display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--line);
  border-radius:999px;background:rgba(13,17,24,.8);font-size:12px;color:#b8c1d0
}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 10px var(--green)}
.hero{
  border:1px solid var(--line);border-radius:22px;padding:25px;
  background:linear-gradient(145deg,rgba(18,24,34,.95),rgba(9,12,17,.96));
  box-shadow:0 18px 60px rgba(0,0,0,.28);margin-bottom:18px
}
.heroRow{display:flex;justify-content:space-between;align-items:flex-end;gap:20px}
.kicker{font-size:11px;color:var(--green);font-weight:800;letter-spacing:1.6px;text-transform:uppercase}
.hero h2{font-size:30px;margin:8px 0 7px;letter-spacing:-1px}
.hero p{margin:0;color:var(--muted);font-size:13px}
.stats{display:flex;gap:10px;flex-wrap:wrap}
.stat{
  min-width:110px;padding:12px 14px;border:1px solid var(--line);border-radius:14px;
  background:rgba(255,255,255,.02)
}
.stat b{display:block;font-size:17px}.stat span{display:block;color:var(--muted);font-size:10px;margin-top:3px;text-transform:uppercase;letter-spacing:.7px}
.controls{display:flex;justify-content:space-between;align-items:center;gap:15px;margin:18px 0}
.tabs{display:flex;gap:7px;padding:5px;border:1px solid var(--line);border-radius:13px;background:var(--panel)}
button{
  border:0;background:transparent;color:var(--muted);padding:9px 15px;border-radius:9px;
  cursor:pointer;font-weight:800;font-size:11px;letter-spacing:.4px
}
button:hover{color:var(--text)} button.active{background:#eafcf5;color:#07110d}
.status{font-size:11px;color:var(--muted)}
.podium{display:grid;grid-template-columns:1fr 1.08fr 1fr;gap:12px;margin-bottom:18px;align-items:end}
.pod{
  min-height:170px;border:1px solid var(--line);border-radius:18px;padding:20px;
  background:linear-gradient(145deg,#111722,#0c1017);position:relative;overflow:hidden
}
.pod.first{min-height:195px;border-color:rgba(245,199,106,.35);box-shadow:0 0 40px rgba(245,199,106,.05)}
.medal{font-size:22px}.place{font-size:10px;color:var(--muted);font-weight:800;letter-spacing:1px;margin-top:9px}
.podname{font-size:17px;font-weight:850;margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.podwallet{font:11px ui-monospace,SFMono-Regular,Menlo,monospace;color:#687385;margin-top:5px}
.podpnl{font-size:25px;font-weight:900;margin-top:17px}
.pos{color:var(--green)} .neg{color:var(--red)}
.tableWrap{border:1px solid var(--line);border-radius:18px;overflow:hidden;background:rgba(13,17,24,.92)}
table{width:100%;border-collapse:collapse}
th{background:#0a0e14;color:#687385;font-size:10px;letter-spacing:1px;text-transform:uppercase;font-weight:800}
th,td{padding:15px 13px;border-bottom:1px solid #191f29;text-align:right}
tr:last-child td{border-bottom:0}
tbody tr{transition:.15s}
tbody tr:hover{background:rgba(255,255,255,.025)}
th:first-child,td:first-child{text-align:center;width:65px}
th:nth-child(2),td:nth-child(2),th:nth-child(3),td:nth-child(3){text-align:left}
.rank{font-weight:900;color:#9da8b8}
.rank.top{color:var(--gold)}
.trader{display:flex;align-items:center;gap:11px}
.avatar{
  width:34px;height:34px;border-radius:10px;display:grid;place-items:center;
  background:#161d28;border:1px solid #27303e;font-size:11px;font-weight:900;color:#dce3ee
}
.name{font-weight:750;font-size:13px}.wallet{font:10px ui-monospace,SFMono-Regular,Menlo,monospace;color:#697487;margin-top:3px}
.num{font-variant-numeric:tabular-nums;font-weight:700;font-size:12px}
.pnl{font-size:13px;font-weight:900}
.footer{display:flex;justify-content:space-between;color:#566172;font-size:10px;margin-top:14px;padding:0 3px}
.err{padding:16px;border:1px solid rgba(255,100,124,.25);background:rgba(255,100,124,.07);color:#ff9aaa;border-radius:13px}
@media(max-width:850px){
  .heroRow{display:block}.stats{margin-top:18px}
  .podium{grid-template-columns:1fr}
  .pod,.pod.first{min-height:auto}
  .controls{align-items:flex-start;flex-direction:column}
  .tableWrap{overflow-x:auto} table{min-width:850px}
  .topbar{align-items:flex-start}
}
</style>
</head>
<body>
<div class="wrap">

  <div class="topbar">
    <div class="brand">
      <div class="logo">O</div>
      <div>
        <h1>Origami Trading</h1>
        <p>Private competition leaderboard</p>
      </div>
    </div>
    <div class="live"><span class="dot"></span> LIVE DATA</div>
  </div>

  <section class="hero">
    <div class="heroRow">
      <div>
        <div class="kicker">Trading Competition</div>
        <h2>Origami Leaderboard</h2>
        <p>20 selected wallets · ranked by PnL · powered by HyperTracker data</p>
      </div>
      <div class="stats">
        <div class="stat"><b id="walletCount">20</b><span>Traders</span></div>
        <div class="stat"><b id="periodLabel">30D</b><span>Period</span></div>
      </div>
    </div>
  </section>

  <div class="controls">
    <div class="tabs" id="buttons"></div>
    <div id="status" class="status">Loading live data...</div>
  </div>

  <div id="podium" class="podium"></div>
  <div id="out"></div>

  <div class="footer">
    <span>Origami · Selected 20 wallets</span>
    <span>Auto-refresh: 30 seconds</span>
  </div>

</div>

<script>
const WALLETS = new Set(WALLETS_PLACEHOLDER);
const USERNAMES = USERNAMES_PLACEHOLDER;

const money = x => Number(x || 0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
let DATA = null;
let TF = "30d";

function isAddress(s){return typeof s==="string" && /^0x[a-fA-F0-9]{40}$/.test(s)}
function shortWallet(a){return a.slice(0,6)+"..."+a.slice(-4)}
function safe(s){
  return String(s ?? "").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))
}
function findAddressInObject(obj){
  if(!obj || typeof obj!=="object") return null;
  if(isAddress(obj.address)) return obj.address;
  if(isAddress(obj.user)) return obj.user;
  if(isAddress(obj.wallet)) return obj.wallet;
  if(isAddress(obj.addr)) return obj.addr;
  return null;
}
function normalizeUsers(raw){
  const result={}; if(!raw) return result;
  if(Array.isArray(raw)){
    for(const item of raw){const a=findAddressInObject(item);if(a) result[a.toLowerCase()]=item}
    return result;
  }
  if(typeof raw==="object"){
    for(const [key,value] of Object.entries(raw)){
      if(isAddress(key)) result[key.toLowerCase()]=value||{};
      else {const a=findAddressInObject(value);if(a) result[a.toLowerCase()]=value}
    }
  }
  return result;
}
function getUsersForTimeframe(tf){
  if(DATA?.users?.[tf]) return normalizeUsers(DATA.users[tf]);
  if(DATA?.[tf]?.users) return normalizeUsers(DATA[tf].users);
  function walk(x){
    if(!x || typeof x!=="object") return null;
    if(x[tf]) return normalizeUsers(x[tf]);
    for(const v of Object.values(x)){const r=walk(v);if(r && Object.keys(r).length)return r}
    return null;
  }
  return walk(DATA)||{};
}
function getNum(u,names){
  for(const n of names) if(u && u[n]!==undefined && u[n]!==null) return Number(u[n])||0;
  return 0;
}
function avatar(name,address){
  const n=name && name!=="—" ? name : address.slice(2,4);
  return safe(n.slice(0,2).toUpperCase());
}
function renderPodium(rows){
  const el=document.getElementById("podium");
  const top=rows.slice(0,3);
  if(!top.length){el.innerHTML="";return}
  const order=[1,0,2].filter(i=>top[i]);
  const medals=["🥇","🥈","🥉"];
  el.innerHTML=order.map(i=>{
    const x=top[i];
    return `<div class="pod ${i===0?"first":""}">
      <div class="medal">${medals[i]}</div>
      <div class="place">#${i+1} TOP TRADER</div>
      <div class="podname">${safe(x.username==="—"?"Anonymous Trader":x.username)}</div>
      <div class="podwallet">${shortWallet(x.address)}</div>
      <div class="podpnl ${x.pnl>=0?"pos":"neg"}">${x.pnl>=0?"+":"-"}$${money(Math.abs(x.pnl))}</div>
    </div>`;
  }).join("");
}
function render(){
  try{
    const users=getUsersForTimeframe(TF);
    if(!Object.keys(users).length) throw new Error("No user records found for "+TF+".");
    const rows=[];
    for(const address of WALLETS){
      const u=users[address];
      rows.push({
        address:u?.address||u?.user||address,
        username:USERNAMES[address.toLowerCase()]||"—",
        pnl:u?getNum(u,["pnl"]):0,
        closedPnl:u?getNum(u,["closedPnl","closed_pnl"]):0,
        builderFee:u?getNum(u,["builderFee","builder_fee"]):0,
        volume:u?getNum(u,["volume"]):0
      });
    }
    rows.sort((a,b)=>b.pnl-a.pnl);
    renderPodium(rows);

    document.getElementById("out").innerHTML=`<div class="tableWrap"><table>
      <thead><tr><th>Rank</th><th>Trader</th><th>Username</th><th>PnL</th><th>Closed PnL</th><th>Builder Fee</th><th>Volume</th></tr></thead>
      <tbody>${rows.map((x,i)=>`
        <tr>
          <td><span class="rank ${i<3?"top":""}">${i<3?["🥇","🥈","🥉"][i]:i+1}</span></td>
          <td><div class="trader"><div class="avatar">${avatar(x.username,x.address)}</div><div><div class="name">${safe(x.username==="—"?"Anonymous Trader":x.username)}</div><div class="wallet">${shortWallet(x.address)}</div></div></div></td>
          <td>${safe(x.username)}</td>
          <td class="pnl ${x.pnl>=0?"pos":"neg"}">${x.pnl>=0?"+":"-"}$${money(Math.abs(x.pnl))}</td>
          <td class="num">$${money(x.closedPnl)}</td>
          <td class="num">$${money(x.builderFee)}</td>
          <td class="num">$${money(x.volume)}</td>
        </tr>`).join("")}</tbody>
    </table></div>`;

    document.getElementById("status").textContent="20 wallets · "+TF.toUpperCase()+" · updated "+new Date().toLocaleTimeString();
    document.getElementById("periodLabel").textContent=TF.toUpperCase();
  }catch(e){
    document.getElementById("out").innerHTML=`<div class="err">${safe(e.message)}</div>`;
    document.getElementById("podium").innerHTML="";
  }
}
async function load(){
  try{
    const r=await fetch("/data?x="+Date.now());
    if(!r.ok) throw new Error("CoinMarketMan request failed: HTTP "+r.status);
    DATA=await r.json(); render();
  }catch(e){document.getElementById("out").innerHTML=`<div class="err">${safe(e.message)}</div>`}
}
const buttons=document.getElementById("buttons");
["24h","7d","30d","all"].forEach(tf=>{
  const b=document.createElement("button"); b.textContent=tf.toUpperCase();
  if(tf===TF)b.className="active";
  b.onclick=()=>{TF=tf;document.querySelectorAll("#buttons button").forEach(x=>x.classList.remove("active"));b.classList.add("active");render()};
  buttons.appendChild(b);
});
load(); setInterval(load,30000);
</script>
</body>
</html>"""


HTML = HTML.replace("WALLETS_PLACEHOLDER", WALLETS_JSON)
HTML = HTML.replace("USERNAMES_PLACEHOLDER", USERNAMES_JSON)


# ============================================================
# LOCAL SERVER
# ============================================================

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):

        if self.path.startswith("/data"):

            try:
                r = requests.get(DATA_URL, timeout=30)
                r.raise_for_status()

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()

                self.wfile.write(r.content)

            except Exception as e:

                self.send_response(502)
                self.send_header(
                    "Content-Type",
                    "text/plain; charset=utf-8"
                )
                self.end_headers()

                self.wfile.write(str(e).encode())

        else:

            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )
            self.end_headers()

            self.wfile.write(HTML.encode())


# ============================================================
# START
# ============================================================

server = HTTPServer(("127.0.0.1", 8765), Handler)

threading.Timer(
    1,
    lambda: webbrowser.open("http://127.0.0.1:8765")
).start()

print("Opening http://127.0.0.1:8765")
print("Default view: 30D")
print("Refreshes every 30 seconds.")
print("Press Ctrl+C to stop.")

try:
    server.serve_forever()

except KeyboardInterrupt:
    server.server_close()
    print("Stopped.")
