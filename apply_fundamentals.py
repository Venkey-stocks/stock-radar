import os
import math
import pandas as pd

MCAP_MIN_ULTRA = 1000     # Rs కోట్లు
MIN_FINAL_SCORE = 50.0    # కఠినమైన కట్-ఆఫ్: స్కోర్ 50 కంటే తక్కువ ఉంటే డాష్‌బోర్డ్‌లో చూపించకూడదు!

if not os.path.exists("data/fundamentals.csv"):
    print("fundamentals.csv లేదు, ఏమీ మార్చలేదు")
    raise SystemExit(0)
fund = pd.read_csv("data/fundamentals.csv")
if fund.empty:
    print("fundamentals ఖాళీ, ఏమీ మార్చలేదు")
    raise SystemExit(0)
fund = fund.drop_duplicates("Symbol").set_index("Symbol")


def fl(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except Exception:
        return None


def band_of(s):
    return "High Conviction" if s >= 80 else ("Good Setup" if s >= 65 else "Watchlist")


excluded = []


def process(path, scan, hist_prefix):
    if not os.path.exists(path):
        return
    df = pd.read_csv(path)
    if df.empty:
        print(scan, ": ఫలితాలు లేవు")
        return
    if "FundChecked" in df.columns:
        print(scan, ": ఇప్పటికే వర్తింపజేశాం, దాటవేస్తున్నాం")
        return
    date = str(df["Date"].iloc[0])
    keep = []
    n_pen = 0
    for r in df.to_dict("records"):
        sym = r["Symbol"]
        old = r.get("Warning")
        warns = [w for w in str(old).split("; ") if w] if (old is not None and pd.notna(old)) else []
        score = float(r["Score"])
        info = {"MarketCapCr": "", "DebtEquity": "", "PledgeOfPromoterPct": "", "PromoterPct": "",
                "Sector": "", "NextResults": ""}
        if sym in fund.index:
            fr = fund.loc[sym]
            
            # 1. ASM / GSM కఠినమైన నిషేధం (క్యాపిటల్ ప్రొటెక్షన్)
            if str(fr["ASM"]) == "Yes" or str(fr["GSM"]) == "Yes":
                why = "Exchange ASM List" if str(fr["ASM"]) == "Yes" else "Exchange GSM List"
                excluded.append({"Date": date, "Scan": scan, "Symbol": sym, "Score": score, "Reason": why})
                continue
                
            # 2. అల్ట్రా స్కాన్ మార్కెట్ క్యాప్ ఫిల్టర్
            mcap = fl(fr["MarketCapCr"])
            if scan == "ultra" and mcap is not None and mcap < MCAP_MIN_ULTRA:
                excluded.append({"Date": date, "Scan": scan, "Symbol": sym, "Score": score,
                                 "Reason": "Market cap Rs %d crore (below 1,000)" % mcap})
                continue
            if scan == "ultra" and mcap is None:
                warns.append("Market cap unknown (Rs 1,000 crore minimum not verified)")

            # 3. అప్పుల విశ్లేషణ (Debt Check)
            sector = str(fr["Sector"]) if pd.notna(fr["Sector"]) else ""
            de = fl(fr["DebtEquity"])
            if de is not None and sector != "Financial Services":
                if de > 2.0:
                    score -= 8
                    warns.append("High debt: debt/equity %.2f" % de)
                elif de > 1.0:
                    score -= 4
                    warns.append("Debt is on the high side: debt/equity %.2f" % de)

            # 4. ప్రమోటర్ ప్లెడ్జింగ్
            pl, pr = fl(fr["PledgePct"]), fl(fr["PromoterPct"])
            if pr is not None and pr <= 0:
                pr = None
            pp = None
            if pl is not None and pr is not None and pr > 0:
                pp = round(pl / pr * 100, 1)
                if pp >= 25:
                    score -= 8
                    warns.append("High promoter pledge: %.1f%% of promoter shares" % pp)
                elif pp >= 10:
                    score -= 4
                    warns.append("Promoter pledge %.1f%% of promoter shares" % pp)

            # 5. ఫలితాల రిస్క్ (Earnings Risk)
            d = fl(fr["DaysToResults"])
            if d is not None and d < 999:
                if scan == "ultra":
                    if d <= 5:
                        # అల్ట్రా స్వింగ్ ట్రేడ్‌లో 5 రోజుల్లో ఫలితాలు ఉంటే ట్రేడ్ తీసుకోకూడదు!
                        excluded.append({"Date": date, "Scan": scan, "Symbol": sym, "Score": score,
                                         "Reason": "Earnings in %d days (Gap Risk - Avoid Ultra Trade)" % d})
                        continue
                    elif d <= 10:
                        score -= 6
                        warns.append("Results in %d days (gap risk)" % d)

            info = {"MarketCapCr": "" if mcap is None else int(mcap),
                    "DebtEquity": "" if de is None else de,
                    "PledgeOfPromoterPct": "" if pp is None else pp,
                    "PromoterPct": "" if pr is None else pr,
                    "Sector": sector,
                    "NextResults": fr["NextResults"] if pd.notna(fr["NextResults"]) else ""}

        if score != float(r["Score"]):
            n_pen += 1
            
        score = round(max(score, 0.0), 1)

        # 6. కఠినమైన కట్-ఆఫ్: స్కోర్ 50 దాటకపోతే డాష్‌బోర్డ్‌లో కనిపించకూడదు
        if score < MIN_FINAL_SCORE:
            excluded.append({"Date": date, "Scan": scan, "Symbol": sym, "Score": score,
                             "Reason": f"Conviction Score too low ({score:.1f} < {MIN_FINAL_SCORE})"})
            continue

        r["Score"] = score
        r["Band"] = band_of(score)
        r["Warning"] = "; ".join(dict.fromkeys(warns))
        r.update(info)
        r["FundChecked"] = "Yes"
        keep.append(r)

    cols = list(df.columns)
    for c in ["MarketCapCr", "DebtEquity", "PledgeOfPromoterPct", "PromoterPct", "Sector", "NextResults", "FundChecked"]:
        if c not in cols:
            cols.append(c)
            
    out = pd.DataFrame(keep, columns=cols)
    if len(out):
        out = out.sort_values("Score", ascending=False)
    out.to_csv(path, index=False)
    os.makedirs("data/history", exist_ok=True)
    out.to_csv("data/history/%s_%s.csv" % (hist_prefix, date), index=False)
    print(scan, ": మొదట", len(df), "| తొలగించినవి", len(df) - len(out), "| score తగ్గినవి", n_pen, "| అర్హత సాధించినవి (>=50)", len(out))


process("data/ultra_short.csv", "ultra", "ultra")
process("data/short_term.csv", "short", "short")

pd.DataFrame(excluded, columns=["Date", "Scan", "Symbol", "Score", "Reason"]).to_csv("data/excluded.csv", index=False)
for e in excluded:
    print("తొలగింపు:", e["Scan"], e["Symbol"], "-", e["Reason"])
