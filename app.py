"""Shiny for Python demo with Tabulator and Plotly widgets."""

from __future__ import annotations

import html
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from shinyswatch.theme import lumen as shiny_theme
from pytabulator import (
    TableOptions,
    Tabulator,
    output_tabulator,
    render_tabulator,
)
from shiny import App, render, ui, reactive
from shinywidgets import output_widget, render_widget

from data_service import DataService
from data_service import VENUE_MAPPING
from plotly_order_viz import create_order_viz


def format_display_date(value: object) -> str:
    """Format a date-like value for display as YYYY.MM.DD.

    Keeps underlying input/query formats unchanged (we only use this for UI text/tables).
    """

    if value is None:
        return ""

    text = str(value)
    dt = pd.to_datetime(text, errors="coerce")
    if pd.isna(dt):
        return text.replace("-", ".")
    return dt.strftime("%Y.%m.%d")


# Data access layer (Option B)
DATA_SERVICE = DataService.demo()

# Layout tuning: add a bit more room for the Venues table (now includes Venue F)
# and subtract the same amount from Order Details to keep the left column height stable.
VENUE_DETAILS_HEIGHT_DELTA_PX = 40

TABLE_OPTIONS = TableOptions(
    index="id",
    height=420,
    layout="fitColumns",
    selectable_rows=1,
    columns=[
        {"field": "orderid", "title": "OrderID", "width": 90, "hozAlign": "center"},
        {"field": "Date", "title": "Date", "width": 100, "hozAlign": "center"},
        {"field": "Country", "title": "Country", "width": 80, "hozAlign": "center"},
        {"field": "Side", "title": "Side", "width": 70, "hozAlign": "center"},
        {"field": "Ticker", "title": "Ticker", "width": 80, "hozAlign": "center"},
        {"field": "OrderQty", "title": "OrderQty", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 0}, "hozAlign": "right"},
        {"field": "ExecQty", "title": "ExecQty", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 0}, "hozAlign": "right"},
        {"field": "Notional", "title": "Notional", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 0}, "hozAlign": "right"},
        {"field": "AvgPrice", "title": "AvgPrice", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 3}, "hozAlign": "right"},
        {"field": "PctADV", "title": "PctADV", "hozAlign": "right"},
        {"field": "SpreadCapture", "title": "SpreadCapture", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 1}, "hozAlign": "right"},
        {"field": "Strategy", "title": "Strategy", "width": 90, "hozAlign": "center"},
        {"field": "StartTime", "title": "Start", "width": 70, "hozAlign": "center"},
        {"field": "EndTime", "title": "End", "width": 70, "hozAlign": "center"},
        {
            "field": "Return",
            "title": "Return (%)",
            "formatter": "progress",
            "formatterParams": {
                "min": 0,
                "max": 10,
                "color": ["#ef4444", "#3b82f6", "#22c55e"],
                "legend": True,
                "legendAlign": "center",
            },
            "hozAlign": "left",
        },
        {"field": "PerfArrival", "title": "PerfArrival<br><span style='display:block; text-align:center;'>(bps)</span>", "hozAlign": "right", "headerHozAlign": "center"},
        {"field": "PerfVWAP", "title": "PerfVWAP<br><span style='display:block; text-align:center;'>(bps)</span>", "hozAlign": "right", "headerHozAlign": "center"},
        {"field": "PerfClose", "title": "PerfClose<br><span style='display:block; text-align:center;'>(bps)</span>", "hozAlign": "right", "headerHozAlign": "center"},
    ],
)




