#!/usr/bin/env python3
"""Debug script to check actual rangeslider handle positions"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from playwright.sync_api import sync_playwright

def check_rangeslider():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Start the app manually first: cd /Users/vivek/projects/shinytheme && shiny run app.py
        page.goto("http://localhost:8000")
        
        page.locator("#query_btn").click()
        page.wait_for_timeout(1000)
        
        first_row = page.locator("#orders_table .tabulator-row").first
        first_row.click()
        page.wait_for_timeout(500)
        
        page.get_by_text("Chart", exact=True).click()
        page.wait_for_timeout(2000)
        
        # Check Plotly layout values
        layout_values = page.evaluate("""() => {
            const gd = document.querySelector("#order_chart .js-plotly-plot");
            return {
                xaxis_range: gd?.layout?.xaxis?.range,
                xaxis3_range: gd?.layout?.xaxis3?.range,
                xaxis3_autorange: gd?.layout?.xaxis3?.autorange,
            };
        }""")
        
        print("=== Plotly Layout Values ===")
        print(f"xaxis.range (main view):   {layout_values['xaxis_range']}")
        print(f"xaxis3.range (slider):     {layout_values['xaxis3_range']}")
        print(f"xaxis3.autorange:          {layout_values['xaxis3_autorange']}")
        
        # Check actual rangeslider DOM positions
        slider_info = page.evaluate("""() => {
            const slider = document.querySelector('.rangeslider-slidebox');
            if (!slider) return {error: "Slider not found"};
            
            const rect = slider.getBoundingClientRect();
            const parent = slider.parentElement;
            const parentRect = parent.getBoundingClientRect();
            
            return {
                sliderLeft: rect.left - parentRect.left,
                sliderWidth: rect.width,
                parentWidth: parentRect.width,
                leftPercent: ((rect.left - parentRect.left) / parentRect.width * 100).toFixed(2),
                rightPercent: (((rect.left - parentRect.left + rect.width) / parentRect.width) * 100).toFixed(2),
            };
        }""")
        
        print("\n=== Visual Rangeslider Position ===")
        print(f"Slider box info: {slider_info}")
        
        print("\nPress Enter to close...")
        input()
        browser.close()

if __name__ == "__main__":
    check_rangeslider()
