import os
import sys
import httpx
from dotenv import load_dotenv
load_dotenv()

key = os.getenv("GEMINI_API_KEY", "")
model = os.getenv("GEMINI_MODEL", "")
base = "https://generativelanguage.googleapis.com/v1beta"
if not key:
    sys.exit("GEMINI_API_KEY is not set")
headers = {"x-goog-api-key": key}

try:
    if not model:
        r = httpx.get(base + "/models", headers=headers, timeout=20)
        r.raise_for_status()
        for m in r.json().get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                print(m["name"].replace("models/", ""))
        print("\nPick one model name and set GEMINI_MODEL in .env")
    else:
        body = {"contents": [{"parts": [{"text":
                "Give 2 short stock-footage search phrases for: Within weeks, small green shoots will appear. Reply with one phrase per line."}]}]}
        r = httpx.post("%s/models/%s:generateContent" % (base, model), headers=headers, json=body, timeout=30)
        print("status:", r.status_code)
        print(r.text[:600] if r.status_code != 200 else r.json()["candidates"][0]["content"]["parts"][0]["text"])
except httpx.HTTPError as exc:
    print("request failed:", str(exc).replace(key, "***"))
