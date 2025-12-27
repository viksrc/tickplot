"""Data access layer (DAL) for the Shiny order visualizer.

This module intentionally keeps UI formatting out of the data layer.
It returns raw DataFrames / primitives that the Shiny layer formats.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


def _build_venue_mapping() -> dict[str, dict[str, str]]:
    """Stable (but pseudo-random) venue mapping used for UI tooltips.

    Names are plausible and start with the venue label.
    Types are fixed per spec: APEX/BORL/CBLT = Exchange, DELT/ECHO/FLUX = Dark Pool.
    """

    venue_types: dict[str, str] = {
        "APEX": "Exchange",
        "BORL": "Exchange",
        "CBLT": "Exchange",
        "DELT": "Dark Pool",
        "ECHO": "Dark Pool",
        "FLUX": "Dark Pool",
    }

    name_options: dict[str, list[str]] = {
        "APEX": ["Apex Exchange", "Aurora Exchange", "Atlas Exchange"],
        "BORL": ["Boreal Exchange", "Banyan Exchange", "Beacon Exchange"],
        "CBLT": ["Cobalt Exchange", "Catalyst Exchange", "Cascade Exchange"],
        "DELT": ["Delta Dark Pool", "Drift Dark Pool", "Dusk Dark Pool"],
        "ECHO": ["Eclipse Dark Pool", "Echo Dark Pool", "Everest Dark Pool"],
        "FLUX": ["Flux Dark Pool", "Fjord Dark Pool", "Fable Dark Pool"],
    }

    rng = np.random.default_rng(20251221)
    mapping: dict[str, dict[str, str]] = {}
    for label, vtype in venue_types.items():
        mapping[label] = {
            "label": label,
            "name": str(rng.choice(name_options[label])),
            "type": vtype,
        }
    return mapping


VENUE_MAPPING: dict[str, dict[str, str]] = _build_venue_mapping()


# Country -> (ExchOpenTime, ExchCloseTime) in local exchange time (HH:MM format)
EXCHANGE_HOURS: dict[str, tuple[str, str]] = {
    "US": ("09:30", "16:00"),  # NYSE/NASDAQ
    "CA": ("09:30", "16:00"),  # TSX
    "GB": ("08:00", "16:30"),  # LSE
    "DE": ("09:00", "17:30"),  # Xetra
    "FR": ("09:00", "17:30"),  # Euronext Paris
    "JP": ("09:00", "15:00"),  # Tokyo (lunch break ignored)
    "CN": ("09:30", "15:00"),  # Shanghai (lunch break ignored)
    "IN": ("09:15", "15:30"),  # NSE India
    "AU": ("10:00", "16:00"),  # ASX
    "BR": ("10:00", "17:00"),  # B3
}


def _irregular_time_index(
    *,
    date: str,
    exch_open_time: str,
    exch_close_time: str,
    rng: np.random.Generator,
    min_step_s: int = 2,
    max_step_s: int = 25,
) -> pd.DatetimeIndex:
    start_ts = pd.to_datetime(f"{date} {exch_open_time}:00")
    end_ts = pd.to_datetime(f"{date} {exch_close_time}:00")

    times: list[pd.Timestamp] = [start_ts]
    current = start_ts
    while True:
        step_s = int(rng.integers(min_step_s, max_step_s + 1))
        current = current + pd.to_timedelta(step_s, unit="s")
        if current >= end_ts:
            break
        times.append(current)

    if times[-1] != end_ts:
        times.append(end_ts)

    return pd.DatetimeIndex(times)


def _generate_stock_and_execution_data(
    *,
    date: str,
    ticker: str,
    exec_qty: int | None,
    start_time: str | None,
    end_time: str | None,
    side: str | None,
    exch_open_time: str,
    exch_close_time: str,
    country: str = "US",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pure simulation function used by the DataService.

    Returns:
      stock_data: columns Time, Bid, Ask, BidSize, AskSize, Volume
      execution_data: columns Time, Price, Size, Venue, Bid, Ask, spreadcapture
    """

    seed = sum(ord(c) for c in ticker) * 42
    rng = np.random.default_rng(seed)

    time_index = _irregular_time_index(date=date, exch_open_time=exch_open_time, exch_close_time=exch_close_time, rng=rng)
    n_points = len(time_index)

    base_price = 50 + (seed % 400)
    mid_price = base_price + np.cumsum(rng.standard_normal(n_points) * 0.5)

    spread_bps = rng.uniform(10, 30, n_points)
    spread = mid_price * spread_bps / 10000

    volume = rng.integers(10000, 50000, n_points)
    bid_size = rng.integers(100, 5000, n_points)
    ask_size = rng.integers(100, 5000, n_points)

    stock_data = pd.DataFrame(
        {
            "Time": time_index,
            "Bid": mid_price - spread / 2,
            "Ask": mid_price + spread / 2,
            "BidSize": bid_size,
            "AskSize": ask_size,
            "Volume": volume,
        }
    )

    # Split Volume into Lit/Dark for US orders (Dark ~10-40%)
    if country == "US":
        dark_pct = rng.uniform(0.1, 0.5, n_points)
        dark_vol = (volume * dark_pct).astype(int)
        lit_vol = volume - dark_vol
    else:
        # Non-US: 100% Lit, 0% Dark
        dark_vol = np.zeros(n_points, dtype=int)
        lit_vol = volume
    
    stock_data["LitVolume"] = lit_vol
    stock_data["DarkVolume"] = dark_vol

    exec_seed = seed + 123
    exec_rng = np.random.default_rng(exec_seed)

    # Determine execution times
    if start_time and end_time:
        start_dt = pd.to_datetime(f"{date} {start_time}:00")
        end_dt = pd.to_datetime(f"{date} {end_time}:00")

        first_offset = exec_rng.integers(2, 11)
        first_exec_time = start_dt + pd.Timedelta(seconds=first_offset)

        duration_s = (end_dt - first_exec_time).total_seconds()
        if duration_s > 0:
            offsets = exec_rng.uniform(0, duration_s, 48)
            exec_times = pd.to_datetime(
                [
                    first_exec_time,
                    *[first_exec_time + pd.Timedelta(seconds=o) for o in offsets],
                    end_dt,
                ]
            )
        else:
            exec_times = pd.to_datetime([first_exec_time] * 50)
        exec_times = pd.Series(exec_times).sort_values().reset_index(drop=True)
    else:
        # Calculate session duration in seconds from exchange hours
        open_dt = pd.to_datetime(f"{date} {exch_open_time}:00")
        close_dt = pd.to_datetime(f"{date} {exch_close_time}:00")
        session_duration_s = int((close_dt - open_dt).total_seconds())
        exec_offsets_s = exec_rng.integers(0, session_duration_s + 1, 50)
        exec_times = open_dt + pd.to_timedelta(exec_offsets_s, unit="s")
        exec_times = exec_times.sort_values()

    # Sizes
    log_sizes = exec_rng.lognormal(mean=6.0, sigma=0.8, size=50)
    raw_sizes = np.clip(log_sizes, 50, 5000)

    if exec_qty:
        scale_factor = exec_qty / raw_sizes.sum()
        exec_sizes = np.round(raw_sizes * scale_factor).astype(int)
        exec_sizes[-1] = int(exec_qty) - int(exec_sizes[:-1].sum())
    else:
        exec_sizes = raw_sizes.astype(int)

    # Prevailing quotes at execution time
    exec_time_df = pd.DataFrame({"Time": pd.to_datetime(exec_times)})
    quote_df = stock_data[["Time", "Bid", "Ask"]].sort_values("Time")
    exec_time_df = pd.merge_asof(
        exec_time_df.sort_values("Time"),
        quote_df,
        on="Time",
        direction="backward",
        allow_exact_matches=True,
    )

    side_norm = (side or "Buy").strip().capitalize()
    bid = exec_time_df["Bid"].to_numpy(dtype=float)
    ask = exec_time_df["Ask"].to_numpy(dtype=float)
    mid = (bid + ask) / 2.0
    spread_abs = ask - bid

    n_exec = len(exec_time_df)
    u = exec_rng.random(n_exec)

    near = bid if side_norm == "Buy" else ask
    far = ask if side_norm == "Buy" else bid

    exec_prices = np.empty(n_exec, dtype=float)
    r = exec_rng.random(n_exec)
    exec_prices[:] = bid + r * spread_abs

    mask_near = u < 0.20
    exec_prices[mask_near] = near[mask_near]

    mask_far = (u >= 0.20) & (u < 0.35)
    exec_prices[mask_far] = far[mask_far]

    mask_mid = (u >= 0.35) & (u < 0.55)
    exec_prices[mask_mid] = mid[mask_mid]

    mask_bad = ~np.isfinite(exec_prices) | ~np.isfinite(mid) | (spread_abs == 0)
    exec_prices[mask_bad] = mid[mask_bad]

    buy_capture = (ask - exec_prices) / spread_abs
    sell_capture = (exec_prices - bid) / spread_abs
    spreadcapture = np.where(
        spread_abs != 0,
        np.where(side_norm == "Buy", buy_capture, sell_capture),
        np.nan,
    )

    venues = ["APEX", "BORL", "CBLT", "DELT", "ECHO", "FLUX"]
    # APEX/BORL/CBLT are exchanges; DELT/ECHO/FLUX are dark pools. Keep weights plausible and summing to 1.
    venue_probs = [0.30, 0.12, 0.12, 0.22, 0.12, 0.12]
    exec_venues = exec_rng.choice(venues, 50, p=venue_probs)

    execution_data = pd.DataFrame(
        {
            "Time": pd.to_datetime(exec_times),
            "Price": exec_prices,
            "Size": exec_sizes,
            "Venue": exec_venues,
            "Bid": exec_time_df["Bid"].to_numpy(),
            "Ask": exec_time_df["Ask"].to_numpy(),
            "spreadcapture": spreadcapture,
        }
    )

    return stock_data, execution_data


