import os
import pandas as pd
import yfinance as yf
from datetime import datetime

OUTPUT_FILE = "data/q2_turnaround.csv"
INPUT_TRACKER = "data/performance.csv"

def get_symbols_to_scan():
    symbols = set()
    # 1. ఇప్పటికే రాడార్ పెర్ఫార్మెన్స్ ఫైల్ లో ఉన్న స్టాక్స్ సేకరణ
    if os.path.exists(INPUT_TRACKER):
        try:
            df = pd.read_csv(INPUT_TRACKER)
            if "Symbol" in df.columns:
                symbols.update(df["Symbol"].dropna().unique().tolist())
        except Exception as e:
            print("Error reading tracker:", e)
    
    # 2. అదనపు ప్రముఖ లిక్విడ్ కంపెనీల పూల్
    default_pool = [
        "PPLPHARMA", "NAVINFLUOR", "AJANTPHARM", "LAURUSLABS", 
        "TATACHEM", "DEEPAKNTR", "DIXON", "KAYNES", "POLYCAB", "TRENT"
    ]
    symbols.update(default_pool)
    return sorted(list(symbols))

def scan_q2_financials(sym):
    ticker_str = f"{sym}.NS" if not sym.endswith(".NS") else sym
    tk = yf.Ticker(ticker_str)
    
    try:
        q_fin = tk.quarterly_financials
        if q_fin is None or q_fin.empty or len(q_fin.columns) < 2:
            return None
        
        # నికర లాభం (Net Income / PAT) రో వెతకడం
        net_income_row = None
        for key in ["Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"]:
            if key in q_fin.index:
                net_income_row = q_fin.loc[key]
                break
        
        # ఆదాయం / అమ్మకాలు (Revenue / Sales) రో వెతకడం
        rev_row = None
        for key in ["Total Revenue", "Operating Revenue", "Revenue"]:
            if key in q_fin.index:
                rev_row = q_fin.loc[key]
                break
                
        if net_income_row is None or rev_row is None:
            return None

        # ప్రస్తుత త్రైమాసికం (Q2) మరియు గత ఏడాది ఇదే త్రైమాసికం (YoY Q2)
        cur_pat = float(net_income_row.iloc[0])
        # క్వార్టర్లీ ఫైనాన్షియల్స్ లో 4 క్వార్టర్ల వెనుక డేటా (YoY)
        idx_yoy = 4 if len(net_income_row) > 4 else (len(net_income_row) - 1)
        prev_yoy_pat = float(net_income_row.iloc[idx_yoy])
        
        cur_sales = float(rev_row.iloc[0])
        prev_yoy_sales = float(rev_row.iloc[idx_yoy])
        
        # లాజిక్ 1: టర్నరౌండ్ (గత ఏడాది నష్టం, ఈసారి లాభం)
        is_turnaround = (prev_yoy_pat < 0 and cur_pat > 0)
        
        # లాజిక్ 2: PAT వృద్ధి శాతం
        if prev_yoy_pat > 0:
            pat_growth = ((cur_pat - prev_yoy_pat) / prev_yoy_pat) * 100
        elif is_turnaround:
            pat_growth = 999.0  # టర్నరౌండ్ ఇండికేటర్
        else:
            pat_growth = 0.0

        # లాజిక్ 3: సేల్స్ వృద్ధి శాతం
        sales_growth = ((cur_sales - prev_yoy_sales) / prev_yoy_sales) * 100 if prev_yoy_sales > 0 else 0.0
        
        # కనీస ఫిల్టర్: టర్నరౌండ్ అయినా ఉండాలి లేదా PAT వృద్ధి కనీసం 25% ఉండాలి
        if not (is_turnaround or pat_growth >= 25.0):
            return None

        # టెక్నికల్ ప్రైస్ & వాల్యూమ్ ధృవీకరణ
        hist = tk.history(period="3mo")
        if hist.empty:
            return None
            
        cur_price = round(float(hist["Close"].iloc[-1]), 2)
        avg_vol = float(hist["Volume"].tail(20).mean())
        cur_vol = float(hist["Volume"].iloc[-1])
        vol_ratio = round(cur_vol / avg_vol, 2) if avg_vol > 0 else 1.0

        # స్కోరింగ్ విధానం (0 నుండి 100)
        score = 60
        if is_turnaround: 
            score += 20
        if pat_growth >= 50: 
            score += 10
        if vol_ratio >= 2.0: 
            score += 10

        return {
            "Symbol": sym.replace(".NS", ""),
            "Score": min(100, score),
            "Turnaround": "Yes" if is_turnaround else "No",
            "PAT_Growth%": round(pat_growth, 1) if pat_growth != 999.0 else "Turnaround (Loss to Profit)",
            "Sales_Growth%": round(sales_growth, 1),
            "CurPrice": cur_price,
            "VolRatio": vol_ratio,
            "Verdict": "Super Turnaround" if is_turnaround else "Strong Growth"
        }
    except Exception:
        return None

def main():
    symbols = get_symbols_to_scan()
    results = []
    print(f"Q2 స్కానింగ్ మొదలైంది... మొత్తం స్టాక్స్: {len(symbols)}")
    
    for sym in symbols:
        data = scan_q2_financials(sym)
        if data:
            results.append(data)
            print(f"దొరికింది: {data['Symbol']} | టర్నరౌండ్: {data['Turnaround']} | స్కోర్: {data['Score']}")

    if results:
        df_out = pd.DataFrame(results)
        df_out = df_out.sort_values(by="Score", ascending=False)
        os.makedirs("data", exist_ok=True)
        df_out.to_csv(OUTPUT_FILE, index=False)
        print(f"విజయవంతంగా సేవ్ చేయబడింది: {OUTPUT_FILE}")
    else:
        print("క్రైటీరియాకు సరిపోయే స్టాక్స్ లభించలేదు.")

if __name__ == "__main__":
    main()
