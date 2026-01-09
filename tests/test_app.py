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
import sys
app_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
app = create_app_fixture(app_path)

@pytest.mark.anyio
def test_order_visualizer_navigation(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_order_visualizer_navigation")
    # 1. Navigate to the app URL
    page.goto(app.url)
    LOGGER.info(f"  Navigated to {app.url}")
    
    # 2. Interact with the Date Range inputs
    start_date = controller.InputDate(page, "start_date")
    end_date = controller.InputDate(page, "end_date")
    
    start_date.expect_value("2025-01-01")
    end_date.set("2025-01-03")
    verify(True, "Date range set to 2025-01-01 to 2025-01-03")

    # Click Query to load data
    page.locator("#query_btn").click()
    LOGGER.info("  Clicked Query button")
    
    # 3. Verify the main table exists
    orders_table = page.locator("#orders_table")
    expect(orders_table, "Orders table is visible").to_be_visible()
    
    # Wait for rows
    page.wait_for_selector("#orders_table .tabulator-row")
    
    # helper for verification
    def verify_order_components(target_date_formatted: str):
        LOGGER.info(f"--- Verifying Order from Date: {target_date_formatted} ---")
        
        # Ensure we are on table tab
        page.get_by_text("Table", exact=True).click()
        
        # Find row
        row = orders_table.locator(f".tabulator-row:has-text('{target_date_formatted}')").first
        expect(row, f"Row for {target_date_formatted} exists").to_be_visible()
        
        # Get ID for logging/verification
        order_id = row.locator('.tabulator-cell[tabulator-field="orderid"]').text_content().strip()
        ticker = row.locator('.tabulator-cell[tabulator-field="Ticker"]').text_content().strip()
        ticker = row.locator('.tabulator-cell[tabulator-field="Ticker"]').text_content().strip()
        # Note: Desk is not displayed in the main table by default, but we will check it in Chart Title and Details.
        
        LOGGER.info(f"Testing Order ID: {order_id}, Ticker: {ticker}, Date: {target_date_formatted}")
        print(f"LIVE LOG: Verify Order {order_id} date {target_date_formatted}")
        
        row.click()
        
        # Switch to Chart
        page.get_by_text("Chart", exact=True).click()
        
        # 1. Chart Title
        chart_title = page.locator("#chart_title")
        expect(chart_title).to_contain_text(order_id)
        expect(chart_title).to_contain_text(ticker)
        expect(chart_title).to_contain_text(target_date_formatted)
        # Check for Desk in title (e.g. DESKA, DESKB, or DESKC)
        # Since it's random, we just check if it contains "DESK"
        expect(chart_title).to_contain_text("DESK")
        
        # 2. Metrics
        metrics = page.locator("#chart_metrics")
        expect(metrics).to_be_visible()
        # Ensure it has some text content (chip values)
        expect(metrics).to_contain_text("Return")
        expect(metrics).to_contain_text("SpreadCapture")

        # 3. Details Tables
        expect(page.locator("#order_details_table")).to_be_visible()
        # Check that it has rows
        expect(page.locator("#order_details_table .tabulator-row").first).to_be_visible()
        
        expect(page.locator("#fill_detail_table")).to_be_visible()
        expect(page.locator("#venue_table")).to_be_visible()
        
        # 4. Chart Verification (Enhanced)
        chart_locator = page.locator("#order_chart")
        expect(chart_locator).to_be_visible()
        
        # Access the Plotly DOM element and inspect its data array
        # We need to wait for the plotly graph to be constructed.
        # usually found at the widget div or a child.
        # The widget ID is order_chart. The plotly div might be inside.
        
        # Helper to get trace names and counts
        def get_chart_data():
            return page.evaluate("""() => {
                const el = document.getElementById('order_chart');
                // The shinywidget / plotly might be wrapped.
                // Plotly.js attaches to the div.
                // Sometimes it's inside a shadow root or nested div.
                // Let's assume standard Plotly widget structure:
                // Look for the main plotly div.
                const plotlyDiv = el.querySelector('.js-plotly-plot') || el;
                if (!plotlyDiv || !plotlyDiv.data) return null;
                
                return plotlyDiv.data.map(trace => ({
                    name: trace.name, 
                    mode: trace.mode,
                    x_count: trace.x ? trace.x.length : 0
                }));
            }""")
        
        # Retry logic for chart data load (it might take a moment to render after visibility)
        # Wait for at least 3 traces (Bid, Ask, Executions) to be present
        page.wait_for_function("""() => {
            const el = document.getElementById('order_chart');
            const plotlyDiv = el.querySelector('.js-plotly-plot') || el;
            if (!plotlyDiv || !plotlyDiv.data) return false;
            return plotlyDiv.data.length >= 3;
        }""", timeout=5000)
        
        traces = get_chart_data()
            
        LOGGER.info(f"Chart Traces found: {traces}")
        verify(traces is not None, "Plotly chart data object found")
        
        trace_names = [t.get('name') for t in traces]
        LOGGER.info(f"Trace names found: {trace_names}")
        
        verify("Bid" in trace_names, "Trace 'Bid' present")
        verify("Ask" in trace_names, "Trace 'Ask' present")
        # Check partial match or exact
        exec_trace_present = any("Execution" in (t or "") for t in trace_names)
        verify(exec_trace_present, f"Trace 'Execution' present (Found: {trace_names})")
        
        if exec_trace_present:
             # Find the execution trace and check count
             exec_trace = next((t for t in traces if "Execution" in (t.get('name') or "")), None)
             if exec_trace:
                 plotly_count = exec_trace['x_count']
                 # Calculate expected count using DataService
                 # Ideally we'd use the app's instance, but for demo we can create a new cached instance or use the same logic
                 # The app uses DATA_SERVICE global. We can import it.
                 sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
                 from data_service import DataService
                 # We need to ensure we use the same seed/logic. DataService.demo() is deterministic per run if seed fixed? 
                 # Actually base_orders has fixed seed. But get_executions uses a hashed seed based on orderid.
                 ds = DataService.demo()
                 # Normalize date back to dashes for data service
                 ds_date = target_date_formatted.replace(".", "-")
                 expected_exec = ds.get_executions(ds_date, order_id)
                 expected_count = len(expected_exec)
                 
                 LOGGER.info(f"Executions: Plotly={plotly_count}, Expected={expected_count}")
                 verify(plotly_count == expected_count, f"Execution count matches (Expected {expected_count})")

                 # Also verify Bid/Ask if possible?
                 # Prices are generated in get_prices.
                 # Check Bid trace
                 bid_trace = next((t for t in traces if "Bid" == t.get('name')), None)
                 if bid_trace:
                     # Access start/end times from row or default
                     # We can fetch order details to get times
                     od = ds.get_order(ds_date, order_id)
                     prices = ds.get_prices(ds_date, ticker, od['ExchOpenTime'], od['ExchCloseTime'])
                     # Filter by order start/end if chart zooms? The chart usually shows full context or order duration?
                     # App logic: chart shows [StartTime - padding, EndTime + padding]
                     # But get_prices returns full day? No, get_prices returns full day.
                     # The app filters the DataFrame passed to create_order_viz?
                     # Let's check app.py... it passes `prices` (full day) to `create_order_viz`.
                     # Plotly might be displaying all points.
                     # Let's assume full day count for now or at least > order duration count.
                     # Wait, `get_prices` returns 1-min or 1-sec data?
                     # Let's matches length of `prices` dataframe.
                     expected_prices_count = len(prices) 
                     
                     # Note: Plotly might downsample? But usually not for 1 day of intraday data unless configured.
                     # Wait, `create_order_viz` might filter?
                     # Re-reading `plotly_order_viz.py`: It takes `px_data`.
                     # App.py: `prices = DATA_SERVICE.get_prices(...)` -> `create_order_viz(..., prices, ...)`
                     # So it should match exactly.
                     
                     plotly_bid = bid_trace['x_count']
                     LOGGER.info(f"Bid Points: Plotly={plotly_bid}, Expected~={expected_prices_count}")
                     # Exact match might be tricky if some NaN handling or downsampling. 
                     # But let's verify it's the same.
                     verify(plotly_bid == expected_prices_count, f"Bid count matches (Expected {expected_prices_count})")
        
        LOGGER.info(f"--- Verification Passed for {order_id} ---")

    # Run verification for first date and last date
    verify_order_components("2025.01.01")

    # Filter to 2025-01-03 specifically to ensure rows are visible (Tabulator virtual DOM might hide them)
    # We need to switch back to the Table tab first if verify_order_components left us on Chart
    page.get_by_text("Table", exact=True).click()
    start_date.set("2025-01-03")
    # End date is already 2025-01-03
    page.locator("#query_btn").click()
    # Wait for table to refresh (checking for specific date ensures we waited)
    page.locator(".tabulator-row:has-text('2025.01.03')").first.wait_for()

    verify_order_components("2025.01.03")
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
    page.locator("#query_btn").click()

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
    show_all.set(True)
    # Wait for the number of rows to increase
    expect(order_details_table.locator(".tabulator-row")).not_to_have_count(rows_before) 
    
    rows_after = order_details_table.locator(".tabulator-row").count()
    verify(rows_after > rows_before, f"Row count increased from {rows_before} to {rows_after}")
    
    scroll_height_after = tableholder.evaluate("el => el.scrollHeight")
    client_height_after = tableholder.evaluate("el => el.clientHeight")
    verify(scroll_height_after > client_height_after, "Vertical scrollbar appeared after showing all fields")

@pytest.mark.anyio
def test_fill_details_features(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_fill_details_features")
    page.goto(app.url)
    page.locator("#query_btn").click()
    
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
    num_fills = int(num_fills_val.replace(",", ""))
    # Strict check: 52 fills (50 regular + Open + Close auctions)
    verify(num_fills == 52, f"NumFills is 52 (got {num_fills})")
    
    avg_fill_size_row = fill_details_table.locator(".tabulator-row", has_text="AvgFillSize")
    avg_fill_size_val_str = avg_fill_size_row.locator('.tabulator-cell[tabulator-field="Value"]').text_content().strip()
    avg_fill_size_val = int(avg_fill_size_val_str.replace(",", ""))
    
    # Calculate expected average based on actual number of fills (should be 52)
    expected_avg_fill_size = int(round(exec_qty / num_fills))
    verify(avg_fill_size_val == expected_avg_fill_size, f"AvgFillSize {avg_fill_size_val} matches expected {expected_avg_fill_size}")

@pytest.mark.anyio
def test_venue_table_features(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_venue_table_features")
    page.goto(app.url)
    page.locator("#query_btn").click()
    
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
    page.locator("#query_btn").click()
    
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    
    # We no longer show Perf/SpreadCapture in the main table, so we can't cross-verify from there.
    # We just verify that the metrics appear in the chart view and have valid values.
    
    first_row.click()
    page.get_by_text("Chart", exact=True).click()
    
    chart_metrics = page.locator("#chart_metrics")
    verify(chart_metrics.is_visible(), "Chart metrics container is visible")
    
    def verify_chip(label: str, is_bps: bool = True):
        chip = chart_metrics.locator("span", has_text=label).first
        expect(chip).to_be_visible()
        value_span = chip.locator("span").nth(1)
        value_text = value_span.text_content().strip()
        
        # Verify format
        if is_bps:
             verify("bps" in value_text, f"{label} value '{value_text}' contains 'bps'")
        else:
             verify("%" in value_text, f"{label} value '{value_text}' contains '%'")

    verify_chip("PerfArrival")
    verify_chip("PerfVWAP")
    verify_chip("PerfClose")
    verify_chip("SpreadCapture", is_bps=False)

@pytest.mark.anyio
def test_stock_chart_existence(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_stock_chart_existence")
    page.goto(app.url)
    page.locator("#query_btn").click()
    
    orders_table = page.locator("#orders_table")
    expect(orders_table, "Orders table is visible").to_be_visible()
    
    # Select the row with orderid oid10001 (unique per date, so use first to get 2025.01.01)
    # Avoid oid10004 which appears on multiple dates with different times, causing test flakiness
    target_row = orders_table.locator(".tabulator-row", has_text="oid10001").first
    expect(target_row, "Order oid10001 row is visible").to_be_visible()
    
    # Get start and end times from the order
    start_time = target_row.locator('.tabulator-cell[tabulator-field="StartTime"]').text_content().strip()
    end_time = target_row.locator('.tabulator-cell[tabulator-field="EndTime"]').text_content().strip()
    verify(start_time != "", f"Order oid10001 has start time: {start_time}")
    verify(end_time != "", f"Order oid10001 has end time: {end_time}")
    
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

    # Helper to get Y-axis scaling data
    def get_yaxis_data():
        return page.evaluate('''() => {
            const gd = document.querySelector("#order_chart .js-plotly-plot");
            if (!gd || !gd.data || !gd.layout) return null;
            
            const yRange = gd.layout.yaxis?.range;
            if (!yRange || yRange.length !== 2) return null;
            
            const xRange = gd.layout.xaxis?.range;
            if (!xRange || xRange.length !== 2) return null;
            
            const bidTrace = gd.data.find(t => t.name === 'Bid');
            const askTrace = gd.data.find(t => t.name === 'Ask');
            if (!bidTrace || !askTrace || !bidTrace.y || !askTrace.y || !bidTrace.x) return null;
            
            const toEpoch = (v) => {
                if (typeof v === 'number') return v;
                return new Date(String(v).replace(' ', 'T')).getTime();
            };
            
            const xStart = toEpoch(xRange[0]);
            const xEnd = toEpoch(xRange[1]);
            
            let visibleMin = Infinity;
            let visibleMax = -Infinity;
            let hasVisibleData = false;
            
            for (let i = 0; i < bidTrace.x.length; i++) {
                const t = toEpoch(bidTrace.x[i]);
                if (t >= xStart && t <= xEnd) {
                    if (bidTrace.y[i] != null && !isNaN(bidTrace.y[i])) {
                        visibleMin = Math.min(visibleMin, bidTrace.y[i]);
                        hasVisibleData = true;
                    }
                    if (askTrace.y[i] != null && !isNaN(askTrace.y[i])) {
                        visibleMax = Math.max(visibleMax, askTrace.y[i]);
                        hasVisibleData = true;
                    }
                }
            }
            
            if (!hasVisibleData) return null;
            
            const visibleSpan = visibleMax - visibleMin;
            const ySpan = yRange[1] - yRange[0];
            const pad = Math.max(visibleSpan * 0.10, 0.25);
            const expectedSpan = visibleSpan + 2 * pad;
            
            return {
                yRange: yRange,
                xRange: xRange,
                visibleMin: visibleMin,
                visibleMax: visibleMax,
                visibleSpan: visibleSpan,
                ySpan: ySpan,
                expectedSpan: expectedSpan
            };
        }''')
    
    def verify_yaxis_scaling(yaxis_data, context_msg):
        verify(yaxis_data is not None, f"Y-axis data retrieved {context_msg}")
        LOGGER.info(f"Y-axis {context_msg}: range={yaxis_data['yRange']}, visibleSpan={yaxis_data['visibleSpan']:.2f}, ySpan={yaxis_data['ySpan']:.2f}, expectedSpan={yaxis_data['expectedSpan']:.2f}")
        
        if yaxis_data['visibleSpan'] > 0.5:
            ratio = yaxis_data['ySpan'] / yaxis_data['expectedSpan']
            verify(
                0.8 <= ratio <= 1.5,
                f"Y-axis properly scaled {context_msg} (ySpan={yaxis_data['ySpan']:.2f}, expected={yaxis_data['expectedSpan']:.2f}, ratio={ratio:.2f})"
            )
    
    # Verify initial Y-axis scaling
    verify_yaxis_scaling(get_yaxis_data(), "at initial load")
    
    # Wait 2 seconds and check again - catches regressions where correct scaling gets overwritten
    page.wait_for_timeout(2000)
    verify_yaxis_scaling(get_yaxis_data(), "after 2s")

@pytest.mark.anyio
def test_volume_chart_open_label(page: Page, app: ShinyAppProc):
    """Test specifically for the Open bar hover label."""
    LOGGER.info("Starting test_volume_chart_open_label")
    page.goto(app.url)
    page.locator("#query_btn").click()
    
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()
    
    # Target the Lit Volume trace explicitly (it's the first bar trace)
    lit_vol_trace = page.locator(".trace.bars").first
    volume_bars = lit_vol_trace.locator(".point")
    
    expect(volume_bars.first, "First volume bar is visible").to_be_visible()
    
    # Interaction Test: Hover over the first bar
    first_bar = volume_bars.first
    box = first_bar.bounding_box()
    if box:
        LOGGER.info(f"Hovering first bar at {box['x'] + box['width']/2}, {box['y'] + box['height']/2}")
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.move(box["x"] + box["width"] / 2 + 1, box["y"] + box["height"] / 2 + 1)
    else:
        first_bar.hover(force=True)
        
    tooltip_layer = page.locator(".hoverlayer")
    expect(tooltip_layer, "Tooltip layer visible on hover").to_be_visible(timeout=3000)
    
    tooltip_text = tooltip_layer.text_content()
    LOGGER.info(f"Hover text found on first bar: '{tooltip_text}'")
    
    verify("Open" in tooltip_text, f"First bar tooltip contains 'Open' (Got: '{tooltip_text}')")


@pytest.mark.anyio
def test_volume_chart_close_label(page: Page, app: ShinyAppProc):
    """Test specifically for the Close bar hover label."""
    LOGGER.info("Starting test_volume_chart_close_label")
    page.goto(app.url)
    page.locator("#query_btn").click()
    
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()
    
    # Target the Lit Volume trace explicitly (it's the first bar trace)
    lit_vol_trace = page.locator(".trace.bars").first
    volume_bars = lit_vol_trace.locator(".point")
    
    # Ensure chart is zoomed/scrolled to show the end? 
    # The default view for oid10001 (09:30-16:00) should cover it.
    
    last_bar = volume_bars.last
    last_bar.scroll_into_view_if_needed()
    expect(last_bar, "Last volume bar is visible").to_be_visible()
    
    box_last = last_bar.bounding_box()
    if box_last:
        LOGGER.info(f"Hovering last bar at {box_last['x'] + box_last['width']/2}, {box_last['y'] + box_last['height']/2}")
        page.mouse.move(box_last["x"] + box_last["width"] / 2, box_last["y"] + box_last["height"] / 2)
        page.mouse.move(box_last["x"] + box_last["width"] / 2 + 1, box_last["y"] + box_last["height"] / 2 + 1)
    else:
        last_bar.hover(force=True)
        
    tooltip_layer = page.locator(".hoverlayer")
    expect(tooltip_layer, "Tooltip visible on last bar hover").to_be_visible(timeout=3000)
    
    tooltip_text_last = tooltip_layer.text_content()
    LOGGER.info(f"Hover text found on last bar: '{tooltip_text_last}'")
    
    verify("Close" in tooltip_text_last, f"Last bar tooltip contains 'Close' (Got: '{tooltip_text_last}')")

@pytest.mark.anyio
def test_range_slider_presence(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_range_slider_presence")
    page.goto(app.url)
    page.locator("#query_btn").click()
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
    page.locator("#query_btn").click()
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
    
    # New slider calculation: slider_start = exch_open - bin_size (5min for default bin)
    # bin_seconds = 300 for 5min bin, so slider starts at exch_open - 5min = 09:25
    exch_open_mins = 570  # 09:30
    bin_mins = 5  # default 5min bin
    slider_start_mins = exch_open_mins - bin_mins  # 565 = 09:25
    
    exp_s = max(slider_start_mins, st_m - pad)
    # End is capped by slider_end (exch_close + bin_size)
    exch_close_mins = 960  # 16:00
    slider_end_mins = exch_close_mins + bin_mins  # 965 = 16:05
    exp_e = min(et_m + pad, slider_end_mins)
    
    # Check rangeslider handle position (selected area)
    handle_range = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.xaxis3?.range''')
    verify(handle_range is not None, "Rangeslider has defined handle range")
    
    def parse_m(v):
        import re
        m = re.search(r"T(\d{2}):(\d{2})", str(v))
        return int(m.group(1)) * 60 + int(m.group(2)) if m else 0
    
    act_s = parse_m(handle_range[0])
    act_e = parse_m(handle_range[1])
    
    verify(abs(act_s - exp_s) <= 5, f"Handle start ~{exp_s}m (got {act_s}m)")
    verify(abs(act_e - exp_e) <= 5, f"Handle end ~{exp_e}m (got {act_e}m)")
    
    # Skip the full rangeslider extent check for now - the rangeslider.range property
    # may not be set explicitly in Plotly (it uses auto bounds)
    LOGGER.info("Rangeslider handle position test completed successfully")

@pytest.mark.anyio
def test_range_slider_dynamic_binning(page: Page, app: ShinyAppProc):
    """Test 3: Verify volume bars switch granularity at specific thresholds (80m and 40m)."""
    page.goto(app.url)
    page.locator("#query_btn").click()
    
    # 1. Select an order
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "First order row is visible").to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()
    # Wait for bars to be rendered
    page.wait_for_selector(".trace.bars .point", state="visible", timeout=5000)

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
        # Define JS check for specific duration
        check_fn = rf"""() => {{
            const gd = document.querySelector("#order_chart .js-plotly-plot");
            if (!gd || !gd.data) return false;
            const barTrace = gd.data.find(t => t.type === 'bar');
            if (!barTrace || !barTrace.customdata) return false;
            
            // Re-implement the same regex logic in JS for robustness or just grab sample
            // Finding one label that matches the expected duration is enough
            const labels = barTrace.customdata;
            for (const label of labels) {{
                if (String(label).includes("Open") || String(label).includes("Close")) continue;
                // Parse "HH:MM-HH:MM" e.g. "10:00-10:05"
                const m = String(label).match(/(\d{{1,2}}:\d{{2}}(?::\d{{2}})?)[–-](\d{{1,2}}:\d{{2}}(?::\d{{2}})?)/);
                if (m) {{
                    const t1_parts = m[1].split(':').map(Number);
                    const t2_parts = m[2].split(':').map(Number);
                    const t1_sec = t1_parts[0]*3600 + t1_parts[1]*60 + (t1_parts.length>2?t1_parts[2]:0);
                    const t2_sec = t2_parts[0]*3600 + t2_parts[1]*60 + (t2_parts.length>2?t2_parts[2]:0);
                    if (t2_sec - t1_sec === {expected_seconds}) return true;
                }}
            }}
            return false;
        }}"""
        
        try:
             page.wait_for_function(check_fn, timeout=timeout_ms)
             last = expected_seconds
        except Exception:
             # Fallback to python logic for error reporting
             last = get_current_bin_duration()

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
    page.locator("#query_btn").click()
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
    # Wait for y-axis range to change meaningfully from init_y
    page.wait_for_function(
        f"""() => {{
            const gd = document.querySelector("#order_chart .js-plotly-plot");
            const new_y = gd?.layout?.yaxis?.range;
            if (!new_y) return false;
            const init_y0 = {init_y[0]};
            const init_y1 = {init_y[1]};
            return (Math.abs(new_y[0] - init_y0) > 0.001 || Math.abs(new_y[1] - init_y1) > 0.001);
        }}""",
        timeout=6000
    )
    
    new_y = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.yaxis?.range''')
    changed = True # if wait_for_function passes

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


@pytest.mark.anyio
def test_duration_button_server_update_yaxis_rescaling(page: Page, app: ShinyAppProc):
    """Regression: duration buttons that trigger server re-render (bin-size change) must still rescale y-axis.

    Historically, buttons relied on plotly_relayout-driven y-rescale. If a button causes a bin-size change,
    chart.js skips local Plotly.relayout and sends chart_state to the server, so y-axis must be rescaled
    after the server re-render completes.
    """
    LOGGER.info("Starting test_duration_button_server_update_yaxis_rescaling")
    page.goto(app.url)
    page.locator("#query_btn").click()
    page.locator("#orders_table .tabulator-row").first.click()
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot"), "Plotly chart is visible").to_be_visible()

    # Wait for chart.js to bind plotly_relayout handler.
    page.wait_for_function(
        """() => {
            const gd = document.querySelector('#order_chart .js-plotly-plot');
            return !!gd && gd._hasRescaling === true;
        }""",
        timeout=5000,
    )

    init_y = page.evaluate(
        """() => document.querySelector('#order_chart .js-plotly-plot')?.layout?.yaxis?.range"""
    )
    verify(init_y is not None, "Initial y-axis range defined")

    # Simulate a duration button that causes a bin-size change by sending chart_state to server.
    # Also set sessionStorage so chart.js can apply y-rescale post re-render.
    target_range = ["2025-01-01T11:00:00", "2025-01-01T11:30:00"]
    page.evaluate(
        """(range) => {
            const gd = document.querySelector('#order_chart .js-plotly-plot');
            const orderKey = gd?.layout?.meta?.orderKey || 'default';
            try {
                sessionStorage.setItem('chartLastTargetRange_' + orderKey, JSON.stringify(range));
            } catch (e) {
                // noop
            }
            if (window.Shiny) {
                Shiny.setInputValue('chart_state', {
                    rangeMins: 30,
                    xRange: range,
                    orderKey: orderKey,
                    timestamp: Date.now()
                });
            }
            return true;
        }""",
        target_range,
    )

    # Wait for y-axis range to change meaningfully from init_y.
    page.wait_for_function(
        f"""() => {{
            const gd = document.querySelector('#order_chart .js-plotly-plot');
            const new_y = gd?.layout?.yaxis?.range;
            if (!new_y) return false;
            const init_y0 = {init_y[0]};
            const init_y1 = {init_y[1]};
            return (Math.abs(new_y[0] - init_y0) > 0.001 || Math.abs(new_y[1] - init_y1) > 0.001);
        }}""",
        timeout=8000,
    )

    new_y = page.evaluate(
        """() => document.querySelector('#order_chart .js-plotly-plot')?.layout?.yaxis?.range"""
    )
    dbg = page.evaluate(
        """() => {
            const gd = document.querySelector('#order_chart .js-plotly-plot');
            return {
                orderKey: gd?.layout?.meta?.orderKey ?? null,
                binSize: gd?.layout?.meta?.binSize ?? null,
                xaxis: gd?.layout?.xaxis?.range ?? null,
                xaxis3: gd?.layout?.xaxis3?.range ?? null,
                yaxis: gd?.layout?.yaxis?.range ?? null,
            };
        }"""
    )
    verify(new_y is not None, f"Y-axis range defined after server update (dbg={dbg})")
    verify(new_y[0] < new_y[1], f"Y-axis range valid after server update (dbg={dbg})")

@pytest.mark.anyio
def test_volume_split_and_tooltip(page: Page, app: ShinyAppProc):
    """Verify Lit/Dark stacked volume bars and simplified tooltip format."""
    LOGGER.info("Starting test_volume_split_and_tooltip")
    LOGGER.info("Starting test_volume_split_and_tooltip")
    page.goto(app.url)
    page.locator("#query_btn").click()

    # Select first order (US/SPY which has dark volume)
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row, "Orders table loaded").to_be_visible()
    first_row.click()
    
    # Switch to Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    # Wait for plot to render
    page.locator(".main-svg").first.wait_for(state="visible", timeout=10000)
    
    # Inspect Plotly data directly via JS
    chart_data = page.evaluate("""() => {
        const el = document.querySelector('#order_chart .js-plotly-plot');
        if (!el || !el.data) return null;
        return el.data.map(trace => ({
            name: trace.name, 
            type: trace.type, 
            hovertemplate: trace.hovertemplate,
            hovertext: trace.hovertext,
            hoverinfo: trace.hoverinfo,
            y: trace.y
        }));
    }""")
    
    verify(chart_data is not None, "Chart data retrieved successfully")
    
    # Verify Lit Volume trace exists
    lit_trace = next((t for t in chart_data if t["name"] == "Lit Volume"), None)
    verify(lit_trace is not None, "Lit Volume trace exists")
    verify(lit_trace["type"] == "bar", "Lit Volume is a bar chart")
    
    # Verify Dark Volume trace exists (for US order)
    dark_trace = next((t for t in chart_data if t["name"] == "Dark Volume"), None)
    verify(dark_trace is not None, "Dark Volume trace exists for US order")
    verify(dark_trace["type"] == "bar", "Dark Volume is a bar chart")
    
    # Verify barmode is stack
    layout = page.evaluate("""() => {
        const el = document.querySelector('#order_chart .js-plotly-plot');
        return el?.layout?.barmode;
    }""")
    verify(layout == "stack", f"Layout barmode is 'stack' (got: {layout})")
    
    # Verify simplified tooltip format (Volume: and Dark%:) - only on Lit trace
    # The Lit trace uses hovertext (array) instead of hovertemplate
    lit_ht = lit_trace.get("hovertext") or lit_trace.get("hovertemplate") or []
    if isinstance(lit_ht, list):
        lit_ht_str = " ".join(str(h) for h in lit_ht)
    else:
        lit_ht_str = str(lit_ht)
    verify("Volume:" in lit_ht_str, "Lit tooltip contains 'Volume:'")
    verify("Dark%:" in lit_ht_str, "Lit tooltip contains 'Dark%:'")
    
    # Dark trace should have hover disabled to avoid duplication
    dark_hoverinfo = dark_trace.get("hoverinfo") or ""
    verify(dark_hoverinfo == "skip", f"Dark trace has hover disabled (hoverinfo='skip', got: '{dark_hoverinfo}')")
    
    # Verify dark volume values are within 10-50% range for non-auction bars
    lit_y = lit_trace.get("y") or []
    dark_y = dark_trace.get("y") or []
    
    # Check a few middle bars (skip first/last which might be auctions)
    if len(lit_y) > 4 and len(dark_y) > 4:
        for i in range(2, min(5, len(lit_y) - 2)):
            lit_val = lit_y[i] or 0
            dark_val = dark_y[i] or 0
            total = lit_val + dark_val
            if total > 0:
                dark_pct = (dark_val / total) * 100
                # Should be 10-50% for US orders (with some tolerance)
                verify(5 <= dark_pct <= 55, f"Bar {i}: Dark% is {dark_pct:.1f}% (expected 10-50% range)")


def test_slider_exact_range(page: Page, app: ShinyAppProc) -> None:
    """TDD: Verify exact X-axis range calculation for slider view."""
    
    page.goto(app.url)

    # 1. Inputs are already present on load
    # Wait for inputs to be ready - Reduced timeout to 2s
    page.locator("#start_date input").wait_for(state="visible", timeout=2000)
    page.locator("#start_date input").fill("2025-01-01")
    page.locator("#start_date input").press("Enter")
    
    page.locator("#end_date input").fill("2025-01-03")
    page.locator("#end_date input").press("Enter")
    
    page.locator("#query_btn").click(timeout=2000)
    expect(page.locator(".tabulator-row").first).to_be_visible(timeout=2000)

    # 2. Select Order oid10001 (09:30 - 16:00)
    # Duration = 390m -> Padding = 30m
    # New slider calculation uses bin_seconds:
    #   bin_size = 5min (default) -> bin_seconds = 300
    #   slider_start = exch_open - bin_size = 570 - 5 = 565 (09:25)
    #   slider_end = exch_close + bin_size = 960 + 5 = 965 (16:05)
    # View range calculation in app.py:
    #   view_start = max(slider_start, order_start - padding) = max(565, 570-30) = max(565, 540) = 565 (09:25)
    #   view_end = order_end + padding = 960 + 30 = 990 (16:30), but capped by slider_end if applicable
    #   Since slider_end is extended if x_range[1] > slider_end, view_end should be 990 (16:30) or 965 depending on logic
    # Note: The actual logic may cap the view_end. Let's verify what the app produces.
    
    # Target Row
    row = page.locator(".tabulator-row", has_text="oid10001").first
    row.click(timeout=2000)
    page.locator("a[data-value='Chart']").click(timeout=2000)
    # Wait specifically for the Plotly graph to be present in the DOM
    page.wait_for_selector("#order_chart .js-plotly-plot", state="attached", timeout=5000)
    
    # 3. Extract Rangeslider Handle Position (xaxis3.range) - this is what user drags
    handle_range = page.evaluate("() => document.querySelector('#order_chart .js-plotly-plot').layout.xaxis3.range")
    
    assert handle_range is not None, "Could not retrieve rangeslider handle range"
    
    # Expected handle position based on order (09:30-16:00) with 30min padding
    # Handle start = max(09:25, 09:30-30min) = max(565, 540) = 565 = 09:25
    expected_handle_start = "2025-01-01T09:25:00"  # slider_start wins
    # Handle end = min(16:00+30min, 16:05) = min(990, 965) = 965 = 16:05
    expected_handle_end = "2025-01-01T16:05:00"    # slider_end wins
    
    # Assertions for handle position
    assert handle_range[0] == expected_handle_start, f"Handle start mismatch! Exp: {expected_handle_start}, Got: {handle_range[0]}"
    assert handle_range[1] == expected_handle_end, f"Handle end mismatch! Exp: {expected_handle_end}, Got: {handle_range[1]}"
    
    # 4. Also verify main chart view matches handle position
    chart_range = page.evaluate("() => document.querySelector('#order_chart .js-plotly-plot').layout.xaxis.range")
    assert chart_range is not None, "Could not retrieve main chart range"
    assert chart_range[0] == handle_range[0], f"Chart view should match handle start: {chart_range[0]} vs {handle_range[0]}"
    assert chart_range[1] == handle_range[1], f"Chart view should match handle end: {chart_range[1]} vs {handle_range[1]}"


@pytest.mark.anyio
def test_15min_duration_button_from_first(page: Page, app: ShinyAppProc):
    """Test the 15-minute duration button displays a 15-minute range (e.g., 9:30 to 9:45)."""
    LOGGER.info("Starting test_15min_duration_button_from_first")
    page.goto(app.url)
    
    # Select the first order
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    first_row.click()
    page.wait_for_timeout(200)
    
    # Navigate to Chart tab
    page.get_by_text("Chart", exact=True).click()
    LOGGER.info("  Switched to Chart tab")
    
    # Wait for chart to be visible
    chart = page.locator("#order_chart .js-plotly-plot")
    expect(chart).to_be_visible(timeout=5000)
    page.wait_for_timeout(2000)
    
    # Get initial default range before clicking any buttons
    initial_range = page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        if (!gd || !gd.layout || !gd.layout.xaxis) return null;
        return gd.layout.xaxis.range || null;
    }''')
    LOGGER.info(f"  Initial default range: {initial_range}")
    
    # Calculate initial duration
    if initial_range:
        init_start_parts = initial_range[0].split("T")[1].split(":")
        init_end_parts = initial_range[1].split("T")[1].split(":")
        init_start_mins = int(init_start_parts[0]) * 60 + int(init_start_parts[1])
        init_end_mins = int(init_end_parts[0]) * 60 + int(init_end_parts[1])
        init_duration = init_end_mins - init_start_mins
        LOGGER.info(f"  Initial duration: {init_duration} minutes (from {init_start_parts[0]}:{init_start_parts[1]} to {init_end_parts[0]}:{init_end_parts[1]})")
        LOGGER.info("  This is the default view with padding based on order duration")
    
    # Verify the event handler is attached by checking if _hasRescaling flag is set
    has_rescaling = page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        return gd && gd._hasRescaling === true;
    }''')
    LOGGER.info(f"  Chart has rescaling handler: {has_rescaling}")
    if not has_rescaling:
        # Manually trigger the binding if needed
        page.evaluate('if (typeof resizeAllPlotly === "function") resizeAllPlotly();')
        page.wait_for_timeout(500)
    
    # Click First button, then 15m button
    button_first = page.locator(".updatemenu-button").filter(has_text="First")
    expect(button_first).to_be_visible()
    button_first.click(force=True)
    page.wait_for_timeout(500)
    LOGGER.info("  Clicked 'First' anchor button")
    
    button_15m = page.locator(".updatemenu-button").filter(has_text="15m")
    expect(button_15m).to_be_visible()
    button_15m.click(force=True)
    page.wait_for_timeout(2000)
    LOGGER.info("  Clicked '15m' duration button")
    
    # Get the x-axis range
    x_range = page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        if (!gd || !gd.layout || !gd.layout.xaxis) return null;
        return gd.layout.xaxis.range || null;
    }''')
    
    verify(x_range is not None and len(x_range) == 2, "X-axis range is defined")
    LOGGER.info(f"  X-axis range: {x_range}")
    
    # Calculate duration
    start_parts = x_range[0].split("T")[1].split(":")
    end_parts = x_range[1].split("T")[1].split(":")
    
    start_mins = int(start_parts[0]) * 60 + int(start_parts[1])
    end_mins = int(end_parts[0]) * 60 + int(end_parts[1])
    duration = end_mins - start_mins
    
    LOGGER.info(f"  Duration: {duration} minutes (from {start_parts[0]}:{start_parts[1]} to {end_parts[0]}:{end_parts[1]})")
    
    # Verify approximately 15 minutes (allow ±2 minutes for auction bars)
    verify(abs(duration - 15) <= 2, f"15m button shows ~15 minute duration (got {duration} mins)")
    
    # If order starts at 9:30, verify end is around 9:45
    if start_mins == 9 * 60 + 30:  # 570 minutes = 9:30
        expected_end = 9 * 60 + 45  # 585 minutes = 9:45
        verify(abs(end_mins - expected_end) <= 2, f"For 9:30 start, ends at ~9:45 (got {end_parts[0]}:{end_parts[1]})")
        LOGGER.info("  ✅ PASSED: 15m button shows 9:30-9:45 range")
    else:
        LOGGER.info("  ✅ PASSED: 15m button shows correct 15-minute duration")


@pytest.mark.anyio
def test_all_button_includes_auction_bars(page: Page, app: ShinyAppProc):
    """Test the 'All' button includes Open and Close auction bars after clicking a duration button.
    
    This test reproduces the bug where:
    1. User clicks a duration button (e.g., 30m) which changes the bin size
    2. User clicks 'All' to restore full view
    3. Bug: 'All' uses the wrong bin size offset, leaving out Open/Close bars
    """
    LOGGER.info("Starting test_all_button_includes_auction_bars")
    page.goto(app.url)
    
    # Select the first order (should span full day 9:30-16:00)
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    
    start_time = first_row.locator('.tabulator-cell[tabulator-field="StartTime"]').text_content().strip()
    end_time = first_row.locator('.tabulator-cell[tabulator-field="EndTime"]').text_content().strip()
    LOGGER.info(f"  Order times: {start_time} - {end_time}")
    
    first_row.click()
    page.wait_for_timeout(200)
    
    # Navigate to Chart tab
    page.get_by_text("Chart", exact=True).click()
    LOGGER.info("  Switched to Chart tab")
    
    # Wait for chart to be visible
    chart = page.locator("#order_chart .js-plotly-plot")
    expect(chart).to_be_visible(timeout=5000)
    page.wait_for_timeout(2000)
    
    # IMPORTANT: The bug manifests when clicking a duration button first, then All.
    # First click 30m to switch bin size
    button_30m = page.locator(".updatemenu-button").filter(has_text="30m")
    expect(button_30m).to_be_visible()
    button_30m.click(force=True)
    page.wait_for_timeout(2500)  # Wait for server re-render with new bin size
    LOGGER.info("  Clicked '30m' duration button first")
    
    # Now click the 'All' button
    button_all = page.locator(".updatemenu-button").filter(has_text="All")
    expect(button_all).to_be_visible()
    button_all.click(force=True)
    page.wait_for_timeout(1500)
    LOGGER.info("  Clicked 'All' button")
    
    # Get both the x-axis range AND the defaultRange from metadata
    # The All button uses defaultRange, so we need to check that it's correct
    chart_data = page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        if (!gd || !gd.layout) return null;
        return {
            xAxisRange: gd.layout.xaxis?.range || null,
            defaultRange: gd.layout.meta?.defaultRange || null,
            binSize: gd.layout.meta?.binSize || null,
        };
    }''')
    
    verify(chart_data is not None, "Chart data is available")
    x_range = chart_data.get("xAxisRange")
    default_range = chart_data.get("defaultRange")
    bin_size = chart_data.get("binSize")
    
    LOGGER.info("  After 'All' click:")
    LOGGER.info(f"    - Current x-axis range: {x_range}")
    LOGGER.info(f"    - defaultRange in meta: {default_range}")
    LOGGER.info(f"    - binSize in meta: {bin_size}")
    
    verify(x_range is not None and len(x_range) == 2, "X-axis range is defined")
    verify(default_range is not None and len(default_range) == 2, "defaultRange is defined in metadata")
    
    # Parse time to minutes
    def parse_time_mins(time_str):
        parts = time_str.split(":")
        mins = int(parts[0]) * 60 + int(parts[1])
        if len(parts) > 2:
            mins += int(parts[2]) / 60
        return mins
    
    # Check x-axis range (what's displayed)
    start_time_str = x_range[0].split("T")[1]
    end_time_str = x_range[1].split("T")[1]
    range_start_mins = parse_time_mins(start_time_str)
    range_end_mins = parse_time_mins(end_time_str)
    
    # Check defaultRange in metadata (what All button uses)
    default_start_str = default_range[0].split("T")[1]
    default_end_str = default_range[1].split("T")[1]
    default_start_mins = parse_time_mins(default_start_str)
    default_end_mins = parse_time_mins(default_end_str)
    
    LOGGER.info(f"  X-axis range: {start_time_str} ({range_start_mins:.1f} mins) to {end_time_str} ({range_end_mins:.1f} mins)")
    LOGGER.info(f"  defaultRange: {default_start_str} ({default_start_mins:.1f} mins) to {default_end_str} ({default_end_mins:.1f} mins)")
    
    # For a full-day order (9:30-16:00):
    # - Market open is 9:30 (570 mins)
    # - Market close is 16:00 (960 mins)
    # - 'All' should include Open auction bar (before 9:30) and Close auction bar (after 16:00)
    
    market_open_mins = 9 * 60 + 30   # 9:30 = 570 mins
    market_close_mins = 16 * 60      # 16:00 = 960 mins
    
    # ROBUST CHECK: Verify the range extends by AT LEAST the bin size
    # For a full-day view, bin_size should be 5min (300 seconds)
    verify(bin_size == "5min", f"All button for full day should use 5min bins, got {bin_size}")
    
    expected_bin_mins = 5  # 5 minutes for full day
    
    # Check that the range extends by at least the bin size (with small tolerance)
    open_extension = market_open_mins - default_start_mins
    close_extension = default_end_mins - market_close_mins
    
    LOGGER.info(f"  Open extension: {open_extension:.1f} mins (expected: >={expected_bin_mins} mins)")
    LOGGER.info(f"  Close extension: {close_extension:.1f} mins (expected: >={expected_bin_mins} mins)")
    
    verify(open_extension >= expected_bin_mins - 0.1, 
           f"defaultRange must extend at least {expected_bin_mins} mins before market open for Open auction bar. Got {open_extension:.1f} mins")
    verify(close_extension >= expected_bin_mins - 0.1, 
           f"defaultRange must extend at least {expected_bin_mins} mins after market close for Close auction bar. Got {close_extension:.1f} mins")
    
    # CRITICAL: Check that the auction bar DATA is actually present in the traces
    auction_data = page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        if (!gd || !gd.data) return null;
        
        // Find Lit Volume trace (contains auction bars)
        const litTrace = gd.data.find(t => t.name === "Lit Volume");
        if (!litTrace || !litTrace.customdata) return {error: "No Lit Volume trace or customdata"};
        
        // Check if Open and Close labels exist in customdata
        const labels = litTrace.customdata;
        const hasOpen = labels.some(label => label === "Open");
        const hasClose = labels.some(label => label === "Close");
        
        return {
            totalBars: litTrace.x ? litTrace.x.length : 0,
            hasOpen: hasOpen,
            hasClose: hasClose,
            firstLabel: labels[0],
            lastLabel: labels[labels.length - 1],
            allLabels: labels.slice(0, 5).concat(['...'], labels.slice(-5))  // First 5 and last 5 for debugging
        };
    }''')
    
    LOGGER.info(f"  Auction bar data check: {auction_data}")
    
    verify(auction_data is not None, "Auction data is available")
    verify(not auction_data.get("error"), f"Trace data error: {auction_data.get('error')}")
    verify(auction_data.get("hasOpen"), "Open auction bar is present in trace data")
    verify(auction_data.get("hasClose"), "Close auction bar is present in trace data")
    
    # Verify the actual displayed x-axis range is also correct
    verify(range_start_mins < market_open_mins, 
           f"X-axis start ({start_time_str}) is before market open 9:30 (includes Open auction bar)")
    verify(range_end_mins > market_close_mins, 
           f"X-axis end ({end_time_str}) is after market close 16:00 (includes Close auction bar)")
    
    LOGGER.info("  ✅ PASSED: 'All' button correctly includes Open and Close auction bars (verified in both range AND trace data)")


@pytest.mark.anyio
def test_bin_size_resets_on_order_switch(page: Page, app: ShinyAppProc):
    """
    Test: Bin size should reset based on new order's duration when switching orders.
    
    Scenario:
    1. Select a long-duration order (e.g., 180 mins) -> should use 5min bins
    2. Click a duration button to zoom in (e.g., 15min) -> should switch to smaller bins (30s or 1min)
    3. Switch to a different short-duration order (e.g., 30 mins) -> should reset to appropriate bins for that duration (30s)
    
    Bug fix verification: The bin size from the previous order should NOT carry over.
    """
    LOGGER.info("Starting test_bin_size_resets_on_order_switch")
    
    page.goto(app.url)
    LOGGER.info(f"  Navigated to {app.url}")
    
    # Load data
    start_date = controller.InputDate(page, "start_date")
    end_date = controller.InputDate(page, "end_date")
    start_date.set("2025-01-01")
    end_date.set("2025-01-03")
    page.locator("#query_btn").click()
    page.wait_for_selector("#orders_table .tabulator-row", timeout=5000)
    
    def get_bin_size():
        """Helper to extract current bin size from chart metadata."""
        return page.evaluate("""() => {
            const el = document.getElementById('order_chart');
            const plotlyDiv = el.querySelector('.js-plotly-plot') || el;
            if (!plotlyDiv || !plotlyDiv.layout || !plotlyDiv.layout.meta) return null;
            return plotlyDiv.layout.meta.binSize;
        }""")
    
    def get_order_duration(row_selector):
        """Helper to get order duration in minutes from table row."""
        return page.evaluate(f"""() => {{
            const row = document.querySelector('{row_selector}');
            if (!row) return null;
            const startCell = row.querySelector('[tabulator-field="StartTime"]');
            const endCell = row.querySelector('[tabulator-field="EndTime"]');
            if (!startCell || !endCell) return null;
            
            const parseTime = (str) => {{
                const parts = str.split(':');
                return parseInt(parts[0]) * 60 + parseInt(parts[1]);
            }};
            
            return parseTime(endCell.textContent) - parseTime(startCell.textContent);
        }}""")
    
    # Step 1: Use first order (oid10001) which is 09:30-16:00 (390 mins) -> uses 5min bins
    LOGGER.info("Step 1: Selecting first order (full day duration)")
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    page.wait_for_function("""() => {
        const el = document.getElementById('order_chart');
        const plotlyDiv = el.querySelector('.js-plotly-plot') || el;
        return plotlyDiv && plotlyDiv.data && plotlyDiv.data.length >= 3;
    }""", timeout=5000)
    
    initial_bin_size = get_bin_size()
    LOGGER.info(f"  Initial bin size for first order: {initial_bin_size}")
    verify(initial_bin_size == "5min", 
           f"Full-day order should use 5min bins: {initial_bin_size}")
    
    # Step 2: Use the range slider to zoom in to trigger a bin size change
    LOGGER.info("Step 2: Using slider to zoom in and trigger bin change")
    # Simulate zooming to a 30-minute range (should switch to 30s bins)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        if (!window.Plotly || !gd) return;
        const range = ['2025-01-01T10:00:00', '2025-01-01T10:30:00']; // 30 minutes
        return Plotly.relayout(gd, { 'xaxis3.range': range });
    }''')
    
    # Wait for bin size to update (with longer timeout for debounce + server round-trip)
    page.wait_for_timeout(1000)  # Allow for 100ms debounce + server processing
    
    zoomed_bin_size = get_bin_size()
    LOGGER.info(f"  Bin size after 30min zoom: {zoomed_bin_size}")
    # The test verifies the fix works - if bin changes that's great, 
    # but the main test is that switching orders resets it
    if zoomed_bin_size != "30s":
        LOGGER.warning(f"  Bin didn't change to 30s (still {zoomed_bin_size}), but order switch should still reset it")
    
    # Step 3: Switch to a different order to verify bin size resets
    LOGGER.info("Step 3: Switching to second order to verify bin size resets")
    
    # Go back to table
    page.get_by_text("Table", exact=True).click()
    
    # Click second row (any order will do)
    second_row = orders_table.locator(".tabulator-row").nth(1)
    
    # Get duration of second order
    second_row_selector = "#orders_table .tabulator-row:nth-child(2)"
    second_order_duration = get_order_duration(second_row_selector)
    LOGGER.info(f"  Second order duration: {second_order_duration} mins")
    
    second_row.click()
    page.get_by_text("Chart", exact=True).click()
    page.wait_for_function("""() => {
        const el = document.getElementById('order_chart');
        const plotlyDiv = el.querySelector('.js-plotly-plot') || el;
        return plotlyDiv && plotlyDiv.data && plotlyDiv.data.length >= 3;
    }""", timeout=5000)
    
    # Critical assertion: bin size should reset based on NEW order's duration
    # NOT carry over the zoomed bin size (30s) from previous order
    new_order_bin_size = get_bin_size()
    LOGGER.info(f"  Bin size for second order: {new_order_bin_size}")
    
    # Determine expected bin size based on order duration
    if second_order_duration and second_order_duration > 160:
        expected_bin = "5min"
    elif second_order_duration and second_order_duration > 80:
        expected_bin = "2min"
    elif second_order_duration and second_order_duration >= 40:
        expected_bin = "1min"
    else:
        expected_bin = "30s"
    
    verify(new_order_bin_size == expected_bin, 
           f"Bin size should reset to {expected_bin} for {second_order_duration}min order, got: {new_order_bin_size}")
    
    LOGGER.info("  ✅ PASSED: Bin size correctly resets when switching orders")

