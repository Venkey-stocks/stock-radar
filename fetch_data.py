import io, os, time
import requests
import pandas as pd
import yfinance as yf

TEST_LIMIT = None
BATCH = 100

URLS = [
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
]
text = None
for u in URLS:
    try:
        r = requests.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        print("Tried:", u, "status:", r.status_code)
        if r.status_code == 200:
            text = r.text
            break
    except Exception as e:
        print("Failed:", u, e)
if text is None:
    raise SystemExit("Could not download NSE stock list")

lst = pd.read_csv(io.StringIO(text))
lst.columns = [c.strip() for c in lst.columns]
lst = lst[lst["SERIES"].str.strip() == "EQ"]
symbols = lst["SYMBOL"].str.strip().tolist()
if TEST_LIMIT:
    symbols = symbols[:TEST_LIMIT]
print("Total stocks:", len(symbols))

frames, failed = [], []
for i in range(0, len(symbols), BATCH):
    batch = symbols[i:i + BATCH]
    tickers = [s + ".NS" for s in batch]
    try:
        df = yf.download(tickers, period="1y", interval="1d",
                         group_by="ticker", auto_adjust=True,
                         progress=False, threads=True)
    except Exception as e:
        print("Batch failed:", i, e)
        failed += batch
        continue
    for s in batch:
        try:
            d = df[s + ".NS"].dropna(how="all").reset_index()
            if d.empty:
                failed.append(s)
                continue
            d["Symbol"] = s
            frames.append(d[["Symbol", "Date", "Open", "High", "Low", "Close", "Volume"]])
        except Exception:
            failed.append(s)
    time.sleep(2)

os.makedirs("data", exist_ok=True)
if frames:
    out = pd.concat(frames, ignore_index=True)
    out.to_csv("data/prices.csv.gz", index=False, compression="gzip")
    print("Saved rows:", len(out), "stocks:", out["Symbol"].nunique())
with open("data/failed.txt", "w") as f:
    f.write("\n".join(failed))
print("Failed:", len(failed))

# ---------- Index data (Nifty 50 మరియు Nifty 500) ----------
# ఇది విఫలమైనా stocks data పై ప్రభావం ఉండదు
INDEXES = {"NIFTY50": "^NSEI", "NIFTY500": "^CRSLDX"}
idx_frames = []
for name, tk in INDEXES.items():
    try:
        d = yf.Ticker(tk).history(period="1y", interval="1d", auto_adjust=True)
        if d is None or d.empty:
            print("Index no data:", name, tk)
            continue
        d.index = d.index.tz_localize(None).normalize()
        d = d.reset_index().rename(columns={d.index.name or "Date": "Date"})
        d["Symbol"] = name
        idx_frames.append(d[["Symbol", "Date", "Open", "High", "Low", "Close", "Volume"]])
        print("Index saved:", name, len(d), "rows")
    except Exception as e:
        print("Index failed:", name, tk, e)
if idx_frames:
    pd.concat(idx_frames, ignore_index=True).to_csv("data/index.csv", index=False)


# =====================================================================
# NSE SURVEILLANCE (ASM / GSM) AUTO-FETCH
# =====================================================================
def fetch_nse_surveillance():
    """
    NSE నుండి అధికారిక ASM మరియు GSM లిస్ట్‌లను డౌన్‌లోడ్ చేసి data/surveillance.csv గా భద్రపరుస్తుంది.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    surv_records = []
    endpoints = [
        {"url": "https://nsearchives.nseindia.com/content/equities/sec_list.csv", "type": "ASM", "desc": "Short-term/Long-term ASM"},
        {"url": "https://nsearchives.nseindia.com/content/equities/gsm_list.csv", "type": "GSM", "desc": "Graded Surveillance Measure"}
    ]
    
    session = requests.Session()
    try:
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
    except Exception:
        pass

    for ep in endpoints:
        try:
            res = session.get(ep["url"], headers=headers, timeout=15)
            if res.status_code == 200 and len(res.text.strip()) > 20:
                lines = res.text.strip().splitlines()
                for line in lines[1:]:
                    parts = [p.strip().replace('"', '') for p in line.split(",")]
                    if len(parts) >= 2:
                        sym = parts[1].upper().replace(".NS", "").strip() if len(parts) > 1 else parts[0].upper().strip()
                        if sym and not sym.startswith("SYMBOL"):
                            surv_records.append({
                                "Symbol": sym,
                                "Type": ep["type"],
                                "Category": ep["desc"]
                            })
                print(f"NSE {ep['type']} లిస్ట్ విజయవంతంగా ఫెచ్ అయ్యింది.")
            else:
                print(f"హెచ్చరిక: {ep['type']} డేటా అందుబాటులో లేదు (Status: {res.status_code})")
        except Exception as e:
            print(f"{ep['type']} ఫెచ్ చేయడంలో లోపం: {e}")

    if surv_records:
        df_surv = pd.DataFrame(surv_records).drop_duplicates(subset=["Symbol"])
        df_surv.to_csv("data/surveillance.csv", index=False)
        print(f"మొత్తం {len(df_surv)} సర్వైలెన్స్ స్టాక్స్ 'data/surveillance.csv' లో సేవ్ అయ్యాయి.")
    else:
        pd.DataFrame(columns=["Symbol", "Type", "Category"]).to_csv("data/surveillance.csv", index=False)
        print("సర్వైలెన్స్ రికార్డ్స్ లభించలేదు, ఖాళీ ఫైల్ సిద్ధం చేయబడింది.")

try:
    fetch_nse_surveillance()
except Exception as _e:
    print("Surveillance fetch error:", _e)
