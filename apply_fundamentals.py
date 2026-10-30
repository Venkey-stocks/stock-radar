import os
import math
import pandas as pd

MCAP_MIN_ULTRA = 1000     # Rs కోట్లు (మరీ చిన్న కంపెనీలను మాత్రమే ఆపడానికి)

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
    return "High Conviction" if s >= 75 else ("Good Setup" if s >= 55 else "Early Watch")


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
            
            # ASM / GSM కఠినమైన నిషేధం
            if str(fr["ASM"]) == "Yes" or str(fr["GSM"]) == "Yes":
                why = "ASM list" if str(fr["ASM"]) == "Yes" else "GSM list"
                excluded.append({"Date": date, "Scan": scan, "Symbol": sym, "Score": score, "Reason": why})
                continue
                
            mcap = fl(fr["MarketCapCr"])
            # మార్కెట్ క్యాప్ మరీ చిన్నది (< 1,000 కోట్లు) ఉంటేనే తీసేస్తాం, డేటా లేకపోతే వార్నింగ్ మాత్రమే ఇస్తాం
            if scan == "ultra" and mcap is not None and mcap < MCAP_MIN_ULTRA:
                excluded.append({"Date": date, "Scan": scan, "Symbol": sym, "Score": score,
                                 "Reason": "Market cap Rs %d crore (below 1,000)" % mcap})
                continue
            if scan == "ultra" and mcap is None:
                warns.append("Market cap unknown (Rs 1,000 crore minimum not verified)")
                
            if str(fr["ASM"]) == "Unknown" or str(fr["GSM"]) == "Unknown":
                warns.append("ASM/GSM list could not be checked today")

            sector = str(fr["Sector"]) if pd.notna(fr["Sector"]) else ""
            de = fl(fr["DebtEquity"])
            if de is not None and sector != "Financial Services":
                if de > 2.0:
                    score -= 5
                    warns.append("High debt: debt/equity %.2f" % de)
                elif de > 1.0:
                    score -= 2
                    warns.append("Debt is on the high side: debt/equity %.2f" % de)

            pl, pr = fl(fr["PledgePct"]), fl(fr["PromoterPct"])
            if pr is not None and pr <= 0:
                pr = None
            pp = None
            if pl is not None and pr is not None and pr > 0:
                pp = round(pl / pr * 100, 1)
                if pp >= 25:
                    score -= 5
                    warns.append("High promoter pledge: %.1f%% of promoter shares" % pp)
                elif pp >= 10:
                    score -= 2
                    warns.append("Promoter pledge %.1f%% of promoter shares" % pp)

            d = fl(fr["DaysToResults"])
            if d is not None and d < 999:
                if scan == "ultra":
                    if d <= 2:
                        score -= 8
                        warns.append("Results in %d day(s), too close for a 1-5 day trade" % d)
                    elif d <= 5:
                        score -= 4
                        warns.append("Results in %d days" % d)
                    elif d <= 10:
                        score -= 3
                        warns.append("Results in %d days (gap risk)" % d)

            info = {"MarketCapCr": "" if mcap is None else int(mcap),
                    "DebtEquity": "" if de is None else de,
                    "PledgeOfPromoterPct": "" if pp is None else pp,
                    "PromoterPct": "" if pr is None else pr,
                    "Sector": sector,
                    "NextResults": fr["NextResults"] if pd.notna(fr["NextResults"]) else ""}

        if score != float(r["Score"]):
            n_pen += 1
            
        # స్కోర్ కనీసం 10 పాయింట్లు ఉండేలా బౌండరీ
        score = round(max(score, 10.0), 1)
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
    print(scan, ": మొదట", len(df), "| తొలగించినవి", len(df) - len(out), "| score తగ్గినవి", n_pen, "| మిగిలినవి", len(out))


process("data/ultra_short.csv", "ultra", "ultra")
process("data/short_term.csv", "short", "short")

pd.DataFrame(excluded, columns=["Date", "Scan", "Symbol", "Score", "Reason"]).to_csv("data/excluded.csv", index=False)
for e in excluded:
    print("తొలగింపు:", e["Scan"], e["Symbol"], "-", e["Reason"])
