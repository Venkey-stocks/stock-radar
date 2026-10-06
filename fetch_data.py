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
