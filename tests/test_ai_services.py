"""Comprehensive tests for AI services (NLService and DatabotService)."""

import pytest
import polars as pl
import pandas as pd
import os
import re
import json
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock, patch, mock_open
from typing import Any


# Test fixtures
@pytest.fixture
def sample_polars_df():
    """Create a sample Polars DataFrame for testing."""
    return pl.DataFrame({
        "orderid": ["oid001", "oid002", "oid003"],
        "Ticker": ["AAPL", "GOOGL", "MSFT"],
        "ExecQty": [1000, 2000, 1500],
        "PerfArrival": [1.5, -0.5, 2.3],
        "Date": ["2025-01-01", "2025-01-02", "2025-01-03"],
        "Side": ["Buy", "Sell", "Buy"],
        "IsActive": [True, False, True],
    })


@pytest.fixture
def sample_pandas_df():
    """Create a sample Pandas DataFrame for testing."""
    return pd.DataFrame({
        "orderid": ["oid001", "oid002", "oid003"],
        "Ticker": ["AAPL", "GOOGL", "MSFT"],
        "ExecQty": [1000, 2000, 1500],
    })


@pytest.fixture
def mock_data_service(sample_polars_df):
    """Mock DataService for DatabotService tests."""
    service = Mock()
    service.base_orders = sample_polars_df
    return service


@pytest.fixture
def sample_nl_prompt():
    """Sample NL service prompt template."""
    return """You are a SQL assistant.

Schema:
{{ SCHEMA }}

Please help with queries."""


@pytest.fixture
def sample_databot_prompt():
    """Sample Databot service prompt template."""
    return """You are Databot.

Available data:
{{ SCHEMA }}

Session: {{ SESSION_ID }}

Ready to assist!"""


# ==============================================================================
# NLService Tests
# ==============================================================================

class TestNLService:
    """Tests for NLService class."""

    def test_pl_to_schema_basic_types(self, sample_polars_df):
        """Test schema generation from Polars DataFrame with various types."""
        from nl_service import NLService

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("nl_service.ChatOpenRouter"):
            service = NLService(sample_polars_df)
            schema = service._pl_to_schema(sample_polars_df, "orders")

        # Verify schema structure
        assert "Table: orders" in schema
        assert "Columns:" in schema

        # Verify column types
        assert "orderid (TEXT)" in schema
        assert "ExecQty (INTEGER)" in schema
        assert "PerfArrival (FLOAT)" in schema
        assert "IsActive (BOOLEAN)" in schema

    def test_pl_to_schema_categorical_values(self, sample_polars_df):
        """Test schema includes categorical values for text columns with few unique values."""
        from nl_service import NLService

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("nl_service.ChatOpenRouter"):
            service = NLService(sample_polars_df)
            schema = service._pl_to_schema(sample_polars_df, "orders")

        # Side has only 2 unique values, should show categorical
        assert "Side (TEXT)" in schema
        assert "Categorical values:" in schema
        assert "'Buy'" in schema
        assert "'Sell'" in schema

    def test_pl_to_schema_numeric_ranges(self, sample_polars_df):
        """Test schema includes min/max ranges for numeric columns."""
        from nl_service import NLService

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("nl_service.ChatOpenRouter"):
            service = NLService(sample_polars_df)
            schema = service._pl_to_schema(sample_polars_df, "orders")

        # Check for range information
        assert "ExecQty (INTEGER)" in schema
        assert "Range:" in schema
        assert "1000 to 2000" in schema

    def test_build_system_prompt_template_replacement(self, sample_polars_df, sample_nl_prompt):
        """Test system prompt template variable replacement."""
        from nl_service import NLService

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("nl_service.ChatOpenRouter"), \
             patch("builtins.open", mock_open(read_data=sample_nl_prompt)):
            service = NLService(sample_polars_df)
            prompt = service._build_system_prompt()

        # Verify template variable was replaced
        assert "{{ SCHEMA }}" not in prompt
        assert "Table: orders" in prompt
        assert "Columns:" in prompt

    def test_build_system_prompt_missing_file(self, sample_polars_df):
        """Test system prompt generation when prompt file is missing."""
        from nl_service import NLService

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("nl_service.ChatOpenRouter"), \
             patch("pathlib.Path.exists", return_value=False):
            service = NLService(sample_polars_df)
            prompt = service._build_system_prompt()

        # Should return fallback prompt
        assert "You are a SQL assistant" in prompt
        assert "Schema:" in prompt

    def test_register_tools(self, sample_polars_df):
        """Test tool registration."""
        from nl_service import NLService

        mock_session = Mock()
        update_fn = Mock()
        query_fn = Mock()

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("nl_service.ChatOpenRouter", return_value=mock_session):
            service = NLService(sample_polars_df)
            service.register_tools(update_fn, query_fn)

        # Verify tools were registered
        assert mock_session.register_tool.call_count == 2
        mock_session.register_tool.assert_any_call(update_fn)
        mock_session.register_tool.assert_any_call(query_fn)

    @pytest.mark.asyncio
    async def test_perform_chat(self, sample_polars_df):
        """Test chat streaming."""
        from nl_service import NLService

        mock_session = Mock()
        mock_stream = AsyncMock()
        mock_session.stream_async = AsyncMock(return_value=mock_stream)

        mock_chat_ui = AsyncMock()

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("nl_service.ChatOpenRouter", return_value=mock_session):
            service = NLService(sample_polars_df)
            await service.perform_chat("test query", mock_chat_ui)

        # Verify stream was created and passed to UI
        mock_session.stream_async.assert_called_once_with("test query", echo="all")
        mock_chat_ui.append_message_stream.assert_called_once_with(mock_stream)

    def test_initialization_without_api_key(self, sample_polars_df):
        """Test initialization without OPENROUTER_API_KEY."""
        from nl_service import NLService

        with patch.dict(os.environ, {}, clear=True), \
             patch("nl_service.ChatOpenRouter") as mock_chat:
            service = NLService(sample_polars_df)

        # Service should still initialize, but api_key will be None
        assert service.api_key is None


