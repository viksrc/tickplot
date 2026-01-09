import pytest
import pandas as pd
import numpy as np
import os
import sys

# Ensure project root is in path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from data_service import DataService, DataServiceInterface
from plotly_order_viz import get_bin_policy, calculate_default_range, create_order_viz

def test_calculate_analytics_math():
    """Priority 1: Unit test _calculate_analytics logic."""
    ds = DataService.demo()
    
    # 1. Create mock execution data
    # (Simplified from _generate_stock_and_execution_data)
    exec_df = pd.DataFrame([
        {"Size": 100, "Price": 150.0, "spreadcapture": 0.5},
        {"Size": 200, "Price": 150.5, "spreadcapture": -0.1},
    ])
    
    # 2. Create mock price data (though not strictly needed for current analytics)
    price_df = pd.DataFrame([{"Volume": 1000}])
    
    analytics = ds._calculate_analytics(exec_df, price_df)
    
    # Expected calculations:
    # FillSize = mean(100, 200) = 150
    # TotalQty = 300
    # SpreadCapture = (0.5*100 + -0.1*200) / 300 = (50 - 20) / 300 = 30 / 300 = 0.1
    # SpreadCapturePct = 0.1 * 100 = 10.0%
    # AvgPrice = (150*100 + 150.5*200) / 300 = (15000 + 30100) / 300 = 45100 / 300 = 150.333...
    
    assert analytics["FillSize"] == 150
    assert pytest.approx(analytics["SpreadCapture"]) == 10.0
    assert pytest.approx(analytics["AvgPrice"]) == 150.33333333

def test_calculate_analytics_empty():
    """Precision: Check empty execution handling."""
    ds = DataService.demo()
    analytics = ds._calculate_analytics(pd.DataFrame(), pd.DataFrame())
    assert analytics["FillSize"] == 0
    assert np.isnan(analytics["SpreadCapture"])
    assert np.isnan(analytics["AvgPrice"])

class MockDataService(DataServiceInterface):
    """Stub to test base class behavior by providing fixed implementation of abstracts."""
    def __init__(self, exec_df, volume_df):
        self.exec_df = exec_df
        self.volume_df = volume_df
        
    def get_executions(self, date, orderid): return self.exec_df
    def get_volume_data(self, date, ticker, open_t, close_t, interval="1min"): return self.volume_df
    def query_orders(self, s_date, e_date): return pd.DataFrame()
    def query_sql(self, query, df=None): return pd.DataFrame()
    def get_order_enriched(self, d, o): return {}
    def get_order(self, d, o): return {}
    def get_prices(self, d, t, ot, ct): return pd.DataFrame()

def test_binned_analytics_auctions():
    """Priority 1: Verify get_binned_analytics handles auctions correctly."""
    date = "2025-01-01"
    # Fills: 1 Open, 1 Regular, 1 Close
    exec_df = pd.DataFrame([
        {"Time": f"{date} 09:25:00", "Size": 10, "Kind": "Open"},
        {"Time": f"{date} 10:00:00", "Size": 50, "Kind": "Regular"},
        {"Time": f"{date} 16:00:00", "Size": 20, "Kind": "Close"},
    ])
    
    # Volume: 1 Open bin, many regular, 1 Close bin
    # Use 5min interval for simplicity
    volume_df = pd.DataFrame([
        {"Time": pd.to_datetime(f"{date} 09:25:00"), "Volume": 100, "Kind": "Open"},
        {"Time": pd.to_datetime(f"{date} 09:30:00"), "Volume": 500, "Kind": "Regular"},
        {"Time": pd.to_datetime(f"{date} 10:00:00"), "Volume": 500, "Kind": "Regular"},
        {"Time": pd.to_datetime(f"{date} 16:00:00"), "Volume": 200, "Kind": "Close"},
    ])
    
    mock_ds = MockDataService(exec_df, volume_df)
    binned = mock_ds.get_binned_analytics(date, "oid1", "TICK", "09:30", "16:00", interval="5min")
    
    # Check counts
    assert len(binned) == 4
    
    # Order: Open (09:25), 09:30, 10:00, Close (16:00)
    # Open
    assert binned.iloc[0]["Kind"] == "Open"
    assert binned.iloc[0]["ExecQty"] == 10
    assert binned.iloc[0]["PRate"] == 10.0 # 10/100
    
    # Regular (10:00)
    reg_10 = binned[binned["Time"] == pd.to_datetime(f"{date} 10:00:00")].iloc[0]
    assert reg_10["ExecQty"] == 50
    assert reg_10["PRate"] == 10.0 # 50/500
    
    # Close
    assert binned.iloc[3]["Kind"] == "Close"
    assert binned.iloc[3]["ExecQty"] == 20
    assert binned.iloc[3]["PRate"] == 10.0 # 20/200

