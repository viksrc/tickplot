"""Plotly order visualization builder.

This module contains a pure(ish) helper used by the Shiny server to build
the main order chart figure.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def create_order_viz(
	*,
	data_service: Any,
	date: str,
	ticker: str,
	orderid: str,
	start_time_str: str,
	end_time_str: str,
	bin_size: str,
	is_dark: bool,
	theme_colors: dict[str, str],
	x_range: list[str],
	default_x_range: list[str],
	exch_open_time: str,
	exch_close_time: str,
) -> go.Figure:
	"""Create the Plotly figure for an order.

	Parameters
	- data_service: object that provides get_prices/get_executions/get_volume_data
	- date, ticker, orderid: selection keys
	- start_time_str, end_time_str: order window (HH:MM)
	- bin_size: one of "5min" | "2min" | "1min" | "30s"
	- is_dark: whether UI is in dark mode
	- theme_colors: mapping with keys: primary, secondary, body_color, warning, danger
	- x_range: [start_iso, end_iso] strings for the current view (may be user-modified)
	- default_x_range: [start_iso, end_iso] strings for the default/All view
	- exch_open_time, exch_close_time: exchange trading hours (HH:MM)
	"""

	primary = str(theme_colors.get("primary", "#0d6efd"))
	body_color = str(theme_colors.get("body_color", "#212529"))
	warning = str(theme_colors.get("warning", "#ffc107"))
	danger = str(theme_colors.get("danger", "#dc3545"))

	if is_dark:
		font_color = "#c9d1d9"
		grid_color = "rgba(255, 255, 255, 0.1)"
		volume_color = "rgba(92, 124, 250, 0.95)"

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

		bid_color = "#2dd4bf"
		ask_rgb = _mix_hex(warning, danger, 0.70)
		ask_color = f"rgb({ask_rgb[0]}, {ask_rgb[1]}, {ask_rgb[2]})"
		fill_color = f"rgba({ask_rgb[0]}, {ask_rgb[1]}, {ask_rgb[2]}, 0.15)"
		exec_bubble_color = "rgba(125, 211, 252, 0.95)" # Sky Blue 300, less transparent
		exec_bubble_line = "#7dd3fc" # Sky Blue 300
		dark_vol_color = "#7e868e"  # Slightly brighter than #6c757d (~+8%)
		spike_color = "rgba(255, 255, 255, 0.04)"
		spike_thickness = 0.5
	else:
		font_color = body_color
		grid_color = "rgba(0, 0, 0, 0.1)"
		volume_color = "rgba(24, 100, 171, 0.95)"
		bid_color = "#059669"
		ask_color = "#e33e19"
		fill_color = "rgba(234, 88, 12, 0.1)"
		exec_bubble_color = "rgba(30, 58, 138, 0.6)"
		exec_bubble_line = "rgba(30, 58, 138, 0.8)"
		dark_vol_color = "#495057"  # Dark grey for Light theme
		spike_color = "rgba(0, 0, 0, 0.4)"
		spike_thickness = 0.5

	stock_data = data_service.get_prices(date, ticker, exch_open_time, exch_close_time)
	execution_data = data_service.get_executions(date, orderid)

	# 3 rows: Stock price (row 1), Volume (row 2), Hidden price for rangeslider (row 3)
	# Row 3 has zero height but its rangeslider shows bid/ask price series
	# Row 2 has secondary_y enabled for PRate overlay
	fig = make_subplots(
		rows=3,
		cols=1,
		shared_xaxes=False,
		vertical_spacing=0.0,
		row_heights=[0.55, 0.25, 0.001],  # Row 3 is invisible (just for rangeslider)
		specs=[
			[{"secondary_y": False}],  # Row 1: Price chart
			[{"secondary_y": True}],   # Row 2: Volume chart with secondary y for PRate
			[{"secondary_y": False}],  # Row 3: Hidden rangeslider
		],
	)

	fig.update_layout(barmode="stack")

	time_values = stock_data["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()

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
		row=1,
		col=1,
	)

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
		row=1,
		col=1,
	)

	# Pre-compute bubble colors based on venue type for executions
	# Color bubbles based on venue type: Exchange=Lit (volume_color), Dark Pool=Dark (dark_vol_color)
	# Venues A/B/C are Exchanges, D/E/F are Dark Pools
	bubble_colors = []
	bubble_lines = []
	if not execution_data.empty:
		for venue in execution_data["Venue"]:
			if venue in ["DELT", "ECHO", "FLUX"]:  # Dark Pool
				bubble_colors.append(dark_vol_color)
				bubble_lines.append(dark_vol_color)
			else:  # Exchange (A/B/C)
				bubble_colors.append(volume_color)
				bubble_lines.append(volume_color)

	if not execution_data.empty:
		exec_time_values = execution_data["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()
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
					color=bubble_colors,
					line=dict(width=1, color=bubble_lines),
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
						execution_data["Size"].to_numpy(),
						execution_data["Venue"].to_numpy(),
					)
				),
				hovertemplate=(
					"<b>Execution</b>: %{customdata[3]:,} @ %{y:.2f}"
					"<br>%{customdata[4]} %{customdata[0]:.2f}x%{customdata[1]:.2f} SC: %{customdata[2]:.1f}%"
					"<extra></extra>"
				),
				xaxis="x2",
			),
			row=1,
			col=1,
		)

	volume_df = data_service.get_volume_data(date, ticker, exch_open_time, exch_close_time, interval=bin_size)
	
	# Get binned analytics (PRate) for the order
	binned_analytics = data_service.get_binned_analytics(
		date=date,
		orderid=orderid,
		ticker=ticker,
		exch_open_time=exch_open_time,
		exch_close_time=exch_close_time,
		interval=bin_size,
	)

	if "Kind" in volume_df.columns:
		regular_vol = volume_df.loc[volume_df["Kind"] == "Regular"].copy()
		auction_vol = volume_df.loc[volume_df["Kind"] != "Regular"].copy()
	else:
		regular_vol = volume_df.copy()
		auction_vol = volume_df.iloc[0:0].copy()

	plot_vol = regular_vol.copy()
	
	# Calculate open_bin_time based on exchange hours and bin size
	exch_open_dt = pd.to_datetime(f"{date} {exch_open_time}:00")
	exch_close_dt = pd.to_datetime(f"{date} {exch_close_time}:00")
	
	if bin_size == "5min":
		bin_delta = pd.to_timedelta(5, unit="m")
		time_fmt = "%H:%M"
		open_bin_time = exch_open_dt - pd.Timedelta(minutes=5)
	elif bin_size == "2min":
		bin_delta = pd.to_timedelta(2, unit="m")
		time_fmt = "%H:%M"
		open_bin_time = exch_open_dt - pd.Timedelta(minutes=2)
	elif bin_size == "1min":
		bin_delta = pd.to_timedelta(1, unit="m")
		time_fmt = "%H:%M"
		open_bin_time = exch_open_dt - pd.Timedelta(minutes=1)
	else:  # 30s
		bin_delta = pd.to_timedelta(30, unit="s")
		time_fmt = "%H:%M:%S"
		open_bin_time = exch_open_dt - pd.Timedelta(seconds=30)

	close_bin_time = exch_close_dt

	if not plot_vol.empty and "Time" in plot_vol.columns:
		start_txt = plot_vol["Time"].dt.strftime(time_fmt)
		end_txt = (plot_vol["Time"] + bin_delta).dt.strftime(time_fmt)
		plot_vol["HoverLabel"] = start_txt + "–" + end_txt

	open_rows = (
		auction_vol.loc[auction_vol.get("Kind", "") == "Open"].copy()
		if not auction_vol.empty
		else auction_vol.iloc[0:0].copy()
	)
	close_rows = (
		auction_vol.loc[auction_vol.get("Kind", "") == "Close"].copy()
		if not auction_vol.empty
		else auction_vol.iloc[0:0].copy()
	)

	def _append_auction_bar(target_time: pd.Timestamp, auction_df: pd.DataFrame, label: str) -> None:
		nonlocal plot_vol
		if auction_df.empty:
			return
		auction_total = float(pd.to_numeric(auction_df["Volume"], errors="coerce").fillna(0).sum())
		# Auctions are 100% Lit, 0% Dark
		row_data = {
			"Time": target_time, 
			"Volume": auction_total, 
			"LitVolume": auction_total,
			"DarkVolume": 0,
			"HoverLabel": label
		}
		if "Kind" in plot_vol.columns:
			row_data["Kind"] = label
		plot_vol = pd.concat([plot_vol, pd.DataFrame([row_data])], ignore_index=True)

	_append_auction_bar(open_bin_time, open_rows, "Open")
	_append_auction_bar(close_bin_time, close_rows, "Close")

	open_x_val = open_bin_time.strftime("%Y-%m-%dT%H:%M:%S") if not open_rows.empty else None
	close_x_val = close_bin_time.strftime("%Y-%m-%dT%H:%M:%S") if not close_rows.empty else None

	if not plot_vol.empty:
		plot_vol = plot_vol.sort_values("Time").reset_index(drop=True)
		vol_time_values = plot_vol["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()
		hover_labels = (
			plot_vol["HoverLabel"].astype(str).tolist()
			if "HoverLabel" in plot_vol.columns
			else plot_vol["Time"].dt.strftime("%H:%M").tolist()
		)
		
		# Lit/Dark/Total calculations
		lit_vols = plot_vol.get("LitVolume", plot_vol["Volume"]).fillna(0).astype(int).tolist()
		dark_vols = plot_vol.get("DarkVolume", pd.Series(0, index=plot_vol.index)).fillna(0).astype(int).tolist()
		total_vols = (np.array(lit_vols) + np.array(dark_vols)).tolist()
		
		# Calculate %Dark for tooltip
		pct_dark_list = []
		for l, d in zip(lit_vols, dark_vols):
			tot = l + d
			if tot > 0:
				pct_dark_list.append(d / tot * 100.0)
			else:
				pct_dark_list.append(0.0)
				
		custom_data = list(zip(hover_labels, total_vols, pct_dark_list))
		
		# Build hovertext strings directly for each bar
		hover_texts = []
		for label, vol, dark_pct in custom_data:
			hover_texts.append(f"{label}<br>Volume: {vol:,}<br>Dark%: {dark_pct:.1f}%")

		# Extract just the hover labels for customdata (used by dynamic binning tests)
		hover_labels = [item[0] for item in custom_data]

		# Trace 1: Lit Volume (Bottom of stack)
		fig.add_trace(
			go.Bar(
				x=vol_time_values,
				y=lit_vols,
				name="Lit Volume",
				offset=0,
				hovertext=hover_texts,
				customdata=hover_labels,
				hoverinfo="text",
				marker_color=volume_color,
				marker_line_width=0.5,
				marker_line_color=grid_color,
				showlegend=False,
			),
			row=2,
			col=1,
		)
		
		# Trace 2: Dark Volume (Top of stack)
		if any(v > 0 for v in dark_vols):
			fig.add_trace(
				go.Bar(
					x=vol_time_values,
					y=dark_vols,
					name="Dark Volume",
					offset=0,
					customdata=custom_data,
					marker_color=dark_vol_color,
					marker_line_width=0.5,
					marker_line_color=grid_color,
					showlegend=False,
					hoverinfo="skip",  # Tooltip shown only on Lit trace to avoid duplication
				),
				row=2,
				col=1,
			)

	# Trace: PRate line on secondary y-axis for Volume chart (row 2)
	if not binned_analytics.empty and "PRate" in binned_analytics.columns:
		prate_time_values = binned_analytics["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()
		prate_values = binned_analytics["PRate"].tolist()
		
		# Choose a distinct color for PRate line
		prate_color = "#f59e0b" if is_dark else "#d97706"  # Amber/orange
		
		fig.add_trace(
			go.Scatter(
				x=prate_time_values,
				y=prate_values,
				name="PRate",
				mode="lines",
				line=dict(color=prate_color, width=2),
				hovertemplate="<b>PRate</b>: %{y:.1f}%<extra></extra>",
				showlegend=False,
			),
			row=2,
			col=1,
			secondary_y=True,  # Use secondary y-axis
		)

	# Row 3: Hidden price traces for the rangeslider (shows bid/ask in the slider)
	# These traces render in the rangeslider - the main plot area is near-zero height
	fig.add_trace(
		go.Scatter(
			x=time_values,
			y=stock_data["Bid"],
			name="Bid (slider)",
			mode="lines",
			line=dict(color=bid_color, width=1, shape="hv"),
			showlegend=False,
			hoverinfo="skip",
		),
		row=3,
		col=1,
	)
	fig.add_trace(
		go.Scatter(
			x=time_values,
			y=stock_data["Ask"],
			name="Ask (slider)",
			mode="lines",
			line=dict(color=ask_color, width=1, shape="hv"),
			fill="tonexty",
			fillcolor=fill_color,
			showlegend=False,
			hoverinfo="skip",
		),
		row=3,
		col=1,
	)
	# Also add execution bubbles to row 3 so they appear in the rangeslider
	if not execution_data.empty:
		slider_exec_times = execution_data["Time"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()
		# Reuse bubble_colors from main chart (computed earlier)
		fig.add_trace(
			go.Scatter(
				x=slider_exec_times,
				y=execution_data["Price"],
				mode="markers",
				name="Executions (slider)",
				marker=dict(
					size=8,  # Visible in slider
					color=bubble_colors,  # Same Lit/Dark coloring as main chart
				),
				showlegend=False,
				hoverinfo="skip",
			),
			row=3,
			col=1,
		)

	start_time_full = f"{date}T{start_time_str}:00"
	end_time_full = f"{date}T{end_time_str}:00"

	bid_min = float(stock_data["Bid"].min()) if not stock_data.empty else 0.0
	ask_max = float(stock_data["Ask"].max()) if not stock_data.empty else 1.0
	exec_min = float(execution_data["Price"].min()) if not execution_data.empty else bid_min
	exec_max = float(execution_data["Price"].max()) if not execution_data.empty else ask_max
	y_min = min(bid_min, exec_min)
	y_max = max(ask_max, exec_max)
	y_padding = (y_max - y_min) * 0.05 if (y_max - y_min) > 0 else 0.25

	fig.add_trace(
		go.Scatter(
			x=[start_time_full, start_time_full],
			y=[y_min - y_padding, y_max + y_padding],
			mode="lines",
			name="Start",
			line=dict(color="#22c55e", width=2, dash="dash"),
			hovertemplate="<b>Start Time</b><extra></extra>",
		),
		row=1,
		col=1,
	)

	fig.add_trace(
		go.Scatter(
			x=[end_time_full, end_time_full],
			y=[y_min - y_padding, y_max + y_padding],
			mode="lines",
			name="End",
			line=dict(color="#ef4444", width=2, dash="dash"),
			hovertemplate="<b>End Time</b><extra></extra>",
		),
		row=1,
		col=1,
	)

	fig.update_layout(
		title=None,
		bargap=0.2,
		legend=dict(
			orientation="h",
			yanchor="bottom",
			y=1.02,
			xanchor="left",
			x=0,
			bgcolor="rgba(30, 41, 59, 0.8)" if is_dark else "rgba(255,255,255,0.8)",
			font=dict(color=font_color),
			bordercolor=grid_color,
			borderwidth=1,
		),
		margin=dict(l=60, r=40, t=50, b=50),
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
			matches="x",
			type="date",
			showticklabels=False,
			showgrid=False,
			zeroline=False,
			hoverformat="%H:%M:%S",
		),
		# Meta will be set later with button-related data
	)

	# Removed unifiedhovertitle clearing to restore time display in price chart hover
	# fig.update_xaxes(unifiedhovertitle=dict(text=""), row=1, col=1)

	# Calculate rangeslider bounds based on exchange hours
	exch_open_mins = int(exch_open_time.split(":")[0]) * 60 + int(exch_open_time.split(":")[1])
	exch_close_mins = int(exch_close_time.split(":")[0]) * 60 + int(exch_close_time.split(":")[1])
	
	bin_seconds = {"5min": 300, "2min": 120, "1min": 60, "30s": 30}.get(bin_size, 300)

	# Slider start: Exch Open - bin_size
	exch_open_secs = exch_open_mins * 60
	slider_start_secs = exch_open_secs - bin_seconds
	slider_start_h, slider_start_rem = divmod(slider_start_secs, 3600)
	slider_start_m, slider_start_s = divmod(slider_start_rem, 60)
	slider_start_iso = f"{date}T{slider_start_h:02d}:{slider_start_m:02d}:{slider_start_s:02d}"
	min_left_mins = slider_start_secs // 60  # For time label calculations below

	# Default slider end is Exch Close + bin_size
	exch_close_secs = exch_close_mins * 60
	slider_end_secs = exch_close_secs + bin_seconds
	slider_end_h, slider_end_rem = divmod(slider_end_secs, 3600)
	slider_end_m, slider_end_s = divmod(slider_end_rem, 60)
	slider_end_iso = f"{date}T{slider_end_h:02d}:{slider_end_m:02d}:{slider_end_s:02d}"
	
	# If the initial view (x_range[1]) extends beyond the default slider end (due to padding),
	# extend the slider to match.
	if x_range and len(x_range) > 1 and x_range[1] > slider_end_iso:
		slider_end_iso = x_range[1]

	x_range_slider = [
		slider_start_iso,
		slider_end_iso,
	]

	# Calculate button ranges for time durations from order start and end
	start_dt = pd.to_datetime(start_time_full)
	end_dt = pd.to_datetime(end_time_full)
	
	# Check if order starts at market open or ends at market close
	exch_open_dt = pd.to_datetime(f"{date} {exch_open_time}:00")
	exch_close_dt = pd.to_datetime(f"{date} {exch_close_time}:00")
	
	# Adjust effective start/end to include auction bars if applicable
	starts_at_open = (start_dt == exch_open_dt)
	ends_at_close = (end_dt == exch_close_dt)
	
	# Helper function to determine bin size based on duration (same logic as dynamic binning)
	def get_bin_minutes_for_duration(duration_mins):
		if duration_mins > 160:
			return 5  # 5min bins
		elif duration_mins > 80:
			return 2  # 2min bins
		elif duration_mins > 40:
			return 1  # 1min bins
		else:
			return 0.5  # 30s bins
	
	# Helper to calculate effective start/end for a given duration
	def get_effective_range(duration_mins):
		bin_mins = get_bin_minutes_for_duration(duration_mins)
		
		# Effective start: if order starts at market open, include Open auction bar (mkt_open - bin_size)
		eff_start_dt = exch_open_dt - pd.Timedelta(minutes=bin_mins) if starts_at_open else start_dt
		
		# Effective end: if order ends at market close, include Close auction bar (mkt_close + bin_size)
		eff_end_dt = exch_close_dt + pd.Timedelta(minutes=bin_mins) if ends_at_close else end_dt
		
		return eff_start_dt, eff_end_dt
	
	# Calculate ranges for each button
	# Store effective start/end for each duration in metadata for JS to use
	duration_data = {}
	for dur in [5, 15, 30, 60, 120, 240]:
		eff_start, eff_end = get_effective_range(dur)
		duration_data[str(dur)] = {
			"effStart": eff_start.strftime("%Y-%m-%dT%H:%M:%S"),
			"effEnd": eff_end.strftime("%Y-%m-%dT%H:%M:%S"),
		}
	
	# Buttons: First/Last are anchors, duration buttons apply from anchor, All resets
	time_buttons = [
		dict(label="First", method="skip", args=[{"action": "anchor", "anchor": "first"}]),
		dict(label="Last", method="skip", args=[{"action": "anchor", "anchor": "last"}]),
	]
	
	# Add duration buttons
	for duration_mins, label in [(5, "5m"), (15, "15m"), (30, "30m"), (60, "1h"), (120, "2h"), (240, "4h")]:
		time_buttons.append(dict(
			label=label,
			method="skip",
			args=[{"action": "duration", "mins": duration_mins}],
		))
	
	# All button restores initial view
	time_buttons.append(dict(
		label="All",
		method="skip",
		args=[{"action": "all"}],
	))

	# Add all buttons via updatemenus for consistent highlighting
	# Include duration data and default range in metadata for JS
	fig.update_layout(
		meta=dict(
			orderKey=f"{date}:{orderid}",
			binSize=bin_size,
			durationData=duration_data,
			defaultRange=default_x_range,
		),
		updatemenus=[
			dict(
				type="buttons",
				direction="right",
				x=0.42,
				y=1.015,
				xanchor="left",
				yanchor="bottom",
				bgcolor="rgba(30, 41, 59, 0.8)" if is_dark else "rgba(255, 255, 255, 0.8)",
				bordercolor=grid_color,
				borderwidth=1,
				font=dict(color=font_color, size=11),
				pad=dict(r=1, t=0, l=1, b=0),
				showactive=True,
				active=-1,  # No button selected by default
				buttons=time_buttons,
			),
		],
	)

	fig.update_xaxes(
		gridcolor=grid_color,
		linecolor=grid_color,
		row=1,
		col=1,
		showticklabels=False,
		showgrid=False,
		showline=False,
		ticks="",
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
		type="date",
		showspikes=True,
		spikemode="across",
		spikesnap="cursor",
		spikethickness=spike_thickness,
		spikedash="solid",
		spikecolor=spike_color,
	)

	fig.update_xaxes(
		gridcolor=grid_color,
		linecolor=font_color,
		row=2,
		col=1,
		showticklabels=True,
		showgrid=False,
		showline=True,
		ticks="outside",
		ticklen=5,
		tickwidth=1.5,
		tickcolor=font_color,
		tickangle=45,
		tickmode="auto",
		nticks=20,
		hoverformat="%H:%M:%S",
		tickformatstops=[
			{"dtickrange": [None, 60_000], "value": "%H:%M:%S"},
			{"dtickrange": [60_000, None], "value": "%H:%M"},
		],
		matches="x",
		type="date",
		showspikes=True,
		spikemode="across",
		spikesnap="cursor",
		spikethickness=spike_thickness,
		spikedash="solid",
		spikecolor=spike_color,
	)

	# Row 3: Hidden chart area but visible rangeslider showing price data
	fig.update_xaxes(
		row=3,
		col=1,
		showticklabels=False,
		showgrid=False,
		zeroline=False,
		showline=False,
		matches="x",
		range=x_range,
		autorange=False,
		type="date",
		rangeslider=dict(
			visible=True,
			thickness=0.12,  # 20% larger than original
			range=x_range_slider,  # Set full extent of rangeslider to slider bounds
		),
	)
	fig.update_yaxes(
		row=3,
		col=1,
		showticklabels=False,
		showgrid=False,
		zeroline=False,
		showline=False,
		visible=False,
	)
	
	# Add fixed time annotations below the rangeslider (not tied to view range)
	# These show the full trading session regardless of zoom level
	slider_y_pos = -0.18  # Below the rangeslider
	
	# Calculate the actual slider data range (with padding on both ends)
	# Parse slider end time to get total minutes
	slider_end_parts = slider_end_iso.split("T")[1].split(":")
	slider_end_mins = int(slider_end_parts[0]) * 60 + int(slider_end_parts[1])
	slider_total_mins = slider_end_mins - min_left_mins
	
	# Generate time labels every 30 minutes from open to close
	time_labels = []
	
	# Include open time, then round to 30-min boundaries, then close
	# Start with exchange open time
	current_mins = exch_open_mins
	while current_mins <= exch_close_mins:
		h, m = divmod(current_mins, 60)
		time_str = f"{h:02d}:{m:02d}"
		# Calculate x position as fraction of SLIDER range (accounts for padding)
		x_pos = (current_mins - min_left_mins) / slider_total_mins if slider_total_mins > 0 else 0
		time_labels.append((time_str, x_pos))
		
		# Move to next 30-min boundary
		if current_mins == exch_open_mins and exch_open_mins % 30 != 0:
			# Round up to next 30-min mark
			current_mins = ((exch_open_mins // 30) + 1) * 30
		else:
			current_mins += 30
	
	for time_str, x_pos in time_labels:
		fig.add_annotation(
			text=time_str,
			xref="paper",
			yref="paper",
			x=x_pos,
			y=slider_y_pos,
			showarrow=False,
			textangle=45,
			xanchor="left",
			yanchor="top",
			font=dict(color=font_color, size=12),
		)

	if open_x_val:
		fig.add_annotation(
			x=open_x_val,
			y=-0.08,
			xref="x",
			yref="y2 domain",
			text="Open",
			textangle=45,  # Match Plotly tick label angle
			showarrow=False,
			xanchor="center",
			yshift=4,      # Move up slightly
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
			textangle=45,  # Match Plotly tick label angle
			showarrow=False,
			xanchor="left",
			xshift=10,  # Extra shift to avoid overlapping with 16:00
			yshift=4,   # Move up slightly
			yanchor="top",
			font=dict(color=font_color, size=12),
			bgcolor="rgba(0,0,0,0)",
		)

	fig.update_yaxes(
		gridcolor=grid_color,
		linecolor=grid_color,
		row=1,
		col=1,
		tickprefix="$",
		tickformat=".2f",
		title_text="Price",
		domain=[0.38, 1.0],  # Row 1: top 62%
	)
	fig.update_yaxes(
		gridcolor=grid_color,
		linecolor=grid_color,
		row=2,
		col=1,
		title_text="Volume",
		domain=[0.15, 0.38],  # Row 2: right below Row 1, slider pushed lower
		secondary_y=False,  # Primary y-axis for Volume bars
	)
	# Secondary y-axis for PRate line overlay
	fig.update_yaxes(
		row=2,
		col=1,
		title_text="PRate%",
		ticksuffix="%",
		showgrid=False,  # Don't show grid for secondary axis
		secondary_y=True,  # Secondary y-axis for PRate
	)
	fig.update_yaxes(
		row=3,
		col=1,
		domain=[0.0, 0.001],  # Row 3: hidden, rangeslider appears in gap above
		showticklabels=False,
		showgrid=False,
		zeroline=False,
		showline=False,
	)

	# Initial y-axis autoscale based on the initial x-axis view window.
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

