import os
import pandas as pd
import numpy as np

OUT_CSV = "data/smart_money.csv"
PRICES_PATH = "data/prices.csv.gz"
FUND_PATH = "data/fundamentals.csv"
EVENTS_PATH = "data/events.csv"

# ప్రధాన సూపర్ ఇన్వెస్టర్ల తాజా ప్రధాన పోర్ట్‌ఫోలియో హోల్డింగ్స్ (బేస్ డేటా)
CORE_PORTFOLIOS = [
    # Ashish Kacholia (Small & Micro Cap Focused)
    {"Symbol": "SHILCTECH", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.4%"},
    {"Symbol": "GARUDA", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.8%"},
    {"Symbol": "ADFFOODS", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.1%"},
    {"Symbol": "BALAMINES", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.2%"},
    {"Symbol": "GRAVITA", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.2%"},
    {"Symbol": "SAFARI", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.3%"},
    
    # Vijay Kedia (Multi-bagger Growth)
    {"Symbol": "PATELENG", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.6%"},
    {"Symbol": "ELECON", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.8%"},
    {"Symbol": "TALBROAUTO", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.2%"},
    {"Symbol": "ATULAUTO", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.4%"},
    {"Symbol": "VAIBHAVGBL", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.0%"},

    # Mukul Mahavir Agrawal (High Growth & Turnaround)
    {"Symbol": "RAYMOND", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.9%"},
    {"Symbol": "NEULANDLAB", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.3%"},
    {"Symbol": "TASTYBITE", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.5%"},
    {"Symbol": "GOKEX", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "3.5%"},
    {"Symbol": "DVL", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.1%"},

    # Quant Mutual Fund (Aggressive Momentum & Growth)
    {"Symbol": "RELIANCE", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Accumulating", "HoldingPct": "Top Pick"},
    {"Symbol": "JIOFIN", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Accumulating", "HoldingPct": "Top Pick"},
    {"Symbol": "ADANIPOWER", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Accumulating", "HoldingPct": "Top Pick"},
    {"Symbol": "SAIL", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Accumulating", "HoldingPct": "Top Pick"},
    {"Symbol": "HINDCOPPER", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "High Weight"},
    {"Symbol": "BIOCON", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "High Weight"},

    # Nippon India Small Cap Fund (Small Cap King)
    {"Symbol": "TUBEINVEST", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Holding"},
    {"Symbol": "APARINDS", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Holding"},
    {"Symbol": "KPITTECH", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Holding"},
    {"Symbol": "CREDITACC", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Holding"},
    {"Symbol": "ELGIEQUIP", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Holding"},

    # Top Super Institutional (Radhakishan Damani & Rekha Jhunjhunwala)
    {"Symbol": "DMART", "Investor": "Radhakishan Damani", "Type": "Super Investor", "Action": "Promoter/Core", "HoldingPct": "65.0%"},
    {"Symbol": "VSTIND", "Investor": "Radhakishan Damani", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "32.0%"},
    {"Symbol": "INDIASTATS", "Investor": "Radhakishan Damani", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.6%"},
    {"Symbol": "TITAN", "Investor": "Rekha Jhunjhunwala", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "5.1%"},
    {"Symbol": "TATACOMM", "Investor": "Rekha Jhunjhunwala", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.8%"},
    {"Symbol": "CANBK", "Investor": "Rekha Jhunjhunwala", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.5%"},

    # FIIs (GIC & Norges Bank)
    {"Symbol": "ZOMATO", "Investor": "Government of Singapore", "Type": "FII", "Action": "Holding", "HoldingPct": "2.3%"},
    {"Symbol": "INDIGO", "Investor": "Norges Bank", "Type": "FII", "Action": "Holding", "HoldingPct": "1.5%"}
]

# శోధన కోసం పేర్లు
SUPER_INVESTORS = [
    "ASHISH KACHOLIA", "VIJAY KEDIA", "MUKUL AGRAWAL", "DOLLY KHANNA",
    "PORINJU VELIYATH", "NEMISH SHAH", "SUNIL SINGHANIA", "MADHUSUDAN KELA",
    "ANIL KUMAR GOEL", "REKHA JHUNJHUNWALA", "RARE ENTERPRISES", "RADHAKISHAN DAMANI",
    "AKASH BHANSHALI"
]

GROWTH_FUNDS = [
    "QUANT MUTUAL FUND", "QUANT SMALL CAP", "QUANTUM MUTUAL FUND",
    "NIPPON INDIA SMALL CAP", "HDFC SMALL CAP", "KOTAK SMALL CAP",
    "SBI SMALL CAP", "MOTILAL OSWAL", "BANDHAN EMERGING",
    "LIFE INSURANCE CORPORATION OF INDIA", "LIC OF INDIA"
]

FII_FUNDS = ["GOVERNMENT OF SINGAPORE", "GIC PRIVATE LIMITED", "NORGES BANK"]


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

            inv_type, inv_name = None, None

            for si in SUPER_INVESTORS:
                if si in detail:
                    inv_type, inv_name = "Super Investor", si
                    break
            if not inv_name:
                for gf in GROWTH_FUNDS:
                    if gf in detail:
                        inv_type, inv_name = "Mutual Fund / DII", gf
                        break
            if not inv_name:
                for ff in FII_FUNDS:
                    if ff in detail:
                        inv_type, inv_name = "FII", ff
                        break

            if inv_name:
                action = "Recent Buy" if "BUY" in cat or "PURCHASE" in detail else ("Recent Sell" if "SELL" in cat else "Bulk Deal")
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

    records = []
    seen_keys = set()

    # 1. తాజా ఈవెంట్స్ డీల్స్ (ప్రాధాన్యత మొదటిది)
    for d in event_deals:
        sym = d["Symbol"]
        k = (sym, d["Investor"])
        if k in seen_keys:
            continue
        seen_keys.add(k)

        fm = fund_map.get(sym, {})
        mc = fm.get("MarketCapCr", np.nan)
        records.append({
            "Date": d["Date"],
            "Symbol": sym,
            "Investor": d["Investor"],
            "Type": d["Type"],
            "Action": d["Action"],
            "HoldingPct": d["HoldingPct"],
            "MarketCapCr": round(mc, 1) if pd.notna(mc) else "n/a",
            "Category": get_mcap_category(mc),
            "Sector": fm.get("Sector", "n/a"),
            "ClosePrice": price_map.get(sym, "n/a"),
            "RadarSetup": radar_map.get(sym, "Not on radar"),
            "Source": d["Source"]
        })

    # 2. ప్రధాన కోర్ పోర్ట్‌ఫోలియో హోల్డింగ్స్
    for c in CORE_PORTFOLIOS:
        sym = c["Symbol"]
        k = (sym, c["Investor"])
        if k in seen_keys:
            continue
        seen_keys.add(k)

        fm = fund_map.get(sym, {})
        mc = fm.get("MarketCapCr", np.nan)
        records.append({
            "Date": "Quarterly Filing",
            "Symbol": sym,
            "Investor": c["Investor"],
            "Type": c["Type"],
            "Action": c["Action"],
            "HoldingPct": c["HoldingPct"],
            "MarketCapCr": round(mc, 1) if pd.notna(mc) else "n/a",
            "Category": get_mcap_category(mc),
            "Sector": fm.get("Sector", "n/a"),
            "ClosePrice": price_map.get(sym, "n/a"),
            "RadarSetup": radar_map.get(sym, "Not on radar"),
            "Source": "Shareholding Filing"
        })

    out_df = pd.DataFrame(records)
    out_df.to_csv(OUT_CSV, index=False)
    print("Smart Money డేటా సిద్ధమైంది:", len(out_df), "ఎంట్రీలు.")


if __name__ == "__main__":
    main()
