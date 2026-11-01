import os
import pandas as pd
import numpy as np
import yfinance as yf

OUT_CSV = "data/smart_money.csv"
PRICES_PATH = "data/prices.csv.gz"
FUND_PATH = "data/fundamentals.csv"
EVENTS_PATH = "data/events.csv"
Q2_EXTERNAL_PATH = "data/holdings_q2.csv"

# తాజా Q2 ప్రధాన సూపర్ ఇన్వెస్టర్లు & ఫండ్ల పోర్ట్‌ఫోలియో బేస్ డేటా
CORE_PORTFOLIOS = [
    # Ashish Kacholia (Q2 Fresh & Core Growth)
    {"Symbol": "SHILCTECH", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.4%"},
    {"Symbol": "GARUDA", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.8%"},
    {"Symbol": "ADFFOODS", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.1%"},
    {"Symbol": "BALAMINES", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.2%"},
    {"Symbol": "GRAVITA", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.2%"},
    {"Symbol": "SAFARI", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.3%"},
    {"Symbol": "TANFACIND", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.3%"},
    {"Symbol": "SANSERA", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Accumulating", "HoldingPct": "1.6%"},
    {"Symbol": "CIGNITITEC", "Investor": "Ashish Kacholia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.5%"},
    
    # Vijay Kedia (Q2 Picks)
    {"Symbol": "PATELENG", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.6%"},
    {"Symbol": "ELECON", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.8%"},
    {"Symbol": "TALBROAUTO", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.2%"},
    {"Symbol": "ATULAUTO", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.4%"},
    {"Symbol": "VAIBHAVGBL", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.0%"},
    {"Symbol": "OMINFRAL", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.7%"},
    {"Symbol": "TAC", "Investor": "Vijay Kedia", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.1%"},

    # Mukul Mahavir Agrawal (Turnaround & Aggressive Mid/Small)
    {"Symbol": "RAYMOND", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.9%"},
    {"Symbol": "NEULANDLAB", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.3%"},
    {"Symbol": "TASTYBITE", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.5%"},
    {"Symbol": "GOKEX", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "3.5%"},
    {"Symbol": "DVL", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "2.1%"},
    {"Symbol": "SHILCTECH", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.6%"},
    {"Symbol": "PTCIL", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.2%"},
    {"Symbol": "PARAS", "Investor": "Mukul Agrawal", "Type": "Super Investor", "Action": "Accumulating", "HoldingPct": "1.8%"},

    # Quant Mutual Fund (Aggressive Momentum Top Buys)
    {"Symbol": "RELIANCE", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Accumulating", "HoldingPct": "Top Pick"},
    {"Symbol": "JIOFIN", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Accumulating", "HoldingPct": "Top Pick"},
    {"Symbol": "ADANIPOWER", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Pick"},
    {"Symbol": "SAIL", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Pick"},
    {"Symbol": "HINDCOPPER", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "High Weight"},
    {"Symbol": "BIOCON", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "High Weight"},
    {"Symbol": "SAMVARDHANA", "Investor": "Quant Mutual Fund", "Type": "Mutual Fund / DII", "Action": "Accumulating", "HoldingPct": "Top Pick"},

    # Nippon India Small Cap Fund (Q2 Small Cap Holdings)
    {"Symbol": "TUBEINVEST", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Holding"},
    {"Symbol": "APARINDS", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Holding"},
    {"Symbol": "KPITTECH", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Holding"},
    {"Symbol": "CREDITACC", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Holding"},
    {"Symbol": "ELGIEQUIP", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "Top Holding"},
    {"Symbol": "GARUDA", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Holding", "HoldingPct": "3.1%"},
    {"Symbol": "HBLPOWER", "Investor": "Nippon Small Cap Fund", "Type": "Mutual Fund / DII", "Action": "Accumulating", "HoldingPct": "2.8%"},

    # Top Super Institutional
    {"Symbol": "DMART", "Investor": "Radhakishan Damani", "Type": "Super Investor", "Action": "Promoter/Core", "HoldingPct": "65.0%"},
    {"Symbol": "VSTIND", "Investor": "Radhakishan Damani", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "32.0%"},
    {"Symbol": "TITAN", "Investor": "Rekha Jhunjhunwala", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "5.1%"},
    {"Symbol": "TATACOMM", "Investor": "Rekha Jhunjhunwala", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.8%"},
    {"Symbol": "CANBK", "Investor": "Rekha Jhunjhunwala", "Type": "Super Investor", "Action": "Holding", "HoldingPct": "1.5%"},

    # FIIs (GIC & Norges Bank)
    {"Symbol": "ZOMATO", "Investor": "Government of Singapore", "Type": "FII", "Action": "Holding", "HoldingPct": "2.3%"},
    {"Symbol": "INDIGO", "Investor": "Norges Bank", "Type": "FII", "Action": "Holding", "HoldingPct": "1.5%"}
]

SUPER_INVESTORS = [
    "ASHISH KACHOLIA", "VIJAY KEDIA", "MUKUL AGRAWAL", "DOLLY KHANNA",
    "PORINJU VELIYATH", "NEMISH SHAH", "SUNIL SINGHANIA", "MADHUSUDAN KELA",
    "ANIL KUMAR GOEL", "REKHA JHUNJHUNWALA", "RARE ENTERPRISES", "RADHAKISHAN DAMANI",
    "AKASH BHANSHALI"
]

GROWTH_FUNDS = [
    "QUANT MUTUAL FUND", "QUANT SMALL CAP", "QUANT ACTIVE",
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
        ("quality", "data/quality.csv", "Quality"),
        ("newlistings", "data/newlistings.csv", "New Listings")
    ]
    for key, path, label in scan_files:
        if os.path.exists(path):
            try:
                d = pd.read_csv(path)
                if "Symbol" in d.columns:
                    for _, r in d.iterrows():
                        sym = str(r["Symbol"]).upper().strip()
                        sc = r.get("Score", "")
                        score_txt = f" ({sc})" if pd.notna(sc) and str(sc).strip() else ""
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

    for p in ("data/multibagger.csv", "data/quality.csv"):
        if os.path.exists(p):
            try:
                d = pd.read_csv(p)
                for _, r in d.iterrows():
                    sym = str(r.get("Symbol", "")).upper().strip()
                    mc = pd.to_numeric(r.get("MarketCapCr"), errors="coerce")
                    if sym not in fund or np.isnan(fund[sym].get("MarketCapCr", np.nan)):
                        sec = r.get("Sector", "n/a")
                        fund[sym] = {"Sector": sec, "MarketCapCr": mc}
            except Exception:
                pass
    return fund

def fetch_missing_mcap_fast(symbols, fund_map):
    for sym in symbols:
        k = sym.upper().strip()
        fm = fund_map.setdefault(k, {})
        mc = fm.get("MarketCapCr", np.nan)
        if np.isnan(mc) or mc is None or mc <= 0:
            try:
                t = yf.Ticker(k + ".NS")
                # fast_info వాడుకోవడం వల్ల rate-limits రావు
                fi = t.fast_info
                raw_mc = getattr(fi, "market_cap", None)
                if raw_mc and raw_mc > 0:
                    fm["MarketCapCr"] = round(raw_mc / 1e7, 1)
            except Exception:
                pass

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
    print("Smart Money Q2 డేటా ప్రాసెసింగ్ ప్రారంభమైంది...")
    os.makedirs("data", exist_ok=True)

    radar_map = load_radar_symbols()
    fund_map = load_fundamentals()
    price_map = load_latest_prices()
    event_deals = scan_events()

    # డైనమిక్ Q2 CSV ఎక్స్‌టర్నల్ ఫైల్ ఉంటే లోడ్ చేయడం
    external_q2 = []
    if os.path.exists(Q2_EXTERNAL_PATH):
        try:
            ext_df = pd.read_csv(Q2_EXTERNAL_PATH)
            for _, r in ext_df.iterrows():
                external_q2.append({
                    "Symbol": str(r.get("Symbol", "")).upper().strip(),
                    "Investor": str(r.get("Investor", "")).strip(),
                    "Type": str(r.get("Type", "Super Investor")).strip(),
                    "Action": str(r.get("Action", "Holding")).strip(),
                    "HoldingPct": str(r.get("HoldingPct", "Filing")).strip(),
                    "Date": "Q2 Filing",
                    "Source": "Q2 Shareholding CSV"
                })
            print(f"External Q2 ఫైల్ నుండి {len(external_q2)} రికార్డులు లోడ్ అయ్యాయి.")
        except Exception as e:
            print("External Q2 ఫైల్ లోడింగ్ ఎర్రర్:", e)

    combined_core = external_q2 if len(external_q2) > 0 else CORE_PORTFOLIOS

    all_symbols = set([d["Symbol"] for d in event_deals] + [c["Symbol"] for c in combined_core])
    fetch_missing_mcap_fast(all_symbols, fund_map)

    raw_records = []
    seen_keys = set()

    for d in event_deals:
        sym = d["Symbol"]
        k = (sym, d["Investor"])
        if k in seen_keys:
            continue
        seen_keys.add(k)
        raw_records.append(d)

    for c in combined_core:
        sym = c["Symbol"]
        k = (sym, c["Investor"])
        if k in seen_keys:
            continue
        seen_keys.add(k)
        if "Date" not in c:
            c["Date"] = "Q2 Filing"
        if "Source" not in c:
            c["Source"] = "Shareholding Filing"
        raw_records.append(c)

    # Overlap / Clustered Buying గణన
    sym_investors = {}
    for r in raw_records:
        s = r["Symbol"]
        sym_investors.setdefault(s, []).append(r["Investor"])

    records = []
    for r in raw_records:
        sym = r["Symbol"]
        fm = fund_map.get(sym, {})
        mc = fm.get("MarketCapCr", np.nan)
        close_px = price_map.get(sym, "n/a")
        
        if close_px == "n/a":
            try:
                t = yf.Ticker(sym + ".NS")
                fi = t.fast_info
                lp = getattr(fi, "last_price", None)
                if lp:
                    close_px = round(lp, 2)
            except Exception:
                pass

        inv_list = sym_investors.get(sym, [])
        overlap_cnt = len(set(inv_list))
        other_invs = [inv for inv in set(inv_list) if inv != r["Investor"]]
        co_holders = ", ".join(other_invs) if other_invs else "None"

        records.append({
            "Date": r["Date"],
            "Symbol": sym,
            "Investor": r["Investor"],
            "Type": r["Type"],
            "Action": r["Action"],
            "HoldingPct": r["HoldingPct"],
            "MarketCapCr": round(mc, 1) if pd.notna(mc) else "n/a",
            "Category": get_mcap_category(mc),
            "Sector": fm.get("Sector", "n/a"),
            "ClosePrice": close_px,
            "RadarSetup": radar_map.get(sym, "Not on radar"),
            "OverlapCount": overlap_cnt,
            "CoInvestors": co_holders,
            "Source": r["Source"]
        })

    out_df = pd.DataFrame(records)
    out_df.to_csv(OUT_CSV, index=False)
    print("Smart Money Q2 డేటా సిద్ధమైంది:", len(out_df), "ఎంట్రీలు.")
    overlap_syms = out_df[out_df["OverlapCount"] >= 2]["Symbol"].unique().tolist()
    print("Overlap స్టాక్స్ (2+ Investors):", overlap_syms)

if __name__ == "__main__":
    main()
