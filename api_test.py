import os
import requests

API_KEY = os.getenv("CMM_API_KEY")

if not API_KEY:
    print("ERROR: CMM_API_KEY is not set in Render.")
    raise SystemExit(1)

BASE_URL = "https://ht-api.coinmarketman.com/api/external"

BUILDER = "0x9b451f8941240db8bedc99bff8917a2ed9550074"

WALLET = "0x28d6dda751db999b991ed169bb773e8e855c36c2"

url = f"{BASE_URL}/builders/{BUILDER}/fills"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
}

params = {
    "start": "2026-10-02T00:00:00.000Z",
    "end": "2026-10-03T00:00:00.000Z",
    "address[]": WALLET,
    "fillType": "perp",
    "limit": 500,
}

print("======================================")
print("Testing HyperTracker Builder Fills API")
print("======================================")
print("Builder:", BUILDER)
print("Wallet:", WALLET)
print("Competition day:")
print("2026-10-02 00:00 UTC -> 2026-10-03 00:00 UTC")
print()

try:
    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=60,
    )

    print("HTTP STATUS:", response.status_code)
    print()

    print("REQUEST URL:")
    print(response.url)
    print()

    print("RESPONSE:")
    print(response.text[:30000])

except Exception as e:
    print("REQUEST ERROR:", repr(e))
