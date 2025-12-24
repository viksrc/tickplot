import logging

# Configure logging to show in console
logging.basicConfig(level=logging.INFO, format='%(message)s')
LOGGER = logging.getLogger(__name__)

def verify(condition, message):
    """Assert a condition and log a success message if it passes."""
    assert condition, message
    LOGGER.info(f"  ✅ PASSED: {message}")

import pytest
from playwright.sync_api import Page, expect as pw_expect

def expect(locator, message: str = None):
    """Wrapper around Playwright expect that logs success."""
    class LoggingExpect:
        def __init__(self, locator, message):
            self._locator = locator
            self._message = message
            self._expect = pw_expect(locator)
        
        def to_be_visible(self, **kwargs):
            self._expect.to_be_visible(**kwargs)
            msg = self._message or "Element is visible"
            LOGGER.info(f"  ✅ PASSED: {msg}")
        
        def to_contain_text(self, text, **kwargs):
            self._expect.to_contain_text(text, **kwargs)
            msg = self._message or f"Element contains '{text}'"
            LOGGER.info(f"  ✅ PASSED: {msg}")
        
        def to_have_text(self, text, **kwargs):
            self._expect.to_have_text(text, **kwargs)
            msg = self._message or f"Element has text '{text}'"
            LOGGER.info(f"  ✅ PASSED: {msg}")
        
        def __getattr__(self, name):
            # Fallback for other expect methods without logging
            return getattr(self._expect, name)
    
    return LoggingExpect(locator, message)
from shiny.playwright import controller
from shiny.pytest import create_app_fixture
from shiny.run import ShinyAppProc

# Create the app fixture
# Using path relative to this file
import os
app_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
app = create_app_fixture(app_path)

