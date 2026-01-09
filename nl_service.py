import os
import polars as pl
from pathlib import Path
from chatlas import ChatOpenRouter
from typing import Any, Callable
import dotenv

dotenv.load_dotenv()

class NLService:
    def __init__(self, df: pl.DataFrame, model: str = "deepseek/deepseek-v3.1-terminus"):
        self.df = df
        self.model = model
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        
        # We need a system prompt. We'll use the one from query.py but adapted.
        self.system_prompt = self._build_system_prompt()
        
        self.session = ChatOpenRouter(
            system_prompt=self.system_prompt,
            model=self.model,
            api_key=self.api_key
        )
        
    def _build_system_prompt(self) -> str:
        # Schema generation logic similar to sidebot/query.py but for Polars
        schema = self._pl_to_schema(self.df, "orders")
        prompt_path = Path(__file__).parent / "nl_prompt.md"
        if not prompt_path.exists():
            # Fallback or initialization logic
            return f"You are a SQL assistant. Schema:\n{schema}"
            
        with open(prompt_path, "r") as f:
            return f.read().replace("${SCHEMA}", schema)

    def _pl_to_schema(self, df: pl.DataFrame, name: str) -> str:
        schema = [f"Table: {name}", "Columns:"]
        for col, dtype in df.schema.items():
            sql_type = "TEXT"
            if dtype.is_integer(): sql_type = "INTEGER"
            elif dtype.is_float(): sql_type = "FLOAT"
            elif dtype == pl.Boolean: sql_type = "BOOLEAN"
            elif dtype == pl.Datetime: sql_type = "DATETIME"
            
            schema.append(f"- {col} ({sql_type})")
            
            # Categorical hints
            if sql_type == "TEXT":
                unique_count = df[col].n_unique()
                if unique_count <= 20:
                    cats = df[col].unique().to_list()
                    schema.append(f"  Categorical values: {', '.join(map(repr, cats))}")
            elif sql_type in ["INTEGER", "FLOAT"]:
                min_v = df[col].min()
                max_v = df[col].max()
                schema.append(f"  Range: {min_v} to {max_v}")
        
        return "\n".join(schema)

    def register_tools(self, update_dashboard_fn: Callable, query_db_fn: Callable):
        self.session.register_tool(update_dashboard_fn)
        self.session.register_tool(query_db_fn)

    async def perform_chat(self, user_input: str, chat_ui_obj: Any):
        stream = await self.session.stream_async(user_input, echo="all")
        await chat_ui_obj.append_message_stream(stream)
