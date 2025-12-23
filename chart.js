// Dynamic Y-axis rescaling when range slider changes
function resizeAllPlotly() {
    const plotDivs = document.querySelectorAll('.js-plotly-plot');
    plotDivs.forEach(graphDiv => {
        try {
            if (window.Plotly && Plotly.Plots && Plotly.Plots.resize) {
                Plotly.Plots.resize(graphDiv);
            }
        } catch (e) {
            // noop
        }
    });
}

function setupRescaling() {
    const plotDivs = document.querySelectorAll('.js-plotly-plot');
    plotDivs.forEach(graphDiv => {
        if (graphDiv._hasRescaling) return;
        graphDiv._hasRescaling = true;

        // Ensure Plotly fits the container on first bind
        setTimeout(() => {
            try {
                if (window.Plotly && Plotly.Plots && Plotly.Plots.resize) {
                    Plotly.Plots.resize(graphDiv);
                }
            } catch (e) {
                // noop
            }
        }, 50);

        graphDiv.on('plotly_relayout', function (eventdata) {
            const isXChange = eventdata['xaxis.range[0]'] || eventdata['xaxis.range[1]'] ||
                eventdata['xaxis.range'] || eventdata['xaxis.autorange'];
            if (!isXChange) return;

            // Get data from chart traces
            const traces = graphDiv.data;
            if (!traces || traces.length < 2) return;

            const times = traces[0].x;  // Bid times
            const bids = traces[0].y;   // Bid prices
            const asks = traces[1].y;   // Ask prices

            let xStart, xEnd;
            if (eventdata['xaxis.autorange']) {
                xStart = times[0];
                xEnd = times[times.length - 1];
            } else if (eventdata['xaxis.range']) {
                xStart = eventdata['xaxis.range'][0];
                xEnd = eventdata['xaxis.range'][1];
            } else {
                const currentRange = graphDiv.layout.xaxis.range;
                xStart = eventdata['xaxis.range[0]'] || currentRange[0];
                xEnd = eventdata['xaxis.range[1]'] || currentRange[1];
            }

            // Keep the overlay execution axis (x2) aligned with x.
            // We intentionally do NOT use `matches: "x"` on x2 so executions don't participate
            // in x-unified hover for the Bid/Ask traces.
            try {
                if (eventdata['xaxis.autorange']) {
                    Plotly.relayout(graphDiv, { 'xaxis2.autorange': true });
                } else {
                    Plotly.relayout(graphDiv, { 'xaxis2.range': [xStart, xEnd], 'xaxis2.autorange': false });
                }
            } catch (e) {
                // noop
            }

            const toTime = (val) => {
                if (typeof val === 'number') return val;
                let s = String(val).replace(' ', 'T');
                return new Date(s).getTime();
            };

            const tStart = toTime(xStart);
            const tEnd = toTime(xEnd);

            // Send range to Shiny for dynamic binning (Option B)
            // Thresholds: <40min -> 30s, 40-80min -> 1min, >80min -> 5min
            const rangeMins = (tEnd - tStart) / 60000;
            if (window.Shiny && !isNaN(rangeMins)) {
                const newBinSize = rangeMins > 80 ? '5min' : (rangeMins >= 40 ? '1min' : '30s');
                // Initialize _lastBinSize if not set (e.g., after re-render)
                if (!graphDiv._lastBinSize) {
                    // Get initial range from layout to determine current bin size
                    const layoutRange = graphDiv.layout.xaxis.range;
                    if (layoutRange) {
                        const initStart = toTime(layoutRange[0]);
                        const initEnd = toTime(layoutRange[1]);
                        const initMins = (initEnd - initStart) / 60000;
                        graphDiv._lastBinSize = initMins > 80 ? '5min' : (initMins >= 40 ? '1min' : '30s');
                    } else {
                        graphDiv._lastBinSize = '5min';
                    }
                }
                const prevBinSize = graphDiv._lastBinSize;
                if (newBinSize !== prevBinSize) {
                    graphDiv._lastBinSize = newBinSize;
                    // Send both range_mins and x_range for zoom preservation
                    Shiny.setInputValue('chart_range_mins', rangeMins);
                    Shiny.setInputValue('chart_x_range', [xStart, xEnd]);
                }
            }

            let minP = Infinity, maxP = -Infinity;
            let hasData = false;

            // Check bid/ask data
            for (let i = 0; i < times.length; i++) {
                const t = new Date(times[i]).getTime();
                if (t >= tStart && t <= tEnd) {
                    if (bids[i] < minP) minP = bids[i];
                    if (asks[i] > maxP) maxP = asks[i];
                    hasData = true;
                }
            }

            // Also check execution prices (trace index 2)
            if (traces.length > 2 && traces[2].y) {
                const execTimes = traces[2].x;
                const execPrices = traces[2].y;
                for (let i = 0; i < execTimes.length; i++) {
                    const t = new Date(execTimes[i]).getTime();
                    if (t >= tStart && t <= tEnd) {
                        if (execPrices[i] < minP) minP = execPrices[i];
                        if (execPrices[i] > maxP) maxP = execPrices[i];
                    }
                }
            }

            if (hasData) {
                const range = maxP - minP;
                const padding = Math.max(range * 0.10, 0.25);
                Plotly.relayout(graphDiv, {
                    'yaxis.range': [minP - padding, maxP + padding]
                });
            }
        });
    });
}

// Setup on load and after Shiny renders
setTimeout(setupRescaling, 1000);
$(document).on('shiny:value', function () {
    // Reset rescaling flag when chart updates
    document.querySelectorAll('.js-plotly-plot').forEach(div => {
        div._hasRescaling = false;
    });
    setTimeout(setupRescaling, 500);
    setTimeout(resizeAllPlotly, 600);
});

// Resize when switching navbar tabs (Chart tab becomes visible)
document.addEventListener('shown.bs.tab', function () {
    setTimeout(resizeAllPlotly, 100);
});

// Resize on window resize
window.addEventListener('resize', function () {
    resizeAllPlotly();
});