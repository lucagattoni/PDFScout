import copy
import json
from pathlib import Path
from typing import Any

import jsonschema

from src.config import EXTRACTION_NOTE_MAX_LENGTH, FALLBACK_DOC_TYPE

_SCHEMA_DIR = Path(__file__).parent.parent / "schemas"

# JSON Schema keywords the API's strict tool-use validator does not support.
# They are stripped from the API-side schema only — the local jsonschema
# validation layer keeps the full schema, so these constraints are still
# enforced (two-layer validation, same approach as the SDK's parse() helper).
_STRICT_UNSUPPORTED = (
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "multipleOf",
    "minItems",
    "maxItems",
    "uniqueItems",
    "pattern",
)


def _strictify(node: Any) -> Any:
    """Deep-copy a JSON Schema into its strict-tool-use-compatible form:
    every object gets additionalProperties: false, unsupported constraint
    keywords are removed."""
    if isinstance(node, dict):
        out = {k: _strictify(v) for k, v in node.items() if k not in _STRICT_UNSUPPORTED}
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_strictify(v) for v in node]
    return copy.copy(node)


class SchemaRegistry:
    def __init__(self, schema_dir: Path = _SCHEMA_DIR):
        self.schema_dir = Path(schema_dir)

    def _load_schema(self, doc_type: str) -> dict[str, Any]:
        path = self.schema_dir / f"{doc_type}.json"
        if not path.exists():
            path = self.schema_dir / f"{FALLBACK_DOC_TYPE}.json"
        with open(path) as f:
            schema = json.load(f)
        note_props = (
            schema.get("properties", {})
            .get("blocks", {})
            .get("items", {})
            .get("properties", {})
            .get("extraction_note")
        )
        if note_props is not None:
            note_props["maxLength"] = EXTRACTION_NOTE_MAX_LENGTH
        return schema

    def get_schema_and_tool(
        self, doc_type: str, strict: bool = True
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        schema = self._load_schema(doc_type)
        # Strip JSON Schema meta-fields rejected by Anthropic's tool input_schema spec
        tool_schema = {k: v for k, v in schema.items() if k not in ("$schema", "title")}
        tool = {
            "name": f"extract_{doc_type}_structure",
            "description": f"Outputs structured semantic and layout blocks for a {doc_type} document.",
        }
        if strict:
            # strict: the API guarantees tool inputs validate against the
            # (sanitized) schema exactly — structural variance and invalid
            # shapes are rejected at generation time instead of surfacing as
            # jsonschema retries. Full constraints still enforced locally.
            #
            # Caveat: strict compiles input_schema into a constrained-decoding
            # grammar with a complexity ceiling. Rich per-doc-type schemas
            # (scientific_paper, contract) exceed it and the API returns
            # 400 "Schema is too complex" — callers must fall back to
            # strict=False for those types (see worker_node). The non-strict
            # tool has no complexity ceiling; local jsonschema validation still
            # enforces the full schema either way.
            tool["strict"] = True
            tool["input_schema"] = _strictify(tool_schema)
        else:
            tool["input_schema"] = tool_schema
        return schema, tool

    def validate(self, doc_type: str, payload: dict[str, Any]) -> None:
        """Raises jsonschema.ValidationError if payload violates the schema."""
        schema = self._load_schema(doc_type)
        jsonschema.validate(instance=payload, schema=schema)
