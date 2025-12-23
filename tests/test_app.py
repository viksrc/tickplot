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
    country_table = page.locator("#country_table")
    expect(country_table).to_be_visible()
    LOGGER.info("  ✅ PASSED: Country table is visible")
    
    # Select the first row
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    
    def get_cell_text(field: str) -> str:
        return first_row.locator(f'.tabulator-cell[tabulator-field="{field}"]').text_content().strip()

    order_id = get_cell_text("orderid")
    side = get_cell_text("Side")
    ticker = get_cell_text("Ticker")
    exec_qty = get_cell_text("ExecQty") 
    strategy = get_cell_text("Strategy")
    
    LOGGER.info(f"  Selecting order {order_id} ({ticker})")
    first_row.click()
    
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
    
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
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
    page.wait_for_timeout(500) 
    
    rows_after = order_details_table.locator(".tabulator-row").count()
    verify(rows_after > rows_before, f"Row count increased from {rows_before} to {rows_after}")
    
    scroll_height_after = tableholder.evaluate("el => el.scrollHeight")
    client_height_after = tableholder.evaluate("el => el.clientHeight")
    verify(scroll_height_after > client_height_after, "Vertical scrollbar appeared after showing all fields")

@pytest.mark.anyio
def test_fill_details_features(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_fill_details_features")
    page.goto(app.url)
    
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
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
    
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
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
    
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
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
    
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#stock_chart")).to_be_visible(timeout=5000)
    expect(page.locator("#stock_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    LOGGER.info("  ✅ PASSED: Stock chart and Plotly container are visible")

@pytest.mark.anyio
def test_volume_chart_features(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_volume_chart_features")
    page.goto(app.url)
    
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#stock_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    
    volume_bars = page.locator(".trace.bars .point")
    expect(volume_bars.first).to_be_visible(timeout=5000)
    bar_count = volume_bars.count()
    verify(bar_count > 0, f"Volume chart has {bar_count} bars")
    
    hover_labels = page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
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
    page.locator("#country_table .tabulator-row").first.click()
    page.get_by_text("Chart", exact=True).click()
    
    expect(page.locator("#stock_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    
    has_rangeslider = page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        const xaxis = gd?.layout?.xaxis;
        return xaxis?.rangeslider?.visible === true;
    }''')
    verify(has_rangeslider, "Rangeslider is visible in Plotly layout")
    expect(page.locator("#stock_chart .rangeslider-container")).to_be_visible()
    LOGGER.info("  ✅ PASSED: Rangeslider SVG container is visible")

@pytest.mark.anyio
def test_range_slider_initial_range(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_range_slider_initial_range")
    page.goto(app.url)
    first_row = page.locator("#country_table .tabulator-row").first
    start_time = first_row.locator('.tabulator-cell[tabulator-field="StartTime"]').text_content().strip()
    end_time = first_row.locator('.tabulator-cell[tabulator-field="EndTime"]').text_content().strip()
    first_row.click()
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#stock_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    
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
    
    actual_range = page.evaluate('''() => document.querySelector("#stock_chart .js-plotly-plot")?.layout?.xaxis?.range''')
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
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#stock_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    page.wait_for_timeout(2000)

    def get_current_bin_duration():
        labels = page.evaluate('''() => {
            const gd = document.querySelector("#stock_chart .js-plotly-plot");
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
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T11:21:00']; // 81 minutes
        if (window.Shiny) {
            Shiny.setInputValue('chart_range_mins', 81);
            Shiny.setInputValue('chart_x_range', range);
        }
        if (window.Plotly) {
            Plotly.relayout(gd, { 'xaxis.range': range });
        }
    }''')
    page.wait_for_timeout(3000)
    verify(get_current_bin_duration() == 300, "81-min range uses 5-min bins (300s)")

    # Step B: Check 80 mins (Switchover! Should be 1min / 60s)
    page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T11:20:00']; // 80 minutes
        if (window.Shiny) {
            Shiny.setInputValue('chart_range_mins', 80);
            Shiny.setInputValue('chart_x_range', range);
        }
        if (window.Plotly) {
            Plotly.relayout(gd, { 'xaxis.range': range });
        }
    }''')
    page.wait_for_timeout(3000)
    verify(get_current_bin_duration() == 60, "80-min range (just below 81) switched to 1-min bins (60s)")

    # Step C: Check 41 mins (Still 1min / 60s)
    page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T10:41:00']; // 41 minutes
        if (window.Shiny) {
            Shiny.setInputValue('chart_range_mins', 41);
            Shiny.setInputValue('chart_x_range', range);
        }
        if (window.Plotly) {
            Plotly.relayout(gd, { 'xaxis.range': range });
        }
    }''')
    page.wait_for_timeout(3000)
    verify(get_current_bin_duration() == 60, "41-min range uses 1-min bins (60s)")

    # Step D: Check 39 mins (Switchover! Should be 30s)
    page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T10:39:00']; // 39 minutes
        if (window.Shiny) {
            Shiny.setInputValue('chart_range_mins', 39);
            Shiny.setInputValue('chart_x_range', range);
        }
        if (window.Plotly) {
            Plotly.relayout(gd, { 'xaxis.range': range });
        }
    }''')
    page.wait_for_timeout(3000)
    verify(get_current_bin_duration() == 30, "39-min range (just below 41) switched to 30s bins")

@pytest.mark.anyio
def test_range_slider_yaxis_rescaling(page: Page, app: ShinyAppProc):
    LOGGER.info("Starting test_range_slider_yaxis_rescaling")
    page.goto(app.url)
    page.locator("#country_table .tabulator-row").first.click()
    page.get_by_text("Chart", exact=True).click()
    expect(page.locator("#stock_chart .js-plotly-plot")).to_be_visible(timeout=5000)
    
    init_y = page.evaluate('''() => document.querySelector("#stock_chart .js-plotly-plot")?.layout?.yaxis?.range''')
    verify(init_y is not None, "Initial y-axis range defined")
    
    # Zoom to 30 mins
    page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        Plotly.relayout(gd, { 'xaxis.range': ['2025-01-01T11:00:00', '2025-01-01T11:30:00'] });
    }''')
    page.wait_for_timeout(1500)
    
    new_y = page.evaluate('''() => document.querySelector("#stock_chart .js-plotly-plot")?.layout?.yaxis?.range''')
    verify(new_y is not None, "Y-axis range defined after zoom")
    
    changed = abs(new_y[0] - init_y[0]) > 0.001 or abs(new_y[1] - init_y[1]) > 0.001
    verify(changed, "Y-axis range adjusted after zoom")
    verify(new_y[1] - new_y[0] <= (init_y[1] - init_y[0]) * 1.5, "Zoomed y-axis span is reasonable")
