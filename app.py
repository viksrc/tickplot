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
                ui.p("Click any country row to see details below."),
                output_tabulator("country_table"),
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
                output_widget("stock_chart"),
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
            row = input.country_table_row_clicked()
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
        row = input.country_table_row_clicked()
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
        row = input.country_table_row_clicked()
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
    def country_table():
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
        row = input.country_table_row_clicked()
        
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

        row = input.country_table_row_clicked()
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

        row = input.country_table_row_clicked()
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
    def stock_chart():
        is_dark = input.dark_mode() == "dark"

        date = str(input.date_picker())
        
        # Get selected ticker from table
        row = input.country_table_row_clicked()
        if not row:
            row = DATA_SERVICE.query_orders(date).iloc[0].to_dict()

        ticker = row.get('Ticker') if row else "SPY"
        orderid = str(row.get("orderid", ""))
        
        # Get colors from theme
        primary = shiny_theme.colors.primary
        secondary = shiny_theme.colors.secondary
        
        # Set colors based on dark/light mode
        if is_dark:
            font_color = "#c9d1d9"  # Light gray for dark mode
            grid_color = "rgba(255, 255, 255, 0.1)"
            volume_color = "rgba(92, 124, 250, 0.6)"  # Blue with transparency
            def _hex_to_rgb(h: str) -> tuple[int, int, int]:
                h = str(h).lstrip("#")
                if len(h) == 3:
                    h = "".join([c + c for c in h])
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

            def _mix_hex(a: str, b: str, b_weight: float) -> tuple[int, int, int]:
                b_weight = float(max(0.0, min(1.0, b_weight)))
                ar, ag, ab = _hex_to_rgb(a)
                br, bg, bb = _hex_to_rgb(b)
                r = int(round(ar * (1.0 - b_weight) + br * b_weight))
                g = int(round(ag * (1.0 - b_weight) + bg * b_weight))
                bl = int(round(ab * (1.0 - b_weight) + bb * b_weight))
                return (r, g, bl)

            # Adaptive Bid/Ask colors for dark mode
            bid_color = "#2dd4bf"  # Teal - bright on dark
            # Make the orange slightly more reddish using theme palette (warning + a bit of danger).
            ask_rgb = _mix_hex(shiny_theme.colors.warning, shiny_theme.colors.danger, 0.30)
            ask_color = f"rgb({ask_rgb[0]}, {ask_rgb[1]}, {ask_rgb[2]})"
            fill_color = f"rgba({ask_rgb[0]}, {ask_rgb[1]}, {ask_rgb[2]}, 0.15)"
            exec_bubble_color = "rgba(56, 189, 248, 0.7)"
            exec_bubble_line = "#38bdf8"
        else:
            font_color = shiny_theme.colors.body_color
            grid_color = "rgba(0, 0, 0, 0.1)"
            volume_color = "rgba(24, 100, 171, 0.6)"  # Theme primary with transparency
            # Adaptive Bid/Ask colors for light mode
            bid_color = "#0891b2"  # Darker cyan - visible on light
            ask_color = "#ea580c"  # Darker orange - visible on light
            fill_color = "rgba(234, 88, 12, 0.1)"
            exec_bubble_color = "rgba(30, 58, 138, 0.5)"  # Lightened navy blue
            exec_bubble_line = "rgba(30, 58, 138, 0.8)"
        
        # Generate data for the selected ticker/order
        stock_data = DATA_SERVICE.get_prices(date, ticker)
        execution_data = DATA_SERVICE.get_executions(date, orderid)
        
        # Create subplots - Price on top with range slider, Volume below
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=False,
            vertical_spacing=0.22,
            row_heights=[0.55, 0.25],
        )
        
        # Convert datetime to ISO strings for proper JS serialization
        time_values = stock_data["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()

        # Add Bid line (step line with detailed hover)
        fig.add_trace(
            go.Scatter(
                x=time_values,
                y=stock_data["Bid"],
                name="Bid",
                mode="lines",
                line=dict(color=bid_color, width=2, shape="hv"),
                fill=None,
                customdata=stock_data["BidSize"].tolist(),
                hovertemplate="<b>Bid</b>: %{y:.2f} x %{customdata}<extra></extra>",
                hoveron="points+fills",
            ),
            row=1, col=1
        )
        
        # Add Ask line (step line with fill to bid, detailed hover)
        fig.add_trace(
            go.Scatter(
                x=time_values,
                y=stock_data["Ask"],
                name="Ask",
                mode="lines",
                line=dict(color=ask_color, width=2, shape="hv"),
                fill="tonexty",
                fillcolor=fill_color,
                customdata=stock_data["AskSize"].tolist(),
                hovertemplate="<b>Ask</b>: %{y:.2f} x %{customdata}<extra></extra>",
                hoveron="points+fills",
            ),
            row=1, col=1
        )
        
        # Add Execution bubbles
        exec_time_values = execution_data["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()
        # Scale bubble sizes: min 9.2px (15% larger), max 30px based on share size
        min_size, max_size = 9.2, 30
        sizes_normalized = (execution_data["Size"] - 50) / (3000 - 50)
        bubble_sizes = min_size + sizes_normalized * (max_size - min_size)
        
        fig.add_trace(
            go.Scatter(
                x=exec_time_values,
                y=execution_data["Price"],
                mode="markers",
                name="Executions",
                marker=dict(
                    size=bubble_sizes,
                    sizemode="diameter",
                    color=exec_bubble_color,
                    line=dict(width=1, color=exec_bubble_line),
                ),
                text=[
                    f"Size: {s:,}<br>Venue: {v}"
                    for s, v in zip(execution_data["Size"], execution_data["Venue"])
                ],
                customdata=list(
                    zip(
                        execution_data["Bid"].to_numpy(),
                        execution_data["Ask"].to_numpy(),
                        (execution_data["spreadcapture"].to_numpy() * 100.0),
                    )
                ),
                hovertemplate=(
                    "<b>Execution</b>: %{y:.2f}"
                    "<br>%{text}"
                    "<br>Bid: %{customdata[0]:.2f}"
                    "<br>Ask: %{customdata[1]:.2f}"
                    "<br>SC: %{customdata[2]:.1f}%"
                    "<extra></extra>"
                ),
                xaxis="x2",
            ),
            row=1, col=1
        )
        
        # Add Volume bars (Dynamic buckets - Option B)
        bin_size = volume_bin_size()
        volume_df = DATA_SERVICE.get_volume_data(date, ticker, interval=bin_size)

        if "Kind" in volume_df.columns:
            regular_vol = volume_df.loc[volume_df["Kind"] == "Regular"].copy()
            auction_vol = volume_df.loc[volume_df["Kind"] != "Regular"].copy()
        else:
            regular_vol = volume_df.copy()
            auction_vol = volume_df.iloc[0:0].copy()

        # Volume bars: keep a single Bar trace so Plotly preserves the original bar thickness.
        plot_vol = regular_vol.copy()
        # Precompute per-bar hover labels.
        # For regular bins: show the covered interval (e.g., 10:00–10:05).
        # For auctions: override to "Open" / "Close".
        if bin_size == "5min":
            bin_delta = pd.to_timedelta(5, unit="m")
            time_fmt = "%H:%M"
        elif bin_size == "1min":
            bin_delta = pd.to_timedelta(1, unit="m")
            time_fmt = "%H:%M"
        else:  # 30s
            bin_delta = pd.to_timedelta(30, unit="s")
            time_fmt = "%H:%M:%S"

        if not plot_vol.empty and "Time" in plot_vol.columns:
            start_txt = plot_vol["Time"].dt.strftime(time_fmt)
            end_txt = (plot_vol["Time"] + bin_delta).dt.strftime(time_fmt)
            plot_vol["HoverLabel"] = start_txt + "–" + end_txt

        open_rows = auction_vol.loc[auction_vol.get("Kind", "") == "Open"].copy() if not auction_vol.empty else auction_vol.iloc[0:0].copy()
        close_rows = auction_vol.loc[auction_vol.get("Kind", "") == "Close"].copy() if not auction_vol.empty else auction_vol.iloc[0:0].copy()

        # Place auctions as distinct, adjacent bins:
        # - Open: the bin immediately before 09:30 (09:25 for 5min, 09:29 for 1min, 09:29:30 for 30s)
        # - Close: 16:00
        # This preserves Plotly's auto bar-width calculation (no tiny x-gaps).
        if bin_size == "5min":
            open_bin_time = pd.Timestamp("2025-01-01 09:25:00")
            close_bin_time = pd.Timestamp("2025-01-01 16:00:00")
        elif bin_size == "1min":
            open_bin_time = pd.Timestamp("2025-01-01 09:29:00")
            close_bin_time = pd.Timestamp("2025-01-01 16:00:00")
        else:  # 30s
            open_bin_time = pd.Timestamp("2025-01-01 09:29:30")
            close_bin_time = pd.Timestamp("2025-01-01 16:00:00")

        def _append_auction_bar(target_time: pd.Timestamp, auction_df: pd.DataFrame, label: str) -> None:
            nonlocal plot_vol
            if auction_df.empty:
                return

            auction_total = float(pd.to_numeric(auction_df["Volume"], errors="coerce").fillna(0).sum())
            row_data = {"Time": target_time, "Volume": auction_total, "HoverLabel": label}
            if "Kind" in plot_vol.columns:
                row_data["Kind"] = label
            plot_vol = pd.concat([plot_vol, pd.DataFrame([row_data])], ignore_index=True)

        _append_auction_bar(open_bin_time, open_rows, "Open")
        _append_auction_bar(close_bin_time, close_rows, "Close")

        # Track Open/Close x-values for axis labels
        open_x_val = open_bin_time.strftime("%Y-%m-%dT%H:%M:%S") if not open_rows.empty else None
        close_x_val = close_bin_time.strftime("%Y-%m-%dT%H:%M:%S") if not close_rows.empty else None

        if not plot_vol.empty:
            plot_vol = plot_vol.sort_values("Time")
            vol_time_values = plot_vol["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()
            hover_labels = (
                plot_vol["HoverLabel"].astype(str).tolist()
                if "HoverLabel" in plot_vol.columns
                else plot_vol["Time"].dt.strftime("%H:%M").tolist()
            )

            fig.add_trace(
                go.Bar(
                    x=vol_time_values,
                    y=plot_vol["Volume"],
                    name=f"Volume ({bin_size})",
                    customdata=hover_labels,
                    marker_color=volume_color,
                    marker_line_width=0.5,
                    marker_line_color=grid_color,
                    showlegend=False,
                    hovertemplate="<b>%{customdata}</b><br>Volume: %{y:,}<extra></extra>",
                ),
                row=2, col=1
            )

        # Add vertical dashed lines for order StartTime and EndTime
        start_time_str = row.get('StartTime', '09:30') if row else '09:30'
        end_time_str = row.get('EndTime', '16:00') if row else '16:00'
        
        # Convert to full datetime strings for the chart
        start_time_full = f"2025-01-01T{start_time_str}:00"
        end_time_full = f"2025-01-01T{end_time_str}:00"
        
        # Get y-axis range for the vertical lines
        y_min = min(stock_data["Bid"].min(), execution_data["Price"].min())
        y_max = max(stock_data["Ask"].max(), execution_data["Price"].max())
        y_padding = (y_max - y_min) * 0.05
        
        # Add StartTime vertical line
        fig.add_trace(
            go.Scatter(
                x=[start_time_full, start_time_full],
                y=[y_min - y_padding, y_max + y_padding],
                mode="lines",
                name="Start",
                line=dict(color="#22c55e", width=2, dash="dash"),  # Green dashed
                hovertemplate="<b>Start Time</b><extra></extra>",
            ),
            row=1, col=1
        )
        
        # Add EndTime vertical line
        fig.add_trace(
            go.Scatter(
                x=[end_time_full, end_time_full],
                y=[y_min - y_padding, y_max + y_padding],
                mode="lines",
                name="End",
                line=dict(color="#ef4444", width=2, dash="dash"),  # Red dashed
                hovertemplate="<b>End Time</b><extra></extra>",
            ),
            row=1, col=1
        )
        
        fig.update_layout(
            title=None,
            bargap=0.2,
            legend=dict(
                orientation="h",
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01,
                bgcolor="rgba(30, 41, 59, 0.8)" if is_dark else "rgba(255,255,255,0.8)",
                font=dict(color=font_color),
                bordercolor=grid_color,
                borderwidth=1,
            ),
            margin=dict(l=60, r=20, t=10, b=80),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color=font_color,
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor="rgba(255, 255, 255, 0.6)" if not is_dark else "rgba(30, 41, 59, 0.6)",
                font_size=12,
                font_family="Inter, sans-serif",
            ),
            height=600,
            xaxis2=dict(
                overlaying="x",
                matches="x",
                type="date",
                showticklabels=False,
                showgrid=False,
                zeroline=False,
                hoverformat="%H:%M:%S",
            ),
        )

        # In x-unified hover mode, Plotly shows an axis-level header.
        # Set it to blank so users see only our per-point label (Open/Close or interval)
        # plus the single Volume line.
        fig.update_xaxes(unifiedhovertitle=dict(text=""), row=1, col=1)
        
        # Update axes - time is already formatted as strings
        # Calculate initial view range based on order duration
        # Parse start and end times to minutes since midnight
        st_parts = start_time_str.split(":")
        et_parts = end_time_str.split(":")
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
        
        # Calculate padded range (clamp to market hours 9:30-16:00)
        # Add extra left padding so the Open auction bar isn't clipped at the plot boundary.
        # (Plotly centers bars on x; if the range starts exactly at Open, you only see half the bar.)
        # min_left_mins: 09:20 (5min), 09:25 (1min), 09:29 (30s)
        if bin_size == "5min":
            min_left_mins = 560  # 09:20
        elif bin_size == "1min":
            min_left_mins = 565  # 09:25
        else:  # 30s
            min_left_mins = 569  # 09:29
        view_start_mins = max(min_left_mins, st_minutes - padding_mins)
        view_end_mins = min(965, et_minutes + padding_mins)    # 965 = 16:05 (allow label space)
        
        # Convert back to time strings
        view_start_h, view_start_m = divmod(view_start_mins, 60)
        view_end_h, view_end_m = divmod(view_end_mins, 60)
        default_x_range = [f"2025-01-01T{view_start_h:02d}:{view_start_m:02d}:00",
                           f"2025-01-01T{view_end_h:02d}:{view_end_m:02d}:00"]
        
        # Use x_range from JS if bin size is switching (preserves zoom when switching bins)
        # Only use it when we're actually switching bins (bin_size changed)
        current_bin = bin_size
        x_range = default_x_range
        if "chart_x_range" in input and current_bin != _last_bin_size["value"]:
            saved_range = input.chart_x_range()
            if saved_range and len(saved_range) == 2:
                x_range = saved_range
            _last_bin_size["value"] = current_bin
        
        # Extend the slider window slightly so Open/Close auction points can be included.
        # Keep it aligned with the left clamp so Open isn't half-clipped.
        x_range_slider = [f"2025-01-01T{min_left_mins // 60:02d}:{min_left_mins % 60:02d}:00", "2025-01-01T16:05:00"]
        
        # Use Plotly auto mode - it will adapt ticks based on zoom level
        fig.update_xaxes(
            gridcolor=grid_color, 
            linecolor=grid_color, 
            row=1, col=1,
            showticklabels=True,
            tickangle=45,
            tickmode="auto",
            nticks=20,
            range=x_range,
            autorange=False,
            hoverformat="%H:%M:%S",
            tickformatstops=[
                {"dtickrange": [None, 60_000], "value": "%H:%M:%S"},
                {"dtickrange": [60_000, None], "value": "%H:%M"},
            ],
            rangeslider=dict(
                visible=True, 
                thickness=0.1,
                range=x_range_slider,
            ),
            type="date",
        )

        # Volume subplot x-axis: keep adaptive tick logic (matches the price axis behavior)
        fig.update_xaxes(
            gridcolor=grid_color,
            linecolor=grid_color,
            row=2, col=1,
            showticklabels=True,
            tickangle=45,
            tickmode="auto",
            nticks=20,
            hoverformat="%H:%M:%S",
            tickformatstops=[
                {"dtickrange": [None, 60_000], "value": "%H:%M:%S"},
                {"dtickrange": [60_000, None], "value": "%H:%M"},
            ],
            matches="x",  # Sync with top chart
            type="date",
        )

        # Open/Close as axis-anchored labels (not ticks) so the axis can remain fully adaptive on zoom.
        # Place these just below the volume subplot x-axis.
        if open_x_val:
            fig.add_annotation(
                x=open_x_val,
                y=-0.08,
                xref="x",
                yref="y2 domain",
                text="Open",
                textangle=30,
                showarrow=False,
                xanchor="center",
                yanchor="top",
                font=dict(color=font_color, size=12),
                bgcolor="rgba(0,0,0,0)",
            )
        if close_x_val:
            fig.add_annotation(
                x=close_x_val,
                y=-0.08,
                xref="x",
                yref="y2 domain",
                text="Close",
                textangle=30,
                showarrow=False,
                xanchor="center",
                yanchor="top",
                font=dict(color=font_color, size=12),
                bgcolor="rgba(0,0,0,0)",
            )
        fig.update_yaxes(gridcolor=grid_color, linecolor=grid_color, row=1, col=1, tickprefix="$", tickformat=".2f", title_text="Price")
        fig.update_yaxes(gridcolor=grid_color, linecolor=grid_color, row=2, col=1, title_text="Volume")

        # Initial y-axis autoscale based on the initial x-axis view window (same logic as JS).
        view_start_dt = pd.to_datetime(x_range[0])
        view_end_dt = pd.to_datetime(x_range[1])
        stock_view = stock_data[(stock_data["Time"] >= view_start_dt) & (stock_data["Time"] <= view_end_dt)]
        exec_view = execution_data[(execution_data["Time"] >= view_start_dt) & (execution_data["Time"] <= view_end_dt)]

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

        if has_data and np.isfinite(min_p) and np.isfinite(max_p):
            rng = max_p - min_p
            pad = max(rng * 0.10, 0.25)
            fig.update_yaxes(range=[min_p - pad, max_p + pad], autorange=False, row=1, col=1)
        
        return fig

    @render.text
    def selected_country():
        row = input.country_table_row_clicked()
        if not row:
            return "Click a row in the table to see order info."
        
        return (
            f"{row.get('Country')} | Ticker: {row.get('Ticker')} | "
            f"ExecQty: {row.get('ExecQty'):,} | Return: {row.get('Return'):.2f}%"
        )


app = App(app_ui, server)
