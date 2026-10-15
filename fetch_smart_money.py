import os
import glob
import pandas as pd
import numpy as np
import yfinance as yf

OUT_CSV = "data/smart_money.csv"
PRICES_PATH = "data/prices.csv.gz"
FUND_PATH = "data/fundamentals.csv"
EVENTS_PATH = "data/events.csv"

# ప్రధాన సూపర్ ఇన్వెస్టర్లు (కీవర్డ్ శోధన కోసం)
SUPER_INVESTORS = [
    "ASHISH KACHOLIA", "VIJAY KEDIA", "MUKUL AGRAWAL", "DOLLY KHANNA",
    "PORINJU VELIYATH", "NEMISH SHAH", "SUNIL SINGHANIA", "MADHUSUDAN KELA",
    "ANIL KUMAR GOEL", "REKHA JHUNJHUNWALA", "RARE ENTERPRISES", "RADHAKISHAN DAMANI",
    "AKASH BHANSHALI", "KENNETH ANDRADE", "SAURABH MUKHERJEA"
]

# ప్రముఖ స్మాల్/మిడ్ క్యాప్ & అగ్రెసివ్ గ్రోత్ మ్యూచువల్ ఫండ్స్ & DIIs
GROWTH_FUNDS = [
    "QUANT MUTUAL FUND", "QUANT SMALL CAP", "QUANTUM MUTUAL FUND",
    "NIPPON INDIA SMALL CAP", "HDFC SMALL CAP", "KOTAK SMALL CAP",
    "SBI SMALL CAP", "AXIS SMALL CAP", "MOTILAL OSWAL",
    "BANDHAN EMERGING", "DSP SMALL CAP", "ICICI PRUDENTIAL",
    "LIFE INSURANCE CORPORATION OF INDIA", "LIC OF INDIA"
]

# గ్లోబల్ / FII ఫండ్స్
FII_FUNDS = [
    "GOVERNMENT OF SINGAPORE", "GIC PRIVATE LIMITED",
    "NORGES BANK", "VANGUARD", "BLACKROCK"
]

# మార్కెట్ క్యాప్ వర్గీకరణ
def get_mcap_category(mcap_cr):
    if mcap_cr is None or np.isnan(mcap_cr):
        return "Unknown"
    if mcap_cr >= 50000:
        return "Large Cap"
    if mcap_cr >= 15000:
        return "Mid Cap"
    if mcap_cr >= 1000:
        return "Small Cap"
    return "Micro Cap"


# రాడార్ స్కాన్ల క్రాస్-చెక్
def load_radar_symbols():
    radar = {}
    scan_files = [
        ("ultra", "data/ultra_short.csv", "Ultra Short"),
        ("short", "data/short_term.csv", "Short Term"),
        ("early", "data/early_movers.csv", "Early Movers"),
        ("multi", "data/multibagger.csv", "Multibagger"),
        ("quality", "data/quality.csv", "Quality")
    ]
    for key, path, label in scan_files:
        if os.path.exists(path):
            try:
                d = pd.read_csv(path)
                if "Symbol" in d.columns:
                    for _, r in d.iterrows():
                        sym = str(r["Symbol"]).upper().strip()
                        sc = r.get("Score", "")
                        score_txt = f" (Score: {sc})" if pd.notna(sc) and str(sc).strip() else ""
                        radar[sym] = f"{label}{score_txt}"
            except Exception:
                pass
    return radar


# ఫండమెంటల్స్ నుండి సెక్టార్ & మార్కెట్ క్యాప్
def load_fundamentals():
    fund = {}
    if os.path.exists(FUND_PATH):
        try:
            d = pd.read_csv(FUND_PATH)
            for _, r in d.iterrows():
                sym = str(r.get("Symbol", "")).upper().strip()
                fund[sym] = {
                    "Sector": r.get("Sector", "n/a"),
                    "MarketCapCr": pd.to_numeric(r.get("MarketCapCr"), errors="coerce")
                }
        except Exception:
            pass
    return fund


