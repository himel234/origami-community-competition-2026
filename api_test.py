import os
import requests

API_KEY = os.getenv("CMM_API_KEY")

if not API_KEY:
    print("ERROR: CMM_API_KEY is not set")
    raise SystemExit(1)

print("API key found.")

# We will test the documented API base first.
BASE_URL = "https://api.hypertracker.io"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
}

url = f"{BASE_URL}/builders/0x9b451f8941240db8bedc99bff8917a2ed9550074/fills"

params = {
    "start": "2026-10-02T00:00:00Z",
    "end": "2026-10-02T01:00:00Z",
    "address": "0x28d6dda751db999b991ed169bb773e8e855c36c2",
}

print("Testing:", url)

try:
    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30,
    )

    print("HTTP STATUS:", response.status_code)
    print("RESPONSE:")
    print(response.text[:5000])

except Exception as e:
    print("REQUEST ERROR:", repr(e))
