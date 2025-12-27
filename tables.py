"""Table creation logic for the Order Visualizer app."""

from __future__ import annotations

import html
import pandas as pd
from shiny import ui
from pytabulator import TableOptions, Tabulator

from data_service import VENUE_MAPPING

# Layout constant
VENUE_DETAILS_HEIGHT_DELTA_PX = 40


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



def create_perf_chip(label: str, value: float, is_percentage: bool = False, percentage_decimals: int = 2):
    """
    Create a styled performance chip (pill) for display in UI.
    
    Args:
        label: The label text (e.g., "Return", "PerfArrival")
        value: The numeric value to display.
        is_percentage: If True, format as %, and positive is Good (Green).
                       If False, format as bps, and positive is Bad (Red).
        percentage_decimals: Number of decimals for percentage formatting.
    """
    # Handle missing/NaN values
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
        # For Perf metrics (Arrival, VWAP, etc): positive is bad (slippage), negative is good (improvement)
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


def get_orders_table(df: pd.DataFrame) -> Tabulator:
    """Create the main Orders table."""
    df = df.copy()
    
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

    table_options = TableOptions(
        index="id",
        height=420,
        layout="fitColumns",
        selectable_rows=1,
        columns=[
            {"field": "orderid", "title": "OrderID", "width": 90, "hozAlign": "center"},
            {"field": "Date", "title": "Date", "width": 100, "hozAlign": "center"},
            {"field": "Country", "title": "Country", "width": 80, "hozAlign": "center"},
            {"field": "Desk", "title": "Desk", "width": 80, "hozAlign": "center"},
            {"field": "Broker", "title": "Broker", "width": 80, "hozAlign": "center"},
            {"field": "Side", "title": "Side", "width": 70, "hozAlign": "center"},
            {"field": "Ticker", "title": "Ticker", "width": 80, "hozAlign": "center"},
            {"field": "OrderQty", "title": "OrderQty", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 0}, "hozAlign": "right", "visible": False},
            {"field": "ExecQty", "title": "ExecQty", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 0}, "hozAlign": "right"},
            {"field": "Notional", "title": "Notional", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 0}, "hozAlign": "right"},
            {"field": "AvgPrice", "title": "AvgPrice", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 3}, "hozAlign": "right", "visible": False},
            {"field": "PctADV", "title": "PctADV", "hozAlign": "right"},
            {"field": "SpreadCapture", "title": "SpreadCapture", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 1}, "hozAlign": "right", "visible": False},
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
    return Tabulator(df, table_options=table_options)


    if not row:
        # Fallback if no row selected: return empty or default
        # For robustness, if no row selected, we show empty or handle gracefully.
        # But 'app.py' might guarantee a valid default row from the dataset.
        # Assuming app.py passes a default row via some mechanism or we fetch default.
        # But wait, app.py calls this. Let's make this robust.
        # If no row selected, we can try to fetch a default from data_service using a default date,
        # OR app.py ensures row is populated.
        # Let's assume input.date_picker is NOT available.
        # We'll use a sensible default of today if we really have to, but better to return empty structure?
        # Re-reading plan: "Use default_row if no row is selected".
        # So we should modify signature to accept default_row context.
        pass