app_ui = ui.page_navbar(
    ui.nav_panel(
        "Table",
        ui.layout_sidebar(
            ui.sidebar(
                ui.input_date("date_picker", "Select Date", value="2025-01-01"),
                width=250,
            ),
            ui.card(
                ui.card_header("Order Table"),
                ui.p("Click any order row to see details below."),
                output_tabulator("orders_table"),
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
        ui.include_js("chart.js"),
    ),
    title="Order Visualizer",
    header=ui.TagList(
        ui.include_css("www/styles.css"),
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

    @reactive.calc
    def volume_bin_size():
        if "chart_range_mins" not in input:
            range_mins = None
        else:
            range_mins = input.chart_range_mins()
        
        if range_mins is None:
            # Initial state: check the duration of the selected order
            date = str(input.date_picker())
            row = input.orders_table_row_clicked()
            if not row:
                try:
                    row = DATA_SERVICE.query_orders(date).iloc[0].to_dict()
                except (IndexError, KeyError):
                    return "5min"
            
            st_str = row.get('StartTime', '09:30')
            et_str = row.get('EndTime', '16:00')
            try:
                st_parts = st_str.split(":")
                et_parts = et_str.split(":")
                duration = (int(et_parts[0])*60 + int(et_parts[1])) - (int(st_parts[0])*60 + int(st_parts[1]))
                
                # Add padding similar to chart logic
                if duration > 120: pad = 60
                elif duration > 20: pad = 20
                else: pad = 10
                
                total_range = duration + pad
                if total_range > 80:
                    return "5min"
                # Updated switch logic: 40-80m -> 1min, < 40m -> 30s
                elif total_range >= 40:
                    return "1min"
                return "30s"
            except (ValueError, AttributeError):
                return "5min"

        if range_mins > 80:
            return "5min"
        elif range_mins >= 40:
            return "1min"
        return "30s"

    @render.ui
    def chart_title():
        date = str(input.date_picker())
        row = input.orders_table_row_clicked()
        if not row:
            row = DATA_SERVICE.query_orders(date).iloc[0].to_dict()

        order_id = row.get("orderid", "")
        order_detail = DATA_SERVICE.get_order_detail(date, str(order_id))
        trader_id = str(order_detail.get("TraderID", ""))
        date = format_display_date(row.get("Date", date))
        side = row.get("Side", "")
        ticker = row.get("Ticker", "SPY")
        country = row.get("Country", "")
        exec_qty = row.get("ExecQty", 0)
        avg_price_raw = row.get("AvgPrice", None)
        strategy = row.get("Strategy", "")
        start_time = row.get("StartTime", "")
        end_time = row.get("EndTime", "")

        try:
            avg_price = float(avg_price_raw)
        except (TypeError, ValueError):
            avg_price = float("nan")

        avg_price_str = f"{avg_price:.3f}" if pd.notna(avg_price) else ""

        return ui.div(
            ui.span(f"{order_id}", class_="me-2 text-muted"),
            ui.span(f"{date}", class_="me-2"),
            ui.span(f"{side}", class_="me-2"),
            ui.span(f"{int(exec_qty):,}{(' @' + avg_price_str) if avg_price_str else ''}", class_="me-2"),
            ui.span(f"{ticker}", class_="me-2"),
            ui.span(f"{country}", class_="me-2"),
            ui.span(f"{strategy}", class_="me-2"),
            ui.span(f"{start_time} - {end_time}", class_="me-2"),
            ui.span(f"{trader_id}", class_="text-muted"),
            class_="fw-semibold",
        )

    @render.ui
    def chart_metrics():
        date = str(input.date_picker())
        row = input.orders_table_row_clicked()
        if not row:
            row = DATA_SERVICE.query_orders(date).iloc[0].to_dict()

        orderid = str(row.get("orderid", ""))
        execution_data = DATA_SERVICE.get_executions(date, orderid)

        total_qty = float(execution_data["Size"].sum())
        if total_qty > 0:
            spread_capture_pct = float((execution_data["spreadcapture"] * execution_data["Size"]).sum() / total_qty) * 100.0
        else:
            spread_capture_pct = float("nan")

        def perf_chip(label: str, value: float, is_percentage: bool = False, percentage_decimals: int = 2):
            # Positive is bad (red), negative is good (green) for performance metrics
            if value is None or (isinstance(value, float) and pd.isna(value)):
                color = "secondary"
                value_str = "—"
                return ui.span(
                    ui.span(label, class_="fw-medium", style="font-size: 0.75rem; opacity: 0.8; display:block;"),
                    ui.span(value_str, class_="fw-semibold", style="font-size: 0.9rem; display:block;"),
                    class_=f"bg-{color}-subtle text-{color} border border-{color}-subtle rounded",
                    style=(
                        "display:inline-flex; flex-direction:column; align-items:center; justify-content:center; "
                        "text-align:center; line-height:1.1; gap:0.1rem; padding:0.4rem 0.75rem; min-height:2.4rem;"
                    ),
                )

            if is_percentage:
                # For Return: positive is good (green)
                if value > 0:
                    color = "success"
                else:
                    color = "secondary"
                value_str = f"{value:.{percentage_decimals}f}%"
            else:
                # For Perf metrics: positive is bad, negative is good
                if value > 0:
                    color = "danger"
                elif value < 0:
                    color = "success"
                else:
                    color = "secondary"
                value_str = f"{value:+.1f} bps"

            return ui.span(
                ui.span(label, class_="fw-medium", style="font-size: 0.75rem; opacity: 0.8; display:block;"),
                ui.span(value_str, class_="fw-semibold", style="font-size: 0.9rem; display:block;"),
                class_=f"bg-{color}-subtle text-{color} border border-{color}-subtle rounded",
                style=(
                    "display:inline-flex; flex-direction:column; align-items:center; justify-content:center; "
                    "text-align:center; line-height:1.1; gap:0.1rem; padding:0.4rem 0.75rem; min-height:2.4rem;"
                ),
            )

        return ui.div(
            perf_chip("Return", float(row.get("Return", 0.0)), is_percentage=True),
            perf_chip("PerfArrival", float(row.get("PerfArrival", 0.0))),
            perf_chip("PerfVWAP", float(row.get("PerfVWAP", 0.0))),
            perf_chip("PerfClose", float(row.get("PerfClose", 0.0))),
            perf_chip("SpreadCapture", spread_capture_pct, is_percentage=True, percentage_decimals=1),
            class_="d-flex gap-2 justify-content-start px-2 py-1",
        )

    @render.ui
    def theme_tabulator_css():
        """Generate dynamic CSS for tabulator based on current theme colors."""
        primary = shiny_theme.colors.primary
        secondary = shiny_theme.colors.secondary
        body_bg = shiny_theme.colors.body_bg
        body_color = shiny_theme.colors.body_color
        
        css = f"""
        <style id="theme-tabulator-css">
        .tabulator {{
            background-color: {body_bg} !important;
            border-color: {secondary} !important;
            color: {body_color} !important;
        }}
        .tabulator-header {{
            background-color: {primary} !important;
            color: white !important;
            border-color: {primary} !important;
        }}
        .tabulator-header .tabulator-col {{
            background-color: {primary} !important;
            border-color: {primary} !important;
            color: white !important;
        }}
        .tabulator-header .tabulator-col-content {{
            color: white !important;
        }}
        .tabulator-tableholder {{
            background-color: {body_bg} !important;
        }}
        .tabulator-row {{
            background-color: {body_bg} !important;
            color: {body_color} !important;
        }}
        .tabulator-row:nth-child(even) {{
            background-color: color-mix(in srgb, {body_bg} 90%, {secondary}) !important;
        }}
        .tabulator-row:hover {{
            background-color: color-mix(in srgb, {primary} 20%, {body_bg}) !important;
        }}
        .tabulator-row.tabulator-selected {{
            background-color: color-mix(in srgb, {primary} 40%, {body_bg}) !important;
            color: {body_color} !important;
        }}
        .tabulator-cell {{
            border-color: color-mix(in srgb, {secondary} 50%, transparent) !important;
            color: {body_color} !important;
        }}
        .tabulator-footer {{
            background-color: {secondary} !important;
            color: {body_color} !important;
            border-color: {secondary} !important;
        }}
        </style>
        """
        return ui.HTML(css)

    @render_tabulator
    def orders_table():
        date = str(input.date_picker())
        df = DATA_SERVICE.query_orders(date).copy()
        # Do not display FillSize in the Orders table (AvgFillSize is shown in Fill Details)
        if "FillSize" in df.columns:
            df = df.drop(columns=["FillSize"])
        if "Date" in df.columns:
            df["Date"] = df["Date"].map(format_display_date)
        if "PctADV" in df.columns:
            def _fmt_pct_adv(v: object) -> str:
                try:
                    return f"{float(v):.2f}%"
                except (TypeError, ValueError):
                    return ""

            df["PctADV"] = df["PctADV"].map(_fmt_pct_adv)
        # Add OrderQty (for now = ExecQty) and Notional (ExecQty * AvgPrice)
        if "ExecQty" in df.columns:
            df["OrderQty"] = df["ExecQty"]
        if "ExecQty" in df.columns and "AvgPrice" in df.columns:
            df["Notional"] = (df["ExecQty"] * df["AvgPrice"]).astype(int).round(0)
        return Tabulator(df, table_options=TABLE_OPTIONS)

    @render_tabulator
    def order_details_table():
        date = str(input.date_picker())

        # Get selected row from table
        row = input.orders_table_row_clicked()
        
        if not row:
            row = DATA_SERVICE.query_orders(date).iloc[0].to_dict()

        orderid = str(row.get("orderid", ""))
        order_detail = DATA_SERVICE.get_order_detail(date, orderid)
        trader_id = str(order_detail.get("TraderID", ""))

        execution_data = DATA_SERVICE.get_executions(date, orderid)

        total_qty = float(execution_data["Size"].sum())
        if total_qty > 0:
            spread_capture_pct = float((execution_data["spreadcapture"] * execution_data["Size"]).sum() / total_qty) * 100.0
        else:
            spread_capture_pct = float("nan")

        show_all = bool(input.show_all_details())

        # Default display excludes Return and Perf*.
        default_fields = [
            "OrderID",
            "ExecQty",
            "PctADV",
        ]

        all_fields = [
            "ID",
            *default_fields,
            "Date",
            "Country",
            "Strategy",
            "StartTime",
            "EndTime",
            "TraderID",
            "Side",
            "Ticker",
            "Return",
            "PerfArrival",
            "PerfVWAP",
            "PerfClose",
            "SpreadCapture",
        ]

        def format_value(field: str) -> str:
            if field == "ID":
                return str(row.get("id", ""))
            if field == "OrderID":
                return str(row.get("orderid", ""))
            if field == "Date":
                return format_display_date(row.get("Date", date))
            if field == "TraderID":
                return trader_id
            if field in ("Country", "Side", "Ticker", "Strategy", "StartTime", "EndTime"):
                return str(row.get(field, ""))
            if field == "ExecQty":
                return f"{int(row.get('ExecQty', 0) or 0):,}"
            if field == "PctADV":
                raw = order_detail.get("PctADV", row.get("PctADV", ""))
                if isinstance(raw, str):
                    return raw
                try:
                    return f"{float(raw):.2f}%"
                except (TypeError, ValueError):
                    return ""
            if field == "SpreadCapture":
                return f"{spread_capture_pct:.1f}%" if pd.notna(spread_capture_pct) else ""
            if field == "Return":
                try:
                    return f"{float(row.get('Return', 0.0)):.2f}%"
                except (TypeError, ValueError):
                    return ""
            if field.startswith("Perf"):
                try:
                    return f"{float(row.get(field, 0.0)):.1f} bps"
                except (TypeError, ValueError):
                    return ""
            return str(row.get(field, ""))

        fields = all_fields if show_all else default_fields
        order_details = pd.DataFrame(
            {
                "Field": fields,
                "Value": [format_value(f) for f in fields],
            }
        )
        
        # Shrink the table by default (fewer fields). Keep a cap so "All" doesn't blow up the layout.
        row_count = int(len(order_details))
        details_height = min(414, max(220, 56 + row_count * 28))
        # Reduce height by another 15% (stacking with the previous shrink behavior)
        details_height = int(details_height * 0.85)
        details_height = max(140, int(details_height * 0.85))
        # Make room for the Venues table (same delta, opposite direction)
        details_height = max(140, int(details_height) - VENUE_DETAILS_HEIGHT_DELTA_PX)

        order_options = TableOptions(
            height=details_height,
            layout="fitColumns",
            columns=[
                {"field": "Field", "title": "Field", "hozAlign": "left", "headerSort": False},
                {"field": "Value", "title": "Value", "hozAlign": "right", "headerSort": False},
            ],
        )
        
        return Tabulator(order_details, table_options=order_options)

    @render_tabulator
    def fill_detail_table():
        date = str(input.date_picker())

        row = input.orders_table_row_clicked()
        if not row:
            row = DATA_SERVICE.query_orders(date).iloc[0].to_dict()

        orderid = str(row.get("orderid", ""))
        execution_data = DATA_SERVICE.get_executions(date, orderid)

        num_fills = int(len(execution_data))
        if num_fills > 0:
            avg_fill_size = int(round(float(execution_data["Size"].mean())))
        else:
            avg_fill_size = 0

        # FillAgg: classify each execution by spread capture
        # Near: SC > 75% ; Far: SC < 25% ; Mid otherwise
        if num_fills > 0:
            sc = execution_data["spreadcapture"].astype(float)
            near_mask = sc > 0.75
            far_mask = sc < 0.25
            mid_mask = ~(near_mask | far_mask)

            # Aggregate by execution count (simple and stable)
            near_pct = float(near_mask.mean() * 100.0)
            mid_pct = float(mid_mask.mean() * 100.0)
            far_pct = float(far_mask.mean() * 100.0)
        else:
            near_pct = 0.0
            mid_pct = 0.0
            far_pct = 0.0

        def stacked_bar_html(near: float, mid: float, far: float) -> str:
            # Clamp and normalize to 100 (avoid tiny floating errors)
            near = max(0.0, min(100.0, float(near)))
            mid = max(0.0, min(100.0, float(mid)))
            far = max(0.0, min(100.0, float(far)))
            total = near + mid + far
            if total <= 0:
                return "<span class='text-muted'>—</span>"
            scale = 100.0 / total
            near *= scale
            mid *= scale
            far *= scale

            title = f"N {near:.0f}% | M {mid:.0f}% | F {far:.0f}%"

            def seg(width: float, cls: str) -> str:
                if width <= 0.0:
                    return ""
                return f"<div class='{cls}' style='width:{width:.2f}%; height:100%;'></div>"

            bar = (
                "<div style='display:flex; width:100%; height:1.05rem; border-radius:0; overflow:hidden; background: var(--bs-secondary-bg);'"
                f" title='{title}'>"
                + seg(near, "bg-success")
                + seg(mid, "bg-primary")
                + seg(far, "bg-danger")
                + "</div>"
                f"<div class='text-muted' style='font-size:0.75rem; margin-top:0.15rem;'>{title}</div>"
            )
            return bar

        # VenueType: Lit vs Dark % based on executed quantity by venue type
        if num_fills > 0:
            total_exec_qty = float(execution_data["Size"].sum())
        else:
            total_exec_qty = 0.0

        if total_exec_qty > 0:
            venue_types = execution_data["Venue"].astype(str).map(
                lambda v: str(VENUE_MAPPING.get(v, {}).get("type", ""))
            )
            lit_qty = float(execution_data.loc[venue_types.str.contains("Exchange", na=False), "Size"].sum())
            dark_qty = float(execution_data.loc[venue_types.str.contains("Dark", na=False), "Size"].sum())
            lit_pct = (lit_qty / total_exec_qty) * 100.0
            dark_pct = (dark_qty / total_exec_qty) * 100.0
        else:
            lit_pct = 0.0
            dark_pct = 0.0

        def venue_type_bar_html(lit: float, dark: float) -> str:
            lit = max(0.0, min(100.0, float(lit)))
            dark = max(0.0, min(100.0, float(dark)))
            total = lit + dark
            if total <= 0:
                return "<span class='text-muted'>—</span>"
            scale = 100.0 / total
            lit *= scale
            dark *= scale

            title = f"Lit {lit:.0f}% | Dark {dark:.0f}%"

            def seg(width: float, cls: str) -> str:
                if width <= 0.0:
                    return ""
                return f"<div class='{cls}' style='width:{width:.2f}%; height:100%;'></div>"

            # Lit: light blue; Dark: navy-ish blue (Bootstrap primary)
            bar = (
                "<div style='display:flex; width:100%; height:1.05rem; border-radius:0; overflow:hidden; background: var(--bs-secondary-bg);'"
                f" title='{title}'>"
                + seg(lit, "bg-info")
                + seg(dark, "bg-dark")
                + "</div>"
                f"<div class='text-muted' style='font-size:0.75rem; margin-top:0.15rem;'>{title}</div>"
            )
            return bar

        details = pd.DataFrame(
            {
                "Field": ["NumFills", "AvgFillSize", "VenueType", "FillAgg"],
                "Value": [
                    f"{num_fills:,}",
                    f"{avg_fill_size:,}",
                    venue_type_bar_html(lit_pct, dark_pct),
                    stacked_bar_html(near_pct, mid_pct, far_pct),
                ],
            }
        )

        options = TableOptions(
            height=180,
            layout="fitColumns",
            columns=[
                {"field": "Field", "title": "Field", "hozAlign": "left", "headerSort": False},
                {"field": "Value", "title": "Value", "hozAlign": "left", "headerSort": False, "formatter": "html"},
            ],
        )

        return Tabulator(details, table_options=options)

    @render_tabulator
    def venue_table():
        date = str(input.date_picker())

        row = input.orders_table_row_clicked()
        if not row:
            row = DATA_SERVICE.query_orders(date).iloc[0].to_dict()

        orderid = str(row.get("orderid", ""))
        execution_data = DATA_SERVICE.get_executions(date, orderid)
        
        # Calculate venue quantities and percentages
        venue_qty = execution_data.groupby("Venue")["Size"].sum()
        total_qty = int(execution_data["Size"].sum())
        if total_qty > 0:
            venue_pct = (venue_qty / total_qty * 100).round(1)
        else:
            venue_pct = (venue_qty * 0).astype(float)
        
        # Convert to Python floats/ints to preserve display
        def _venue_info(label: str) -> str:
            info = VENUE_MAPPING.get(str(label), None)
            if not info:
                return str(label)
            return f"{info['name']} ({info['type']})"

        def _venue_type(label: str) -> str:
            info = VENUE_MAPPING.get(str(label), None)
            if not info:
                return ""
            return str(info.get("type", ""))

        def _venue_cell(label: str, info: str) -> str:
            # Use the browser's native tooltip via a title attribute.
            # This is more reliable than Tabulator's tooltip settings across wrappers.
            safe_info = html.escape(str(info), quote=True)
            safe_label = html.escape(str(label), quote=True)
            return (
                f"<div title=\"{safe_info}\" "
                "style='width:100%; height:100%; display:flex; align-items:center; justify-content:center;'>"
                f"{safe_label}</div>"
            )

        def _pct_fill_bar_html(pct: float, venue_type: str) -> str:
            try:
                pct_val = float(pct)
            except (TypeError, ValueError):
                pct_val = 0.0

            pct_val = max(0.0, min(100.0, pct_val))
            is_dark = "Dark" in str(venue_type)
            bar_cls = "bg-dark" if is_dark else "bg-info"

            label = f"{pct_val:.1f}%"
            title = f"{venue_type}: {label}" if venue_type else label

            # Keep it one-line tall and readable.
            # Use theme body color for text across all venues for consistency.
            text_style = "color: var(--bs-body-color);"
            text_cls = ""

            safe_title = html.escape(title, quote=True)
            safe_label = html.escape(label, quote=True)

            return (
                f"<div title=\"{safe_title}\" style='position:relative; width:100%; height:1.05rem; border-radius:0; overflow:hidden; background: var(--bs-secondary-bg);'>"
                f"<div class='{bar_cls}' style='width:{pct_val:.2f}%; height:100%;'></div>"
                f"<div class='{text_cls}' style='position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:0.75rem; line-height:1; {text_style}'>"
                f"{safe_label}"
                "</div>"
                "</div>"
            )

        venue_df = pd.DataFrame({
            "Venue": venue_qty.index.tolist(),
            "VenueCell": [_venue_cell(v, _venue_info(v)) for v in venue_qty.index],
            "ExecQty": [int(v) for v in venue_qty.values],
            # Use 1-decimal strings so Tabulator progress legend shows one decimal.
            # (Tabulator 6.2 progress formatter has no `precision` param.)
            "PctFill": [f"{float(venue_pct.loc[v]):.1f}" for v in venue_qty.index],
            "PctFillBar": [
                _pct_fill_bar_html(float(venue_pct.loc[v]), _venue_type(v))
                for v in venue_qty.index
            ],
            "VenueInfo": [_venue_info(v) for v in venue_qty.index],
        }).sort_values("Venue").reset_index(drop=True)
        
        venue_options = TableOptions(
            height=200 + VENUE_DETAILS_HEIGHT_DELTA_PX,
            layout="fitColumns",
            columns=[
                {"field": "VenueCell", "title": "Venue", "hozAlign": "center", "formatter": "html"},
                {"field": "ExecQty", "title": "Qty", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 0}, "hozAlign": "center"},
                {"field": "PctFillBar", "title": "% Fill", "hozAlign": "left", "formatter": "html"},
                {"field": "Venue", "visible": False},
                {"field": "PctFill", "visible": False},
                {"field": "VenueInfo", "visible": False},
            ],
        )
        return Tabulator(venue_df, table_options=venue_options)

    @render_widget
    def order_chart():
        is_dark = input.dark_mode() == "dark"

        date = str(input.date_picker())
        row = input.orders_table_row_clicked()
        if not row:
            row = DATA_SERVICE.query_orders(date).iloc[0].to_dict()

        orderid = str(row.get("orderid", ""))
        order_detail = DATA_SERVICE.get_order_detail(date, orderid)
        
        ticker = str(order_detail.get("Ticker", "SPY"))
        start_time_str = str(order_detail.get("StartTime", "09:30"))
        end_time_str = str(order_detail.get("EndTime", "16:00"))

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

        # Add extra left padding so the Open auction bar isn't clipped.
        if bin_size == "5min":
            min_left_mins = 560  # 09:20
        elif bin_size == "1min":
            min_left_mins = 565  # 09:25
        else:  # 30s
            min_left_mins = 569  # 09:29

        view_start_mins = max(min_left_mins, st_minutes - padding_mins)
        view_end_mins = min(965, et_minutes + padding_mins)  # 965 = 16:05 (allow label space)

        view_start_h, view_start_m = divmod(view_start_mins, 60)
        view_end_h, view_end_m = divmod(view_end_mins, 60)
        default_x_range = [
            f"2025-01-01T{view_start_h:02d}:{view_start_m:02d}:00",
            f"2025-01-01T{view_end_h:02d}:{view_end_m:02d}:00",
        ]

        # Use x_range from JS if bin size is switching (preserves zoom when switching bins)
        current_bin = bin_size
        x_range = default_x_range
        if "chart_x_range" in input and current_bin != _last_bin_size["value"]:
            saved_range = input.chart_x_range()
            if saved_range and len(saved_range) == 2:
                x_range = saved_range
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
        )

    @render.text
    def selected_country():
        row = input.orders_table_row_clicked()
        if not row:
            return "Click a row in the table to see order info."
        
        return (
            f"{row.get('Country')} | Ticker: {row.get('Ticker')} | "
            f"ExecQty: {row.get('ExecQty'):,} | Return: {row.get('Return'):.2f}%"
        )


app = App(app_ui, server)
