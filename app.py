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

from data_service import DataService
from plotly_order_viz import create_order_viz
import tables

# Data access layer (Option B)
DATA_SERVICE = DataService.demo()




app_ui = ui.page_navbar(
    ui.nav_panel(
        "Table",
        ui.layout_sidebar(
            ui.sidebar(
                ui.input_date("start_date", "Start Date", value="2025-01-01"),
                ui.input_date("end_date", "End Date", value="2025-01-01"),
                ui.input_action_button("query_btn", "Query", class_="btn-primary"),
                width=250,
            ),
            ui.card(
                ui.card_header("Order Table"),
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
    title="Order Visualizer",
    header=ui.TagList(
        ui.include_css("www/styles.css"),
        ui.include_js("www/chart.js"),
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
    # Store the user's zoom range when switching bins (non-reactive for tracking)
    _last_bin_size = {"value": "5min"}
    
    # Reactive value to hold the orders data
    orders_df = reactive.Value(pd.DataFrame())

    @reactive.Effect
    def _fetch_data():
        # Fetch data on button click, but also run once on startup (by reacting to the inputs initially if we want?)
        # Or we can just explicitly init orders_df.
        # But user pattern is usually: inputs -> button -> update.
        # To show data on load, we can check a flag or just run it.
        # However, input.query_btn() is 0 initially.
        
        # We can use reactive.isolate to read inputs without dependency?
        # But we want to trigger on button.
        # Let's check `input.query_btn()`
        _ = input.query_btn() # Dependency
        
        # Isolate inputs to avoid updating on date change without button press
        with reactive.isolate():
            start = input.start_date()
            end = input.end_date()
        
        if not start or not end:
            return

        # Convert to string if necessary, though input_date returns date object
        start_str = str(start)
        end_str = str(end)
        
        df = DATA_SERVICE.query_orders(start_str, end_str)
        orders_df.set(df)
        
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
        df = orders_df.get()
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
                text_values = " ".join(str(row[c]).lower() for c in text_cols)
                
                # Build numeric strings without commas for prefix match
                numeric_strs = [str(int(row[c])).lower() if pd.notna(row[c]) else "" 
                               for c in numeric_cols]
                
                # Each token must match somewhere
                for token in tokens:
                    token_clean = token.replace(",", "")  # User might type with commas
                    
                    # Check text columns (substring match)
                    if token_clean in text_values:
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

        # Add extra left padding so the Open auction bar isn't clipped.
        if bin_size == "5min":
            min_left_mins = exch_open_mins - 10
        elif bin_size == "1min":
            min_left_mins = exch_open_mins - 5
        else:  # 30s
            min_left_mins = exch_open_mins - 1

        view_start_mins = max(min_left_mins, st_minutes - padding_mins)
        
        # Dynamic upper bound: Exch Close + 5 mins
        max_view_mins = exch_close_mins + 5
        calculated_end = et_minutes + padding_mins
        
        # Ensure we don't clip tightly if close to market close, unless strictly closed
        # trusting calculated padding over ExchClose to avoid cutting off chart
        view_end_mins = calculated_end

        view_start_h, view_start_m = divmod(view_start_mins, 60)
        view_end_h, view_end_m = divmod(view_end_mins, 60)
        default_x_range = [
            f"{date}T{view_start_h:02d}:{view_start_m:02d}:00",
            f"{date}T{view_end_h:02d}:{view_end_m:02d}:00",
        ]

        # Always use current slider position if available, only use default on initial load
        x_range = default_x_range
        if "chart_x_range" in input:
            saved_range = input.chart_x_range()
            if saved_range and len(saved_range) == 2:
                x_range = saved_range
        
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
            exch_open_time=exch_open_time,
            exch_close_time=exch_close_time,
        )



app = App(app_ui, server)
