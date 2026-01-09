"""Shiny for Python demo with Tabulator and Plotly widgets."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from shinyswatch.theme import lumen as shiny_theme
from pytabulator import (
    output_tabulator,
    render_tabulator,
)
from shiny import App, render, ui, reactive
from shinywidgets import output_widget, render_widget, render_plotly
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from data_service import DataService
from plotly_order_viz import create_order_viz
import tables
from nl_service import NLService
from databot_service import DatabotService
import dotenv
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

dotenv.load_dotenv()

# Data access layer (Option B)
DATA_SERVICE = DataService.demo()

# Global storage for session-specific data
# Map: session_id -> DataFrame
SESSION_STORE = {}

# Keep LATEST_DF as a simplified fallback for single-user dev
LATEST_DF = None

# Chat greeting message with clickable suggestions
CHAT_GREETING = """
You can use this sidebar to filter and sort orders based on the columns available in the `orders` table. Here are some examples:

1. Filtering: <span class="suggestion">Show only Buy orders for SPY.</span>
2. Sorting: <span class="suggestion">Sort by ExecQty descending.</span>
3. Performance: <span class="suggestion">Show orders with PerfArrival less than 10.</span>
4. Questions: <span class="suggestion">What is the total ExecQty by Strategy?</span>

You can also say <span class="suggestion">Reset</span> to clear filters, or <span class="suggestion">Help</span> for more tips.
"""

app_ui = ui.page_navbar(
    ui.nav_panel(
        "Table",
        ui.layout_sidebar(
            ui.sidebar(
                ui.input_date("start_date", "Start Date", value="2025-01-01"),
                ui.input_date("end_date", "End Date", value="2025-01-15"),
                ui.input_action_button("query_btn", "Query", class_="btn-primary w-100"),
                ui.hr(),
                ui.chat_ui("chat", height="400px", messages=[CHAT_GREETING]),
                width=400,
            ),
            ui.card(
                ui.card_header(ui.output_text("table_header")),
                ui.input_text(
                    "search_orders",
                    None,
                    placeholder="Search orders... (e.g., SPY Buy)",
                    width="100%",
                ).add_class("search-debounce"),
                output_tabulator("orders_table"),
                ui.output_ui("orders_status"),
            ),
        ),
    ),
    ui.nav_panel(
        "Chart",
        ui.layout_columns(
            ui.div(
                ui.card(
                    ui.card_header(
                        ui.div(
                            ui.span("Order Details", class_="text-nowrap"),
                            ui.div(
                                ui.span("All", class_="text-nowrap"),
                                ui.input_switch("show_all_details", "", value=False),
                                class_="ms-auto flex-shrink-0 d-flex align-items-center",
                                style="margin-bottom: 0; gap: 0.5rem;",
                            ),
                            class_="d-flex align-items-center w-100",
                            # Don't force nowrap on the whole container; it can create horizontal overflow.
                            style="gap: 0.5rem; min-width: 0; overflow-x: hidden;",
                        )
                    ),
                    output_tabulator("order_details_table"),
                    class_="card-tight order-details-card",
                    style="flex-shrink: 0;",
                ),
                ui.card(
                    ui.card_header("Fill Details"),
                    output_tabulator("fill_detail_table"),
                    class_="card-tight",
                    style="flex-shrink: 0;",
                ),
                ui.card(
                    ui.card_header("Venues"),
                    output_tabulator("venue_table"),
                    class_="card-tight",
                    style="margin-top: auto; flex-shrink: 0;",
                ),
                style="height: 100%; display: flex; flex-direction: column;",
            ),
            ui.card(
                ui.card_header(ui.output_ui("chart_title")),
                ui.output_ui("chart_metrics"),
                output_widget("order_chart"),
                class_="h-100",
            ),
            col_widths=[2, 10],
        ),
    ),
    ui.nav_panel(
        "Databot",
        ui.layout_sidebar(
            ui.sidebar(
                ui.chat_ui("databot_chat", height="600px"),
                width=400,
                title="Databot Chat"
            ),
            ui.card(
                ui.card_header("Analysis Result"),
                ui.output_ui("databot_display"),
                class_="h-100"
            ),
        ),
    ),
    title="Order Visualizer",
    header=ui.TagList(
        ui.include_css("www/styles.css"), # shiny include_css reads file content and inlines it, so ?v=2 doesn't work here. 
        # Wait, ui.include_css INLINES the css. It doesn't link it.
        # So browser cache for the file doesn't matter, only the app reload matters.
        # The CSS is refreshed if the app reloads.
        
        ui.include_js("www/chart.js"),
        ui.tags.script(src="https://cdn.plot.ly/plotly-3.3.0.min.js"),
        ui.output_ui("theme_tabulator_css"),
        ui.div(
            ui.input_dark_mode(id="dark_mode", mode="light"),
            style="position: absolute; top: 10px; right: 20px; z-index: 1000;",
        ),
    ),
    theme=shiny_theme,
    fillable=True,
)


def server(input, output, session):
    # Print session ID for manual API testing
    print(f"\n--- User connected. Session ID: {session.id} ---\n")
    
    # Session-level cache for volume data to speed up bin size changes
    # Key: (date, ticker, bin_size) → Value: DataFrame
    volume_data_cache = {}
    
    # Create a caching wrapper for the data service
    class CachedDataService:
        """Wrapper around DATA_SERVICE that caches volume data."""
        
        def get_volume_data(self, date, ticker, exch_open_time, exch_close_time, interval):
            """Get volume data with caching to speed up bin size changes."""
            cache_key = (date, ticker, interval)
            
            if cache_key in volume_data_cache:
                logger.info(f"📦 Volume cache HIT: {ticker} {date} {interval}")
                return volume_data_cache[cache_key]
            
            logger.info(f"⏳ Volume cache MISS: {ticker} {date} {interval} - fetching...")
            import time
            fetch_start = time.time()
            
            volume_data = DATA_SERVICE.get_volume_data(
                date, ticker, exch_open_time, exch_close_time, interval=interval
            )
            
            fetch_elapsed = (time.time() - fetch_start) * 1000
            logger.info(f"✅ Volume data fetched in {fetch_elapsed:.1f}ms, caching for future use")
            
            volume_data_cache[cache_key] = volume_data
            return volume_data
        
        def __getattr__(self, name):
            """Pass through all other methods to the underlying DATA_SERVICE."""
            return getattr(DATA_SERVICE, name)
    
    cached_data_service = CachedDataService()
    
    # Store the user's zoom range when switching bins (non-reactive for tracking)
    _last_bin_size = {"value": "5min"}
    
    # Track last chart state to detect when only bin_size changed (for efficient updates)
    _last_chart_state = {"order_key": None, "is_dark": None, "bin_size": None}
    
    # Reactive values: base data from date query, and SQL filter to apply
    base_orders_df = reactive.Value(pd.DataFrame())
    current_title = reactive.Value("Order Table")
    current_sql = reactive.Value("")
    
    @reactive.Effect
    def _sync_global_df():
        global LATEST_DF
        df = base_orders_df.get()
        if not df.empty:
             LATEST_DF = df
             # Sync to session-specific store
             SESSION_STORE[session.id] = df
             
    # Cleanup on session end
    session.on_ended(lambda: SESSION_STORE.pop(session.id, None))
    
    # Computed filtered data - applies SQL to base data (like sidebot pattern)
    @reactive.calc
    def orders_df():
        base_df = base_orders_df()
        sql_query = current_sql()
        
        if base_df.empty:
            return pd.DataFrame()
        
        if not sql_query:
            # No filter, return all base data
            return base_df
        
        # Apply SQL filter to base data
        return DATA_SERVICE.query_sql(sql_query, base_df)
    
    # Initialize NL Service
    nl_service = NLService(DATA_SERVICE.base_orders)
    
    chat = ui.Chat("chat")

    @chat.on_user_submit
    async def perform_chat(user_input: str):
        if not user_input:
            return
            
        await nl_service.perform_chat(user_input, chat)

    async def update_filter(query: str, title: str):
        """Update the SQL filter - called from tool with reactive lock."""
        async with reactive.lock():
            current_sql.set(query)
            current_title.set(title or "Order Table")
            await reactive.flush()

    async def update_dashboard(query: str, title: str):
        """Tool callback: just updates the filter, doesn't read reactive values."""
        # Validate query by attempting to execute it (like sidebot does)
        if query:
            await query_db(query)
        await update_filter(query, title)

    async def query_db(query: str):
        """Tool callback: executes SQL against base data.
        
        Note: We can't read reactive values here, so we execute against
        the full base orders from DATA_SERVICE. The query_sql method
        will use its internal cache or default data.
        """
        # Execute against the base orders from the service
        # This is safe because DATA_SERVICE.base_orders is not reactive
        return DATA_SERVICE.query_sql(query).to_json(orient="records")

    nl_service.register_tools(update_dashboard, query_db)

    @render.text
    def table_header():
        return current_title()

    @reactive.Effect
    def _fetch_data():
        # Fetch data on button click
        _ = input.query_btn()  # Dependency
        
        # Isolate inputs to avoid updating on date change without button press
        with reactive.isolate():
            start = input.start_date()
            end = input.end_date()
        
        if not start or not end:
            return

        # Convert to string if necessary, though input_date returns date object
        start_str = str(start)
        end_str = str(end)
        
        # Load base data and reset any SQL filter
        df = DATA_SERVICE.query_orders(start_str, end_str)
        base_orders_df.set(df)
        current_sql.set("")
        current_title.set("Order Table")
        
    @reactive.calc
    def volume_bin_size():
        range_mins = None
        if "chart_state" in input:
            state = input.chart_state()
            if state and isinstance(state, dict):
                range_mins = state.get("rangeMins")
        
        if range_mins is None:
            # Initial state: check the duration of the selected order
            row = input.orders_table_row_clicked()
            if not row:
                     # No selection, default to 5min
                     return "5min"
            
            st_str = row.get('StartTime') or row.get('ExchOpenTime', "09:30")
            et_str = row.get('EndTime') or row['ExchCloseTime']
            try:
                st_parts = st_str.split(":")
                et_parts = et_str.split(":")
                duration = (int(et_parts[0])*60 + int(et_parts[1])) - (int(st_parts[0])*60 + int(st_parts[1]))
                range_mins = duration
            except (ValueError, AttributeError, IndexError):
                range_mins = 999

        if range_mins > 160: res = "5min"
        elif range_mins > 80: res = "2min"
        elif range_mins >= 40: res = "1min"
        else: res = "30s"
        
        return res

    @reactive.effect
    def _handle_chart_button():
        """Handle button clicks from chart.js - compute range server-side and update atomically."""
        if "chart_button" not in input:
            return
        
        btn = input.chart_button()
        if not btn or not isinstance(btn, dict):
            return
        
        action = btn.get("action")
        if not action:
            return
        
        logger.info(f"[chart_button] Received button action: {action}, btn={btn}")
        
        # Get current order data
        data = current_order_enriched()
        if not data:
            logger.warning("[chart_button] No order data available")
            return
        
        widget = order_chart.widget
        if widget is None:
            logger.warning("[chart_button] Widget is None")
            return
        
        order_detail = data["order"]
        date = order_detail.get("Date", "").replace(".", "-")
        orderid = order_detail.get("orderid", "")
        ticker = order_detail["Ticker"]
        start_time_str = order_detail["StartTime"]
        end_time_str = order_detail["EndTime"]
        exch_open_time = order_detail["ExchOpenTime"]
        exch_close_time = order_detail["ExchCloseTime"]
        
        current_order_key = f"{date}:{orderid}"
        btn_order_key = btn.get("orderKey")
        
        # Verify button is for current order
        if btn_order_key != current_order_key:
            logger.info(f"[chart_button] Order key mismatch: {btn_order_key} vs {current_order_key}")
            return
        
        # Parse times to minutes
        def parse_time_mins(t_str):
            parts = t_str.split(":")
            return int(parts[0]) * 60 + int(parts[1])
        
        st_mins = parse_time_mins(start_time_str)
        et_mins = parse_time_mins(end_time_str)
        eo_mins = parse_time_mins(exch_open_time)
        ec_mins = parse_time_mins(exch_close_time)
        
        # Get current bin size from widget metadata
        current_bin_size = widget.layout.meta.get("binSize", "5min") if widget.layout.meta else "5min"
        current_bin_seconds = {"5min": 300, "2min": 120, "1min": 60, "30s": 30}.get(current_bin_size, 300)
        
        # Helper to calculate default range for a given bin size
        def calc_default_range(bin_secs):
            duration = et_mins - st_mins
            padding_mins = 30 if duration > 120 else (10 if duration > 20 else 5)
            start_secs = max((eo_mins * 60) - bin_secs, (st_mins - padding_mins) * 60)
            end_secs = min((et_mins + padding_mins) * 60, (ec_mins * 60) + bin_secs)
            return start_secs, end_secs
        
        # Calculate initial default range with current bin size
        default_start_secs, default_end_secs = calc_default_range(current_bin_seconds)
        
        def secs_to_iso(secs):
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            return f"{date}T{h:02d}:{m:02d}:{s:02d}"
        
        default_x_range = [secs_to_iso(default_start_secs), secs_to_iso(default_end_secs)]
        
        # Get durationData from widget metadata
        duration_data = widget.layout.meta.get("durationData", {}) if widget.layout.meta else {}
        
        # Compute target range based on action
        anchor = btn.get("anchor", "first")
        selected_duration = btn.get("duration")
        mins = btn.get("mins")
        
        target_range = None
        
        # Helper to convert ISO string to epoch milliseconds
        def to_epoch_ms(iso_str):
            from datetime import datetime
            dt = datetime.fromisoformat(iso_str.replace(" ", "T"))
            return dt.timestamp() * 1000
        
        if action == "anchor":
            # Anchor button - if duration was selected, apply it from new anchor
            if selected_duration:
                dur_data = duration_data.get(str(selected_duration), {})
                if dur_data:
                    eff_start = dur_data.get("effStart")
                    eff_end = dur_data.get("effEnd")
                    if anchor == "last" and eff_end:
                        # Apply duration backward from effective end
                        eff_end_secs = parse_time_mins(eff_end.split("T")[1]) * 60
                        target_start_secs = eff_end_secs - selected_duration * 60
                        target_range = [secs_to_iso(target_start_secs), eff_end]
                    elif eff_start:
                        # Apply duration forward from effective start
                        eff_start_secs = parse_time_mins(eff_start.split("T")[1]) * 60
                        target_end_secs = eff_start_secs + selected_duration * 60
                        target_range = [eff_start, secs_to_iso(target_end_secs)]
            
            if not target_range:
                logger.info("[chart_button] Anchor click with no duration - no range change")
                return
                
        elif action == "duration":
            # Duration button - apply from current anchor
            if mins is None:
                logger.warning("[chart_button] Duration action without mins")
                return
            
            dur_data = duration_data.get(str(mins), {})
            if not dur_data:
                logger.warning(f"[chart_button] No durationData for {mins}")
                return
            
            eff_start = dur_data.get("effStart")
            eff_end = dur_data.get("effEnd")
            
            if anchor == "last" and eff_end:
                eff_end_secs = parse_time_mins(eff_end.split("T")[1]) * 60
                target_start_secs = eff_end_secs - mins * 60
                target_range = [secs_to_iso(target_start_secs), eff_end]
            elif eff_start:
                eff_start_secs = parse_time_mins(eff_start.split("T")[1]) * 60
                target_end_secs = eff_start_secs + mins * 60
                target_range = [eff_start, secs_to_iso(target_end_secs)]
                
        elif action == "all":
            # For "all", use default range - but need to determine bin size first
            # Use a temporary range to calculate bin size
            temp_range = default_x_range
            temp_t_start = to_epoch_ms(temp_range[0])
            temp_t_end = to_epoch_ms(temp_range[1])
            temp_range_mins = (temp_t_end - temp_t_start) / 60000
            
            # Determine bin size for the full range
            if temp_range_mins > 160: 
                all_bin_size = "5min"
                all_bin_secs = 300
            elif temp_range_mins > 80: 
                all_bin_size = "2min"
                all_bin_secs = 120
            elif temp_range_mins >= 40: 
                all_bin_size = "1min"
                all_bin_secs = 60
            else: 
                all_bin_size = "30s"
                all_bin_secs = 30
            
            # Recalculate default range with the correct bin size for "all" view
            all_start_secs, all_end_secs = calc_default_range(all_bin_secs)
            target_range = [secs_to_iso(all_start_secs), secs_to_iso(all_end_secs)]
            logger.info(f"[chart_button] All button: recalculated range with bin_size={all_bin_size}")
        
        if not target_range:
            logger.warning(f"[chart_button] Could not compute target_range for action={action}")
            return
        
        logger.info(f"[chart_button] Computed target_range: {target_range}")
        
        # Determine if bin size change is needed
        
        t_start = to_epoch_ms(target_range[0])
        t_end = to_epoch_ms(target_range[1])
        range_mins = (t_end - t_start) / 60000
        
        def get_bin_size_for_range(range_mins):
            if range_mins > 160: return "5min"
            if range_mins > 80: return "2min"
            if range_mins >= 40: return "1min"
            return "30s"
        
        new_bin_size = get_bin_size_for_range(range_mins)
        
        logger.info(f"[chart_button] range_mins={range_mins:.1f}, current_bin={current_bin_size}, new_bin={new_bin_size}")
        
        # Compute Y-axis range for the target x-range
        cached_data_service = DATA_SERVICE
        prices = cached_data_service.get_prices(date, ticker, exch_open_time, exch_close_time)
        executions = cached_data_service.get_executions(date, orderid)
        
        view_start_dt = pd.to_datetime(target_range[0])
        view_end_dt = pd.to_datetime(target_range[1])
        
        stock_view = prices[(prices["Time"] >= view_start_dt) & (prices["Time"] <= view_end_dt)]
        exec_view = executions[(executions["Time"] >= view_start_dt) & (executions["Time"] <= view_end_dt)]
        
        min_p = np.inf
        max_p = -np.inf
        has_data = False
        
        if not stock_view.empty:
            min_p = min(min_p, float(stock_view["Bid"].min()))
            max_p = max(max_p, float(stock_view["Ask"].max()))
            has_data = True
        
        if not exec_view.empty:
            min_p = min(min_p, float(exec_view["Price"].min()))
            max_p = max(max_p, float(exec_view["Price"].max()))
            has_data = True
        
        y_range = None
        if has_data and np.isfinite(min_p) and np.isfinite(max_p):
            rng = max_p - min_p
            pad = max(rng * 0.10, 0.25)
            y_range = [min_p - pad, max_p + pad]
        
        logger.info(f"[chart_button] Computed y_range: {y_range}")
        
        if new_bin_size != current_bin_size:
            # Bin size change needed - efficiently update only volume traces
            logger.info(f"[chart_button] 🚀 Efficient bin size change: {current_bin_size} -> {new_bin_size}")
            
            is_dark = input.dark_mode() == "dark"
            theme_colors = {
                "primary": shiny_theme.colors.primary,
                "secondary": shiny_theme.colors.secondary,
                "body_color": shiny_theme.colors.body_color,
                "warning": shiny_theme.colors.warning,
                "danger": shiny_theme.colors.danger,
            }
            
            # Generate new figure to get updated volume traces with new bins
            fig = create_order_viz(
                data_service=cached_data_service,
                date=date,
                ticker=ticker,
                orderid=orderid,
                start_time_str=start_time_str,
                end_time_str=end_time_str,
                bin_size=new_bin_size,
                is_dark=is_dark,
                theme_colors=theme_colors,
                x_range=target_range,
                default_x_range=default_x_range,
                exch_open_time=exch_open_time,
                exch_close_time=exch_close_time,
            )
            
            # EFFICIENT UPDATE: Only replace volume traces (same as _update_order_chart)
            volume_trace_names = {"Lit Volume", "Dark Volume", "PRate"}
            
            with widget.batch_update():
                # Remove old volume traces (in reverse order to preserve indices)
                indices_to_remove = []
                for i, trace in enumerate(widget.data):
                    if hasattr(trace, 'name') and trace.name in volume_trace_names:
                        indices_to_remove.append(i)
                
                for i in reversed(indices_to_remove):
                    widget.data = list(widget.data[:i]) + list(widget.data[i+1:])
                
                logger.info(f"[chart_button] Removed {len(indices_to_remove)} old volume traces")
                
                # Add new volume traces from the figure
                new_volume_traces = []
                for trace in fig.data:
                    if hasattr(trace, 'name') and trace.name in volume_trace_names:
                        new_volume_traces.append(trace)
                        widget.add_trace(trace)
                
                logger.info(f"[chart_button] Added {len(new_volume_traces)} new volume traces")
                
                # Update axis ranges atomically with volume traces
                widget.layout.xaxis.range = target_range
                widget.layout.xaxis2.range = target_range
                widget.layout.xaxis3.range = target_range
                if y_range:
                    widget.layout.yaxis.range = y_range
                    widget.layout.yaxis.autorange = False
                
                # Update metadata (contains binSize info)
                if hasattr(fig.layout, 'meta'):
                    widget.layout.meta = fig.layout.meta
            
            # Update last state
            _last_chart_state["bin_size"] = new_bin_size
            
            logger.info(f"[chart_button] Efficient volume+range update completed")
        else:
            # Same bin size - just update x-range and y-range
            logger.info(f"[chart_button] Same bin size, updating ranges only")
            
            with widget.batch_update():
                widget.layout.xaxis.range = target_range
                widget.layout.xaxis2.range = target_range
                widget.layout.xaxis3.range = target_range
                if y_range:
                    widget.layout.yaxis.range = y_range
                    widget.layout.yaxis.autorange = False
            
            logger.info(f"[chart_button] Range-only update completed")

    @reactive.calc
    def current_order_enriched():
        row = input.orders_table_row_clicked()
        if not row:
            return None
        
        raw_date = str(row.get("Date"))
        date = raw_date.replace(".", "-")
        order_id = str(row.get("orderid", ""))
        
        # This will only be called when consumers (Charts/Metrics) are active
        return DATA_SERVICE.get_order_enriched(date, order_id)

    @render.ui
    def chart_title():
        data = current_order_enriched()
        if not data:
             return ui.div("No Order Selected", class_="text-muted")
        
        # Use enriched order details
        order_detail = data["order"]
        # Basic fields from there or row? row matches order_detail largely but detail is fresher?
        # Let's use order_detail as source of truth along with row fallback
        
        date = tables.format_display_date(order_detail.get("Date"))
        order_id = order_detail.get("orderid", "")
        trader_id = order_detail.get("TraderID", "")
        side = order_detail.get("Side", "")
        ticker = order_detail.get("Ticker", "SPY")
        country = order_detail.get("Country", "")
        exec_qty = order_detail.get("ExecQty", 0)
        avg_price_raw = order_detail.get("AvgPrice", None)
        strategy = order_detail.get("Strategy", "")
        start_time = order_detail.get("StartTime", "")
        end_time = order_detail.get("EndTime", "")
        desk = order_detail.get("Desk", "")

        try:
            avg_price = float(avg_price_raw)
        except (TypeError, ValueError):
            avg_price = float("nan")

        avg_price_str = f"{avg_price:.3f}" if pd.notna(avg_price) else ""

        return ui.div(
            ui.span(f"{date}", class_="me-2"),
            ui.span(f"{order_id}", class_="me-2 text-muted"),
            ui.span(f"{side}", class_="me-2"),
            ui.span(f"{ticker}", class_="me-2"),
            ui.span(f"{country}", class_="me-2"),
            ui.span(f"{int(exec_qty):,}{(' @' + avg_price_str) if avg_price_str else ''}", class_="me-2"),
            ui.span(f"{strategy}", class_="me-2"),
            ui.span(f"{start_time} - {end_time}", class_="me-2"),
            ui.span(f"{trader_id}", class_="text-muted me-2"),
            ui.span(f"{desk}", class_="text-muted"),
            class_="fw-semibold",
        )

    @render.ui
    def chart_metrics():
        data = current_order_enriched()
        if not data:
             return ui.div()
             
        order_detail = data["order"]
        # spread capture is computed in enriched object
        spread_capture_pct = float(order_detail.get("SpreadCapture", float("nan")))

        return ui.div(
            tables.create_perf_chip("Return", float(order_detail.get("Return", 0.0)), is_percentage=True),
            tables.create_perf_chip("PerfArrival", float(order_detail.get("PerfArrival", 0.0))),
            tables.create_perf_chip("PerfVWAP", float(order_detail.get("PerfVWAP", 0.0))),
            tables.create_perf_chip("PerfClose", float(order_detail.get("PerfClose", 0.0))),
            tables.create_perf_chip("SpreadCapture", spread_capture_pct, is_percentage=True, percentage_decimals=1),
            class_="d-flex gap-2 justify-content-start px-2 py-1",
        )

    @render.ui
    def theme_tabulator_css():
        """Generate dynamic CSS for tabulator based on current theme colors."""
        return tables.get_theme_tabulator_css(shiny_theme)

    # Reactive value to track order counts for status display
    orders_counts = reactive.Value({"total": 0, "matching": 0, "displayed": 0})
    
    MAX_DISPLAY_ROWS = 500

    @render_tabulator
    def orders_table():
        df = orders_df()
        total_count = len(df)
        
        # We no longer compute Notional here as it requires AvgPrice which is expensive
        # if not df.empty and "ExecQty" in df.columns and "AvgPrice" in df.columns:
        #    df = df.copy()
        #    df["Notional"] = (df["ExecQty"] * df["AvgPrice"]).astype(int)
        
        # Apply search filter
        search_text = input.search_orders() or ""
        if search_text.strip() and not df.empty:
            tokens = search_text.lower().split()
            
            # Text columns: substring match anywhere
            text_cols = ["orderid", "Date", "Country", "Side", "Ticker", "Strategy", 
                        "StartTime", "EndTime"]
            # Numeric columns: prefix (startswith) match, ignore commas
            numeric_cols = ["OrderQty", "ExecQty"]
            
            # Only use columns that exist in the dataframe
            text_cols = [c for c in text_cols if c in df.columns]
            numeric_cols = [c for c in numeric_cols if c in df.columns]
            
            def row_matches(row):
                # Build text from text columns (substring match)
                # Strip - and . for date-friendly matching
                text_values = " ".join(str(row[c]).lower() for c in text_cols)
                text_values_normalized = text_values.replace("-", "").replace(".", "")
                
                # Build numeric strings without commas for prefix match
                numeric_strs = [str(int(row[c])).lower() if pd.notna(row[c]) else "" 
                               for c in numeric_cols]
                
                # Each token must match somewhere
                for token in tokens:
                    # Clean token: remove commas, dashes, dots for flexible matching
                    token_clean = token.replace(",", "").replace("-", "").replace(".", "")
                    
                    # Check text columns (substring match) - try both normalized and original
                    if token_clean in text_values_normalized or token_clean in text_values:
                        continue
                    
                    # Check numeric columns (prefix match - startswith)
                    if any(num_str.startswith(token_clean) for num_str in numeric_strs):
                        continue
                    
                    # Token didn't match anywhere
                    return False
                
                return True
            
            mask = df.apply(row_matches, axis=1)
            df = df[mask]
        
        matching_count = len(df)
        
        # Limit to MAX_DISPLAY_ROWS
        if len(df) > MAX_DISPLAY_ROWS:
            df = df.head(MAX_DISPLAY_ROWS)
        
        displayed_count = len(df)
        
        # Update counts for status display
        orders_counts.set({"total": total_count, "matching": matching_count, "displayed": displayed_count})
        
        return tables.get_orders_table(df)
    
    @render.ui
    def orders_status():
        counts = orders_counts.get()
        total = counts["total"]
        matching = counts["matching"]
        displayed = counts["displayed"]
        
        if total == 0:
            return ui.div()
        
        # Build status message
        if displayed < matching:
            status_text = f"Displaying first {displayed:,} out of {matching:,} orders matching out of total {total:,} orders"
        elif matching < total:
            status_text = f"Displaying {displayed:,} orders matching out of total {total:,} orders"
        else:
            status_text = f"Displaying all {total:,} orders"
        
        return ui.div(
            status_text,
            class_="text-muted small mt-2",
            style="text-align: right; padding-right: 0.5rem;",
        )

    @render_tabulator
    def order_details_table():
        data = current_order_enriched()
        return tables.get_order_details_table(input, data, DATA_SERVICE)

    @render_tabulator
    def fill_detail_table():
        data = current_order_enriched()
        return tables.get_fill_detail_table(input, data, DATA_SERVICE)

    @render_tabulator
    def venue_table():
        data = current_order_enriched()
        return tables.get_venue_table(input, data, DATA_SERVICE)


    @render_plotly
    def order_chart():
        """Create initial FigureWidget - will be updated by reactive effect."""
        logger.info("Creating initial order chart FigureWidget")
        fig = go.FigureWidget()
        fig.update_layout(
            height=600,
            annotations=[dict(
                text="No Order Selected",
                showarrow=False,
                xref="paper", yref="paper",
                x=0.5, y=0.5,
                font=dict(size=20, color="gray")
            )]
        )
        logger.info(f"Initial FigureWidget created: id={id(fig)}")
        return fig
    
    @reactive.effect
    def _update_order_chart():
        """Update the existing FigureWidget when inputs change."""
        import time
        start_time = time.time()
        logger.info("_update_order_chart effect triggered")
        
        widget = order_chart.widget
        if widget is None:
            logger.warning("Widget is None, skipping update")
            return
        
        logger.info(f"Widget retrieved: id={id(widget)}, traces={len(widget.data)} (elapsed: {(time.time()-start_time)*1000:.1f}ms)")
        
        is_dark = input.dark_mode() == "dark"
        data = current_order_enriched()
        bin_size = volume_bin_size()
        
        logger.info(f"Chart inputs: is_dark={is_dark}, bin_size={bin_size}, has_data={data is not None} (elapsed: {(time.time()-start_time)*1000:.1f}ms)")
        
        if not data:
            logger.info("No data available, showing placeholder")
            # Clear chart and show placeholder
            with widget.batch_update():
                widget.data = []
                widget.layout.annotations = [dict(
                    text="No Order Selected",
                    showarrow=False,
                    xref="paper", yref="paper",
                    x=0.5, y=0.5,
                    font=dict(size=20, color="gray")
                )]
                widget.layout.height = 600
            logger.info("Placeholder update completed")
            return
        
        # Extract order parameters
        order_detail = data["order"]
        date = order_detail.get("Date", "").replace(".", "-")
        orderid = order_detail.get("orderid", "")
        ticker = order_detail["Ticker"]
        start_time_str = order_detail["StartTime"]
        end_time_str = order_detail["EndTime"]
        exch_open_time = order_detail["ExchOpenTime"]
        exch_close_time = order_detail["ExchCloseTime"]
        
        logger.info(f"Order: {ticker} {orderid} on {date}, {start_time_str}-{end_time_str} (elapsed: {(time.time()-start_time)*1000:.1f}ms)")

        # Calculate view range (isolated to avoid triggering on every pan/zoom)
        with reactive.isolate():
            state = input.chart_state() if "chart_state" in input else None
            
        st_parts = start_time_str.split(":")
        et_parts = end_time_str.split(":")
        st_minutes = int(st_parts[0]) * 60 + int(st_parts[1])
        et_minutes = int(et_parts[0]) * 60 + int(et_parts[1])
        duration = et_minutes - st_minutes

        padding_mins = 30 if duration > 120 else (10 if duration > 20 else 5)
        
        eo_parts = exch_open_time.split(":")
        ec_parts = exch_close_time.split(":")
        exch_open_mins = int(eo_parts[0]) * 60 + int(eo_parts[1])
        exch_close_mins = int(ec_parts[0]) * 60 + int(ec_parts[1])

        bin_seconds = {"5min": 300, "2min": 120, "1min": 60, "30s": 30}.get(bin_size, 300)
        
        view_start_secs = max((exch_open_mins * 60) - bin_seconds, (st_minutes - padding_mins) * 60)
        view_end_secs = min((et_minutes + padding_mins) * 60, (exch_close_mins * 60) + bin_seconds)

        view_start_h, view_start_rem = divmod(view_start_secs, 3600)
        view_start_m, view_start_s = divmod(view_start_rem, 60)
        view_end_h, view_end_rem = divmod(view_end_secs, 3600)
        view_end_m, view_end_s = divmod(view_end_rem, 60)
        
        default_x_range = [
            f"{date}T{view_start_h:02d}:{view_start_m:02d}:{view_start_s:02d}",
            f"{date}T{view_end_h:02d}:{view_end_m:02d}:{view_end_s:02d}",
        ]

        current_order_key = f"{date}:{orderid}"
        x_range = default_x_range
        
        if state and isinstance(state, dict):
            saved_range = state.get("xRange")
            saved_key = state.get("orderKey")
            if saved_range and len(saved_range) == 2 and saved_key == current_order_key:
                x_range = saved_range
                logger.info(f"Using saved x_range from state")

        # Generate the figure
        theme_colors = {
            "primary": shiny_theme.colors.primary,
            "secondary": shiny_theme.colors.secondary,
            "body_color": shiny_theme.colors.body_color,
            "warning": shiny_theme.colors.warning,
            "danger": shiny_theme.colors.danger,
        }

        logger.info(f"Creating new chart figure with bin_size={bin_size} (elapsed: {(time.time()-start_time)*1000:.1f}ms)")
        fig_start = time.time()
        fig = create_order_viz(
            data_service=cached_data_service,
            date=date,
            ticker=ticker,
            orderid=orderid,
            start_time_str=start_time_str,
            end_time_str=end_time_str,
            bin_size=bin_size,
            is_dark=is_dark,
            theme_colors=theme_colors,
            x_range=[str(x_range[0]), str(x_range[1])],
            default_x_range=[str(default_x_range[0]), str(default_x_range[1])],
            exch_open_time=exch_open_time,
            exch_close_time=exch_close_time,
        )
        fig_elapsed = (time.time() - fig_start) * 1000
        logger.info(f"Figure created in {fig_elapsed:.1f}ms: {len(fig.data)} traces, {len(fig.layout.annotations or [])} annotations (total elapsed: {(time.time()-start_time)*1000:.1f}ms)")

        # Check if we can do an efficient update (only bin_size changed)
        prev_order_key = _last_chart_state["order_key"]
        prev_is_dark = _last_chart_state["is_dark"]
        prev_bin_size = _last_chart_state["bin_size"]
        
        # Determine if only bin_size changed (same order, same theme)
        bin_size_only_changed = (
            prev_order_key == current_order_key and
            prev_is_dark == is_dark and
            prev_bin_size is not None and
            prev_bin_size != bin_size and
            len(widget.data) > 0  # Widget must have existing traces
        )
        
        # Update tracking state
        _last_chart_state["order_key"] = current_order_key
        _last_chart_state["is_dark"] = is_dark
        _last_chart_state["bin_size"] = bin_size

        # Update the widget in-place with batch_update for efficiency
        batch_start = time.time()
        
        if bin_size_only_changed:
            # EFFICIENT UPDATE: Only replace volume traces (Lit Volume, Dark Volume, PRate)
            # These are the only traces affected by bin_size changes
            logger.info(f"🚀 Efficient update: only bin_size changed ({prev_bin_size} -> {bin_size})")
            
            # Volume trace names that need to be replaced
            volume_trace_names = {"Lit Volume", "Dark Volume", "PRate"}
            
            with widget.batch_update():
                # Find indices of volume traces to remove (iterate in reverse to preserve indices)
                indices_to_remove = []
                for i, trace in enumerate(widget.data):
                    if hasattr(trace, 'name') and trace.name in volume_trace_names:
                        indices_to_remove.append(i)
                
                # Remove old volume traces (in reverse order to maintain indices)
                for i in reversed(indices_to_remove):
                    widget.data = list(widget.data[:i]) + list(widget.data[i+1:])
                
                logger.info(f"Removed {len(indices_to_remove)} old volume traces")
                
                # Add new volume traces from the figure
                new_volume_traces = []
                for trace in fig.data:
                    if hasattr(trace, 'name') and trace.name in volume_trace_names:
                        new_volume_traces.append(trace)
                        widget.add_trace(trace)
                
                logger.info(f"Added {len(new_volume_traces)} new volume traces")
                
                # Update xaxis ranges to match new bin alignment
                if hasattr(fig.layout, 'xaxis') and hasattr(fig.layout.xaxis, 'range'):
                    widget.layout.xaxis.range = fig.layout.xaxis.range
                if hasattr(fig.layout, 'xaxis2') and hasattr(fig.layout.xaxis2, 'range'):
                    widget.layout.xaxis2.range = fig.layout.xaxis2.range
                if hasattr(fig.layout, 'xaxis3') and hasattr(fig.layout.xaxis3, 'range'):
                    widget.layout.xaxis3.range = fig.layout.xaxis3.range

                # Apply y-axis range computed server-side for the current x-range.
                # Without this, initial load (and some server-driven updates) can rely on
                # client-side relayout to trigger scaling.
                if hasattr(fig.layout, 'yaxis') and hasattr(fig.layout.yaxis, 'range') and fig.layout.yaxis.range:
                    logger.info(f"Applying yaxis.range from Python (bin update): {fig.layout.yaxis.range}")
                    widget.layout.yaxis.range = fig.layout.yaxis.range
                    widget.layout.yaxis.autorange = False
                    
                # Update metadata (contains binSize info)
                if hasattr(fig.layout, 'meta'):
                    widget.layout.meta = fig.layout.meta
        else:
            # FULL UPDATE: Replace all traces (order changed, theme changed, or initial load)
            logger.info("Starting batch_update to replace ALL widget content")
            with widget.batch_update():
                # Clear existing traces
                widget.data = []
                
                # Add new traces from the figure
                for trace in fig.data:
                    widget.add_trace(trace)
                
                # Update layout properties (can't replace entire layout object)
                # Update all layout properties from the new figure
                for key in fig.layout:
                    try:
                        setattr(widget.layout, key, fig.layout[key])
                    except (AttributeError, ValueError) as e:
                        # Some properties might be read-only or incompatible
                        logger.debug(f"Skipping layout property {key}: {e}")
                        pass
                
                # Explicitly set xaxis ranges to ensure they're applied atomically with new bins
                # This prevents showing intermediate state with old range and new bins
                if hasattr(fig.layout, 'xaxis') and hasattr(fig.layout.xaxis, 'range'):
                    widget.layout.xaxis.range = fig.layout.xaxis.range
                    logger.info(f"Applied xaxis.range: {fig.layout.xaxis.range}")
                if hasattr(fig.layout, 'xaxis2') and hasattr(fig.layout.xaxis2, 'range'):
                    widget.layout.xaxis2.range = fig.layout.xaxis2.range
                if hasattr(fig.layout, 'xaxis3') and hasattr(fig.layout.xaxis3, 'range'):
                    widget.layout.xaxis3.range = fig.layout.xaxis3.range

                # Explicitly apply y-axis range (computed in create_order_viz from the initial x-range).
                if hasattr(fig.layout, 'yaxis') and hasattr(fig.layout.yaxis, 'range') and fig.layout.yaxis.range:
                    logger.info(f"Applying yaxis.range from Python: {fig.layout.yaxis.range}")
                    widget.layout.yaxis.range = fig.layout.yaxis.range
                    widget.layout.yaxis.autorange = False
                else:
                    logger.warning(f"No yaxis.range in fig.layout! yaxis exists: {hasattr(fig.layout, 'yaxis')}, has range: {hasattr(fig.layout.yaxis, 'range') if hasattr(fig.layout, 'yaxis') else False}, value: {fig.layout.yaxis.range if hasattr(fig.layout, 'yaxis') and hasattr(fig.layout.yaxis, 'range') else None}")
        
        batch_elapsed = (time.time() - batch_start) * 1000
        total_elapsed = (time.time() - start_time) * 1000
        update_type = "EFFICIENT (volume only)" if bin_size_only_changed else "FULL"
        logger.info(f"batch_update ({update_type}) completed in {batch_elapsed:.1f}ms: widget now has {len(widget.data)} traces (TOTAL: {total_elapsed:.1f}ms)")





    # --- Databot Logic ---
    
    # Reactive value to hold the generated plot
    databot_fig = reactive.Value(None)
    
    # Initialize Databot Service with session ID
    databot_service = DatabotService(DATA_SERVICE, session_id=session.id)
    
    # Callback to update the plot from the tool
    async def update_databot_plot(fig):
        async with reactive.lock():
            databot_fig.set(fig)
            await reactive.flush()
        
    databot_service.register_plot_callback(update_databot_plot)
    
    @reactive.Effect
    async def _register_databot_tools():
        await databot_service.register_tools()
    
    databot_chat = ui.Chat("databot_chat")
    
    @databot_chat.on_user_submit
    async def perform_databot_chat(user_input: str):
        if not user_input:
            return
        await databot_service.perform_chat(user_input, databot_chat)

    @render.ui
    def databot_display():
        val = databot_fig()
        if isinstance(val, str):
            return ui.HTML(val)
        return val  # Should be a widget or None



app_shiny = App(app_ui, server)


async def orders_api(request):
    """API endpoint to get orders data as JSON."""
    session_id = request.query_params.get("session_id")
    
    # 1. Try session-specific data
    if session_id and session_id in SESSION_STORE:
        df = SESSION_STORE[session_id]
        return Response(df.to_json(orient="records", date_format="iso"), media_type="application/json")

    # 2. Fallback to latest global (single-user dev mode)
    if LATEST_DF is not None and not LATEST_DF.empty:
         return Response(LATEST_DF.to_json(orient="records", date_format="iso"), media_type="application/json")
         
    # 3. Fallback to base templates
    json_str = DATA_SERVICE.base_orders.write_json()
    return Response(content=json_str, media_type="application/json")

routes = [
    Route('/orders', orders_api),
    Mount('/', app=app_shiny),
]

app = Starlette(routes=routes)