# ==============================================================================
# DatabotService Tests
# ==============================================================================

class TestDatabotService:
    """Tests for DatabotService class."""

    def test_build_schema_text_polars(self, mock_data_service):
        """Test schema generation from Polars DataFrame."""
        from databot_service import DatabotService

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_data_service, session_id="test123")
            schema = service._build_schema_text("orders")

        # Verify schema structure
        assert "Table: orders" in schema
        assert "Columns:" in schema
        assert "orderid (TEXT)" in schema
        assert "ExecQty (INTEGER)" in schema
        assert "PerfArrival (FLOAT)" in schema

    def test_build_schema_text_pandas_fallback(self, sample_pandas_df):
        """Test schema generation fallback for pandas-like objects."""
        from databot_service import DatabotService

        mock_service = Mock()
        mock_service.base_orders = sample_pandas_df

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_service, session_id="test123")
            schema = service._build_schema_text("orders")

        # Should fall back to generic schema
        assert "Table: orders" in schema
        assert "Columns:" in schema

    def test_build_schema_text_no_data(self):
        """Test schema generation when no data is available."""
        from databot_service import DatabotService

        mock_service = Mock()
        mock_service.base_orders = None

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_service, session_id="test123")
            schema = service._build_schema_text("orders")

        # Should return unavailable message
        assert "schema unavailable" in schema

    def test_load_system_prompt_template_replacement(self, mock_data_service, sample_databot_prompt):
        """Test system prompt template variable replacement."""
        from databot_service import DatabotService

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"), \
             patch("builtins.open", mock_open(read_data=sample_databot_prompt)):
            service = DatabotService(mock_data_service, session_id="session456")
            prompt = service._load_system_prompt()

        # Verify template variables were replaced
        assert "{{ SCHEMA }}" not in prompt
        assert "{{ SESSION_ID }}" not in prompt
        assert "Table: orders" in prompt
        assert "session456" in prompt

    def test_load_system_prompt_missing_file(self, mock_data_service):
        """Test system prompt loading when file is missing."""
        from databot_service import DatabotService

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"), \
             patch("pathlib.Path.exists", return_value=False):
            service = DatabotService(mock_data_service)
            prompt = service._load_system_prompt()

        # Should return fallback prompt
        assert "Databot" in prompt

    def test_load_system_prompt_adds_session_context(self, mock_data_service):
        """Test session context is added to prompt."""
        from databot_service import DatabotService

        # Prompt without explicit SESSION_ID reference
        simple_prompt = "You are Databot.\n{{ SCHEMA }}\nReady!"

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"), \
             patch("builtins.open", mock_open(read_data=simple_prompt)):
            service = DatabotService(mock_data_service, session_id="mysession")
            prompt = service._load_system_prompt()

        # Should add session context at the end
        assert "SYSTEM CONTEXT:" in prompt
        assert "mysession" in prompt
        assert "http://127.0.0.1:8000/orders?session_id=mysession" in prompt

    def test_register_plot_callback(self, mock_data_service):
        """Test plot callback registration."""
        from databot_service import DatabotService

        mock_callback = Mock()

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_data_service)
            service.register_plot_callback(mock_callback)

        assert service._plot_callback == mock_callback

    @pytest.mark.asyncio
    async def test_register_tools(self, mock_data_service):
        """Test MCP tool registration."""
        from databot_service import DatabotService

        mock_session = Mock()
        mock_session.register_tool = Mock()
        mock_session.register_mcp_tools_stdio_async = AsyncMock()
        mock_session.on_tool_result = Mock(return_value=lambda f: f)

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter", return_value=mock_session):
            service = DatabotService(mock_data_service)
            await service.register_tools()

        # Verify local tools registered
        mock_session.register_tool.assert_called_once_with(service.display_plot)

        # Verify MCP tools registered
        mock_session.register_mcp_tools_stdio_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_perform_chat(self, mock_data_service):
        """Test chat streaming."""
        from databot_service import DatabotService

        mock_session = Mock()
        mock_stream = AsyncMock()
        mock_session.stream_async = AsyncMock(return_value=mock_stream)

        mock_chat_ui = AsyncMock()

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter", return_value=mock_session):
            service = DatabotService(mock_data_service)
            await service.perform_chat("test query", mock_chat_ui)

        # Verify stream was created with correct parameters
        mock_session.stream_async.assert_called_once_with("test query", content="all")
        mock_chat_ui.append_message_stream.assert_called_once_with(mock_stream)

    @pytest.mark.asyncio
    async def test_display_plot_success(self, mock_data_service, tmp_path):
        """Test display_plot with valid file."""
        from databot_service import DatabotService

        # Create a test plot file
        plot_file = tmp_path / "test_plot.json"
        plot_data = {"data": [], "layout": {"title": "Test"}}
        plot_file.write_text(json.dumps(plot_data))

        mock_callback = AsyncMock()

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_data_service)
            service.register_plot_callback(mock_callback)

            result = await service.display_plot(str(plot_file))

        assert "successfully displayed" in result
        mock_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_display_plot_file_not_found(self, mock_data_service):
        """Test display_plot with non-existent file."""
        from databot_service import DatabotService

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_data_service)
            result = await service.display_plot("/nonexistent/file.json")

        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_display_plot_no_callback(self, mock_data_service, tmp_path):
        """Test display_plot without registered callback."""
        from databot_service import DatabotService

        plot_file = tmp_path / "test_plot.json"
        plot_file.write_text(json.dumps({"data": [], "layout": {}}))

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_data_service)
            result = await service.display_plot(str(plot_file))

        assert "callback not registered" in result

    @pytest.mark.asyncio
    async def test_display_html_success(self, mock_data_service):
        """Test display_html with valid HTML."""
        from databot_service import DatabotService

        mock_callback = AsyncMock()
        test_html = "<div>Test HTML</div>"

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_data_service)
            service.register_plot_callback(mock_callback)

            result = await service.display_html(test_html)

        assert "successfully displayed" in result
        mock_callback.assert_called_once_with(test_html)

    @pytest.mark.asyncio
    async def test_display_html_no_callback(self, mock_data_service):
        """Test display_html without registered callback."""
        from databot_service import DatabotService

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_data_service)
            result = await service.display_html("<div>Test</div>")

        assert "callback not registered" in result