# Events.csv నుండి తాజా Bulk/Block Deals మ్యాపింగ్
def scan_events():
    deals = []
    if not os.path.exists(EVENTS_PATH):
        return deals
    try:
        ev = pd.read_csv(EVENTS_PATH)
        for _, r in ev.iterrows():
            sym = str(r.get("symbol", "")).upper().strip()
            detail = str(r.get("detail", "")).upper()
            date = str(r.get("date", ""))
            cat = str(r.get("category", ""))

            # ఇన్వెస్టర్ రకం శోధన
            inv_type = None
            inv_name = None

            for si in SUPER_INVESTORS:
                if si in detail:
                    inv_type = "Super Investor"
                    inv_name = si
                    break
            if not inv_name:
                for gf in GROWTH_FUNDS:
                    if gf in detail:
                        inv_type = "Mutual Fund / DII"
                        inv_name = gf
                        break
            if not inv_name:
                for ff in FII_FUNDS:
                    if ff in detail:
                        inv_type = "FII"
                        inv_name = ff
                        break

            if inv_name:
                action = "Buy" if "BUY" in cat or "PURCHASE" in detail else ("Sell" if "SELL" in cat else "Bulk Deal")
                deals.append({
                    "Date": date,
                    "Symbol": sym,
                    "Investor": inv_name.title(),
                    "Type": inv_type,
                    "Action": action,
                    "HoldingPct": "Bulk Deal",
                    "Source": "NSE Bulk/Block Deal"
                })
    except Exception as e:
        print("Events scan error:", e)
    return deals


# మార్కెట్ ధరల నుండి తాజా క్లోజింగ్
def load_latest_prices():
    prices = {}
    if os.path.exists(PRICES_PATH):
        try:
            px = pd.read_csv(PRICES_PATH, parse_dates=["Date"])
            for sym, g in px.groupby("Symbol"):
                g = g.sort_values("Date")
                prices[str(sym).upper().strip()] = float(g["Close"].iloc[-1])
        except Exception:
            pass
    return prices


def main():
    print("Smart Money డేటా ప్రాసెసింగ్ ప్రారంభమైంది...")
    os.makedirs("data", exist_ok=True)

    radar_map = load_radar_symbols()
    fund_map = load_fundamentals()
    price_map = load_latest_prices()
    event_deals = scan_events()

    # తాజా సమాచారాన్ని సమగ్రపరచడం
    records = []
    seen_keys = set()

    for d in event_deals:
        sym = d["Symbol"]
        k = (sym, d["Investor"])
        if k in seen_keys:
            continue
        seen_keys.add(k)

        fm = fund_map.get(sym, {})
        sec = fm.get("Sector", "n/a")
        mc = fm.get("MarketCapCr", np.nan)
        cat = get_mcap_category(mc)
        rad = radar_map.get(sym, "Not on radar")
        close_px = price_map.get(sym, "n/a")

        records.append({
            "Date": d["Date"],
            "Symbol": sym,
            "Investor": d["Investor"],
            "Type": d["Type"],
            "Action": d["Action"],
            "HoldingPct": d["HoldingPct"],
            "MarketCapCr": round(mc, 1) if pd.notna(mc) else "n/a",
            "Category": cat,
            "Sector": sec,
            "ClosePrice": close_px,
            "RadarSetup": rad,
            "Source": d["Source"]
        })

    out_df = pd.DataFrame(records)
    if out_df.empty:
        # కనీస కాలమ్స్ తో ఖాళీ ఫైల్ సిద్ధం చేయడం
        cols = ["Date", "Symbol", "Investor", "Type", "Action", "HoldingPct",
                "MarketCapCr", "Category", "Sector", "ClosePrice", "RadarSetup", "Source"]
        out_df = pd.DataFrame(columns=cols)

    out_df.to_csv(OUT_CSV, index=False)
    print("Smart Money డేటా సిద్ధమైంది:", len(out_df), "ఎంట్రీలు.")


if __name__ == "__main__":
    main()
