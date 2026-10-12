import os
import json
import time
import math
import datetime
import pandas as pd
import yfinance as yf

FILES = ["data/ultra_short.csv", "data/short_term.csv", "data/multibagger.csv",
         "data/quality.csv", "data/newlistings.csv"]
FUND_FILES = ["data/multibagger.csv", "data/quality.csv"]
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

# ---------- Multibagger/Quality csv నుంచి Ret1Y, ROCE, growth ----------
FUND_COLS = {"Ret1Y": "ret1y", "ROCE": "roce",
             "SalesCAGR3": "sales_cagr3", "ProfitCAGR3": "profit_cagr3"}
fund = {}
for f in FUND_FILES:
    if not os.path.exists(f):
        continue
    try:
        df = pd.read_csv(f)
    except Exception as e:
        print("చదవలేకపోయాం", f, e)
        continue
    if "Symbol" not in df.columns:
        continue
    for _, row in df.iterrows():
        s = str(row["Symbol"]).strip()
        d = fund.setdefault(s, {})
        for col, key in FUND_COLS.items():
            if col in df.columns:
                v = pd.to_numeric(row[col], errors="coerce")
                if pd.notna(v):
                    d[key] = round(float(v), 1)

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


def get_info(t):
    for attempt in range(3):
        try:
            info = t.info or {}
            if info.get("sector") or info.get("longBusinessSummary") or info.get("marketCap"):
                return info
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return None


def get_ret1y(t):
    # సుమారు 1 సంవత్సరం return % (అంచనా). 200 రోజుల కంటే తక్కువ data ఉంటే n/a
    try:
        h = t.history(period="1y")["Close"].dropna()
        if len(h) >= 200 and h.iloc[0] > 0:
            return round((h.iloc[-1] / h.iloc[0] - 1) * 100, 1)
    except Exception:
        pass
    return "n/a"


prof = {}
fail = 0
for sym in syms:
    t = yf.Ticker(sym + ".NS")
    info = get_info(t)
    if info is None:
        fail += 1
        if sym in old:
            prof[sym] = old[sym]
        continue
    mc = info.get("marketCap")
    pe = info.get("trailingPE")
    fd = fund.get(sym, {})
    ret1y = fd.get("ret1y")
    if ret1y is None:
        ret1y = get_ret1y(t)
    prof[sym] = {
        "name": info.get("longName") or info.get("shortName") or "n/a",
        "sector": info.get("sector") or "n/a",
        "industry": info.get("industry") or "n/a",
        "summary": short(info.get("longBusinessSummary")) or "n/a",
        "mcap_cr": round(mc / 1e7) if mc else "n/a",
        "pe": round(pe, 1) if isinstance(pe, (int, float)) else "n/a",
        "ret1y": ret1y,
        "roce": fd.get("roce", "n/a"),
        "sales_cagr3": fd.get("sales_cagr3", "n/a"),
        "profit_cagr3": fd.get("profit_cagr3", "n/a"),
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
print("Ret1Y ఉన్నవి:", sum(1 for p in prof.values() if p.get("ret1y") not in (None, "n/a")))
print("ROCE ఉన్నవి:", sum(1 for p in prof.values() if p.get("roce") not in (None, "n/a")))