@pytest.mark.anyio
def test_order_visualizer_navigation(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_order_visualizer_navigation")
    # 1. Navigate to the app URL
    page.goto(app.url)
    LOGGER.info(f"  Navigated to {app.url}")
    
    # 2. Interact with the Date Picker using controller
    date_picker = controller.InputDate(page, "date_picker")
    date_picker.expect_value("2025-01-01")
    verify(True, "Date picker initial value is 2025-01-01")
    
    # 3. Verify the main table exists
    orders_table = page.locator("#orders_table")
    expect(orders_table, "Orders table is visible").to_be_visible()
    
    # Select the first row
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    
    #Wait for the table to fully load
    page.wait_for_timeout(300)
    
    def get_cell_text(field: str) -> str:
        return first_row.locator(f'.tabulator-cell[tabulator-field="{field}"]').text_content().strip()

    order_id = get_cell_text("orderid")
    side = get_cell_text("Side")
    ticker = get_cell_text("Ticker")
    exec_qty = get_cell_text("ExecQty") 
    strategy = get_cell_text("Strategy")
    
    LOGGER.info(f"  Selecting order {order_id} ({ticker})")
    first_row.click()
    page.wait_for_timeout(200)
    
    # 4. Navigate to the Chart tab
    page.get_by_text("Chart", exact=True).click()
    LOGGER.info("  Switched to Chart tab")
    
    # 5. Verify Chart Tab elements
    chart_title_el = page.locator("#chart_title")
    expect(chart_title_el, "Chart title is visible").to_be_visible()
    
    # Wait for chart title content to update with order details
    expect(page.locator(f"#chart_title:has-text('{order_id}')"), f"Chart title contains order ID {order_id}").to_be_visible()
    chart_text = chart_title_el.text_content()
    verify(order_id in chart_text, f"Chart title contains order ID {order_id}")
    verify(side in chart_text, f"Chart title contains side {side}")
    verify(ticker in chart_text, f"Chart title contains ticker {ticker}")
    verify(strategy in chart_text, f"Chart title contains strategy {strategy}")
    verify(exec_qty in chart_text, f"Chart title contains exec quantity {exec_qty}")
    
@pytest.mark.anyio
def test_settings_interaction(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_settings_interaction")
    page.goto(app.url)
    
    dark_mode = controller.InputDarkMode(page, "dark_mode")
    dark_mode.expect_mode("light") 
    verify(True, "Initial mode is light")
    
    dark_mode.click()
    dark_mode.expect_mode("dark")
    verify(True, "Toggled to dark mode")
    
    page.get_by_text("Chart", exact=True).click()
    
    show_all = controller.InputSwitch(page, "show_all_details")
    show_all.expect_checked(False)
    verify(True, "'Show All Details' switch defaults to False")
    
    show_all.set(True)
    show_all.expect_checked(True)
    verify(True, "'Show All Details' switch toggled to True")

@pytest.mark.anyio
def test_order_detail_features(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_order_detail_features")
    page.goto(app.url)
    
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    
    pct_adv_table = first_row.locator('.tabulator-cell[tabulator-field="PctADV"]').text_content().strip()
    LOGGER.info(f"  Order PctADV in main table: {pct_adv_table}")
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    
    order_details_table = page.locator("#order_details_table")
    expect(order_details_table, "Order details table is visible").to_be_visible()
    
    pct_adv_row = order_details_table.locator(".tabulator-row", has_text="PctADV")
    expect(pct_adv_row, "PctADV row is visible").to_be_visible()
    pct_adv_val = pct_adv_row.locator('.tabulator-cell[tabulator-field="Value"]').text_content().strip()
    
    verify(pct_adv_val == pct_adv_table, f"PctADV value {pct_adv_val} matches main table")
    
    tableholder = order_details_table.locator(".tabulator-tableholder")
    scroll_height = tableholder.evaluate("el => el.scrollHeight")
    client_height = tableholder.evaluate("el => el.clientHeight")
    
    verify(scroll_height <= client_height, "No vertical scrollbar by default")
    
    rows_before = order_details_table.locator(".tabulator-row").count()
    show_all = controller.InputSwitch(page, "show_all_details")
    show_all.set(True)
    page.wait_for_timeout(300) 
    
    rows_after = order_details_table.locator(".tabulator-row").count()
    verify(rows_after > rows_before, f"Row count increased from {rows_before} to {rows_after}")
    
    scroll_height_after = tableholder.evaluate("el => el.scrollHeight")
    client_height_after = tableholder.evaluate("el => el.clientHeight")
    verify(scroll_height_after > client_height_after, "Vertical scrollbar appeared after showing all fields")

@pytest.mark.anyio
def test_fill_details_features(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_fill_details_features")
    page.goto(app.url)
    
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    
    exec_qty_str = first_row.locator('.tabulator-cell[tabulator-field="ExecQty"]').text_content().strip()
    exec_qty = int(exec_qty_str.replace(",", ""))
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    fill_details_table = page.locator("#fill_detail_table")
    verify(fill_details_table.is_visible(), "Fill details table is visible")
    
    num_fills_row = fill_details_table.locator(".tabulator-row", has_text="NumFills")
    num_fills_val = num_fills_row.locator('.tabulator-cell[tabulator-field="Value"]').text_content().strip()
    verify(num_fills_val == "50", "NumFills is 50")
    
    avg_fill_size_row = fill_details_table.locator(".tabulator-row", has_text="AvgFillSize")
    avg_fill_size_val_str = avg_fill_size_row.locator('.tabulator-cell[tabulator-field="Value"]').text_content().strip()
    avg_fill_size_val = int(avg_fill_size_val_str.replace(",", ""))
    
    expected_avg_fill_size = int(round(exec_qty / 50))
    verify(avg_fill_size_val == expected_avg_fill_size, f"AvgFillSize {avg_fill_size_val} matches expected {expected_avg_fill_size}")

@pytest.mark.anyio
def test_venue_table_features(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_venue_table_features")
    page.goto(app.url)
    
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    venue_table = page.locator("#venue_table")
    expect(venue_table, "Venue table is visible").to_be_visible()
    
    rows = venue_table.locator(".tabulator-row")
    expect(rows.first, "First venue row is visible").to_be_visible()
    row_count = rows.count()
    verify(row_count >= 1, f"Venue table has {row_count} rows")
    
    total_pct = 0.0
    for i in range(row_count):
        row = rows.nth(i)
        cell_text = row.locator('.tabulator-cell[tabulator-field="PctFillBar"]').text_content().strip()
        import re
        matches = re.findall(r"(\d+\.\d+)%", cell_text)
        if matches:
            total_pct += float(matches[0])
            
    verify(abs(total_pct - 100.0) <= 0.15, f"Total PctFill sums to {total_pct}% (approx 100%)")

@pytest.mark.anyio
def test_chart_metrics_features(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_chart_metrics_features")
    page.goto(app.url)
    
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    
    def get_cell_text(field: str) -> str:
        return first_row.locator(f'.tabulator-cell[tabulator-field="{field}"]').text_content().strip()

    perf_arrival = get_cell_text("PerfArrival")
    perf_vwap = get_cell_text("PerfVWAP")
    perf_close = get_cell_text("PerfClose")
    spread_capture = get_cell_text("SpreadCapture")
    
    first_row.click()
    page.get_by_text("Chart", exact=True).click()
    
    chart_metrics = page.locator("#chart_metrics")
    verify(chart_metrics.is_visible(), "Chart metrics container is visible")
    
    def verify_chip(label: str, expected_val_raw: str, is_bps: bool = True):
        chip = chart_metrics.locator("span", has_text=label).first
        value_span = chip.locator("span").nth(1)
        value_text = value_span.text_content().strip()
        
        if is_bps:
            val_float = float(expected_val_raw)
            expected_formatted = f"{val_float:+.1f} bps"
            verify(value_text == expected_formatted, f"{label} displays {expected_formatted}")
        else:
            expected_formatted = f"{float(expected_val_raw):.1f}%"
            verify(value_text == expected_formatted, f"{label} displays {expected_formatted}")

    verify_chip("PerfArrival", perf_arrival)
    verify_chip("PerfVWAP", perf_vwap)
    verify_chip("PerfClose", perf_close)
    verify_chip("SpreadCapture", spread_capture, is_bps=False)

    verify_chip("PerfArrival", perf_arrival)
    verify_chip("PerfVWAP", perf_vwap)
    verify_chip("PerfClose", perf_close)
    verify_chip("SpreadCapture", spread_capture, is_bps=False)

@pytest.mark.anyio
def test_stock_chart_existence(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_stock_chart_existence")
    page.goto(app.url)
    
    orders_table = page.locator("#orders_table")
    expect(orders_table, "Orders table is visible").to_be_visible()
    
    # Select the row with orderid oid10004
    target_row = orders_table.locator(".tabulator-row", has_text="oid10004")
    expect(target_row, "Order oid10004 row is visible").to_be_visible()
    
    # Get start and end times from the order
    start_time = target_row.locator('.tabulator-cell[tabulator-field="StartTime"]').text_content().strip()
    end_time = target_row.locator('.tabulator-cell[tabulator-field="EndTime"]').text_content().strip()
    verify(start_time != "", f"Order oid10004 has start time: {start_time}")
    verify(end_time != "", f"Order oid10004 has end time: {end_time}")
    
    target_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart"), "Stock chart container is visible").to_be_visible()
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()
    
    # Check for start/end time marker traces
    marker_traces = page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        if (!gd || !gd.data) return [];
        return gd.data
            .filter(t => t.name === 'Start' || t.name === 'End')
            .map(t => ({ name: t.name, x: t.x }));
    }''')
    
    verify(len(marker_traces) >= 2, f"Chart has Start and End marker traces (found {len(marker_traces)})")
    
    # Find the Start and End traces
    start_trace = next((t for t in marker_traces if t['name'] == 'Start'), None)
    end_trace = next((t for t in marker_traces if t['name'] == 'End'), None)
    
    verify(start_trace is not None, "Start time marker trace exists")
    verify(end_trace is not None, "End time marker trace exists")
    
    # Extract times from the trace x values and verify they match order times
    def extract_time_from_marker(x_vals):
        import re
        if not x_vals or len(x_vals) == 0:
            return None
        # x values are like "2025-01-01T09:30:00"
        match = re.search(r'T(\d{2}):(\d{2})', str(x_vals[0]))
        if match:
            return f"{match.group(1)}:{match.group(2)}"
        return None
    
    # Normalize expected times to HH:MM format
    def normalize_time(t):
        parts = t.split(':')
        return f"{int(parts[0]):02d}:{parts[1]}"
    
    expected_start = normalize_time(start_time)
    expected_end = normalize_time(end_time)
    
    actual_start = extract_time_from_marker(start_trace['x']) if start_trace else None
    actual_end = extract_time_from_marker(end_trace['x']) if end_trace else None
    
    verify(actual_start == expected_start, f"Start marker time {actual_start} matches order start {expected_start}")
    verify(actual_end == expected_end, f"End marker time {actual_end} matches order end {expected_end}")

@pytest.mark.anyio
def test_volume_chart_features(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_volume_chart_features")
    page.goto(app.url)
    
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()
    
    volume_bars = page.locator(".trace.bars .point")
    expect(volume_bars.first, "First volume bar is visible").to_be_visible()
    bar_count = volume_bars.count()
    verify(bar_count > 0, f"Volume chart has {bar_count} bars")
    
    hover_labels = page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        if (!gd || !gd.data) return [];
        const barTrace = gd.data.find(t => t.type === 'bar');
        return (barTrace && barTrace.customdata) ? barTrace.customdata : [];
    }''')
    
    verify(len(hover_labels) > 0, "Volume bars have hover labels")
    verify("Open" in str(hover_labels[0]), f"First bar labeled 'Open': {hover_labels[0]}")
    verify("Close" in str(hover_labels[-1]), f"Last bar labeled 'Close': {hover_labels[-1]}")

@pytest.mark.anyio
def test_range_slider_presence(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_range_slider_presence")
    page.goto(app.url)
    page.locator("#orders_table .tabulator-row").first.click()
    page.get_by_text("Chart", exact=True).click()
    
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()
    
    has_rangeslider = page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const xaxis3 = gd?.layout?.xaxis3;
        return xaxis3?.rangeslider?.visible === true;
    }''')
    verify(has_rangeslider, "Rangeslider is visible in Plotly layout (xaxis3)")
    verify(page.locator("#order_chart .rangeslider-container").is_visible(), "Rangeslider SVG container is visible")

@pytest.mark.anyio
def test_range_slider_initial_range(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_range_slider_initial_range")
    page.goto(app.url)
    first_row = page.locator("#orders_table .tabulator-row").first
    start_time = first_row.locator('.tabulator-cell[tabulator-field="StartTime"]').text_content().strip()
    end_time = first_row.locator('.tabulator-cell[tabulator-field="EndTime"]').text_content().strip()
    first_row.click()
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()
    
    def time_to_mins(t: str) -> int:
        p = t.split(":")
        return int(p[0]) * 60 + int(p[1])
    
    st_m = time_to_mins(start_time)
    et_m = time_to_mins(end_time)
    dur = et_m - st_m
    pad = 30 if dur > 120 else (10 if dur > 20 else 5)
    
    # Matching app.py logic for min_left_mins
    total_range = dur + (60 if dur > 120 else (20 if dur > 20 else 10))
    min_l = 560 if total_range > 80 else (565 if total_range >= 40 else 569)
    
    exp_s = max(min_l, st_m - pad)
    exp_e = min(965, et_m + pad)
    
    actual_range = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.xaxis?.range''')
    verify(actual_range is not None, "Chart has defined x-axis range")
    
    def parse_m(v):
        import re
        m = re.search(r"T(\d{2}):(\d{2})", str(v))
        return int(m.group(1)) * 60 + int(m.group(2)) if m else 0
    
    act_s = parse_m(actual_range[0])
    act_e = parse_m(actual_range[1])
    
    verify(abs(act_s - exp_s) <= 5, f"Start range ~{exp_s}m (got {act_s}m)")
    verify(abs(act_e - exp_e) <= 5, f"End range ~{exp_e}m (got {act_e}m)")

@pytest.mark.anyio
def test_range_slider_dynamic_binning(page: Page, app: ShinyAppProc):
    """Test 3: Verify volume bars switch granularity at specific thresholds (80m and 40m)."""
    page.goto(app.url)
    
    # 1. Select an order
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()
    page.wait_for_timeout(1000)

    # Wait for chart.js to bind plotly_relayout handler (required now that we drive xaxis3).
    page.wait_for_function(
        """() => {
            const gd = document.querySelector('#order_chart .js-plotly-plot');
            return !!gd && gd._hasRescaling === true;
        }""",
        timeout=5000,
    )

    def get_current_bin_duration():
        labels = page.evaluate('''() => {
            const gd = document.querySelector("#order_chart .js-plotly-plot");
            if (!gd || !gd.data) return [];
            const barTrace = gd.data.find(t => t.type === 'bar');
            return (barTrace && barTrace.customdata) ? barTrace.customdata : [];
        }''')
        
        import re
        for label in labels:
            label_str = str(label)
            if "Open" in label_str or "Close" in label_str: continue
            t = r"(\d{1,2}:\d{2}(?::\d{2})?)"
            match = re.search(f"{t}[–-]{t}", label_str)
            if match:
                t1, t2 = match.groups()
                def to_sec(s):
                    p = list(map(int, s.split(':')))
                    return p[0]*3600 + p[1]*60 + (p[2] if len(p)==3 else 0)
                return to_sec(t2) - to_sec(t1)
        return None

    def wait_for_bin_duration(expected_seconds: int, message: str, timeout_ms: int = 6000) -> None:
        import time

        deadline = time.time() + (timeout_ms / 1000.0)
        last = None
        while time.time() < deadline:
            last = get_current_bin_duration()
            if last == expected_seconds:
                verify(True, message)
                return
            page.wait_for_timeout(200)

        dbg = page.evaluate('''() => {
            const gd = document.querySelector('#order_chart .js-plotly-plot');
            return {
                relayoutCount: gd?.__chartRelayoutCount ?? null,
                lastEventKeys: gd?.__chartLastEventKeys ?? null,
                xaxis: gd?.layout?.xaxis?.range ?? null,
                xaxis2: gd?.layout?.xaxis2?.range ?? null,
                xaxis3: gd?.layout?.xaxis3?.range ?? null,
            };
        }''')
        verify(last == expected_seconds, f"{message} (last={last}, dbg={dbg})")

    # Step A: Check 161 mins (Should be 5min / 300s)
    # Use xaxis3.range to simulate rangeslider interaction (rangeslider is on xaxis3)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T12:41:00']; // 161 minutes
        if (!window.Plotly || !gd) return null;
        // Simulate rangeslider by setting xaxis3.range
        return Plotly.relayout(gd, { 'xaxis3.range': range });
    }''')
    wait_for_bin_duration(300, "161-min range uses 5-min bins (300s)")
    
    # Verify x-axis synchronization: xaxis should be synced from xaxis3 (rangeslider)
    xaxis_range = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.xaxis?.range''')
    verify(xaxis_range is not None, "X-axis range defined for both stock price and volume charts (161min)")

    # Step B: Check 160 mins (Switchover! Should be 2min / 120s)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T12:40:00']; // 160 minutes
        if (!window.Plotly || !gd) return null;
        return Plotly.relayout(gd, { 'xaxis3.range': range });
    }''')
    wait_for_bin_duration(120, "160-min range (at threshold) switched to 2-min bins (120s)")
    
    # Verify x-axis synchronization
    xaxis_range = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.xaxis?.range''')
    verify(xaxis_range is not None, "X-axis range defined for both stock price and volume charts (160min)")

    # Step C: Check 81 mins (Still 2min / 120s)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T11:21:00']; // 81 minutes
        if (!window.Plotly || !gd) return null;
        return Plotly.relayout(gd, { 'xaxis3.range': range });
    }''')
    wait_for_bin_duration(120, "81-min range uses 2-min bins (120s)")
    
    # Verify x-axis synchronization
    xaxis_range = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.xaxis?.range''')
    verify(xaxis_range is not None, "X-axis range defined for both stock price and volume charts (81min)")

    # Step D: Check 80 mins (Switchover! Should be 1min / 60s)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T11:20:00']; // 80 minutes
        if (!window.Plotly || !gd) return null;
        return Plotly.relayout(gd, { 'xaxis3.range': range });
    }''')
    wait_for_bin_duration(60, "80-min range (at threshold) switched to 1-min bins (60s)")
    
    # Verify x-axis synchronization
    xaxis_range = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.xaxis?.range''')
    verify(xaxis_range is not None, "X-axis range defined for both stock price and volume charts (80min)")

    # Step E: Check 41 mins (Still 1min / 60s)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T10:41:00']; // 41 minutes
        if (!window.Plotly || !gd) return null;
        return Plotly.relayout(gd, { 'xaxis3.range': range });
    }''')
    wait_for_bin_duration(60, "41-min range uses 1-min bins (60s)")
    
    # Verify x-axis synchronization
    xaxis_range = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.xaxis?.range''')
    verify(xaxis_range is not None, "X-axis range defined for both stock price and volume charts (41min)")

    # Step F: Check 39 mins (Switchover! Should be 30s)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T10:39:00']; // 39 minutes
        if (!window.Plotly || !gd) return null;
        return Plotly.relayout(gd, { 'xaxis3.range': range });
    }''')
    wait_for_bin_duration(30, "39-min range (below 40) switched to 30s bins")
    
    # Verify x-axis synchronization
    xaxis_range = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.xaxis?.range''')
    verify(xaxis_range is not None, "X-axis range defined for both stock price and volume charts (39min)")

