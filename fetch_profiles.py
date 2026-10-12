import os
import json
import time
import math
import datetime
import pandas as pd
import yfinance as yf

FILES = ["data/ultra_short.csv", "data/short_term.csv", "data/multibagger.csv",
         "data/quality.csv", "data/newlistings.csv"]
OUT = "data/profiles.json"

# ---------- symbols ----------
syms = set()
for f in FILES:
    if os.path.exists(f):
        try:
            df = pd.read_csv(f)
            if "Symbol" in df.columns:
                syms |= set(df["Symbol"].astype(str).str.strip())
        except Exception as e:
            print("చదవలేకపోయాం", f, e)
syms = sorted(syms)
print("Symbols:", len(syms))

# ---------- పాత profiles (విఫలమైతే పాతవే ఉంచుతాం) ----------
old = {}
if os.path.exists(OUT):
    try:
        with open(OUT, encoding="utf-8") as fh:
            old = json.load(fh).get("profiles", {})
    except Exception:
        old = {}


def short(txt, n=350):
    txt = (txt or "").strip()
    if len(txt) <= n:
        return txt
    return txt[:n].rsplit(" ", 1)[0] + "…"


def get_info(sym):
    t = yf.Ticker(sym + ".NS")
    for attempt in range(3):
        try:
            info = t.info or {}
            if info.get("sector") or info.get("longBusinessSummary") or info.get("marketCap"):
                return info
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return None


prof = {}
fail = 0
for sym in syms:
    info = get_info(sym)
    if info is None:
        fail += 1
        if sym in old:
            prof[sym] = old[sym]
        continue
    mc = info.get("marketCap")
    pe = info.get("trailingPE")
    prof[sym] = {
        "name": info.get("longName") or info.get("shortName") or "n/a",
        "sector": info.get("sector") or "n/a",
        "industry": info.get("industry") or "n/a",
        "summary": short(info.get("longBusinessSummary")) or "n/a",
        "mcap_cr": round(mc / 1e7) if mc else "n/a",
        "pe": round(pe, 1) if isinstance(pe, (int, float)) else "n/a",
        "peers": [],
    }
    time.sleep(0.6)

# ---------- peers: ఒకే industry, దగ్గరి market cap (అంచనా) ----------
for sym, p in prof.items():
    if p["industry"] == "n/a" or p["mcap_cr"] == "n/a":
        continue
    cand = []
    for s2, q in prof.items():
        if s2 == sym or q["industry"] != p["industry"] or q["mcap_cr"] == "n/a":
            continue
        d = abs(math.log(p["mcap_cr"] / q["mcap_cr"])) if p["mcap_cr"] > 0 and q["mcap_cr"] > 0 else 99
        cand.append((d, s2))
    cand.sort()
    p["peers"] = [s for _, s in cand[:5]]

os.makedirs("data", exist_ok=True)
ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump({"updated": ist.strftime("%Y-%m-%d"), "profiles": prof}, fh, ensure_ascii=False)

print("profiles:", len(prof), "| విఫలమైనవి:", fail)
print("peers ఉన్నవి:", sum(1 for p in prof.values() if p["peers"]))
