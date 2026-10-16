"""
ఫైల్ పేరు: stage_engine.py
వివరణ: స్టాన్ వీన్‌స్టీన్ స్టేజ్ 1B & 2A విశ్లేషణ ఇంజిన్.
ఇది లోతైన గణితాన్ని విశ్లేషించి, ఫ్రంట్‌ఎండ్‌కు సరళమైన తెలుగు రీజనింగ్ అందిస్తుంది.
"""

def evaluate_stage_and_rationale(daily_df, weekly_df, sector_name="", industry_name=""):
    """
    daily_df: కనీసం 50 రోజుల డేటా ఉండాలి (columns: 'close', 'volume')
    weekly_df: కనీసం 30 వారాల డేటా ఉండాలి (columns: 'close', 'high', 'low')
    """
    # డేటా సరిపడా లేకపోతే ఏమీ చేయదు
    if weekly_df is None or daily_df is None or len(weekly_df) < 30 or len(daily_df) < 50:
        return None
    
    current_price = float(daily_df['close'].iloc[-1])
    
    # 1. 30-వారాల (150-DMA) మూవింగ్ యావరేజ్ & స్లోప్
    weekly_df = weekly_df.copy()
    weekly_df['ma30'] = weekly_df['close'].rolling(window=30).mean()
    ma30_current = float(weekly_df['ma30'].iloc[-1])
    ma30_slope = ma30_current - float(weekly_df['ma30'].iloc[-4])
    
    # 2. గత 16 వారాల బేస్ రేంజ్ (Base Formation)
    recent_base = weekly_df.tail(16)
    base_high = float(recent_base['high'].max())
    base_low = float(recent_base['low'].min())
    base_depth_pct = ((base_high - base_low) / base_low) * 100
    
    # 3. వాల్యూమ్ కన్ఫర్మేషన్ (50 రోజుల సగటుతో పోలిక)
    avg_vol_50 = float(daily_df['volume'].rolling(50).mean().iloc[-1])
    vol_ratio = round(float(daily_df['volume'].iloc[-1]) / (avg_vol_50 if avg_vol_50 > 0 else 1), 1)
    
    # బ్రేక్‌అవుట్ లెవల్ (Base High) నుండి దూరం %
    pivot_dist_pct = round(((current_price - base_high) / base_high) * 100, 1)
    
    # రిస్క్ లెవెల్ (స్టాప్ లాస్ - సుమారు 5% డౌన్‌సైడ్)
    stop_loss = round(base_high * 0.95, 2)
    risk_pct = round(((current_price - stop_loss) / current_price) * 100, 1)
    
    # --- అర్హత నిబంధనలు (Stage Rules) ---
    if base_depth_pct <= 35 and ma30_slope >= 0:
        
        # 🟢 PRIME ENTRY: Stage 2A ఫ్రెష్ బ్రేక్‌అవుట్ (0% నుండి 5% లోపు, వాల్యూమ్ >= 1.5x)
        if 0.0 <= pivot_dist_pct <= 5.0 and vol_ratio >= 1.5:
            return {
                "badge": "PRIME ENTRY",
                "badge_color": "green",
                "stage_code": "Stage 2A",
                "score": 95,
                "current_price": current_price,
                "stop_loss": stop_loss,
                "risk_pct": risk_pct,
                "pivot_high": base_high,
                "reasons": [
                    {"title": "సరైన సమయం (Early Stage)", "desc": "గత 4 నెలల నిశ్శబ్దం తర్వాత స్టాక్ ఇప్పుడే ఫ్రెష్ పరుగు ప్రారంభించింది."},
                    {"title": "భారీ కొనుగోళ్లు (Institutional Volume)", "desc": f"రోజూ కంటే {vol_ratio}x రెట్లు ఎక్కువ సంఖ్యలో పెద్ద సంస్థలు డబ్బులు పెట్టాయి."},
                    {"title": "తక్కువ రిస్క్ (Safe Entry Zone)", "desc": f"ప్రస్తుత ధర ₹{current_price}. ఒకవేళ తిరగబడి ₹{stop_loss} కిందకు వస్తే కేవలం {risk_pct}% స్వల్ప నష్టంతో బయటపడొచ్చు."},
                    {"title": "రంగం బలం (Sector Support)", "desc": f"{industry_name or sector_name} పరిశ్రమలోకి ప్రస్తుతం బలమైన పెట్టుబడులు వస్తున్నాయి."}
                ]
            }
            
        # 🟡 WATCHLIST: Stage 1B లేట్ బేస్ (బ్రేక్‌అవుట్‌కు 1% నుండి 3% సమీపంలో)
        elif -3.0 <= pivot_dist_pct < 0.0 and vol_ratio <= 1.2:
            return {
                "badge": "WATCHLIST",
                "badge_color": "gold",
                "stage_code": "Stage 1B",
                "score": 85,
                "current_price": current_price,
                "stop_loss": stop_loss,
                "risk_pct": risk_pct,
                "pivot_high": base_high,
                "reasons": [
                    {"title": "బ్రేక్‌అవుట్ సమీపంలో (Ready to Move)", "desc": f"రెసిస్టెన్స్ లెవెల్ ₹{base_high} కి కేవలం {abs(pivot_dist_pct)}% దూరంలో ఉంది."},
                    {"title": "అమ్మకాలు ఆగిపోయాయి (Supply Absorbed)", "desc": "వాల్యూమ్ పూర్తిగా డ్రై అయిపోయింది; అమ్మకందారులు బలహీనపడ్డారు."},
                    {"title": "చర్య (Action)", "desc": "ముందే కొనకండి. వాల్యూమ్‌తో రెసిస్టెన్స్ దాటగానే ఎంటర్ అవ్వడానికి వాచ్‌లిస్ట్‌లో సిద్ధంగా ఉంచుకోండి."}
                ]
            }
            
    # 🔴 AVOID: ఇప్పటికే 8% కంటే ఎక్కువ పెరిగిపోయినవి (Chasing Risk)
    elif pivot_dist_pct > 8.0:
        return {
            "badge": "AVOID (EXTENDED)",
            "badge_color": "red",
            "stage_code": "Stage 2B",
            "score": 60,
            "current_price": current_price,
            "stop_loss": stop_loss,
            "risk_pct": risk_pct,
            "pivot_high": base_high,
            "reasons": [
                {"title": "చేజ్ చేయకండి (Chasing Risk)", "desc": f"బేస్ నుండి ఇప్పటికే {pivot_dist_pct}% దూరం పెరిగిపోయింది. ఇప్పుడు కొంటే రిస్క్ ఎక్కువ."}
            ]
        }
        
    return None
