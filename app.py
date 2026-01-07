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
from shinywidgets import output_widget, render_widget
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
    
    # Store the user's zoom range when switching bins (non-reactive for tracking)
    _last_bin_size = {"value": "5min"}
    
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
        if "chart_range_mins" not in input:
            range_mins = None
        else:
            range_mins = input.chart_range_mins()
        
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
                
                # Add padding similar to chart logic
                if duration > 120: pad = 60
                elif duration > 20: pad = 20
                else: pad = 10
                
                total_range = duration + pad
                if total_range > 160:
                    return "5min"
                elif total_range > 80:
                    return "2min"
                # Updated switch logic: 40-80m -> 1min, < 40m -> 30s
                elif total_range >= 40:
                    return "1min"
                return "30s"
            except (ValueError, AttributeError):
                return "5min"

        if range_mins > 160:
            return "5min"
        elif range_mins > 80:
            return "2min"
        elif range_mins >= 40:
            return "1min"
        return "30s"

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
        desk = str(order_detail.get("Desk", ""))

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


    @render_widget
    def order_chart():
        is_dark = input.dark_mode() == "dark"

        data = current_order_enriched()
        if not data:
             return None 
        
        order_detail = data["order"]
        date = str(order_detail.get("Date")).replace(".", "-")
        orderid = str(order_detail.get("orderid", ""))
        
        # We need executions? create_order_viz takes DataService and calls get_executions internally...
        # We should optimize create_order_viz to take pre-fetched data, OR just let it fetch from cache.
        # Since DataService caches executions by (date, orderid), calling get_executions again inside create_order_viz is cheap (RAM hit only).
        # We'll just pass the IDs for now to keep refactor minimal, relying on DataService cache which was populated by get_order_enriched.
        
        ticker = str(order_detail["Ticker"])
        start_time_str = str(order_detail["StartTime"])
        end_time_str = str(order_detail["EndTime"])
        exch_open_time = str(order_detail["ExchOpenTime"])
        exch_close_time = str(order_detail["ExchCloseTime"])

        bin_size = volume_bin_size()

        # Calculate initial view range based on order duration
        st_parts = str(start_time_str).split(":")
        et_parts = str(end_time_str).split(":")
        st_minutes = int(st_parts[0]) * 60 + int(st_parts[1])
        et_minutes = int(et_parts[0]) * 60 + int(et_parts[1])
        duration = et_minutes - st_minutes

        # Determine padding based on duration
        if duration > 120:
            padding_mins = 30
        elif duration > 20:
            padding_mins = 10
        else:
            padding_mins = 5

        # Parse exchange hours for dynamic limits
        exch_open_time = str(order_detail["ExchOpenTime"])
        exch_close_time = str(order_detail["ExchCloseTime"])
        eo_parts = exch_open_time.split(":")
        ec_parts = exch_close_time.split(":")
        exch_open_mins = int(eo_parts[0]) * 60 + int(eo_parts[1])
        exch_close_mins = int(ec_parts[0]) * 60 + int(ec_parts[1])

        # Convert bin_size to seconds for precision
        bin_seconds = {"5min": 300, "2min": 120, "1min": 60, "30s": 30}.get(bin_size, 300)
        
        # Open auction bar range: exch_open - bin_size to exch_open
        exch_open_secs = exch_open_mins * 60
        min_left_secs = exch_open_secs - bin_seconds
        
        calculated_start_secs = (st_minutes - padding_mins) * 60
        view_start_secs = max(min_left_secs, calculated_start_secs)
        
        # Dynamic upper bound: Exch Close + bin_size
        exch_close_secs = exch_close_mins * 60
        max_view_secs = exch_close_secs + bin_seconds
        calculated_end_secs = (et_minutes + padding_mins) * 60
        
        # Cap the view end at exchange close + bin_size to avoid extending too far
        view_end_secs = min(calculated_end_secs, max_view_secs)

        view_start_h, view_start_rem = divmod(view_start_secs, 3600)
        view_start_m, view_start_s = divmod(view_start_rem, 60)
        
        view_end_h, view_end_rem = divmod(view_end_secs, 3600)
        view_end_m, view_end_s = divmod(view_end_rem, 60)
        
        default_x_range = [
            f"{date}T{view_start_h:02d}:{view_start_m:02d}:{view_start_s:02d}",
            f"{date}T{view_end_h:02d}:{view_end_m:02d}:{view_end_s:02d}",
        ]

        # Only use saved slider position if it's for the SAME order (date:orderid)
        # Otherwise, reset to default view for newly selected order
        current_order_key = f"{date}:{orderid}"
        x_range = default_x_range
        if "chart_x_range" in input:
            saved_data = input.chart_x_range()
            if saved_data and isinstance(saved_data, dict):
                saved_range = saved_data.get("range")
                saved_key = saved_data.get("orderKey")
                if saved_range and len(saved_range) == 2 and saved_key == current_order_key:
                    x_range = saved_range
            elif saved_data and isinstance(saved_data, list) and len(saved_data) == 2:
                # Legacy format (just the range) - don't use it for new orders
                pass
        
        # Track bin size for any future logic that needs it
        current_bin = bin_size
        _last_bin_size["value"] = current_bin

        theme_colors = {
            "primary": shiny_theme.colors.primary,
            "secondary": shiny_theme.colors.secondary,
            "body_color": shiny_theme.colors.body_color,
            "warning": shiny_theme.colors.warning,
            "danger": shiny_theme.colors.danger,
        }

        return create_order_viz(
            data_service=DATA_SERVICE,
            date=date,
            ticker=str(ticker),
            orderid=orderid,
            start_time_str=str(start_time_str),
            end_time_str=str(end_time_str),
            bin_size=str(bin_size),
            is_dark=bool(is_dark),
            theme_colors=theme_colors,
            x_range=[str(x_range[0]), str(x_range[1])],
            default_x_range=[str(default_x_range[0]), str(default_x_range[1])],
            exch_open_time=exch_open_time,
            exch_close_time=exch_close_time,
        )


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
