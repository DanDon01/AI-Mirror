"""Diagnose the Realtime voice connection.

Checks the OpenAI key, which realtime models the account can use, and
whether the WebSocket handshake succeeds. Run on the Pi:

    ./venv/bin/python voice_diag.py
"""
import json
import os
import sys

from dotenv import load_dotenv

_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_DIR, "..", "Variables.env"))

key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_VOICE_KEY")
if not key:
    print("FAIL: no OPENAI_API_KEY in Variables.env")
    sys.exit(1)
print(f"Key: {key[:7]}...{key[-4:]} (len {len(key)})")

import requests

try:
    r = requests.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {key}"}, timeout=15,
    )
    print(f"GET /v1/models -> {r.status_code}")
    if r.status_code == 200:
        ids = [m["id"] for m in r.json().get("data", [])]
        rt = sorted(i for i in ids if "realtime" in i)
        print("Realtime models available:", rt or "(NONE)")
    else:
        print("Body:", r.text[:300])
except Exception as e:
    print("REST error:", e)

import websocket

candidates = [
    "gpt-realtime", "gpt-realtime-mini", "gpt-realtime-2",
    "gpt-realtime-1.5", "gpt-4o-realtime-preview", "gpt-4o-mini-realtime-preview",
]
print("\nTrying realtime models:")
for model in candidates:
    url = f"wss://api.openai.com/v1/realtime?model={model}"
    try:
        ws = websocket.create_connection(
            url, header=[f"Authorization: Bearer {key}"], timeout=12,
        )
        data = json.loads(ws.recv())
        if data.get("type") == "session.created":
            print(f"  OK    {model}  -> session.created")
        else:
            err = data.get("error", {})
            print(f"  error {model}  -> {err.get('code')}: {err.get('message')}")
        ws.close()
    except Exception as e:
        print(f"  FAIL  {model}  -> {type(e).__name__}: {e}")
