import io
import os
import time
import datetime
import requests
import pandas as pd
import yfinance as yf

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
sess = requests.Session()
sess.headers.update(UA)
try:
    sess.get("https://www.nseindia.com", timeout=30)
except Exception as e:
    print("NSE home:", e)

debug = []


def nse(url):
    for _ in range(2):
        try:
            r = sess.get(url, timeout=30)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(1.5)
    return None


def walk(o, out):
    if isinstance(o, dict):
        if "isin" in o or "symbol" in o:
            out.append(o)
        for v in o.values():
            walk(v, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, out)


def num(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


# ---------- candidates: ఈ రోజు scans లో వచ్చిన stocks ----------
cands = set()
for f in ("data/ultra_short.csv", "data/short_term.csv"):
    if os.path.exists(f):
        try:
            cands |= set(pd.read_csv(f)["Symbol"].astype(str))
        except Exception as e:
            print("చదవలేకపోయాం", f, e)
cands = sorted(cands)
print("Candidates:", len(cands))

# ---------- Symbol -> ISIN ----------
isin_of = {}
for u in ("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
          "https://archives.nseindia.com/content/equities/EQUITY_L.csv"):
    try:
        r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        if r.status_code == 200:
            lst = pd.read_csv(io.StringIO(r.text))
            lst.columns = [c.strip() for c in lst.columns]
            col = [c for c in lst.columns if "ISIN" in c.upper()][0]
            isin_of = dict(zip(lst["SYMBOL"].str.strip(), lst[col].astype(str).str.strip()))
            break
    except Exception as e:
        print("ISIN list:", e)
print("ISIN map:", len(isin_of))


# ---------- ASM / GSM ----------
def flag_sets(url):
    d = nse(url)
    if d is None:
        return None, None
    items = []
    walk(d, items)
    isins, syms = set(), set()
    for it in items:
        if it.get("isin"):
            isins.add(str(it["isin"]).strip())
        if it.get("symbol"):
            syms.add(str(it["symbol"]).strip())
    return isins, syms


asm_i, asm_s = flag_sets("https://www.nseindia.com/api/reportASM")
gsm_i, gsm_s = flag_sets("https://www.nseindia.com/api/reportGSM")
print("ASM list:", None if asm_i is None else (len(asm_i), len(asm_s)))
print("GSM list:", None if gsm_i is None else (len(gsm_i), len(gsm_s)))


def flag(sym, isins, syms):
    if isins is None:
        return "Unknown"
    return "Yes" if (isin_of.get(sym) in isins or sym in syms) else "No"


# ---------- Results calendar ----------
ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
today = pd.Timestamp(ist.date())
res_date = {}
cal = nse("https://www.nseindia.com/api/event-calendar?index=equities")
cal_ok = isinstance(cal, list)
if cal_ok:
    for it in cal:
        txt = (str(it.get("purpose", "")) + " " + str(it.get("bm_desc", ""))).lower()
        if "financial result" not in txt:
            continue
        d = pd.to_datetime(it.get("date"), errors="coerce", dayfirst=True)
        if pd.isna(d) or d < today:
            continue
        s = str(it.get("symbol", "")).strip()
        if s and (s not in res_date or d < res_date[s]):
            res_date[s] = d
print("Results calendar:", "OK" if cal_ok else "FAILED", "| upcoming:", len(res_date))

# ---------- ఒక్కో candidate కి ----------
rows = []
for n, sym in enumerate(cands):
    row = {"Symbol": sym, "ISIN": isin_of.get(sym, ""),
           "ASM": flag(sym, asm_i, asm_s), "GSM": flag(sym, gsm_i, gsm_s),
           "NextResults": "", "DaysToResults": "",
           "MarketCapCr": "", "DebtEquity": "", "Sector": "",
           "PromoterPct": "", "PledgePct": ""}
    if sym in res_date:
        row["NextResults"] = res_date[sym].strftime("%Y-%m-%d")
        row["DaysToResults"] = int((res_date[sym] - today).days)
    elif cal_ok:
        row["DaysToResults"] = 999      # 999 = calendar లో results తేదీ లేదు

    try:
        info = yf.Ticker(sym + ".NS").info or {}
        mc = info.get("marketCap")
        de = info.get("debtToEquity")
        if mc:
            row["MarketCapCr"] = round(mc / 1e7, 0)
        if de is not None:
            row["DebtEquity"] = round(de / 100.0, 2)    # yfinance శాతంలో ఇస్తుంది
        row["Sector"] = info.get("sector") or ""
    except Exception as e:
        print("yfinance", sym, e)

    # promoter %
    sh = nse("https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=" + sym)
    try:
        recs = sh["data"] if isinstance(sh, dict) and "data" in sh else sh
        if isinstance(recs, list) and recs:
            recs = sorted(recs, key=lambda x: pd.to_datetime(x.get("date"), errors="coerce"), reverse=True)
            rec = recs[0]
            if n < 2:
                debug.append("SHAREHOLDING %s keys: %s" % (sym, list(rec.keys())))
            v = num(rec.get("pr_and_prgrp"))
            if v is None:
                for k, val in rec.items():
                    if "promoter" in k.lower() and num(val) is not None:
                        v = num(val)
                        break
            if v is not None:
                row["PromoterPct"] = round(v, 2)
    except Exception as e:
        print("shareholding", sym, e)

    # pledge %
    pl = nse("https://www.nseindia.com/api/corporate-pledgedata?index=equities&symbol=" + sym)
    try:
        data = pl.get("data") if isinstance(pl, dict) else None
        if n < 2:
            debug.append("PLEDGE %s sample: %s" % (sym, str(data[:1])[:600] if data else str(pl)[:300]))
        if data:
            rec = data[0]
            for k, val in rec.items():
                kl = k.lower()
                if "pledg" in kl and ("perc" in kl or "per" in kl) and num(val) is not None:
                    row["PledgePct"] = round(num(val), 2)
                    break
    except Exception as e:
        print("pledge", sym, e)

    rows.append(row)
    time.sleep(0.4)

cols = ["Symbol", "ISIN", "ASM", "GSM", "NextResults", "DaysToResults", "MarketCapCr",
        "DebtEquity", "Sector", "PromoterPct", "PledgePct"]
out = pd.DataFrame(rows, columns=cols)
os.makedirs("data", exist_ok=True)
out.to_csv("data/fundamentals.csv", index=False)
with open("data/fund_debug.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(debug))

print("fundamentals rows:", len(out))
if len(out):
    print("ASM yes:", (out["ASM"] == "Yes").sum(), "| GSM yes:", (out["GSM"] == "Yes").sum())
    for c in ("MarketCapCr", "DebtEquity", "PromoterPct", "PledgePct"):
        print(c, "దొరికినవి:", (out[c].astype(str) != "").sum(), "/", len(out))
    print("results ≤10 రోజుల్లో:", ((pd.to_numeric(out["DaysToResults"], errors="coerce") <= 10)).sum())
