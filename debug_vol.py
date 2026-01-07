
import pandas as pd
import numpy as np
from data_service import DataService

ds = DataService.demo()
date = "2025-01-01"
ticker = "SPY"
orderid = "oid10001"
exch_open = "09:30"
exch_close = "16:00"

vol_df = ds.get_volume_data(date, ticker, exch_open, exch_close, interval="1min")
print("AUCTION ROWS IN DATA_SERVICE:")
print(vol_df[vol_df["Kind"] != "Regular"])

# Now simulate relevant part of plotly_order_viz.py
exch_open_dt = pd.to_datetime(f"{date} {exch_open}:00")
bin_delta = pd.to_timedelta(1, unit="m")
time_fmt = "%H:%M"
open_bin_time = exch_open_dt - pd.Timedelta(minutes=1)
close_bin_time = pd.to_datetime(f"{date} {exch_close}:00")

regular_vol = vol_df.loc[vol_df["Kind"] == "Regular"].copy()
auction_vol = vol_df.loc[vol_df["Kind"] != "Regular"].copy()

plot_vol = regular_vol.copy()
start_txt = plot_vol["Time"].dt.strftime(time_fmt)
end_txt = (plot_vol["Time"] + bin_delta).dt.strftime(time_fmt)
plot_vol["HoverLabel"] = start_txt + "–" + end_txt

def _append_auction_bar(plot_vol, target_time, auction_df, label):
    if auction_df.empty: return plot_vol
    auction_total = float(pd.to_numeric(auction_df["Volume"], errors="coerce").fillna(0).sum())
    row_data = {
        "Time": target_time, 
        "Volume": auction_total, 
        "LitVolume": auction_total,
        "DarkVolume": 0,
        "HoverLabel": label,
        "Kind": label
    }
    return pd.concat([plot_vol, pd.DataFrame([row_data])], ignore_index=True)

open_rows = auction_vol.loc[auction_vol["Kind"] == "Open"].copy()
close_rows = auction_vol.loc[auction_vol["Kind"] == "Close"].copy()

plot_vol = _append_auction_bar(plot_vol, open_bin_time, open_rows, "Open")
plot_vol = _append_auction_bar(plot_vol, close_bin_time, close_rows, "Close")

plot_vol = plot_vol.sort_values("Time")
print("\nFINAL PLOT_VOL HEAD (near Open):")
print(plot_vol.head(3))
print("\nFINAL PLOT_VOL TAIL (near Close):")
print(plot_vol.tail(3))