@dataclass
class DataService:
    """Data access layer.

    Right now this is backed by a deterministic simulation, but it is structured
    like a repository/service so it can later be swapped for DB/API access.
    """

    base_orders: pd.DataFrame

    def __post_init__(self) -> None:
        if "orderid" not in self.base_orders.columns:
            raise ValueError("base_orders must include an 'orderid' column")
        if self.base_orders["orderid"].duplicated().any():
            raise ValueError("base_orders.orderid must be unique")

        # Simple per-instance caches
        self._orders_cache: dict[str, pd.DataFrame] = {}
        self._prices_cache: dict[tuple[str, str], pd.DataFrame] = {}
        self._exec_cache: dict[tuple[str, str], pd.DataFrame] = {}

    @classmethod
    def demo(cls) -> "DataService":
        """Create the demo dataset used by the current app."""

        rng = np.random.default_rng(42)

        # 2 orders per country = 20 orders total
        countries_base = ["US", "DE", "JP", "GB", "FR", "CA", "AU", "BR", "IN", "CN"]
        countries = [c for c in countries_base for _ in range(2)]  # Duplicate each country
        num_orders = len(countries)  # 20 orders

        strategy_choices = rng.choice(["VWAP", "Arrival", "Close"], size=num_orders, p=[0.6, 0.2, 0.2])
        
        # Tickers: 2 per country
        tickers_base = ["SPY", "EWG", "EWJ", "EWU", "EWQ", "EWC", "EWA", "EWZ", "INDA", "FXI"]
        tickers_alt = ["QQQ", "DAX", "NKY", "FTSE", "CAC", "TSX", "ASX", "IBV", "NSEI", "SSEC"]
        tickers = []
        for i, country in enumerate(countries_base):
            tickers.append(tickers_base[i])  # First order uses base ticker
            tickers.append(tickers_alt[i])   # Second order uses alt ticker
        
        # Look up exchange hours for each country
        exch_open_times: list[str] = []
        exch_close_times: list[str] = []
        for country in countries:
            open_t, close_t = EXCHANGE_HOURS[country]  # Require valid country
            exch_open_times.append(open_t)
            exch_close_times.append(close_t)

        # StartTime and EndTime logic - now respects per-country exchange hours
        start_times: list[str] = []
        end_times: list[str] = []
        for i in range(num_orders):
            open_t = exch_open_times[i]
            close_t = exch_close_times[i]
            
            # Convert to minutes since midnight for random generation
            open_min = int(open_t.split(":")[0]) * 60 + int(open_t.split(":")[1])
            close_min = int(close_t.split(":")[0]) * 60 + int(close_t.split(":")[1])
            
            if rng.random() < 0.5:
                st_min = open_min
            else:
                st_min = int(rng.integers(open_min, close_min - 30))  # At least 30 min before close

            st = (pd.to_datetime("00:00") + pd.to_timedelta(st_min, unit="m")).time()

            if rng.random() < 0.5:
                et_min = close_min
            else:
                et_min = int(rng.integers(st_min + 10, close_min + 1))  # At least 10 min after start

            et = (pd.to_datetime("00:00") + pd.to_timedelta(et_min, unit="m")).time()

            start_times.append(st.strftime("%H:%M"))
            end_times.append(et.strftime("%H:%M"))

        # Force first 3 orders to full session
        for i in range(min(3, len(start_times))):
            start_times[i] = exch_open_times[i]
            end_times[i] = exch_close_times[i]

        # PctADV: 50% probability in [0, 1) and 50% in [1, 10]
        pct_adv = np.empty(num_orders, dtype=float)
        mask_small = rng.random(num_orders) < 0.5
        pct_adv[mask_small] = rng.uniform(0.0, 1.0, size=int(mask_small.sum()))
        pct_adv[~mask_small] = rng.uniform(1.0, 10.0, size=int((~mask_small).sum()))
        pct_adv = np.round(pct_adv, 2)

        # PRate = PctADV / durationfrac
        # durationfrac = (EndTime - StartTime) / (ExchCloseTime - ExchOpenTime)
        def _time_to_mins(t: str) -> int:
            parts = t.split(":")
            return int(parts[0]) * 60 + int(parts[1])
        
        prate = []
        for i in range(num_orders):
            order_duration = _time_to_mins(end_times[i]) - _time_to_mins(start_times[i])
            session_duration = _time_to_mins(exch_close_times[i]) - _time_to_mins(exch_open_times[i])
            if session_duration > 0 and order_duration > 0:
                duration_frac = order_duration / session_duration
                prate.append(round(pct_adv[i] / duration_frac, 2))
            else:
                prate.append(pct_adv[i])

        base_orders = pd.DataFrame(
            {
                "id": range(1, num_orders + 1),
                "orderid": [f"oid{10000 + i}" for i in range(1, num_orders + 1)],
                "Country": countries,
                "Side": rng.choice(["Buy", "Sell"], size=num_orders),
                "Ticker": tickers,
                "ExecQty": rng.lognormal(mean=np.log(5000), sigma=1.2, size=num_orders).astype(int).clip(50, 40000),
                "Broker": rng.choice(["CITI", "BAML", "MS", "JPM", "UBS"], size=num_orders),
                "Desk": rng.choice(["DESKA", "DESKB", "DESKC"], size=num_orders),
                "PctADV": pct_adv,
                "PRate": prate,
                "Strategy": strategy_choices,
                "StartTime": start_times,
                "EndTime": end_times,
                "ExchOpenTime": exch_open_times,
                "ExchCloseTime": exch_close_times,
                "Return": rng.uniform(0, 10, size=num_orders).round(2),
                "PerfArrival": rng.normal(15, 50, size=num_orders).round(1).clip(-200, 200),
                "PerfVWAP": rng.normal(3, 15, size=num_orders).round(1).clip(-50, 50),
                "PerfClose": rng.normal(0, 2, size=num_orders).round(1).clip(-5, 5),
            }
        )

        return cls(base_orders=base_orders)

    def _query_orders_for_date(self, date: str) -> pd.DataFrame:
        """Internal helper to return all orders for a single date."""

        if date in self._orders_cache:
            return self._orders_cache[date].copy()

        df = self.base_orders.copy()
        df["Date"] = str(date)
        
        # Consistent with get_order_enriched logic
        self._orders_cache[date] = df
        return df.copy()

    def query_orders(self, start_date: str, end_date: str) -> pd.DataFrame:
        """Return orders for a date range (inclusive), simulating a batch query."""
        try:
            dates = pd.date_range(start=start_date, end=end_date)
        except ValueError:
            # Handle invalid dates or empty range
            return pd.DataFrame()

        dfs = []
        for dt in dates:
            date_str = dt.strftime("%Y-%m-%d")
            dfs.append(self._query_orders_for_date(date_str))
        
        if not dfs:
            return pd.DataFrame()
            
        return pd.concat(dfs, ignore_index=True)

    def get_order_enriched(self, date: str, orderid: str) -> dict[str, Any]:
        """Return a dictionary containing the enriched order and its execution data.
        
        This calculates 'AvgPrice', 'SpreadCapture', 'FillSize' on demand.
        """
        # Get base order details
        try:
            order_detail = self.get_order(date, orderid)
        except KeyError:
            return {}

        # Get executions
        exec_df = self.get_executions(date, orderid)
        
        # Calculate derived metrics
        if len(exec_df) > 0:
            fill_size = int(round(float(exec_df["Size"].mean())))
            total_qty = float(exec_df["Size"].sum())
            
            if total_qty > 0:
                spread_capture_pct = float((exec_df["spreadcapture"] * exec_df["Size"]).sum() / total_qty) * 100.0
                avg_price = float((exec_df["Price"] * exec_df["Size"]).sum() / total_qty)
            else:
                spread_capture_pct = float("nan")
                avg_price = float("nan")
        else:
            fill_size = 0
            spread_capture_pct = float("nan")
            avg_price = float("nan")

        # Enrich the order dictionary
        enriched_order = order_detail.copy()
        enriched_order["FillSize"] = fill_size
        enriched_order["SpreadCapture"] = spread_capture_pct
        enriched_order["AvgPrice"] = avg_price
        
        return {
            "order": enriched_order,
        }

    def get_prices(
        self, date: str, ticker: str,
        exch_open_time: str, exch_close_time: str
    ) -> pd.DataFrame:
        """Return market prices (bid/ask/size/volume) for a date+ticker."""

        key = (str(date), str(ticker))
        if key in self._prices_cache:
            return self._prices_cache[key].copy()

        # Use the same generation, without order-specific overrides.
        stock_df, _ = _generate_stock_and_execution_data(
            date=str(date),
            ticker=str(ticker),
            exec_qty=None,
            start_time=None,
            end_time=None,
            side=None,
            exch_open_time=exch_open_time,
            exch_close_time=exch_close_time,
        )
        self._prices_cache[key] = stock_df
        return stock_df.copy()

    def get_executions(self, date: str, orderid: str) -> pd.DataFrame:
        """Return executions for a date+orderid."""

        key = (str(date), str(orderid))
        if key in self._exec_cache:
            return self._exec_cache[key].copy()

        row = self.base_orders.loc[self.base_orders["orderid"] == str(orderid)]
        if row.empty:
            raise KeyError(f"Unknown orderid: {orderid}")

        rec = row.iloc[0].to_dict()
        exch_open = str(rec["ExchOpenTime"])
        exch_close = str(rec["ExchCloseTime"])
        _, exec_df = _generate_stock_and_execution_data(
            date=str(date),
            ticker=str(rec.get("Ticker", "SPY")),
            exec_qty=int(rec.get("ExecQty") or 0) or None,
            start_time=str(rec.get("StartTime") or "") or None,
            end_time=str(rec.get("EndTime") or "") or None,
            side=str(rec.get("Side") or "") or None,
            exch_open_time=exch_open,
            exch_close_time=exch_close,
            country=str(rec.get("Country", "US")),
        )

        self._exec_cache[key] = exec_df
        return exec_df.copy()

    def get_volume_data(
        self, date: str, ticker: str,
        exch_open_time: str, exch_close_time: str,
        interval: str = "1min"
    ) -> pd.DataFrame:
        """Return aggregated volume data for a date+ticker at the specified interval.

        Includes two synthetic auction points:
        - Open auction (labeled "Open") 30 seconds before exchange open
        - Close auction (labeled "Close") 30 seconds after exchange close

        These are intentionally not treated as a full-duration bin; they are point events
        rendered separately in the UI.
        """
        stock_df = self.get_prices(date, ticker, exch_open_time, exch_close_time)

        # Resample to the requested interval
        volume_df = (
            stock_df.set_index("Time")[["Volume", "LitVolume", "DarkVolume"]]
            .resample(interval)
            .sum()
            .reset_index()
        )

        volume_df["Kind"] = "Regular"

        # Synthetic open/close auction volumes (stable per date+ticker)
        # Use regular bin volumes as a baseline, with deterministic multipliers.
        # Calculate auction times relative to exchange hours
        exch_open_dt = pd.to_datetime(f"{date} {exch_open_time}:00")
        exch_close_dt = pd.to_datetime(f"{date} {exch_close_time}:00")
        open_time = exch_open_dt - pd.Timedelta(seconds=30)
        close_time = exch_close_dt + pd.Timedelta(seconds=30)

        seed = (sum(ord(c) for c in str(ticker)) * 1_000_003) + (sum(ord(c) for c in str(date)) * 97)
        rng = np.random.default_rng(seed)

        def _safe_volume_at(label_time: pd.Timestamp) -> float:
            match = volume_df.loc[volume_df["Time"] == label_time, "Volume"]
            if not match.empty:
                return float(match.iloc[0])
            if not volume_df.empty:
                return float(volume_df["Volume"].iloc[0])
            return 0.0

        open_base = _safe_volume_at(exch_open_dt)
        # Get close base from 1 minute before close
        close_base_dt = exch_close_dt - pd.Timedelta(minutes=1)
        close_base = _safe_volume_at(close_base_dt)

        open_mult = float(rng.uniform(2.0, 4.5))
        close_mult = float(rng.uniform(2.0, 4.5))

        open_vol = int(round(open_base * open_mult))
        close_vol = int(round(close_base * close_mult))

        auction_df = pd.DataFrame(
            {
                "Time": [open_time, close_time],
                "Volume": [open_vol, close_vol],
                "LitVolume": [open_vol, close_vol],  # Auctions are 100% Lit
                "DarkVolume": [0, 0],
                "Kind": ["Open", "Close"],
            }
        )

        volume_df = pd.concat([volume_df, auction_df], ignore_index=True)
        # Fill any NaNs (e.g. if resampling produced empty bins for Lit/Dark)
        volume_df["LitVolume"] = volume_df["LitVolume"].fillna(0)
        volume_df["DarkVolume"] = volume_df["DarkVolume"].fillna(0)
        
        return volume_df

    def get_order(self, date: str, orderid: str) -> dict[str, Any]:
        """Return the base order fields plus a stable demo TraderID."""

        row = self.base_orders.loc[self.base_orders["orderid"] == str(orderid)]
        if row.empty:
            raise KeyError(f"Unknown orderid: {orderid}")

        rec: dict[str, Any] = row.iloc[0].to_dict()
        rec["Date"] = str(date)
        rec["TraderID"] = self._trader_id_for_order(str(orderid))
        return rec

    @staticmethod
    def _trader_id_for_order(orderid: str) -> str:
        # Deterministic 4-letter ID per order (avoids re-randomizing on every render)
        seed = sum(ord(c) for c in orderid) * 97
        rng = np.random.default_rng(seed)
        letters = np.array(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        return "".join(rng.choice(letters, size=4).tolist())
