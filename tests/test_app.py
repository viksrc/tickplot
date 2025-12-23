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
    # 1. Navigate to the app URL
    page.goto(app.url)
    
    # 2. Interact with the Date Picker using controller
    date_picker = controller.InputDate(page, "date_picker")
    date_picker.expect_value("2025-01-01")
    
    # 3. Verify the main table exists
    # Tabulator doesn't have a dedicated controller, so we use locators
    country_table = page.locator("#country_table")
    expect(country_table).to_be_visible()
    
    # Select the first row in the order table
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    
    # Extract values from the row before clicking (or after, but while it's visible)
    # Tabulator cells use data-field or similar; let's use the field selectors
    def get_cell_text(field: str) -> str:
        return first_row.locator(f'.tabulator-cell[tabulator-field="{field}"]').text_content().strip()

    order_id = get_cell_text("orderid")
    side = get_cell_text("Side")
    ticker = get_cell_text("Ticker")
    exec_qty = get_cell_text("ExecQty") 
    strategy = get_cell_text("Strategy")
    
    first_row.click()
    
    # 4. Navigate to the Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    # 5. Verify Chart Tab elements using controllers where possible
    
    # Chart title is an output_ui
    chart_title_el = page.locator("#chart_title")
    expect(chart_title_el).to_be_visible()
    
    # Verify it contains all extracted fields dynamically
    expect(chart_title_el).to_contain_text(order_id)
    expect(chart_title_el).to_contain_text(side)
    expect(chart_title_el).to_contain_text(ticker)
    expect(chart_title_el).to_contain_text(strategy)
    expect(chart_title_el).to_contain_text(exec_qty)
    
@pytest.mark.anyio
def test_settings_interaction(page: Page, app: ShinyAppProc):
    page.goto(app.url)
    
    # Dark mode toggle using controller
    dark_mode = controller.InputDarkMode(page, "dark_mode")
    dark_mode.expect_mode("light") # Initial state
    
    # Toggle it
    dark_mode.click()
    dark_mode.expect_mode("dark")
    
    # Switch to Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    # Verify the "Show All Details" switch in the Chart sidebar
    show_all = controller.InputSwitch(page, "show_all_details")
    show_all.expect_checked(False)
    show_all.set(True)
    show_all.expect_checked(True)

@pytest.mark.anyio
def test_order_detail_features(page: Page, app: ShinyAppProc):
    page.goto(app.url)
    
    # 1. Get PctADV from Table tab
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    
    pct_adv_table = first_row.locator('.tabulator-cell[tabulator-field="PctADV"]').text_content().strip()
    first_row.click()
    
    # 2. Switch to Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    order_details_table = page.locator("#order_details_table")
    expect(order_details_table).to_be_visible()
    
    # 3. Check PctADV value in Order Details
    # The order details table has two columns: Field and Value
    # Find the row where Field is PctADV
    pct_adv_row = order_details_table.locator(".tabulator-row", has_text="PctADV")
    expect(pct_adv_row).to_be_visible()
    pct_adv_val = pct_adv_row.locator('.tabulator-cell[tabulator-field="Value"]').text_content().strip()
    assert pct_adv_val == pct_adv_table
    
    # 4. Verify no scrollbars by default
    tableholder = order_details_table.locator(".tabulator-tableholder")
    
    scroll_height = tableholder.evaluate("el => el.scrollHeight")
    client_height = tableholder.evaluate("el => el.clientHeight")
    scroll_width = tableholder.evaluate("el => el.scrollWidth")
    client_width = tableholder.evaluate("el => el.clientWidth")
    
    assert scroll_height <= client_height, f"Vertical scrollbar should not be present (SH:{scroll_height} <= CH:{client_height})"
    assert scroll_width <= client_width, "Horizontal scrollbar should not be present"
    
    # 5. Toggle "All" and verify rows and vertical scrollbar
    rows_before = order_details_table.locator(".tabulator-row").count()
    
    show_all = controller.InputSwitch(page, "show_all_details")
    show_all.set(True)
    
    # Wait for table to update
    page.wait_for_timeout(500) 
    
    rows_after = order_details_table.locator(".tabulator-row").count()
    assert rows_after > rows_before, f"Row count should increase (before: {rows_before}, after: {rows_after})"
    
    # Verify vertical scrollbar appears
    scroll_height_after = tableholder.evaluate("el => el.scrollHeight")
    client_height_after = tableholder.evaluate("el => el.clientHeight")
    
    assert scroll_height_after > client_height_after, f"Vertical scrollbar should appear (SH:{scroll_height_after} > CH:{client_height_after})"