# ==============================================================================
# HTML Extraction Tests for DatabotService
# ==============================================================================

class TestDatabotHTMLExtraction:
    """Tests for Plotly HTML extraction in DatabotService."""

    def test_html_extraction_pattern1_plotly_config(self):
        """Test Pattern 1: PlotlyConfig HTML extraction."""
        sample_html = """
        Some output text
        <div>
            <script type="text/javascript">window.PlotlyConfig = {MathJaxConfig: 'local'};</script>
        </div>
        More text
        """

        # Pattern from auto_display_html
        match = re.search(r'(<div>\s*<script[^>]*>window\.PlotlyConfig.*?</script>\s*</div>)', sample_html, re.DOTALL)
        assert match is not None
        assert "PlotlyConfig" in match.group(1)

    def test_html_extraction_pattern2_plotly_graph_div(self):
        """Test Pattern 2: plotly-graph-div extraction."""
        sample_html = """
        <div class="plotly-graph-div" id="fig-1" style="width:100%">
        </div>
        <script type="text/javascript">
            Plotly.newPlot('fig-1', [], {});
        </script>
        """

        match = re.search(r'(<div[^>]*class="plotly-graph-div"[^>]*>.*?</div>\s*<script[^>]*>.*?Plotly\.newPlot.*?</script>)', sample_html, re.DOTALL)
        assert match is not None
        assert "plotly-graph-div" in match.group(1)

    def test_html_extraction_pattern3_plotly_newplot(self):
        """Test Pattern 3: Generic Plotly.newPlot extraction."""
        sample_html = """
        <div>
            <div id="chart"></div>
            <script>Plotly.newPlot('chart', data, layout);</script>
        </div>
        """

        match = re.search(r'(<div>.*?Plotly\.newPlot.*?</script>\s*</div>)', sample_html, re.DOTALL)
        assert match is not None
        assert "Plotly.newPlot" in match.group(1)

    def test_html_extraction_no_match(self):
        """Test HTML extraction with non-Plotly content."""
        sample_html = "<div>Just some regular HTML</div>"

        has_plotly = 'PlotlyConfig' in sample_html or 'Plotly.newPlot' in sample_html
        assert not has_plotly

    def test_html_wrapping_logic(self):
        """Test HTML wrapping logic for extracted content."""
        # Content without opening div
        content = "<script>Plotly.newPlot();</script>"

        if not content.strip().startswith('<div'):
            wrapped = f"<div>{content}</div>"
        else:
            wrapped = content

        assert wrapped.startswith('<div>')
        assert wrapped.endswith('</div>')


