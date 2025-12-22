"""Data access layer (DAL) for the Shiny order visualizer.

This module intentionally keeps UI formatting out of the data layer.
It returns raw DataFrames / primitives that the Shiny layer formats.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


def _irregular_time_index(
    *,
    date: str,
    rng: np.random.Generator,
    min_step_s: int = 2,
    max_step_s: int = 25,
) -> pd.DatetimeIndex:
    start_ts = pd.to_datetime(f"{date} 09:30:00")
    end_ts = pd.to_datetime(f"{date} 16:00:00")

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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pure simulation function used by the DataService.

    Returns:
      stock_data: columns Time, Bid, Ask, BidSize, AskSize, Volume
      execution_data: columns Time, Price, Size, Venue, Bid, Ask, spreadcapture
    """

    seed = sum(ord(c) for c in ticker) * 42
    rng = np.random.default_rng(seed)

    time_index = _irregular_time_index(date=date, rng=rng)
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
        exec_offsets_s = exec_rng.integers(0, int(6.5 * 60 * 60) + 1, 50)
        exec_times = pd.to_datetime(f"{date} 09:30:00") + pd.to_timedelta(exec_offsets_s, unit="s")
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

    venues = ["A", "B", "C", "D", "E"]
    venue_probs = [0.35, 0.40 / 3, 0.40 / 3, 0.25, 0.40 / 3]
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

        strategy_choices = rng.choice(["VWAP", "Arrival", "Close"], size=10, p=[0.6, 0.2, 0.2])

        # StartTime and EndTime logic (similar to existing demo)
        start_times: list[str] = []
        end_times: list[str] = []
        for _ in range(10):
            if rng.random() < 0.5:
                st_min = 570
            else:
                st_min = int(rng.integers(570, 901))

            st = (pd.to_datetime("00:00") + pd.to_timedelta(st_min, unit="m")).time()

            if rng.random() < 0.5:
                et_min = 960
            else:
                et_min = int(rng.integers(st_min, 961))

            et = (pd.to_datetime("00:00") + pd.to_timedelta(et_min, unit="m")).time()

            start_times.append(st.strftime("%H:%M"))
            end_times.append(et.strftime("%H:%M"))

        full_session_n = min(3, len(start_times))
        for i in range(full_session_n):
            start_times[i] = "09:30"
            end_times[i] = "16:00"

        base_orders = pd.DataFrame(
            {
                "id": range(1, 11),
                "orderid": [f"oid{10000 + i}" for i in range(1, 11)],
                "Country": ["US", "DE", "JP", "GB", "FR", "CA", "AU", "BR", "IN", "CN"],
                "Side": rng.choice(["Buy", "Sell"], size=10),
                "Ticker": ["SPY", "EWG", "EWJ", "EWU", "EWQ", "EWC", "EWA", "EWZ", "INDA", "FXI"],
                "ExecQty": rng.lognormal(mean=np.log(5000), sigma=1.2, size=10).astype(int).clip(50, 40000),
                "Strategy": strategy_choices,
                "StartTime": start_times,
                "EndTime": end_times,
                "Return": rng.uniform(0, 10, size=10).round(2),
                "PerfArrival": rng.normal(15, 50, size=10).round(1).clip(-200, 200),
                "PerfVWAP": rng.normal(3, 15, size=10).round(1).clip(-50, 50),
                "PerfClose": rng.normal(0, 2, size=10).round(1).clip(-5, 5),
            }
        )

        return cls(base_orders=base_orders)

    def query_orders(self, date: str) -> pd.DataFrame:
        """Return all orders for a date, including derived execution metrics."""

        if date in self._orders_cache:
            return self._orders_cache[date].copy()

        df = self.base_orders.copy()
        df["Date"] = str(date)

        fill_sizes: list[int] = []
        spreadcaptures: list[float] = []

        for rec in df.to_dict("records"):
            oid = str(rec["orderid"])
            exec_df = self.get_executions(date, oid)

            if len(exec_df) > 0:
                fill_sizes.append(int(round(float(exec_df["Size"].mean()))))
            else:
                fill_sizes.append(0)

            total_qty = float(exec_df["Size"].sum())
            if total_qty > 0:
                wavg_sc = float((exec_df["spreadcapture"] * exec_df["Size"]).sum() / total_qty)
                spreadcaptures.append(wavg_sc * 100.0)
            else:
                spreadcaptures.append(float("nan"))

        df["FillSize"] = fill_sizes
        df["SpreadCapture"] = spreadcaptures

        self._orders_cache[date] = df
        return df.copy()

    def get_prices(self, date: str, ticker: str) -> pd.DataFrame:
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
        _, exec_df = _generate_stock_and_execution_data(
            date=str(date),
            ticker=str(rec.get("Ticker", "SPY")),
            exec_qty=int(rec.get("ExecQty") or 0) or None,
            start_time=str(rec.get("StartTime") or "") or None,
            end_time=str(rec.get("EndTime") or "") or None,
            side=str(rec.get("Side") or "") or None,
        )

        self._exec_cache[key] = exec_df
        return exec_df.copy()

    def get_order_detail(self, date: str, orderid: str) -> dict[str, Any]:
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