def test_get_bin_policy_thresholds():
    """Priority 2: Unit test get_bin_policy thresholds."""
    # > 160 => 5min
    assert get_bin_policy(161)[0] == "5min"
    
    # > 80 => 2min
    assert get_bin_policy(81)[0] == "2min"
    assert get_bin_policy(80)[0] == "1min"
    
    # >= 40 => 1min
    assert get_bin_policy(41)[0] == "1min"
    assert get_bin_policy(40)[0] == "1min"
    assert get_bin_policy(39)[0] == "30s"
    
    # Small => 30s
    assert get_bin_policy(5)[0] == "30s"

def test_calculate_default_range_padding():
    """Priority 2: Unit test calculate_default_range padding levels."""
    date = "2025-01-01"
    
    # Long order (>120m) => 30m padding
    # 10:00 to 13:00 (180m)
    s, e, _ = calculate_default_range(date, "10:00", "13:00", "09:30", "16:00")
    assert "09:30" in s # max(09:30, 10:00-30m) = 09:30
    assert "13:30" in e # 13:00+30m = 13:30
    
    # Medium order (>20m) => 10m padding
    # 10:00 to 10:30 (30m)
    s, e, _ = calculate_default_range(date, "10:00", "10:30", "09:30", "16:00")
    assert "09:50" in s # 10:00-10m = 09:50
    assert "10:40" in e # 10:30+10m = 10:40
    
    # Short order (<=20m) => 5m padding
    # 10:00 to 10:10 (10m)
    s, e, _ = calculate_default_range(date, "10:00", "10:10", "09:30", "16:00")
    assert "09:55" in s
    assert "10:15" in e

def test_create_order_viz_traces():
    """Priority 2: Verify create_order_viz returns expected traces."""
    # This requires more state but we can use real DataService and mock parts if needed
    # Or just run it on a small simulated slice
    ds = DataService.demo()
    date = "2025-01-01"
    ticker = "SPY"
    
    fig = create_order_viz(
        data_service=ds,
        date=date,
        ticker=ticker,
        orderid="oid10001",
        start_time_str="09:30",
        end_time_str="16:00",
        bin_size="5min",
        is_dark=False,
        theme_colors={"primary": "blue", "secondary": "gray", "body_color": "white", "warning": "orange", "danger": "red"},
        x_range=[f"{date} 09:25:00", f"{date} 16:05:00"],
        default_x_range=[f"{date} 09:25:00", f"{date} 16:05:00"],
        exch_open_time="09:30",
        exch_close_time="16:00"
    )
    
    trace_names = [t.name for t in fig.data]
    # Expected traces:
    # 0: Bid
    # 1: Ask
    # 2: VWAP
    # 3: Lit Volume
    # 4: Dark Volume (always there in US)
    # 5: Executions (bubbles)
    # 6: PRate (shaded area)
    
    assert "Bid" in trace_names
    assert "Ask" in trace_names
    assert "Lit Volume" in trace_names
    assert "Dark Volume" in trace_names
    assert "Executions" in trace_names
    assert "PRate" in trace_names
    
    # Verify subplots
    # xaxis (price), xaxis2 (volume), xaxis3 (rangeslider/shared)
    # Wait, usually yaxis, yaxis2, yaxis3.
    # Price is on y1, Volume is on y2, PRate is on y4 (overlayed on y2)
    # Spacing and layout checks:
    assert fig.layout.yaxis.domain[0] > 0.3 # Price chart is on top
    assert fig.layout.yaxis2.domain[1] < 0.45 # Volume chart is on bottom

def test_binned_analytics_prate_caps_and_zero():
    """Priority 1: Verify PRate caps at 100% and handles zero volume."""
    date = "2025-01-01"
    # Case 1: Over-participation (Exec > Volume)
    # Case 2: Zero volume (Exec > 0)
    exec_df = pd.DataFrame([
        {"Time": f"{date} 10:00:00", "Size": 1000, "Kind": "Regular"},
        {"Time": f"{date} 10:05:00", "Size": 500, "Kind": "Regular"},
    ])
    
    volume_df = pd.DataFrame([
        {"Time": pd.to_datetime(f"{date} 10:00:00"), "Volume": 500, "Kind": "Regular"},
        {"Time": pd.to_datetime(f"{date} 10:05:00"), "Volume": 0, "Kind": "Regular"},
    ])
    
    mock_ds = MockDataService(exec_df, volume_df)
    binned = mock_ds.get_binned_analytics(date, "oid1", "TICK", "09:30", "16:00", interval="5min")
    
    # 10:00 bin: 1000 exec / 500 vol = 200% -> should cap at 100.0
    bin_1000 = binned[binned["Time"] == pd.to_datetime(f"{date} 10:00:00")].iloc[0]
    assert bin_1000["PRate"] == 100.0
    
    # 10:05 bin: 500 exec / 0 vol = inf -> should cap at 100.0
    bin_1005 = binned[binned["Time"] == pd.to_datetime(f"{date} 10:05:00")].iloc[0]
    assert bin_1005["PRate"] == 100.0