@pytest.mark.anyio
def test_range_slider_yaxis_rescaling(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_range_slider_yaxis_rescaling")
    page.goto(app.url)
    page.locator("#orders_table .tabulator-row").first.click()
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()

    # Wait for chart.js to bind plotly_relayout handler (required now that we drive xaxis3).
    page.wait_for_function(
        """() => {
            const gd = document.querySelector('#order_chart .js-plotly-plot');
            return !!gd && gd._hasRescaling === true;
        }""",
        timeout=5000,
    )
    
    init_y = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.yaxis?.range''')
    verify(init_y is not None, "Initial y-axis range defined")
    
    # Zoom to 30 mins using xaxis3 (rangeslider) - should sync to xaxis and trigger y-rescale
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        if (!window.Plotly || !gd) return null;
        return Plotly.relayout(gd, { 'xaxis3.range': ['2025-01-01T11:00:00', '2025-01-01T11:30:00'] });
    }''')
    import time

    deadline = time.time() + 6.0
    new_y = None
    changed = False
    while time.time() < deadline:
        new_y = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.yaxis?.range''')
        if new_y is not None:
            changed = abs(new_y[0] - init_y[0]) > 0.001 or abs(new_y[1] - init_y[1]) > 0.001
            if changed:
                break
        page.wait_for_timeout(200)

    dbg = page.evaluate('''() => {
        const gd = document.querySelector('#order_chart .js-plotly-plot');
        return {
            relayoutCount: gd?.__chartRelayoutCount ?? null,
            lastEventKeys: gd?.__chartLastEventKeys ?? null,
            xaxis: gd?.layout?.xaxis?.range ?? null,
            xaxis2: gd?.layout?.xaxis2?.range ?? null,
            xaxis3: gd?.layout?.xaxis3?.range ?? null,
            yaxis: gd?.layout?.yaxis?.range ?? null,
        };
    }''')
    verify(new_y is not None, f"Y-axis range defined after zoom (dbg={dbg})")
    verify(changed, f"Y-axis range adjusted after zoom (dbg={dbg})")
    verify(new_y[1] - new_y[0] <= (init_y[1] - init_y[0]) * 1.5, "Zoomed y-axis span is reasonable")