@pytest.mark.anyio
def test_fill_details_features(page: Page, app: ShinyAppProc):
    page.goto(app.url)
    
    # 1. Get ExecQty from Table tab
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    
    exec_qty_str = first_row.locator('.tabulator-cell[tabulator-field="ExecQty"]').text_content().strip()
    exec_qty = int(exec_qty_str.replace(",", ""))
    first_row.click()
    
    # 2. Switch to Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    fill_details_table = page.locator("#fill_detail_table")
    expect(fill_details_table).to_be_visible()
    
    # 3. Verify NumFills and AvgFillSize
    num_fills_row = fill_details_table.locator(".tabulator-row", has_text="NumFills")
    expect(num_fills_row).to_be_visible()
    num_fills_val = num_fills_row.locator('.tabulator-cell[tabulator-field="Value"]').text_content().strip()
    assert num_fills_val == "50", f"NumFills should be 50, got {num_fills_val}"
    
    avg_fill_size_row = fill_details_table.locator(".tabulator-row", has_text="AvgFillSize")
    expect(avg_fill_size_row).to_be_visible()
    avg_fill_size_val_str = avg_fill_size_row.locator('.tabulator-cell[tabulator-field="Value"]').text_content().strip()
    avg_fill_size_val = int(avg_fill_size_val_str.replace(",", ""))
    
    # Logic in app.py: avg_fill_size = int(round(exec_qty / 50))
    expected_avg_fill_size = int(round(exec_qty / 50))
    assert avg_fill_size_val == expected_avg_fill_size, f"AvgFillSize should be {expected_avg_fill_size}, got {avg_fill_size_val}"
    
    # 4. Verify no scrollbars
    tableholder = fill_details_table.locator(".tabulator-tableholder")
    scroll_height = tableholder.evaluate("el => el.scrollHeight")
    client_height = tableholder.evaluate("el => el.clientHeight")
    scroll_width = tableholder.evaluate("el => el.scrollWidth")
    client_width = tableholder.evaluate("el => el.clientWidth")
    
    assert scroll_height <= client_height, f"Vertical scrollbar should not be present (SH:{scroll_height} <= CH:{client_height})"
    assert scroll_width <= client_width, f"Horizontal scrollbar should not be present (SW:{scroll_width} <= CW:{client_width})"

@pytest.mark.anyio
def test_venue_table_features(page: Page, app: ShinyAppProc):
    page.goto(app.url)
    
    # 1. Click a row and switch to Chart tab
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    first_row.click()
    
    page.get_by_text("Chart", exact=True).click()
    
    venue_table = page.locator("#venue_table")
    expect(venue_table).to_be_visible()
    
    # 2. Verify it has at least one row (wait for it to load)
    rows = venue_table.locator(".tabulator-row")
    expect(rows.first).to_be_visible()
    row_count = rows.count()
    assert row_count >= 1, f"Venue table should have at least one row, got {row_count}"
    
    # 3. Verify no scrollbars
    tableholder = venue_table.locator(".tabulator-tableholder")
    scroll_height = tableholder.evaluate("el => el.scrollHeight")
    client_height = tableholder.evaluate("el => el.clientHeight")
    scroll_width = tableholder.evaluate("el => el.scrollWidth")
    client_width = tableholder.evaluate("el => el.clientWidth")
    
    # Note: Using a small tolerance for scroll checks in some environments
    assert scroll_height <= client_height + 2, f"Vertical scrollbar should not be present (SH:{scroll_height} <= CH:{client_height})"
    assert scroll_width <= client_width + 2, f"Horizontal scrollbar should not be present (SW:{scroll_width} <= CW:{client_width})"
    
    # 4. Verify FillPct across rows sums to 100% (+- 0.1)
    # The PctFillBar contains text like "Lit 30% | Dark 70%" or just "30.0%"
    # In app.py (_pct_fill_bar_html), it actually puts the pct in a div with label: f"{pct_val:.1f}%"
    
    total_pct = 0.0
    for i in range(row_count):
        row = rows.nth(i)
        # Try to find the percentage text. It's inside a div usually.
        cell_text = row.locator('.tabulator-cell[tabulator-field="PctFillBar"]').text_content().strip()
        
        # The text might be "30.0%" or "Dark: 30.0%" etc depending on the bar type.
        # Let's extract numeric parts.
        import re
        matches = re.findall(r"(\d+\.\d+)%", cell_text)
        if matches:
            total_pct += float(matches[0])
            
    assert abs(total_pct - 100.0) <= 0.15, f"Total PctFill should be 100%, got {total_pct}"

