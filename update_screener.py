import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
import pandas as pd
import requests

# IST Timezone (UTC +5:30)
IST = timezone(timedelta(hours=5, minutes=30))

def get_target_date():
    now_ist = datetime.now(IST)
    # If run before 6:30 PM IST, use yesterday's date
    if now_ist.hour < 18 or (now_ist.hour == 18 and now_ist.minute < 30):
        now_ist -= timedelta(days=1)
    # Roll back weekend days to Friday
    while now_ist.weekday() >= 5:
        now_ist -= timedelta(days=1)
    return now_ist

def fetch_nse_bhavcopy(date_obj):
    date_str = date_obj.strftime("%Y%m%d")
    url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://www.nseindia.com/all-reports"
    }
    session = requests.Session()
    session.get("https://www.nseindia.com", headers=headers, timeout=15)
    resp = session.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        csv_name = z.namelist()[0]
        df = pd.read_csv(z.open(csv_name))

    # Filter only Equity series (EQ, BE, BZ, SM, ST)
    df = df[df["SctySrs"].isin(["EQ", "BE", "BZ", "SM", "ST"])].copy()
    df = df.rename(columns={
        "TckrSymb": "symbol",
        "FinInstrmNm": "name",
        "ISIN": "isin",
        "OpnPric": "open",
        "HghPric": "high",
        "LwPric": "low",
        "ClsPric": "close",
        "PrvsClsgPric": "prev_close",
        "TtlTradgVol": "nse_volume",
        "TtlTrfVal": "nse_turnover"
    })
    df["exchange"] = "NSE"
    return df[["isin", "symbol", "name", "exchange", "open", "high", "low", "close", "prev_close", "nse_volume", "nse_turnover"]]

def fetch_bse_bhavcopy(date_obj):
    date_str = date_obj.strftime("%Y%m%d")
    url = f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{date_str}_F_0000.CSV"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.bseindia.com/markets/marketinfo/bhavcopy.aspx"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    df = pd.read_csv(io.BytesIO(resp.content))
    df = df[df["FinInstrmTp"] == "STK"].copy()
    df = df.rename(columns={
        "TckrSymb": "bse_symbol",
        "FinInstrmId": "bse_code",
        "FinInstrmNm": "name",
        "ISIN": "isin",
        "OpnPric": "open",
        "HghPric": "high",
        "LwPric": "low",
        "ClsPric": "close",
        "PrvsClsgPric": "prev_close",
        "TtlTradgVol": "bse_volume",
        "TtlTrfVal": "bse_turnover"
    })
    df["exchange"] = "BSE"
    return df[["isin", "bse_symbol", "bse_code", "name", "exchange", "open", "high", "low", "close", "prev_close", "bse_volume", "bse_turnover"]]

def main():
    target_date = get_target_date()
    print(f"Fetching Bhavcopy for {target_date.strftime('%Y-%m-%d')}...")

    nse_df = pd.DataFrame()
    bse_df = pd.DataFrame()

    try:
        nse_df = fetch_nse_bhavcopy(target_date)
        print(f"Loaded {len(nse_df)} NSE stocks.")
    except Exception as e:
        print(f"NSE fetch skipped/failed (possibly market holiday): {e}")

    try:
        bse_df = fetch_bse_bhavcopy(target_date)
        print(f"Loaded {len(bse_df)} BSE stocks.")
    except Exception as e:
        print(f"BSE fetch skipped/failed: {e}")

    if nse_df.empty and bse_df.empty:
        print("No data available for this date (market holiday). Exiting cleanly.")
        return

    # Merge NSE & BSE on ISIN (prefer NSE price if listed on both, combine volumes)
    if not nse_df.empty and not bse_df.empty:
        merged = pd.merge(nse_df, bse_df, on="isin", how="outer", suffixes=("_nse", "_bse"))
        merged["symbol"] = merged["symbol"].fillna(merged["bse_symbol"])
        merged["name"] = merged["name_nse"].fillna(merged["name_bse"])
        merged["exchange"] = merged.apply(lambda r: "NSE+BSE" if pd.notna(r["close_nse"]) and pd.notna(r["close_bse"]) else ("NSE" if pd.notna(r["close_nse"]) else "BSE"), axis=1)
        for col in ["open", "high", "low", "close", "prev_close"]:
            merged[col] = merged[f"{col}_nse"].fillna(merged[f"{col}_bse"])
        merged["volume"] = merged["nse_volume"].fillna(0) + merged["bse_volume"].fillna(0)
        merged["turnover"] = merged["nse_turnover"].fillna(0) + merged["bse_turnover"].fillna(0)
    else:
        merged = nse_df if not nse_df.empty else bse_df
        if "bse_symbol" in merged.columns:
            merged["symbol"] = merged["bse_symbol"]
        merged["volume"] = merged.get("nse_volume", merged.get("bse_volume", 0))
        merged["turnover"] = merged.get("nse_turnover", merged.get("bse_turnover", 0))

    # Calculate daily % change
    merged["change_pct"] = (((merged["close"] - merged["prev_close"]) / merged["prev_close"]) * 100).round(2)
    merged = merged.fillna(0)

    final_cols = ["isin", "symbol", "name", "exchange", "open", "high", "low", "close", "prev_close", "change_pct", "volume", "turnover"]
    records = merged[final_cols].to_dict(orient="records")

    output = {
        "last_updated_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        "trading_date": target_date.strftime("%Y-%m-%d"),
        "total_stocks": len(records),
        "stocks": records
    }

    with open("latest_stocks.json", "w") as f:
        json.dump(output, f)
    print(f"Saved {len(records)} stocks to latest_stocks.json")

if __name__ == "__main__":
    main()
