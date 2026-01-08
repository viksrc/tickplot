import logging

# Configure logging to show in console
logging.basicConfig(level=logging.INFO, format='%(message)s')
LOGGER = logging.getLogger(__name__)

def verify(condition, message):
    """Assert a condition and log a success message if it passes."""
    assert condition, message
    LOGGER.info(f"  ✅ PASSED: {message}")

import pytest
from playwright.sync_api import Page, expect
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
    LOGGER.info("  ✅ PASSED: Date picker initial value is 2025-01-01")
    
    # 3. Verify the main table exists
    orders_table = page.locator("#orders_table")
    expect(orders_table).to_be_visible()
    LOGGER.info("  ✅ PASSED: Orders table is visible")
    
    # Select the first row
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    
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
    expect(chart_title_el).to_be_visible()
    
    expect(chart_title_el).to_contain_text(order_id)
    expect(chart_title_el).to_contain_text(side)
    expect(chart_title_el).to_contain_text(ticker)
    expect(chart_title_el).to_contain_text(strategy)
    expect(chart_title_el).to_contain_text(exec_qty)
    LOGGER.info(f"  ✅ PASSED: Chart title correctly displays order {order_id} details")
    
@pytest.mark.anyio
def test_settings_interaction(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_settings_interaction")
    page.goto(app.url)
    
    dark_mode = controller.InputDarkMode(page, "dark_mode")
    dark_mode.expect_mode("light") 
    LOGGER.info("  ✅ PASSED: Initial mode is light")
    
    dark_mode.click()
    dark_mode.expect_mode("dark")
    LOGGER.info("  ✅ PASSED: Toggled to dark mode")
    
    page.get_by_text("Chart", exact=True).click()
    
    show_all = controller.InputSwitch(page, "show_all_details")
    show_all.expect_checked(False)
    LOGGER.info("  ✅ PASSED: 'Show All Details' switch defaults to False")
    
    show_all.set(True)
    show_all.expect_checked(True)
    LOGGER.info("  ✅ PASSED: 'Show All Details' switch toggled to True")

@pytest.mark.anyio
def test_order_detail_features(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_order_detail_features")
    page.goto(app.url)
    
    orders_table = page.locator("#orders_table")
    first_row = orders_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    
    pct_adv_table = first_row.locator('.tabulator-cell[tabulator-field="PctADV"]').text_content().strip()
    LOGGER.info(f"  Order PctADV in main table: {pct_adv_table}")
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    
    order_details_table = page.locator("#order_details_table")
    expect(order_details_table).to_be_visible()
    
    pct_adv_row = order_details_table.locator(".tabulator-row", has_text="PctADV")
    expect(pct_adv_row).to_be_visible()
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
    expect(first_row).to_be_visible()
    
    exec_qty_str = first_row.locator('.tabulator-cell[tabulator-field="ExecQty"]').text_content().strip()
    exec_qty = int(exec_qty_str.replace(",", ""))
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    fill_details_table = page.locator("#fill_detail_table")
    expect(fill_details_table).to_be_visible()
    
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
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    venue_table = page.locator("#venue_table")
    expect(venue_table).to_be_visible()
    
    rows = venue_table.locator(".tabulator-row")
    expect(rows.first).to_be_visible()
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
    expect(first_row).to_be_visible()
    
    def get_cell_text(field: str) -> str:
        return first_row.locator(f'.tabulator-cell[tabulator-field="{field}"]').text_content().strip()

    perf_arrival = get_cell_text("PerfArrival")
    perf_vwap = get_cell_text("PerfVWAP")
    perf_close = get_cell_text("PerfClose")
    spread_capture = get_cell_text("SpreadCapture")
    
    first_row.click()
    page.get_by_text("Chart", exact=True).click()
    
    chart_metrics = page.locator("#chart_metrics")
    expect(chart_metrics).to_be_visible()
    
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
    page.wait_for_timeout(500)
    verify(orders_table.is_visible(), "Orders table is visible")
    
    # Select the row with orderid oid10004
    target_row = orders_table.locator(".tabulator-row", has_text="oid10004")
    target_row.wait_for(state="visible", timeout=5000)
    verify(target_row.is_visible(), "Order oid10004 row is visible")
    
    # Get start and end times from the order
    start_time = target_row.locator('.tabulator-cell[tabulator-field="StartTime"]').text_content().strip()
    end_time = target_row.locator('.tabulator-cell[tabulator-field="EndTime"]').text_content().strip()
    verify(start_time != "", f"Order oid10004 has start time: {start_time}")
    verify(end_time != "", f"Order oid10004 has end time: {end_time}")
    
    target_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    page.wait_for_timeout(500)
    page.locator("#order_chart").wait_for(state="visible", timeout=5000)
    verify(page.locator("#order_chart").is_visible(), "Stock chart container is visible")
    page.locator("#order_chart .js-plotly-plot").wait_for(state="visible", timeout=5000)
    verify(page.locator("#order_chart .js-plotly-plot").is_visible(), "Plotly chart is visible")
    
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
    expect(first_row).to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    
    volume_bars = page.locator(".trace.bars .point")
    expect(volume_bars.first).to_be_visible(timeout=5000)
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
    
    expect(page.locator("#order_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    
    has_rangeslider = page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const xaxis = gd?.layout?.xaxis;
        return xaxis?.rangeslider?.visible === true;
    }''')
    verify(has_rangeslider, "Rangeslider is visible in Plotly layout")
    expect(page.locator("#order_chart .rangeslider-container")).to_be_visible()
    LOGGER.info("  ✅ PASSED: Rangeslider SVG container is visible")

@pytest.mark.anyio
def test_range_slider_initial_range(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_range_slider_initial_range")
    page.goto(app.url)
    first_row = page.locator("#orders_table .tabulator-row").first
    start_time = first_row.locator('.tabulator-cell[tabulator-field="StartTime"]').text_content().strip()
    end_time = first_row.locator('.tabulator-cell[tabulator-field="EndTime"]').text_content().strip()
    first_row.click()
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    
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
    expect(first_row).to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    page.wait_for_timeout(1000)

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

    # Step A: Check 81 mins (Should be 5min / 300s)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T11:21:00']; // 81 minutes
        if (window.Shiny) {
            Shiny.setInputValue('chart_range_mins', 81);
            Shiny.setInputValue('chart_x_range', range);
        }
        if (window.Plotly) {
            Plotly.relayout(gd, { 'xaxis.range': range });
        }
    }''')
    page.wait_for_timeout(1500)
    verify(get_current_bin_duration() == 300, "81-min range uses 5-min bins (300s)")

    # Step B: Check 80 mins (Switchover! Should be 1min / 60s)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T11:20:00']; // 80 minutes
        if (window.Shiny) {
            Shiny.setInputValue('chart_range_mins', 80);
            Shiny.setInputValue('chart_x_range', range);
        }
        if (window.Plotly) {
            Plotly.relayout(gd, { 'xaxis.range': range });
        }
    }''')
    page.wait_for_timeout(1500)
    verify(get_current_bin_duration() == 60, "80-min range (just below 81) switched to 1-min bins (60s)")

    # Step C: Check 41 mins (Still 1min / 60s)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T10:41:00']; // 41 minutes
        if (window.Shiny) {
            Shiny.setInputValue('chart_range_mins', 41);
            Shiny.setInputValue('chart_x_range', range);
        }
        if (window.Plotly) {
            Plotly.relayout(gd, { 'xaxis.range': range });
        }
    }''')
    page.wait_for_timeout(1500)
    verify(get_current_bin_duration() == 60, "41-min range uses 1-min bins (60s)")

    # Step D: Check 39 mins (Switchover! Should be 30s)
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T10:39:00']; // 39 minutes
        if (window.Shiny) {
            Shiny.setInputValue('chart_range_mins', 39);
            Shiny.setInputValue('chart_x_range', range);
        }
        if (window.Plotly) {
            Plotly.relayout(gd, { 'xaxis.range': range });
        }
    }''')
    page.wait_for_timeout(1500)
    verify(get_current_bin_duration() == 30, "39-min range (just below 41) switched to 30s bins")

@pytest.mark.anyio
def test_range_slider_yaxis_rescaling(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_range_slider_yaxis_rescaling")
    page.goto(app.url)
    page.locator("#orders_table .tabulator-row").first.click()
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#order_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    
    init_y = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.yaxis?.range''')
    verify(init_y is not None, "Initial y-axis range defined")
    
    # Zoom to 30 mins
    page.evaluate('''() => {
        const gd = document.querySelector("#order_chart .js-plotly-plot");
        Plotly.relayout(gd, { 'xaxis.range': ['2025-01-01T11:00:00', '2025-01-01T11:30:00'] });
    }''')
    page.wait_for_timeout(800)
    
    new_y = page.evaluate('''() => document.querySelector("#order_chart .js-plotly-plot")?.layout?.yaxis?.range''')
    verify(new_y is not None, "Y-axis range defined after zoom")
    
    changed = abs(new_y[0] - init_y[0]) > 0.001 or abs(new_y[1] - init_y[1]) > 0.001
    verify(changed, "Y-axis range adjusted after zoom")
    verify(new_y[1] - new_y[0] <= (init_y[1] - init_y[0]) * 1.5, "Zoomed y-axis span is reasonable")

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
        LOGGER.info(f"  This is the default view with padding based on order duration")
    
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
        LOGGER.info(f"  ✅ PASSED: 15m button shows 9:30-9:45 range")
    else:
        LOGGER.info(f"  ✅ PASSED: 15m button shows correct 15-minute duration")


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
    
    LOGGER.info(f"  After 'All' click:")
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
    
    # CRITICAL: Verify the defaultRange in metadata is correct!
    # This is what the All button reads from, so if this is wrong, All won't work
    verify(default_start_mins < market_open_mins, 
           f"defaultRange start ({default_start_str}) must be before market open 9:30 (includes Open auction bar)")
    verify(default_end_mins > market_close_mins, 
           f"defaultRange end ({default_end_str}) must be after market close 16:00 (includes Close auction bar)")
    
    # Verify the actual displayed x-axis range is also correct
    verify(range_start_mins < market_open_mins, 
           f"X-axis start ({start_time_str}) is before market open 9:30 (includes Open auction bar)")
    verify(range_end_mins > market_close_mins, 
           f"X-axis end ({end_time_str}) is after market close 16:00 (includes Close auction bar)")
    
    LOGGER.info(f"  ✅ PASSED: 'All' button correctly includes Open and Close auction bars")

