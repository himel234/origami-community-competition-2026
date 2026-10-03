import os
import requests

API_KEY = os.getenv("CMM_API_KEY")

if not API_KEY:
    print("ERROR: CMM_API_KEY is not set in Render.")
    raise SystemExit(1)

BASE_URL = "https://ht-api.coinmarketman.com/api/external"

WALLET = "0x28d6dda751db999b991ed169bb773e8e855c36c2"

url = f"{BASE_URL}/positions"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
}

params = [
    ("start", "2026-10-02T00:00:00.000Z"),
    ("end", "2026-10-03T00:00:00.000Z"),
    ("address[]", WALLET),
    ("limit", "100"),
]

print("======================================")
print("Testing Historical Positions API")
print("======================================")
print("Wallet:", WALLET)
print("Time: 2026-10-02 00:00 UTC -> 2026-10-03 00:00 UTC")
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
