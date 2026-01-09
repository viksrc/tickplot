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

    // Helper to add minutes to an ISO date string and return the result in the same format
    // This avoids timezone issues from toISOString() which converts to UTC
    function _addMinsToIsoString(isoStr, mins) {
        // Parse the date parts directly from the string (format: YYYY-MM-DDTHH:MM:SS)
        const match = isoStr.match(/(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
        if (!match) return isoStr;

        let [, year, month, day, hour, minute, second] = match.map(Number);

        // Add minutes
        minute += mins;

        // Handle overflow/underflow
        while (minute >= 60) {
            minute -= 60;
            hour += 1;
        }
        while (minute < 0) {
            minute += 60;
            hour -= 1;
        }
        while (hour >= 24) {
            hour -= 24;
            day += 1;
        }
        while (hour < 0) {
            hour += 24;
            day -= 1;
        }
        // Note: Simplified - doesn't handle month/year overflow but works for intraday trading

        const pad = n => String(n).padStart(2, '0');
        return `${year}-${pad(month)}-${pad(day)}T${pad(hour)}:${pad(minute)}:${pad(second)}`;
    }

    // Helper to calculate bin size for a given range in minutes
    function _getBinSizeForRange(rangeMins) {
        if (rangeMins > 160) return '5min';
        if (rangeMins > 80) return '2min';
        if (rangeMins >= 40) return '1min';
        return '30s';
    }

    function _bindRescaling(graphDiv) {
        if (!graphDiv || typeof graphDiv.on !== 'function') return; // Plotly hasn't enhanced it yet.

        // Helper to update button visual selection state
        function _updateButtonSelectionUI() {
            if (!graphDiv.layout?.updatemenus?.[0]?.buttons) return;
            
            const buttons = graphDiv.layout.updatemenus[0].buttons;
            const anchor = graphDiv._anchor || "first";
            const duration = graphDiv._selectedDuration;
            
            buttons.forEach((btn, idx) => {
                const args = btn.args?.[0];
                if (!args || !args.action) return;
                
                let isActive = false;
                if (args.action === "anchor") {
                    isActive = (args.anchor === anchor);
                } else if (args.action === "duration") {
                    isActive = (args.mins === duration);
                }
                
                // Update button styling
                if (isActive) {
                    btn.bgcolor = "#90EE90";
                    btn.font = { color: "black", weight: 600 };
                } else {
                    btn.bgcolor = null;
                    btn.font = null;
                }
            });
            
            // Apply the layout update
            try {
                if (window.Plotly && Plotly.update) {
                    Plotly.update(graphDiv, {}, { 'updatemenus[0].buttons': buttons });
                }
            } catch (e) {
                // noop
            }
        }

        // Always update order key from metadata (order can change without rebind)
        const newOrderKey = graphDiv.layout?.meta?.orderKey;
        if (newOrderKey && newOrderKey !== graphDiv._currentOrderKey) {
            graphDiv._currentOrderKey = newOrderKey;
            // Reset button state for new order
            const storedState = sessionStorage.getItem('chartButtonState_' + newOrderKey);
            const savedState = storedState ? JSON.parse(storedState) : null;
            graphDiv._anchor = savedState?.anchor || "first";
            graphDiv._selectedDuration = savedState?.duration || null;
            
            // Update button visual state to match reset state
            setTimeout(() => _updateButtonSelectionUI(), 50);
        }

        // Only bind event handlers once
        if (graphDiv._hasRescaling) return;
        graphDiv._hasRescaling = true;

        // Ensure Plotly fits the container on first bind
        setTimeout(() => _safePlotlyResize(graphDiv), 50);

        // Helper for slider/zoom Y-axis rescaling (NOT used for buttons - server handles those)
        function _rescaleYAxisToEpochRange(graphDiv, tStart, tEnd) {
            const traces = graphDiv.data;
            if (!traces || traces.length < 2) return;

            const times = traces[0].x;
            const bids = traces[0].y;
            const asks = traces[1].y;
            if (!times || !bids || !asks) return;

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

            // Include executions (if present)
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
        }

        // Helper to get current order key (may change without rebind)
        function _getOrderKey() {
            return graphDiv._currentOrderKey || 'default';
        }

        function _saveButtonState() {
            const orderKey = _getOrderKey();
            const state = { anchor: graphDiv._anchor, duration: graphDiv._selectedDuration };
            sessionStorage.setItem('chartButtonState_' + orderKey, JSON.stringify(state));
        }

        // Handle button clicks - buttons use method="skip" so we control the behavior
        // ALL button actions are handled server-side to ensure atomic updates of:
        // - bin size (if changed)
        // - x-axis range
        // - y-axis range (computed for the new x-range)
        graphDiv.on('plotly_buttonclicked', function (eventdata) {
            if (!eventdata || !eventdata.button || !eventdata.button.args) return;

            const args = eventdata.button.args[0];
            if (!args || !args.action) return;

            // Update local anchor/duration state for UI consistency
            if (args.action === "anchor") {
                graphDiv._anchor = args.anchor;
            } else if (args.action === "duration") {
                graphDiv._selectedDuration = args.mins;
            } else if (args.action === "all") {
                graphDiv._anchor = "first";
                graphDiv._selectedDuration = null;
            }

            // Save state for persistence across re-renders
            _saveButtonState();
            
            // Update button visual selection (defined in _bindRescaling scope)
            if (typeof _updateButtonSelectionUI === 'function') {
                _updateButtonSelectionUI();
            }

            // Send button action to server - server will compute range and update chart atomically
            if (window.Shiny) {
                const orderKey = graphDiv._currentOrderKey || null;
                Shiny.setInputValue('chart_button', {
                    action: args.action,
                    anchor: graphDiv._anchor,
                    duration: graphDiv._selectedDuration,
                    mins: args.mins || null,
                    orderKey: orderKey,
                    timestamp: Date.now()
                });
            }
        });

        // NOTE: plotly_afterplot is no longer needed for button-driven updates.
        // Server now handles all button actions atomically (bin change + x-range + y-range).
        // The plotly_relayout handler below still handles slider/zoom interactions.

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

            // Dynamic bin switching and range syncing
            if (window.Shiny && !Number.isNaN(rangeMins)) {
                // 1. Determine the correct bin size for this range
                const newBinSize = rangeMins > 160 ? '5min' : (rangeMins > 80 ? '2min' : (rangeMins >= 40 ? '1min' : '30s'));

                // Initialize tracking flags from server-rendered bin size (stored in metadata)
                if (!graphDiv._lastBinSize) {
                    // Use the bin size the server rendered with, NOT the current view range
                    const serverBinSize = graphDiv.layout?.meta?.binSize;
                    if (serverBinSize) {
                        graphDiv._lastBinSize = serverBinSize;
                    } else {
                        // Fallback: calculate from initial layout range
                        const layoutRange = graphDiv.layout?.xaxis?.range;
                        if (layoutRange && layoutRange.length === 2) {
                            const iMins = (_toEpochMs(layoutRange[1]) - _toEpochMs(layoutRange[0])) / 60000;
                            graphDiv._lastBinSize = iMins > 160 ? '5min' : (iMins > 80 ? '2min' : (iMins >= 40 ? '1min' : '30s'));
                        } else {
                            graphDiv._lastBinSize = '5min';
                        }
                    }
                }

                // 2. Handle Bin Size Changes - ONLY send to server when bin size changes
                if (newBinSize !== graphDiv._lastBinSize) {
                    if (graphDiv._binChangeTimeout) clearTimeout(graphDiv._binChangeTimeout);

                    graphDiv._binChangeTimeout = setTimeout(() => {
                        graphDiv._lastBinSize = newBinSize;
                        const orderKey = graphDiv._currentOrderKey || null;

                        // Bundle everything into one message to avoid race conditions
                        Shiny.setInputValue('chart_state', {
                            rangeMins: rangeMins,
                            xRange: [xStart, xEnd],
                            orderKey: orderKey,
                            timestamp: Date.now()
                        });
                    }, 100);
                }
                // Range-only changes: DO NOT send to server - Plotly handles view client-side
                // Sending chart_state for every pan/zoom causes unnecessary server re-renders
            }

                // Dynamic y-axis rescale (include executions)
                _rescaleYAxisToEpochRange(graphDiv, tStart, tEnd);
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
