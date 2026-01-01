
import os
import logging
import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from chatlas import ChatOpenRouter
from typing import Any, Callable, Optional, Union
import json
import dotenv
import sys

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

class DatabotService:
    def __init__(self, data_service: Any, session_id: str = "", model: str = "deepseek/deepseek-v3.1-terminus"):
        self.data_service = data_service
        self.session_id = session_id
        self.model = model
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        
        # Load system prompt
        self.system_prompt = self._load_system_prompt()
        
        self.session = ChatOpenRouter(
            system_prompt=self.system_prompt,
            model=self.model,
            api_key=self.api_key
        )
        
        # Callback for updating the UI with a plot or HTML
        self._plot_callback: Optional[Callable[[Union[go.Figure, str]], Any]] = None

    def _load_system_prompt(self) -> str:
        # Load schema from data service to inject into prompt
        # We'll stick to a sample or basic schema for now to avoid huge tokens
        # Or better: inspect the current data.
        # For now, similar to NLService, we can inject schema if needed, 
        # but the prompt we created is generic.
        
        prompt_path = Path(__file__).parent / "databotprompt.md"
        if not prompt_path.exists():
            return "You are Databot, a helpful data assistant."
            
        with open(prompt_path, "r") as f:
            content = f.read()
            
        # Inject session context
        if self.session_id:
             content += f"\n\nSYSTEM CONTEXT:\nYour Session ID is: {self.session_id}\n"
             content += f"Always allow this ID when fetching data: http://127.0.0.1:8000/orders?session_id={self.session_id}\n"
             
        return content

    def register_plot_callback(self, callback: Callable[[go.Figure], Any]):
        self._plot_callback = callback

    async def register_tools(self):
        # Register local display tools (kept for manual use if needed)
        self.session.register_tool(self.display_plot)
        self.session.register_tool(self.display_html)
        
        # Register the Pydantic mcp-run-python server via Deno
        await self.session.register_mcp_tools_stdio_async(
            command="/opt/homebrew/bin/deno",
            args=[
                "run", "-N", "-R=node_modules", "-W=node_modules", "--node-modules-dir=auto",
                "jsr:@pydantic/mcp-run-python", "stdio"
            ],
        )
        
        # Auto-display HTML from run_python_code results
        @self.session.on_tool_result
        async def auto_display_html(content):
            """Automatically display HTML content from run_python_code output."""
            # ContentToolResult has: value, error, extra, request (ContentToolRequest)
            request = getattr(content, 'request', None)
            tool_name = getattr(request, 'name', '') if request else ''

            # Check for errors
            if getattr(content, 'error', None):
                logger.error(f"Tool execution error: {content.error}")
            
            if tool_name == "run_python_code" and self._plot_callback:
                result_value = getattr(content, 'value', None)
                result_str = str(result_value) if result_value else ""
                
                # Look for Plotly HTML patterns
                has_plotly_html = 'PlotlyConfig' in result_str or 'Plotly.newPlot' in result_str
                
                if has_plotly_html:
                    match = None
                    
                    # Pattern 1: Full Plotly with PlotlyConfig (include_plotlyjs='cdn')
                    if 'PlotlyConfig' in result_str:
                        match = re.search(r'(<div>\s*<script[^>]*>window\.PlotlyConfig.*?</script>\s*</div>)', result_str, re.DOTALL)
                    
                    # Pattern 2: Look for plotly-graph-div with surrounding structure
                    if not match and 'plotly-graph-div' in result_str:
                        match = re.search(r'(<div[^>]*class="plotly-graph-div"[^>]*>.*?</div>\s*<script[^>]*>.*?Plotly\.newPlot.*?</script>)', result_str, re.DOTALL)
                    
                    # Pattern 3: Just find any div containing Plotly.newPlot script
                    if not match and 'Plotly.newPlot' in result_str:
                        match = re.search(r'(<div>.*?Plotly\.newPlot.*?</script>\s*</div>)', result_str, re.DOTALL)
                    
                    if match:
                        html_content = match.group(1) if match.lastindex else match.group(0)
                            
                        # Wrap in div if missing
                        if not html_content.strip().startswith('<div'):
                            html_content = f"<div>{html_content}</div>"
                            
                        logger.debug(f"Extracted Plotly HTML ({len(html_content)} chars)")
                        try:
                            await self._plot_callback(html_content)
                        except Exception as e:
                            logger.error(f"Error calling plot callback: {e}", exc_info=True)

    async def perform_chat(self, user_input: str, chat_ui_obj: Any):
        # Stream the response
        stream = await self.session.stream_async(user_input, content="all")
        await chat_ui_obj.append_message_stream(stream)



    async def display_plot(self, filepath: str) -> str:
        """
        Displays a saved plot file in the application UI.
        Call this tool immediately after run_python returns a saved plot file path.
        """
        try:
            if not os.path.exists(filepath):
                return f"Error: File {filepath} not found."
                
            # Read JSON and parse into Figure
            with open(filepath, "r") as f:
                fig_dict = json.load(f)
                fig = go.Figure(fig_dict)
                
            if self._plot_callback:
                await self._plot_callback(fig)
                return "Plot successfully displayed in the Analysis Result panel."
            else:
                return "Plot loaded but display callback not registered."
        except Exception as e:
            return f"Error displaying plot: {str(e)}"
    async def display_html(self, html_str: str) -> str:
        """
        Displays raw HTML content in the application UI.
        Use this to render interactive Plotly charts or custom data visualizations
        generated as HTML strings.
        """
        try:
            if self._plot_callback:
                await self._plot_callback(html_str)
                return "Content successfully displayed in the Analysis Result panel."
            else:
                return "Display callback not registered."
        except Exception as e:
            return f"Error displaying content: {str(e)}"