# ==============================================================================
# Edge Cases and Error Handling
# ==============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_nl_service_empty_dataframe(self):
        """Test NLService with empty DataFrame."""
        from nl_service import NLService

        empty_df = pl.DataFrame()

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("nl_service.ChatOpenRouter"):
            service = NLService(empty_df)
            schema = service._pl_to_schema(empty_df, "empty")

        assert "Table: empty" in schema
        assert "Columns:" in schema

    def test_databot_service_exception_in_schema_generation(self):
        """Test DatabotService handles exceptions in schema generation."""
        from databot_service import DatabotService

        # Mock data service that raises exception when accessing base_orders
        mock_service = Mock()
        mock_service.base_orders = Mock()
        mock_service.base_orders.schema = Mock(side_effect=Exception("Schema error"))

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_service)
            schema = service._build_schema_text("orders")

        # Should fall back gracefully
        assert "orders" in schema

    def test_nl_service_special_characters_in_values(self):
        """Test NLService handles special characters in categorical values."""
        from nl_service import NLService

        df = pl.DataFrame({
            "col1": ["value's", 'value"with"quotes', "normal"],
        })

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("nl_service.ChatOpenRouter"):
            service = NLService(df)
            schema = service._pl_to_schema(df, "test")

        # Should include categorical values without breaking
        assert "Categorical values:" in schema

    @pytest.mark.asyncio
    async def test_display_plot_invalid_json(self, mock_data_service, tmp_path):
        """Test display_plot with invalid JSON file."""
        from databot_service import DatabotService

        plot_file = tmp_path / "invalid.json"
        plot_file.write_text("not valid json {")

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("databot_service.ChatOpenRouter"):
            service = DatabotService(mock_data_service)
            service.register_plot_callback(AsyncMock())

            result = await service.display_plot(str(plot_file))

        assert "Error" in result

    def test_template_variable_case_sensitivity(self, sample_polars_df):
        """Test template variables are case-sensitive."""
        from nl_service import NLService

        prompt_template = "Schema: {{ schema }}\nCorrect: {{ SCHEMA }}"

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}), \
             patch("nl_service.ChatOpenRouter"), \
             patch("builtins.open", mock_open(read_data=prompt_template)):
            service = NLService(sample_polars_df)
            prompt = service._build_system_prompt()

        # {{ SCHEMA }} should be replaced, {{ schema }} should not
        assert "{{ schema }}" in prompt
        assert "{{ SCHEMA }}" not in prompt
        assert "Table: orders" in prompt
