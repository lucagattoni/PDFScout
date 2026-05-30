import json
import os
import jsonschema
from typing import Any
from src.config import FALLBACK_DOC_TYPE


class SchemaRegistry:
    def __init__(self, schema_dir: str = "schemas"):
        self.schema_dir = schema_dir

    def _load_schema(self, doc_type: str) -> dict[str, Any]:
        path = os.path.join(self.schema_dir, f"{doc_type}.json")
        if not os.path.exists(path):
            path = os.path.join(self.schema_dir, f"{FALLBACK_DOC_TYPE}.json")
        with open(path) as f:
            return json.load(f)

    def get_schema_and_tool(self, doc_type: str) -> tuple[dict[str, Any], dict[str, Any]]:
        schema = self._load_schema(doc_type)
        # Strip JSON Schema meta-fields rejected by Anthropic's tool input_schema spec
        tool_schema = {k: v for k, v in schema.items() if k not in ("$schema", "title")}
        tool = {
            "name": f"extract_{doc_type}_structure",
            "description": f"Outputs structured semantic and layout blocks for a {doc_type} document.",
            "input_schema": tool_schema
        }
        return schema, tool

    def validate(self, doc_type: str, payload: dict[str, Any]) -> None:
        """Raises jsonschema.ValidationError if payload violates the schema."""
        schema = self._load_schema(doc_type)
        jsonschema.validate(instance=payload, schema=schema)
