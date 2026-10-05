import io, os, time
import requests
import pandas as pd
import yfinance as yf

TEST_LIMIT = 50
BATCH = 100

URL = "https://nsearchives.nseindia.com/content/equity_l.csv"
r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
r.raise_for_status()
lst = pd.read_csv(io.StringIO(r.text))
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
