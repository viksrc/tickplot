from data_service import DataService
import pandas as pd

ds = DataService.demo()
date = "2025-01-01"
ticker = "SPY"
exch_open_time = "09:30"
exch_close_time = "16:00"

vol_df = ds.get_volume_data(date, ticker, exch_open_time, exch_close_time, interval="5min")
print("Volume Data Head:")
print(vol_df.head())
print("\nVolume Data Auction Rows:")
print(vol_df[vol_df["Kind"] != "Regular"])

# Simulate plotly_order_viz logic
auction_vol = vol_df[vol_df["Kind"] != "Regular"]
open_rows = auction_vol[auction_vol["Kind"] == "Open"]
print("\nOpen Rows Filtered:")
print(open_rows)

if not open_rows.empty:
    auction_total = float(pd.to_numeric(open_rows["Volume"], errors="coerce").fillna(0).sum())
    print(f"\nAuction Total Volume: {auction_total}")
else:
    print("\nOpen Rows is EMPTY!")

# Check if exch_open_time is in regular volume
regular_vol = vol_df[vol_df["Kind"] == "Regular"]
print("\nFirst few regular bins:")
print(regular_vol.head())
