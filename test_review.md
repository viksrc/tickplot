# Test Review: Plotly Internal Checks vs DOM/End-to-End Tests

## Summary
This document identifies tests that are checking Plotly's internal data structures instead of verifying what's actually displayed in the DOM. These tests can **falsely pass** because they verify data was sent to Plotly, but not that it was actually rendered correctly.

---

## 🔴 SUSPECT TESTS - Checking Plotly Internals (NOT End-to-End)

### 1. `test_order_visualizer_navigation` (Lines 55-247)
**Status**: ❌ **HIGHLY SUSPECT**

**Problems**:
- **Lines 139-155**: Directly accesses `plotlyDiv.data` to get trace information
- **Lines 166-178**: Checks trace names by inspecting `plotlyDiv.data.map(trace => trace.name)`
- **Lines 184-199**: Compares execution count from Plotly data (`exec_trace['x_count']`) vs expected count
- **Lines 204-231**: Compares bid/ask point counts from Plotly data structure

**Why it's suspect**:
- Verifies data was **sent to Plotly**, not that it was **rendered in the DOM**
- Could pass even if Plotly fails to render the traces
- Not testing what the user actually sees

**Recommendation**: 
- Replace with DOM-based checks (e.g., count actual SVG elements like `.scatterpts .point`)
- Verify visible elements in the chart SVG, not the JavaScript data structure

---

### 2. `test_stock_chart_existence` (Lines 415-481)
**Status**: ⚠️ **PARTIALLY SUSPECT**

**Problems**:
- **Lines 441-447**: Accesses `gd.data` to filter and map marker traces
- **Lines 452-456**: Checks if Start/End traces exist in Plotly data
- **Lines 458-481**: Extracts times from trace x values (Plotly internal data)

**Why it's suspect**:
- Checks Plotly's data structure for Start/End markers
- Doesn't verify the markers are actually visible in the DOM
- Could pass if data is correct but rendering fails

**Recommendation**:
- Verify Start/End markers exist as visible SVG elements (e.g., `.scatterpts .point` with specific classes)
- Check DOM for visible marker elements, not Plotly data

---

### 3. `test_range_slider_presence` (Lines 566-581)
**Status**: ⚠️ **PARTIALLY SUSPECT**

**Problems**:
- **Lines 575-580**: Checks `gd.layout.xaxis3.rangeslider.visible` (Plotly internal)
- **Line 581**: Does check `.rangeslider-container` visibility (✅ Good!)

**Why it's partially suspect**:
- First check is against Plotly config, not rendered output
- Second check is good (DOM-based)

**Recommendation**:
- Keep the DOM check (line 581)
- Remove or de-emphasize the Plotly layout check (lines 575-580)

---

### 4. `test_range_slider_initial_range` (Lines 584-633)
**Status**: ❌ **HIGHLY SUSPECT**

**Problems**:
- **Line 617**: Accesses `gd.layout.xaxis3.range` (Plotly internal)
- **Lines 620-629**: Parses and validates range from Plotly layout object

**Why it's suspect**:
- Checks Plotly's internal range configuration
- Doesn't verify the slider handle is actually positioned correctly in the DOM
- Could pass if config is correct but rendering fails

**Recommendation**:
- Check actual slider handle position in the DOM (SVG elements)
- Verify visual position of the range selector handles

---

### 5. `test_range_slider_dynamic_binning` (Lines 636-808)
**Status**: ❌ **HIGHLY SUSPECT**

**Problems**:
- **Lines 662-682**: `get_current_bin_duration()` reads `barTrace.customdata` from Plotly data
- **Lines 684-727**: `wait_for_bin_duration()` checks `barTrace.customdata` in JavaScript
- **Lines 731-807**: All test steps use `page.evaluate()` to check Plotly data structure

**Why it's suspect**:
- Entirely based on checking Plotly's `customdata` field
- Doesn't verify the actual bar widths or labels displayed in the DOM
- Could pass if data is correct but bars render incorrectly

**Recommendation**:
- Hover over bars and check the actual tooltip text displayed
- Verify bar widths visually or through SVG element inspection
- Check rendered hover labels, not internal data

---

### 6. `test_range_slider_yaxis_rescaling` (Lines 810-865)
**Status**: ❌ **HIGHLY SUSPECT**

**Problems**:
- **Line 827**: Reads `gd.layout.yaxis.range` (Plotly internal)
- **Lines 837-847**: Waits for y-axis range to change in Plotly layout
- **Line 849**: Reads new y-axis range from Plotly layout
- **Lines 852-862**: Debug info from Plotly layout object

**Why it's suspect**:
- Checks Plotly's internal y-axis range configuration
- Doesn't verify the actual y-axis labels or tick marks in the DOM
- Could pass if layout is updated but rendering fails

