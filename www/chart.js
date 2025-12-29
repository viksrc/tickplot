// Dynamic Y-axis rescaling when range slider changes
function resizeAllPlotly() {
    // Dynamic Y-axis rescaling + dynamic volume bin selection.
    //
    // Notes on robustness:
    // - When loaded as an external file, this may execute before Plotly / Shiny bindings exist.
    // - Shiny for Python doesn't guarantee jQuery is present, so avoid $(document).on(...).
    // - Use MutationObserver to re-bind when Plotly graphs are (re)rendered.

    function _safePlotlyResize(graphDiv) {
        try {
            if (window.Plotly && Plotly.Plots && Plotly.Plots.resize) {
                Plotly.Plots.resize(graphDiv);
            }
        } catch (e) {
            // noop
        }
    }

    function resizeAllPlotly() {
        const plotDivs = document.querySelectorAll('.js-plotly-plot');
        plotDivs.forEach(_safePlotlyResize);
    }

    function _toEpochMs(val) {
        if (typeof val === 'number') return val;
        const s = String(val).replace(' ', 'T');
        return new Date(s).getTime();
    }

    function _bindRescaling(graphDiv) {
        if (!graphDiv || graphDiv._hasRescaling) return;
        if (typeof graphDiv.on !== 'function') return; // Plotly hasn't enhanced it yet.

        graphDiv._hasRescaling = true;

        // Ensure Plotly fits the container on first bind
        setTimeout(() => _safePlotlyResize(graphDiv), 50);

        graphDiv.on('plotly_relayout', function (eventdata) {
            // Detect changes on MAIN axis (xaxis) or SLIDER axis (xaxis3).
            // With matches='x', dragging xaxis3 syncs xaxis VISUALLY but does NOT fire xaxis events.
            // So we must explicitly check for xaxis3 changes.
            const isXChange = (
                eventdata['xaxis.range[0]'] ||
                eventdata['xaxis.range[1]'] ||
                eventdata['xaxis.range'] ||
                eventdata['xaxis.autorange']
            );
            const isX3Change = (
                eventdata['xaxis3.range[0]'] ||
                eventdata['xaxis3.range[1]'] ||
                eventdata['xaxis3.range'] ||
                eventdata['xaxis3.autorange']
            );
            if (!isXChange && !isX3Change) return;

            const traces = graphDiv.data;
            if (!traces || traces.length < 2) return;

            const times = traces[0].x;
            const bids = traces[0].y;
            const asks = traces[1].y;

            let xStart, xEnd;
            // Read range from eventdata first (the actual change), then layout as fallback.
            // When xaxis3 is set programmatically, layout.xaxis may not be synced yet.
            if (eventdata['xaxis.autorange'] || eventdata['xaxis3.autorange']) {
                xStart = times[0];
                xEnd = times[times.length - 1];
            } else if (eventdata['xaxis3.range']) {
                // xaxis3 event (slider) - use xaxis3 range directly
                xStart = eventdata['xaxis3.range'][0];
                xEnd = eventdata['xaxis3.range'][1];
            } else if (eventdata['xaxis.range']) {
                // xaxis event (main chart) - use xaxis range directly
                xStart = eventdata['xaxis.range'][0];
                xEnd = eventdata['xaxis.range'][1];
            } else if (eventdata['xaxis3.range[0]'] || eventdata['xaxis3.range[1]']) {
                const layoutRange = graphDiv.layout?.xaxis3?.range;
                xStart = eventdata['xaxis3.range[0]'] || (layoutRange ? layoutRange[0] : times[0]);
                xEnd = eventdata['xaxis3.range[1]'] || (layoutRange ? layoutRange[1] : times[times.length - 1]);
            } else {
                // Fallback to layout or eventdata fragments
                const currentRange = graphDiv.layout?.xaxis?.range;
                xStart = eventdata['xaxis.range[0]'] || (currentRange ? currentRange[0] : times[0]);
                xEnd = eventdata['xaxis.range[1]'] || (currentRange ? currentRange[1] : times[times.length - 1]);
            }

            // Keep overlay execution axis (x2) aligned with x.
            try {
                if (window.Plotly && Plotly.relayout) {
                    if (eventdata['xaxis.autorange'] || eventdata['xaxis3.autorange']) {
                        Plotly.relayout(graphDiv, { 'xaxis2.autorange': true });
                    } else {
                        Plotly.relayout(graphDiv, { 'xaxis2.range': [xStart, xEnd], 'xaxis2.autorange': false });
                    }
                }
            } catch (e) {
                // noop
            }

            const tStart = _toEpochMs(xStart);
            const tEnd = _toEpochMs(xEnd);
            const rangeMins = (tEnd - tStart) / 60000;

            // Dynamic bin switching - Thresholds: >160m=5min, 80-160m=2min, 40-80m=1min, <40m=30s
            if (window.Shiny && !Number.isNaN(rangeMins)) {
                const newBinSize = rangeMins > 160 ? '5min' : (rangeMins > 80 ? '2min' : (rangeMins >= 40 ? '1min' : '30s'));

                if (!graphDiv._lastBinSize) {
                    const layoutRange = graphDiv.layout?.xaxis?.range;
                    if (layoutRange && layoutRange.length === 2) {
                        const initMins = (_toEpochMs(layoutRange[1]) - _toEpochMs(layoutRange[0])) / 60000;
                        graphDiv._lastBinSize = initMins > 160 ? '5min' : (initMins > 80 ? '2min' : (initMins >= 40 ? '1min' : '30s'));
                    } else {
                        graphDiv._lastBinSize = '5min';
                    }
                }

                const prevBinSize = graphDiv._lastBinSize;
                if (newBinSize !== prevBinSize) {
                    graphDiv._lastBinSize = newBinSize;
                    Shiny.setInputValue('chart_range_mins', rangeMins);
                    Shiny.setInputValue('chart_x_range', [xStart, xEnd]);
                }
            }

            // Dynamic y-axis rescale (include executions)
            let minP = Infinity;
            let maxP = -Infinity;
            let hasData = false;

            for (let i = 0; i < times.length; i++) {
                const t = _toEpochMs(times[i]);
                if (t >= tStart && t <= tEnd) {
                    if (bids[i] < minP) minP = bids[i];
                    if (asks[i] > maxP) maxP = asks[i];
                    hasData = true;
                }
            }

            if (traces.length > 2 && traces[2].y && traces[2].x) {
                const execTimes = traces[2].x;
                const execPrices = traces[2].y;
                for (let i = 0; i < execTimes.length; i++) {
                    const t = _toEpochMs(execTimes[i]);
                    if (t >= tStart && t <= tEnd) {
                        if (execPrices[i] < minP) minP = execPrices[i];
                        if (execPrices[i] > maxP) maxP = execPrices[i];
                    }
                }
            }

            if (hasData && window.Plotly && Plotly.relayout) {
                const range = maxP - minP;
                const padding = Math.max(range * 0.10, 0.25);
                try {
                    Plotly.relayout(graphDiv, { 'yaxis.range': [minP - padding, maxP + padding] });
                } catch (e) {
                    // noop
                }
            }
        });
    }

    function setupRescaling() {
        document.querySelectorAll('.js-plotly-plot').forEach(_bindRescaling);
    }

    function _pokeRebindSoon() {
        // Don't clear _hasRescaling - the check in _bindRescaling prevents double-binding.
        // If Shiny replaces an element, the new element won't have the flag.
        setTimeout(setupRescaling, 250);
        setTimeout(resizeAllPlotly, 350);
    }

    function _installObserversOnce() {
        if (window.__chartRescaleObserverInstalled) return;
        window.__chartRescaleObserverInstalled = true;

        // Rebind when plotly widgets are added/updated.
        const obs = new MutationObserver((_mutations) => {
            // Quick debounce, but short enough not to miss events
            if (window.__chartRescaleRebindPending) return;
            window.__chartRescaleRebindPending = true;
            // Try to bind immediately (in case new chart is ready)
            setupRescaling();
            // Also schedule a backup in case chart isn't fully initialized yet
            setTimeout(() => {
                window.__chartRescaleRebindPending = false;
                setupRescaling();
                resizeAllPlotly();
            }, 50);
        });
        obs.observe(document.body, { childList: true, subtree: true });

        // Resize when switching bootstrap tabs (Chart becomes visible)
        document.addEventListener('shown.bs.tab', function () {
            setTimeout(resizeAllPlotly, 100);
        });

        window.addEventListener('resize', function () {
            resizeAllPlotly();
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        _installObserversOnce();
        // First bind (plotly may render slightly later)
        setTimeout(setupRescaling, 400);
        setTimeout(resizeAllPlotly, 600);
    });
}

resizeAllPlotly();

// Debounce search inputs (100ms delay to reduce re-renders on large datasets)
(function () {
    function setupSearchDebounce() {
        const searchInputs = document.querySelectorAll('.search-debounce input[type="text"]');
        searchInputs.forEach(function (input) {
            if (input._hasDebounce) return;
            input._hasDebounce = true;

            let debounceTimer = null;
            const originalValue = input.value;

            // Override Shiny's default input behavior
            input.addEventListener('input', function (e) {
                e.stopImmediatePropagation();

                if (debounceTimer) {
                    clearTimeout(debounceTimer);
                }

                debounceTimer = setTimeout(function () {
                    // Trigger Shiny update after 100ms delay
                    if (window.Shiny && Shiny.setInputValue) {
                        Shiny.setInputValue(input.id, input.value);
                    }
                }, 100);
            });
        });
    }

    // Setup on DOM ready and observe for dynamic additions
    document.addEventListener('DOMContentLoaded', function () {
        setupSearchDebounce();

        // Re-run when Shiny adds new elements
        const obs = new MutationObserver(function () {
            setupSearchDebounce();
        });
        obs.observe(document.body, { childList: true, subtree: true });
    });

    // Also try immediately (in case DOM is already ready)
    if (document.readyState !== 'loading') {
        setupSearchDebounce();
    }
})();

// Auto-select first row in orders_table when data loads or table re-renders
(function () {
    let lastTableInstance = null;

    function doAutoSelect(table) {
        if (!table) return;

        // Get active rows (visible after filters/sorts)
        const rows = table.getRows("active");
        if (rows && rows.length > 0) {
            // Select the first row
            rows[0].select();

            // Sync with Shiny so the chart and details update
            if (window.Shiny && window.Shiny.setInputValue) {
                setTimeout(() => {
                    const rowData = rows[0].getData();
                    window.Shiny.setInputValue('orders_table_row_clicked', rowData);
                }, 50);
            }
        }
    }

    function checkAndHook() {
        if (typeof Tabulator === 'undefined') return;

        // Correct way to find the instance in pytabulator
        const tables = Tabulator.findTable('#orders_table');
        if (!tables || tables.length === 0) return;

        const currentTable = tables[0];

        // Detect if Shiny replaced the table instance
        if (currentTable !== lastTableInstance) {
            lastTableInstance = currentTable;

            // Hook for future data updates (SQL filters, etc)
            currentTable.on("dataLoaded", function () {
                doAutoSelect(currentTable);
            });

            // Initial selection
            doAutoSelect(currentTable);
        }
    }

    // Poll to catch re-renders
    setInterval(checkAndHook, 300);
})();
