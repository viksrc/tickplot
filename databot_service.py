
import os
import logging
import re
import plotly.graph_objects as go
from pathlib import Path
from chatlas import ChatOpenRouter
from typing import Any, Callable, Optional, Union
import json
import dotenv

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

class DatabotService:
    def __init__(self, data_service: Any, session_id: str = "", model: str = "deepseek/deepseek-v3.2"):
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

        # Render template variables ({{ ... }})
        schema = self._build_schema_text("orders")
        variables = {
            "SCHEMA": schema,
            "SESSION_ID": self.session_id or "",
        }

        def _replace(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            return variables.get(key, match.group(0))

        content = re.sub(r"{{\s*([A-Z0-9_]+)\s*}}", _replace, content)
            
        # Inject session context (only if not already provided via {{ SESSION_ID }})
        if self.session_id and "SYSTEM CONTEXT:" not in content:
            content += f"\n\nSYSTEM CONTEXT:\nYour Session ID is: {self.session_id}\n"
            content += f"Always allow this ID when fetching data: http://127.0.0.1:8000/orders?session_id={self.session_id}\n"
        
        logger.info(f"DatabotService system prompt loaded (model={self.model}, session={self.session_id})")
        logger.debug(f"DatabotService full prompt:\n{content[:500]}...")  # Log first 500 chars to avoid spam
             
        return content

    def _build_schema_text(self, table_name: str) -> str:
        """Build a simple schema block from the underlying data service.

        This is intentionally similar to NLService's schema text, but kept local to avoid
        coupling between NLService and DatabotService.
        """

        base_orders = getattr(self.data_service, "base_orders", None)
        if base_orders is None:
            return f"Table: {table_name}\nColumns:\n- (schema unavailable)"

        # base_orders is typically a Polars DataFrame in this app.
        try:
            import polars as pl

            if isinstance(base_orders, pl.DataFrame):
                schema_lines = [f"Table: {table_name}", "Columns:"]
                for col, dtype in base_orders.schema.items():
                    sql_type = "TEXT"
                    if dtype.is_integer():
                        sql_type = "INTEGER"
                    elif dtype.is_float():
                        sql_type = "FLOAT"
                    elif dtype == pl.Boolean:
                        sql_type = "BOOLEAN"
                    elif dtype == pl.Datetime:
                        sql_type = "DATETIME"
                    schema_lines.append(f"- {col} ({sql_type})")
                return "\n".join(schema_lines)
        except Exception:
            # Fall through to generic schema below.
            pass

        # Generic fallback for pandas-like objects
        try:
            cols = list(getattr(base_orders, "columns", []))
            if cols:
                schema_lines = [f"Table: {table_name}", "Columns:"]
                schema_lines.extend([f"- {c} (TEXT)" for c in cols])
                return "\n".join(schema_lines)
        except Exception:
            pass

        return f"Table: {table_name}\nColumns:\n- (schema unavailable)"

    def register_plot_callback(self, callback: Callable[[go.Figure], Any]):
        self._plot_callback = callback

    async def register_tools(self):
        # Register local display tools (kept for manual use if needed)
        self.session.register_tool(self.display_plot)
        
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