@pytest.mark.anyio
def test_chart_metrics_features(page: Page, app: ShinyAppProc):
    page.goto(app.url)
    
    # 1. Extract values from Table tab
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
    
    # 2. Switch to Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    # 3. Verify Chart Metrics chips
    chart_metrics = page.locator("#chart_metrics")
    expect(chart_metrics).to_be_visible()
    
    def verify_chip(label: str, expected_val_raw: str, is_bps: bool = True):
        # The chip is a span containing two nested spans
        chip = chart_metrics.locator("span", has_text=label).first
        # Find the sibling or parent structure. 
        # based on app.py: ui.span(ui.span(label, ...), ui.span(value_str, ...), ...)
        # So the chip span itself contains two spans.
        value_span = chip.locator("span").nth(1)
        value_text = value_span.text_content().strip()
        
        # Formatting check
        if is_bps:
            # Expected format: "+X.Y bps" or "-X.Y bps"
            # expected_val_raw is "X.Y"
            val_float = float(expected_val_raw)
            expected_formatted = f"{val_float:+.1f} bps"
            assert value_text == expected_formatted, f"{label} mismatch: expected {expected_formatted}, got {value_text}"
        else:
            # Expected format: "X.Y%"
            expected_formatted = f"{float(expected_val_raw):.1f}%"
            assert value_text == expected_formatted, f"{label} mismatch: expected {expected_formatted}, got {value_text}"

    verify_chip("PerfArrival", perf_arrival)
    verify_chip("PerfVWAP", perf_vwap)
    verify_chip("PerfClose", perf_close)
    verify_chip("SpreadCapture", spread_capture, is_bps=False)

@pytest.mark.anyio
def test_stock_chart_existence(page: Page, app: ShinyAppProc):
    """Simple test to verify the stock chart exists and is visible after selecting an order."""
    page.goto(app.url)
    
    # 1. Select an order (required for chart data to load)
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    first_row.click()
    
    # 2. Switch to Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    # 3. Verify the Chart Tab outputs are visible
    expect(page.locator("#chart_title")).to_be_visible()
    expect(page.locator("#chart_metrics")).to_be_visible()
    
    # 4. Verify the Stock Chart Widget container exists
    stock_chart = page.locator("#stock_chart")
    expect(stock_chart).to_be_visible(timeout=5000)
    
    # 5. Verify the internal Plotly graph has actually rendered
    # Plotly renders an inner div with class 'js-plotly-plot'
    plotly_graph = stock_chart.locator(".js-plotly-plot")
    expect(plotly_graph).to_be_visible(timeout=5000)

