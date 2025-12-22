import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

def create_stock_chart(
    ticker: str,
    stock_data: pd.DataFrame,
    execution_data: pd.DataFrame,
    row_data: dict | None,
    is_dark: bool,
    shiny_theme_colors: dict
) -> go.Figure:
    """
    Create the Plotly figure for the stock chart.
    
    Args:
        ticker: The stock ticker symbol
        stock_data: DataFrame containing Time, Bid, Ask, BidSize, AskSize, Volume
        execution_data: DataFrame containing Time, Price, Size, Venue
        row_data: Dictionary containing selected row data (StartTime, EndTime)
        is_dark: Boolean indicating if dark mode is active
        shiny_theme_colors: Dictionary containing theme colors (primary, secondary, body_color)
    """
    
    # Get colors from theme
    primary = shiny_theme_colors.get('primary')
    secondary = shiny_theme_colors.get('secondary')
    body_color = shiny_theme_colors.get('body_color')
    
    # Set colors based on dark/light mode
    if is_dark:
        font_color = "#c9d1d9"  # Light gray for dark mode
        grid_color = "rgba(255, 255, 255, 0.1)"
        volume_color = "rgba(92, 124, 250, 0.6)"  # Blue with transparency
        # Adaptive Bid/Ask colors for dark mode
        bid_color = "#2dd4bf"  # Teal - bright on dark
        ask_color = "#fb923c"  # Orange - warm contrast
        fill_color = "rgba(251, 146, 60, 0.15)"
    else:
        font_color = body_color
        grid_color = "rgba(0, 0, 0, 0.1)"
        volume_color = "rgba(24, 100, 171, 0.6)"  # Theme primary with transparency
        # Adaptive Bid/Ask colors for light mode
        bid_color = "#0891b2"  # Darker cyan - visible on light
        ask_color = "#ea580c"  # Darker orange - visible on light
        fill_color = "rgba(234, 88, 12, 0.1)"
    
    # Create subplots - Price on top with range slider, Volume below
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=False,
        vertical_spacing=0.28,
        row_heights=[0.52, 0.23],
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
            hovertemplate="<b>Bid</b><br>%{y:.2f} x %{customdata}<br>%{x|%H:%M:%S}<extra></extra>",
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
            hovertemplate="<b>Ask</b><br>%{y:.2f} x %{customdata}<br>%{x|%H:%M:%S}<extra></extra>",
            hoveron="points+fills",
        ),
        row=1, col=1
    )
    
    # Add Execution bubbles on secondary x-axis
    exec_time_values = execution_data["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()
    # Scale bubble sizes: min 8px, max 30px based on share size
    min_size, max_size = 8, 30
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
                color="rgba(56, 189, 248, 0.4)",  # Cyan blue - more transparent fill
                line=dict(width=1, color="#38bdf8"),  # Solid border unchanged
            ),
            text=[f"Size: {s:,}<br>Venue: {v}" for s, v in zip(execution_data["Size"], execution_data["Venue"])],
            hovertemplate="<b>Execution</b><br>%{x|%H:%M:%S}<br>Price: %{y:.2f}<br>%{text}<extra></extra>",
            xaxis="x2",
        ),
        row=1, col=1
    )
    
    # Add Volume bars (5-minute buckets)
    volume_5m = (
        stock_data
        .set_index("Time")["Volume"]
        .resample("5min")
        .sum()
        .reset_index()
    )
    volume_time_values = volume_5m["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()
    fig.add_trace(
        go.Bar(
            x=volume_time_values,
            y=volume_5m["Volume"],
            name="Volume",
            marker_color=volume_color,
            showlegend=False,
            hovertemplate="<b>Volume</b><br>%{x|%H:%M}<br>%{y:,}<extra></extra>",
        ),
        row=2, col=1
    )
    
    # Add vertical dashed lines for order StartTime and EndTime
    start_time_str = row_data.get('StartTime', '09:30') if row_data else '09:30'
    end_time_str = row_data.get('EndTime', '16:00') if row_data else '16:00'
    
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
            hovertemplate=f"<b>Start Time</b><br>{start_time_str}<extra></extra>",
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
            hovertemplate=f"<b>End Time</b><br>{end_time_str}<extra></extra>",
        ),
        row=1, col=1
    )
    
    fig.update_layout(
        title=f"{ticker} - Bid/Ask Prices with Volume",
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
        margin=dict(l=60, r=20, t=60, b=60),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color=font_color,
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(255, 255, 255, 0.7)" if not is_dark else "rgba(30, 41, 59, 0.7)",
            font_size=12,
            font_family="Inter, sans-serif",
        ),
        height=600,
        xaxis2=dict(
            overlaying="x",
            type="date",
            hoverformat="%H:%M:%S",
            showticklabels=False,
            showgrid=False,
            zeroline=False,
        ),
    )
    
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
    # Add extra 5 min padding for label visibility at boundaries
    view_start_mins = max(565, st_minutes - padding_mins)  # 565 = 9:25 (allow label space)
    view_end_mins = min(965, et_minutes + padding_mins)    # 965 = 16:05 (allow label space)
    
    # Convert back to time strings
    view_start_h, view_start_m = divmod(view_start_mins, 60)
    view_end_h, view_end_m = divmod(view_end_mins, 60)
    x_range = [f"2025-01-01T{view_start_h:02d}:{view_start_m:02d}:00",
               f"2025-01-01T{view_end_h:02d}:{view_end_m:02d}:00"]
    
    x_range_slider = ["2025-01-01T09:30:00", "2025-01-01T16:00:00"]
    
    # Use Plotly auto mode - it will adapt ticks based on zoom level
    fig.update_xaxes(
        gridcolor=grid_color, 
        linecolor=grid_color, 
        row=1, col=1,
        showticklabels=True,
        tickangle=45,
        tickmode="auto",
        nticks=10,  # Suggest ~10 ticks, Plotly will pick nice values
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
    fig.update_xaxes(
        gridcolor=grid_color, 
        linecolor=grid_color, 
        row=2, col=1,
        showticklabels=True,
        tickangle=45,
        tickmode="auto",
        nticks=10,
        hoverformat="%H:%M:%S",
        tickformatstops=[
            {"dtickrange": [None, 60_000], "value": "%H:%M:%S"},
            {"dtickrange": [60_000, None], "value": "%H:%M"},
        ],
        matches="x",  # Sync with top chart
        type="date",
    )
    fig.update_yaxes(gridcolor=grid_color, linecolor=grid_color, row=1, col=1, tickprefix="$", tickformat=".2f", title_text="Price")
    fig.update_yaxes(gridcolor=grid_color, linecolor=grid_color, row=2, col=1, title_text="Volume")
    
    return fig