**Recommendation**:
- Check actual y-axis tick labels in the DOM
- Verify visible tick marks and their values
- Compare before/after tick positions visually

---

### 7. `test_volume_split_and_tooltip` (Lines 868-948)
**Status**: ⚠️ **PARTIALLY SUSPECT**

**Problems**:
- **Lines 888-899**: Accesses `el.data` to get trace information
- **Lines 904-911**: Checks trace existence and type from Plotly data
- **Lines 914-918**: Checks `layout.barmode` from Plotly layout
- **Lines 922-932**: Validates hover template from Plotly data
- **Lines 935-947**: Checks bar values from `trace.y` (Plotly data)

**Why it's suspect**:
- Checks Plotly data structure for traces, hover templates, and values
- Doesn't actually hover and verify the displayed tooltip
- Could pass if data is correct but tooltip rendering fails

**Recommendation**:
- Actually hover over bars and capture the displayed tooltip text
- Verify stacked bar appearance in the DOM (SVG elements)
- Check visible bar heights, not data values

---

### 8. `test_slider_exact_range` (Lines 950-1006)
**Status**: ❌ **HIGHLY SUSPECT**

**Problems**:
- **Line 987**: Reads `gd.layout.xaxis3.range` (Plotly internal)
- **Lines 998-999**: Asserts handle range from Plotly layout
- **Lines 1002-1005**: Checks chart range from Plotly layout

**Why it's suspect**:
- Entirely based on Plotly layout object
- Doesn't verify slider handle visual position
- Could pass if layout is correct but rendering fails

**Recommendation**:
- Check actual slider handle position in the DOM
- Verify visual range selector appearance

---

## ✅ GOOD TESTS - Checking DOM/Actual Display

### 1. `test_settings_interaction` (Lines 249-269)
**Status**: ✅ **GOOD**
- Uses Shiny controllers to interact with UI elements
- Checks actual switch states and mode changes
- End-to-end verification

### 2. `test_order_detail_features` (Lines 272-314)
**Status**: ✅ **GOOD**
- Checks visible table rows and content
- Verifies scroll behavior (DOM-based)
- Compares displayed text values

### 3. `test_fill_details_features` (Lines 317-345)
**Status**: ✅ **GOOD**
- Checks visible table content
- Validates displayed values
- DOM-based verification

### 4. `test_venue_table_features` (Lines 348-376)
**Status**: ✅ **GOOD**
- Checks visible table rows
- Validates displayed percentages
- DOM-based verification

### 5. `test_chart_metrics_features` (Lines 379-412)
**Status**: ✅ **GOOD**
- Checks visible metric chips
- Validates displayed text content
- DOM-based verification

### 6. `test_volume_chart_open_label` (Lines 484-520)
**Status**: ✅ **MOSTLY GOOD**
- Hovers over actual bar element
- Checks displayed tooltip text
- End-to-end interaction test
- **Minor issue**: Line 499 uses `.trace.bars` selector which is Plotly-specific, but then checks actual DOM elements

### 7. `test_volume_chart_close_label` (Lines 524-563)
**Status**: ✅ **MOSTLY GOOD**
- Hovers over actual bar element
- Checks displayed tooltip text
- End-to-end interaction test
- **Minor issue**: Line 539 uses `.trace.bars` selector which is Plotly-specific, but then checks actual DOM elements

---

## Recommendations Summary

### High Priority Fixes:
1. **`test_order_visualizer_navigation`**: Replace Plotly data checks with SVG element counts
2. **`test_range_slider_dynamic_binning`**: Hover and check actual tooltip text instead of customdata
3. **`test_range_slider_yaxis_rescaling`**: Check actual y-axis tick labels in DOM
4. **`test_slider_exact_range`**: Verify slider handle visual position, not layout config

### Medium Priority Fixes:
5. **`test_stock_chart_existence`**: Check for visible marker SVG elements
6. **`test_range_slider_initial_range`**: Verify slider handle DOM position
7. **`test_volume_split_and_tooltip`**: Actually hover and verify displayed tooltips

### Pattern to Follow:
Instead of:
```javascript
const traces = gd.data.filter(t => t.name === 'Bid');
verify(traces.length > 0, "Bid trace exists");
```

Do this:
```javascript
// Check actual rendered elements
const bidPoints = page.locator('.scatterpts .point[data-trace-name="Bid"]');
expect(bidPoints.first).to_be_visible();
```

### Key Principle:
**Test what the user sees, not what the code sends to Plotly.**

If Plotly has a bug or rendering issue, tests checking internal data structures will pass, but the user will see broken charts. DOM-based tests will catch these issues.
