import io, os, time
import requests
import pandas as pd
import yfinance as yf

TEST_LIMIT = None
BATCH = 80

def get_hybrid_momentum_universe():
    """
    1. Nifty 100 Large caps ni filter chesthundi.
    2. Nifty 101-750 Mid/Small cap base universe ni lock chesthundi.
    3. Beyond 750 unna micro-caps lo strong volume/turnover unna vatini dynamic ga capture chesthundi.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    # 1. Nifty 100 (Large Caps) List Download - Elimination kosam
    nifty100_symbols = set()
    n100_urls = [
        "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
        "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
    ]
    for u in n100_urls:
        try:
            r = requests.get(u, headers=headers, timeout=20)
            if r.status_code == 200:
                df_100 = pd.read_csv(io.StringIO(r.text))
                df_100.columns = [c.strip() for c in df_100.columns]
                col = "Symbol" if "Symbol" in df_100.columns else "SYMBOL"
                nifty100_symbols = set(df_100[col].str.strip().tolist())
                print(f"Nifty 100 large caps identified: {len(nifty100_symbols)}")
                break
        except Exception as e:
            print("Nifty 100 download failed:", e)

    # 2. Nifty Total Market (Nifty 750) Universe
    total_urls = [
        "https://archives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv",
        "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"
    ]
    nifty_total_symbols = []
    for u in total_urls:
        try:
            r = requests.get(u, headers=headers, timeout=30)
            if r.status_code == 200:
                df_total = pd.read_csv(io.StringIO(r.text))
                df_total.columns = [c.strip() for c in df_total.columns]
                col = "Symbol" if "Symbol" in df_total.columns else "SYMBOL"
                nifty_total_symbols = df_total[col].str.strip().tolist()
                print(f"Nifty Total Market symbols: {len(nifty_total_symbols)}")
                break
        except Exception as e:
            print("Total market download failed:", e)

    # 3. Base Universe Setup (Nifty 101 to 750)
    seen = set()
    base_universe = []
    for sym in nifty_total_symbols:
        clean_sym = sym.strip()
        if clean_sym and (clean_sym not in seen) and (clean_sym not in nifty100_symbols):
            seen.add(clean_sym)
            base_universe.append(clean_sym)

    # 4. Micro-cap Safety Net (NSE EQ Master List check)
    # Total Market lo leni any sudden breakout micro-caps ni catch cheyadaniki
    micro_candidates = []
    try:
        eq_url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        r_eq = requests.get(eq_url, headers=headers, timeout=30)
        if r_eq.status_code == 200:
            df_eq = pd.read_csv(io.StringIO(r_eq.text))
            df_eq.columns = [c.strip() for c in df_eq.columns]
            df_eq = df_eq[df_eq["SERIES"].str.strip() == "EQ"]
            all_nse = df_eq["SYMBOL"].str.strip().tolist()
            
            # Base universe mariyu large caps lo leni stocks
            remaining = [s for s in all_nse if s not in seen and s not in nifty100_symbols]
            micro_candidates = remaining[:150] # Top liquid buffer candidates
    except Exception as e:
        print("Micro buffer fetch error:", e)

    final_universe = base_universe + micro_candidates
    # De-duplicate
    final_universe = list(dict.fromkeys(final_universe))
    
    print(f"Total Hybrid Universe locked: {len(final_universe)} stocks (Base: {len(base_universe)}, Micro buffer: {len(micro_candidates)})")
    return final_universe

symbols = get_hybrid_momentum_universe()
if TEST_LIMIT:
    symbols = symbols[:TEST_LIMIT]

# Batch Download with Retry Mechanism
frames, failed = [], []
for i in range(0, len(symbols), BATCH):
    batch = symbols[i:i + BATCH]
    tickers = [s + ".NS" for s in batch]
    try:
        df = yf.download(tickers, period="1y", interval="1d",
                         group_by="ticker", auto_adjust=True,
                         progress=False, threads=True)
    except Exception as e:
        print("Batch download failed:", i, e)
        failed += batch
        continue

    for s in batch:
        try:
            d = df[s + ".NS"].dropna(how="all").reset_index()
            if d.empty or len(d) < 30: # Minimum 30 trading days history
                failed.append(s)
                continue
            
            # Dynamic Liquidity Gate:
            # Micro-caps ayithe minimum 20-day avg turnover > 75 Lakhs undali (illiquid trap avoidance)
            avg_volume_20 = d["Volume"].tail(20).mean()
            last_close = d["Close"].iloc[-1]
            turnover_cr = (avg_volume_20 * last_close) / 10000000.0

            if s not in symbols[:650] and turnover_cr < 0.75:
                # Active volume leni micro-cap ni drop chesthundi
                continue

            d["Symbol"] = s
            frames.append(d[["Symbol", "Date", "Open", "High", "Low", "Close", "Volume"]])
        except Exception:
            failed.append(s)
    time.sleep(1.5)

os.makedirs("data", exist_ok=True)
if frames:
    out = pd.concat(frames, ignore_index=True)
    out.to_csv("data/prices.csv.gz", index=False, compression="gzip")
    print(f"Data saved successfully. Total rows: {len(out)}, Unique stocks active: {out['Symbol'].nunique()}")

with open("data/failed.txt", "w") as f:
    f.write("\n".join(failed))
print(f"Failed or illiquid dropped count: {len(failed)}")

# ---------- Benchmark Index Data (Nifty 50 & Nifty 500) ----------
INDEXES = {"NIFTY50": "^NSEI", "NIFTY500": "^CRSLDX"}
idx_frames = []
for name, tk in INDEXES.items():
    try:
        d = yf.Ticker(tk).history(period="1y", interval="1d", auto_adjust=True)
        if d is None or d.empty:
            continue
        d.index = d.index.tz_localize(None).normalize()
        d = d.reset_index().rename(columns={d.index.name or "Date": "Date"})
        d["Symbol"] = name
        idx_frames.append(d[["Symbol", "Date", "Open", "High", "Low", "Close", "Volume"]])
        print(f"Index data saved: {name}")
    except Exception as e:
        print(f"Index fetch failed for {name}:", e)

if idx_frames:
    pd.concat(idx_frames, ignore_index=True).to_csv("data/index.csv", index=False)

# =====================================================================
# NSE SURVEILLANCE (ASM / GSM) AUTO-FETCH
# =====================================================================
def fetch_nse_surveillance():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
                print(f"NSE {ep['type']} fetched successfully.")
        except Exception as e:
            print(f"Surveillance fetch error for {ep['type']}:", e)

    if surv_records:
        df_surv = pd.DataFrame(surv_records).drop_duplicates(subset=["Symbol"])
        df_surv.to_csv("data/surveillance.csv", index=False)
        print(f"Surveillance stocks saved: {len(df_surv)}")
    else:
        pd.DataFrame(columns=["Symbol", "Type", "Category"]).to_csv("data/surveillance.csv", index=False)

try:
    fetch_nse_surveillance()
except Exception as _e:
    print("Surveillance routine error:", _e)