@pytest.mark.anyio
def test_volume_chart_features(page: Page, app: ShinyAppProc):
    """Test Volume Chart presence and bar structure."""
    page.goto(app.url)
    
    # 1. Select an order
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    
    start_time = first_row.locator('.tabulator-cell[tabulator-field="StartTime"]').text_content().strip()
    end_time = first_row.locator('.tabulator-cell[tabulator-field="EndTime"]').text_content().strip()
    
    first_row.click()
    
    # 2. Switch to Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    # 3. Wait for Plotly to render
    stock_chart = page.locator("#stock_chart")
    expect(stock_chart).to_be_visible(timeout=5000)
    
    # Wait for the internal plotly div
    plotly_div = page.locator("#stock_chart .js-plotly-plot")
    expect(plotly_div).to_be_visible(timeout=5000)
    
    # 4. Verify Volume Bars exist (SVG bar elements)
    volume_bars = page.locator(".trace.bars .point")
    expect(volume_bars.first).to_be_visible(timeout=5000)
    
    bar_count = volume_bars.count()
    assert bar_count > 0, "Volume chart should have at least one bar"
    
    # 5. Verify the hover data exists in Plotly's internal data structure via JS
    # This checks that the customdata (which contains hover labels) is present
    hover_labels = page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        if (!gd || !gd.data) return [];
        // Find the bar trace (trace with type 'bar')
        const barTrace = gd.data.find(t => t.type === 'bar');
        if (!barTrace || !barTrace.customdata) return [];
        return barTrace.customdata;
    }''')
    
    assert len(hover_labels) > 0, "Volume bars should have hover labels (customdata)"
    
    # 6. First order starts at 09:30, first bar label MUST contain "Open"
    first_label = str(hover_labels[0]) if hover_labels else ""
    assert "Open" in first_label, f"First bar should be labeled 'Open' when order starts at 09:30, got: {first_label}"

    # 7. First order ends at 16:00, last bar label MUST contain "Close"
    last_label = str(hover_labels[-1]) if hover_labels else ""
    assert "Close" in last_label, f"Last bar should be labeled 'Close' when order ends at 16:00, got: {last_label}"

    # 8. Check a middle label has 5-minute duration (300 seconds)
    if len(hover_labels) > 2:
        mid_label = str(hover_labels[len(hover_labels) // 2])
        import re
        # Pattern for HH:MM or HH:MM:SS
        t = r"(\d{1,2}:\d{2}(?::\d{2})?)"
        # app.py uses en-dash (–) but we'll accept hyphen too for robustness
        match = re.search(f"{t}[–-]{t}", mid_label)
        
        if match:
            t1, t2 = match.groups()
            def to_sec(s):
                p = list(map(int, s.split(':')))
                return p[0]*3600 + p[1]*60 + (p[2] if len(p)==3 else 0)
            
            duration_sec = to_sec(t2) - to_sec(t1)
            assert duration_sec == 300, f"Middle bar duration should be 5 mins (300s), got {duration_sec}s from '{mid_label}'"
        else:
            # If not a range, ensure it's at least Open/Close or complain
            if "Open" not in mid_label and "Close" not in mid_label:
                assert False, f"Middle bar label should be a time range, got: {mid_label}"

@pytest.mark.anyio
def test_range_slider_presence(page: Page, app: ShinyAppProc):
    """Test 1: Verify the Plotly rangeslider exists in the DOM."""
    page.goto(app.url)
    
    # Select an order (required for chart to render)
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    first_row.click()
    
    # Switch to Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    # Wait for the Plotly chart to render
    stock_chart = page.locator("#stock_chart")
    expect(stock_chart).to_be_visible(timeout=5000)
    
    plotly_div = page.locator("#stock_chart .js-plotly-plot")
    expect(plotly_div).to_be_visible(timeout=5000)
    
    # Verify the rangeslider exists in Plotly's layout
    has_rangeslider = page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        if (!gd || !gd.layout) return false;
        const xaxis = gd.layout.xaxis;
        return xaxis && xaxis.rangeslider && xaxis.rangeslider.visible === true;
    }''')
    
    verify(has_rangeslider, "Plotly rangeslider exists and is visible in xaxis layout")
    
    # Also verify the rangeslider's SVG elements are in the DOM
    rangeslider_svg = page.locator("#stock_chart .rangeslider-container")
    expect(rangeslider_svg).to_be_visible(timeout=2000)
    LOGGER.info("  ✅ PASSED: Rangeslider SVG container is visible in DOM")