def get_order_details_table(input, data_service) -> Tabulator:
    """Create the Order Details table."""
    
    # Get selected row from table
    row = input.orders_table_row_clicked()
    
    if not row:
         # Empty table if no row
         # We can return empty list or empty dataframe
         # Tabulator(pd.DataFrame()) renders empty.
         # But the specific format below expects specific fields. 
         # We should return a properly structured but empty DF for layout consistency
         # But simpler: just return empty row behavior
         row = {} 

    date = str(row.get("Date", "")) # Fallback date if completely empty

    orderid = str(row.get("orderid", ""))
    order_detail = data_service.get_order_detail(date, orderid)
    trader_id = str(order_detail.get("TraderID", ""))

    execution_data = data_service.get_executions(date, orderid)

    total_qty = float(execution_data["Size"].sum())
    if total_qty > 0:
        spread_capture_pct = float((execution_data["spreadcapture"] * execution_data["Size"]).sum() / total_qty) * 100.0
    else:
        spread_capture_pct = float("nan")

    show_all = bool(input.show_all_details())

    # Default display excludes Return and Perf*.
    default_fields = [
        "OrderID",
        "Broker",
        "PctADV",
        "PRate",
    ]

    all_fields = [
        "ID",
        *default_fields,
        "ExecQty",
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
        if field == "Broker":
            return str(row.get("Broker", ""))
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
        if field == "PRate":
            raw = order_detail.get("PRate", row.get("PRate", ""))
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
    details_height = min(450, max(250, 60 + row_count * 30))
    # Reduce height by 15% to keep compact
    details_height = int(details_height * 0.90)
    details_height = max(160, int(details_height * 0.90))
    # Make room for the Venues table (same delta, opposite direction)
    details_height = max(160, int(details_height) - VENUE_DETAILS_HEIGHT_DELTA_PX)

    order_options = TableOptions(
        height=details_height,
        layout="fitColumns",
        columns=[
            {"field": "Field", "title": "Field", "hozAlign": "left", "headerSort": False},
            {"field": "Value", "title": "Value", "hozAlign": "right", "headerSort": False},
        ],
    )
    
    return Tabulator(order_details, table_options=order_options)


def get_fill_detail_table(input, data_service) -> Tabulator:
    """Create the Fill Details table."""
    
    row = input.orders_table_row_clicked()
    if not row:
        row = {}

    date = str(row.get("Date", "")) # Fallback date checks

    orderid = str(row.get("orderid", ""))
    execution_data = data_service.get_executions(date, orderid)

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

        # Use CSS variables for dynamic theme switching
        # Bid = Near, Ask = Far, Mid = Lit Volume Color (Blue/Indigo)
        near_color = "var(--color-bid)"
        mid_color = "var(--color-vol-lit)"
        far_color = "var(--color-ask)"

        def seg(width: float, color: str) -> str:
            if width <= 0.0:
                return ""
            return f"<div style='width:{width:.2f}%; height:100%; background-color:{color};'></div>"

        bar = (
            "<div style='display:flex; width:100%; height:1.05rem; border-radius:0; overflow:hidden; background: var(--bs-secondary-bg);'"
            f" title='{title}'>"
            + seg(near, near_color)
            + seg(mid, mid_color)
            + seg(far, far_color)
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

        # Use same colors as volume bars: Lit=blue, Dark=grey (Theme aware)
        lit_color = "var(--color-vol-lit)"
        dark_color = "var(--color-vol-dark)"

        def seg(width: float, color: str) -> str:
            if width <= 0.0:
                return ""
            return f"<div style='width:{width:.2f}%; height:100%; background-color:{color};'></div>"

        bar = (
            "<div style='display:flex; width:100%; height:1.05rem; border-radius:0; overflow:hidden; background: var(--bs-secondary-bg);'"
            f" title='{title}'>"
            + seg(lit, lit_color)
            + seg(dark, dark_color)
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
            {"field": "Value", "title": "Value", "hozAlign": "right", "headerSort": False, "formatter": "html"},
        ],
    )

    return Tabulator(details, table_options=options)


def get_venue_table(input, data_service) -> Tabulator:
    """Create the Venues table."""
    
    row = input.orders_table_row_clicked()
    if not row:
        row = {}

    date = str(row.get("Date", ""))

    orderid = str(row.get("orderid", ""))
    execution_data = data_service.get_executions(date, orderid)
    
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
        # Use same colors as volume bars: Lit=blue, Dark=grey (Theme aware)
        bar_color = "var(--color-vol-dark)" if is_dark else "var(--color-vol-lit)"

        label = f"{pct_val:.1f}%"
        title = f"{venue_type}: {label}" if venue_type else label

        # Keep it one-line tall and readable.
        # Use theme body color for text across all venues for consistency.
        text_style = "color: var(--bs-body-color);"

        safe_title = html.escape(title, quote=True)
        safe_label = html.escape(label, quote=True)

        return (
            f"<div title=\"{safe_title}\" style='position:relative; width:100%; height:1.05rem; border-radius:0; overflow:hidden; background: var(--bs-secondary-bg);'>"
            f"<div style='width:{pct_val:.2f}%; height:100%; background-color:{bar_color};'></div>"
            f"<div style='position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:0.75rem; line-height:1; {text_style}'>"
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
    }).sort_values("PctFill", key=lambda x: x.astype(float), ascending=False).reset_index(drop=True)
    
    venue_options = TableOptions(
        height=200 + VENUE_DETAILS_HEIGHT_DELTA_PX,
        layout="fitColumns",
        columns=[
            {"field": "VenueCell", "title": "Venue", "hozAlign": "center", "formatter": "html", "headerSort": False},
            {"field": "ExecQty", "title": "Qty", "formatter": "money", "formatterParams": {"thousand": ",", "precision": 0}, "hozAlign": "right", "headerSort": False},
            {"field": "PctFillBar", "title": "% Fill", "hozAlign": "left", "formatter": "html", "headerSort": False},
            {"field": "Venue", "visible": False},
            {"field": "PctFill", "visible": False},
            {"field": "VenueInfo", "visible": False},
        ],
    )
    return Tabulator(venue_df, table_options=venue_options)


def get_theme_tabulator_css(theme) -> ui.HTML:
    """Generate dynamic CSS for tabulator based on current theme colors."""
    primary = theme.colors.primary
    secondary = theme.colors.secondary
    body_bg = theme.colors.body_bg
    body_color = theme.colors.body_color
    
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
