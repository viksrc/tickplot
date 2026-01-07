
import pandas as pd
from data_service import DataService

# Initialize the demo data service
ds = DataService.demo()

date = "2025-01-01"
orderid = "oid10001"
interval = "5min"

# 1. Get order details to determine ticker and market hours
try:
    order = ds.get_order(date, orderid)
    ticker = order["Ticker"]
    exch_open = order["ExchOpenTime"]
    exch_close = order["ExchCloseTime"]
except Exception as e:
    print(f"Error fetching order: {e}")
    exit(1)

# 2. Fetch the volume data
vol_df = ds.get_volume_data(date, ticker, exch_open, exch_close, interval=interval)

# 3. Separate into categories
open_auction = vol_df[vol_df["Kind"] == "Open"]
close_auction = vol_df[vol_df["Kind"] == "Close"]
regular_bins = vol_df[vol_df["Kind"] == "Regular"].sort_values("Time")

print(f"--- Volume Report for {ticker} ({date}) ---")
print(f"Bin Size: {interval}")
print(f"Exchange Hours: {exch_open} - {exch_close}")
print("-" * 50)

# Print Open Auction
if not open_auction.empty:
    row = open_auction.iloc[0]
    print(f"OPEN AUCTION:  Time: {row['Time'].strftime('%H:%M:%S')} | Volume: {int(row['Volume']):>10,}")

print("\nREGULAR BINS:")
for _, row in regular_bins.iterrows():
    print(f"  Bin Start: {row['Time'].strftime('%H:%M:%S')} | Volume: {int(row['Volume']):>10,}")

# Print Close Auction
if not close_auction.empty:
    row = close_auction.iloc[0]
    print(f"\nCLOSE AUCTION: Time: {row['Time'].strftime('%H:%M:%S')} | Volume: {int(row['Volume']):>10,}")
print("-" * 50)