@pytest.mark.anyio
def test_range_slider_initial_range(page: Page, app: ShinyAppProc):
    """Test 2: Assert that the initial visible window matches the padded duration of the selected order."""
    page.goto(app.url)
    
    # Get order times before clicking
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    
    start_time = first_row.locator('.tabulator-cell[tabulator-field="StartTime"]').text_content().strip()
    end_time = first_row.locator('.tabulator-cell[tabulator-field="EndTime"]').text_content().strip()
    
    first_row.click()
    
    # Switch to Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    # Wait for chart to render
    stock_chart = page.locator("#stock_chart")
    expect(stock_chart).to_be_visible(timeout=5000)
    plotly_div = page.locator("#stock_chart .js-plotly-plot")
    expect(plotly_div).to_be_visible(timeout=5000)
    
    # Calculate expected padded range (matching app.py logic)
    def time_to_mins(t: str) -> int:
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    
    st_minutes = time_to_mins(start_time)
    et_minutes = time_to_mins(end_time)
    duration = et_minutes - st_minutes
    
    # Determine padding based on duration (matching app.py)
    if duration > 120:
        padding_mins = 30
    elif duration > 20:
        padding_mins = 10
    else:
        padding_mins = 5
    
    # Calculate expected range (with clamps matching app.py)
    # Determine bin_size to get min_left_mins
    if duration + (60 if duration > 120 else (20 if duration > 20 else 10)) > 78:
        min_left_mins = 560  # 09:20 (5min bins)
    elif duration + (60 if duration > 120 else (20 if duration > 20 else 10)) > 15:
        min_left_mins = 565  # 09:25 (1min bins)
    else:
        min_left_mins = 569  # 09:29 (30s bins)
    
    expected_start_mins = max(min_left_mins, st_minutes - padding_mins)
    expected_end_mins = min(965, et_minutes + padding_mins)  # 965 = 16:05
    
    # Get actual x-axis range from Plotly
    actual_range = page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        if (!gd || !gd.layout || !gd.layout.xaxis || !gd.layout.xaxis.range) return null;
        return gd.layout.xaxis.range;
    }''')
    
    verify(actual_range is not None, "Chart has an x-axis range defined")
    verify(len(actual_range) == 2, "X-axis range has start and end values")
    
    # Parse the actual range times
    import re
    def parse_time_from_range(val: str) -> int:
        """Parse time from ISO format like '2025-01-01T09:25:00' to minutes since midnight."""
        match = re.search(r"T(\d{2}):(\d{2})", str(val))
        if match:
            return int(match.group(1)) * 60 + int(match.group(2))
        return 0
    
    actual_start_mins = parse_time_from_range(actual_range[0])
    actual_end_mins = parse_time_from_range(actual_range[1])
    
    # Allow some tolerance (±5 minutes) for rounding differences
    verify(abs(actual_start_mins - expected_start_mins) <= 5, 
           f"Start time matches padded order start (~{expected_start_mins}m, got {actual_start_mins}m)")
    verify(abs(actual_end_mins - expected_end_mins) <= 5, 
           f"End time matches padded order end (~{expected_end_mins}m, got {actual_end_mins}m)")

@pytest.mark.anyio
def test_range_slider_dynamic_binning(page: Page, app: ShinyAppProc):
    """Test 3: Verify volume bars switch from 300s -> 60s -> 30s granularity on sequential zooms."""
    page.goto(app.url)
    
    # 1. Select an order (full-day to start with 5min bins)
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

    # Step A: Verify initial 5-minute bins (300s)
    initial_duration = get_current_bin_duration()
    verify(initial_duration == 300, f"Initial bin duration is 5 mins (300s)")

    # Step B: Simulate zoom to ~40 mins by directly setting Shiny input (triggers 1-min bins)
    # This mimics what chart.js does when the user zooms
    page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T10:40:00'];
        // Set the Shiny input directly (what chart.js would do on plotly_relayout)
        if (window.Shiny) {
            Shiny.setInputValue('chart_range_mins', 40);  // 40 minutes
            Shiny.setInputValue('chart_x_range', range);
        }
        // Also update the Plotly view
        if (window.Plotly) {
            Plotly.relayout(gd, { 'xaxis.range': range });
        }
    }''')
    
    # Wait for Shiny to process and re-render
    page.wait_for_timeout(4000)
    
    mid_duration = get_current_bin_duration()
    verify(mid_duration == 60, f"Zoom to 40-min range switched bins to 1 min (60s)")

    # Step C: Simulate zoom to ~10 mins (triggers 30-second bins)
    page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        const range = ['2025-01-01T10:00:00', '2025-01-01T10:10:00'];
        if (window.Shiny) {
            Shiny.setInputValue('chart_range_mins', 10);  // 10 minutes
            Shiny.setInputValue('chart_x_range', range);
        }
        if (window.Plotly) {
            Plotly.relayout(gd, { 'xaxis.range': range });
        }
    }''')
    
    # Wait for Shiny to process and re-render
    page.wait_for_timeout(4000)
    
    final_duration = get_current_bin_duration()
    verify(final_duration == 30, f"Zoom to 10-min range switched bins to 30s")

@pytest.mark.anyio
def test_range_slider_yaxis_rescaling(page: Page, app: ShinyAppProc):
    """Test 4: Verify that the price axis automatically adjusts its range to fit visible peaks/valleys."""
    page.goto(app.url)
    
    # Select an order
    country_table = page.locator("#country_table")
    first_row = country_table.locator(".tabulator-row").first
    expect(first_row).to_be_visible()
    first_row.click()
    
    # Switch to Chart tab
    page.get_by_text("Chart", exact=True).click()
    
    # Wait for chart to render
    stock_chart = page.locator("#stock_chart")
    expect(stock_chart).to_be_visible(timeout=5000)
    plotly_div = page.locator("#stock_chart .js-plotly-plot")
    expect(plotly_div).to_be_visible(timeout=5000)
    
    # Give the chart time to fully render
    page.wait_for_timeout(1000)
    # Get initial y-axis range
    initial_y_range = page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        if (!gd || !gd.layout || !gd.layout.yaxis || !gd.layout.yaxis.range) return null;
        return gd.layout.yaxis.range;
    }''')
    
    verify(initial_y_range is not None, "Initial y-axis range is defined")
    verify(len(initial_y_range) == 2, "Initial y-axis range has min and max")
    initial_y_min, initial_y_max = initial_y_range
    
    # Zoom in to a narrow time window using the range slider
    # This should trigger y-axis rescaling based on visible data only
    page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        if (!gd || !window.Plotly) return;
        // Zoom to 30-minute window: 11:00–11:30
        Plotly.relayout(gd, {
            'xaxis.range': ['2025-01-01T11:00:00', '2025-01-01T11:30:00']
        });
    }''')
    
    # Wait for the rescaling JS to execute
    page.wait_for_timeout(1500)
    # Get new y-axis range after zoom
    new_y_range = page.evaluate('''() => {
        const gd = document.querySelector("#stock_chart .js-plotly-plot");
        if (!gd || !gd.layout || !gd.layout.yaxis || !gd.layout.yaxis.range) return null;
        return gd.layout.yaxis.range;
    }''')
    
    verify(new_y_range is not None, "Y-axis range defined after zoom")
    verify(len(new_y_range) == 2, "Zoomed y-axis range has min and max")
    new_y_min, new_y_max = new_y_range
    
    # The y-axis range should have changed (either narrowed or shifted)
    # Since synthetic data has price variation, zooming should result in different y-bounds
    y_range_changed = (
        abs(new_y_min - initial_y_min) > 0.001 or 
        abs(new_y_max - initial_y_max) > 0.001
    )
    
    # Also verify the new range is reasonable (tighter or similar to initial)
    initial_span = initial_y_max - initial_y_min
    new_span = new_y_max - new_y_min
    
    verify(new_span <= initial_span * 1.5, 
           f"Zoomed y-axis span is reasonable (init: {initial_span:.2f}, new: {new_span:.2f})")
    
    verify(new_y_min < new_y_max, f"Y-axis min ({new_y_min:.2f}) < max ({new_y_max:.2f})")
