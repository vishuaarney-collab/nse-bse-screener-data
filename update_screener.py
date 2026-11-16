import numpy as np

    # Calculate daily % change safely (avoid division by zero on new IPOs)
    merged["change_pct"] = np.where(
        merged["prev_close"] > 0,
        ((merged["close"] - merged["prev_close"]) / merged["prev_close"]) * 100,
        0.0
    )
    merged["change_pct"] = pd.Series(merged["change_pct"]).replace([np.inf, -np.inf], 0.0).fillna(0.0).round(2)

    # Clean all numeric columns so no NaN or Infinity ever enters JSON
    numeric_cols = ["open", "high", "low", "close", "prev_close", "change_pct", "volume", "turnover"]
    for col in numeric_cols:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").replace([np.inf, -np.inf], 0.0).fillna(0.0)

    # Ensure string columns have clean defaults
    for col in ["isin", "symbol", "name", "exchange"]:
        merged[col] = merged[col].fillna("").astype(str)

    final_cols = ["isin", "symbol", "name", "exchange", "open", "high", "low", "close", "prev_close", "change_pct", "volume", "turnover"]
    records = merged[final_cols].to_dict(orient="records")

    output = {
        "last_updated_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        "trading_date": target_date.strftime("%Y-%m-%d"),
        "total_stocks": len(records),
        "stocks": records
    }

    with open("latest_stocks.json", "w") as f:
        json.dump(output, f, allow_nan=False)
    print(f"Saved {len(records)} clean stocks to latest_stocks.json")

if __name__ == "__main__":
    main()
