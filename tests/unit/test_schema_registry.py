import jsonschema
import pytest

from src.schema_registry import SchemaRegistry


class TestLoadSchema:
    def test_invoice_loads(self):
        registry = SchemaRegistry()
        schema = registry._load_schema("invoice")
        assert isinstance(schema, dict)
        assert "properties" in schema

    def test_scientific_paper_loads(self):
        registry = SchemaRegistry()
        schema = registry._load_schema("scientific_paper")
        assert isinstance(schema, dict)

    def test_contract_loads(self):
        registry = SchemaRegistry()
        schema = registry._load_schema("contract")
        assert schema.get("title") == "AgnosticContractStructure"

    def test_unknown_falls_back_to_baseline(self):
        registry = SchemaRegistry()
        schema = registry._load_schema("xyz")
        assert isinstance(schema, dict)
        # baseline_core has title "BaselineCoreStructure"
        assert schema.get("title") == "BaselineCoreStructure"


class TestGetSchemaAndTool:
    def test_returns_tuple(self):
        registry = SchemaRegistry()
        result = registry.get_schema_and_tool("baseline_core")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_tool_input_schema_strips_meta_fields(self):
        registry = SchemaRegistry()
        _, tool = registry.get_schema_and_tool("baseline_core")
        assert "$schema" not in tool["input_schema"]
        assert "title" not in tool["input_schema"]

    def test_tool_name_matches_doc_type(self):
        registry = SchemaRegistry()
        _, tool = registry.get_schema_and_tool("invoice")
        assert tool["name"] == "extract_invoice_structure"

    def test_contract_tool_name(self):
        registry = SchemaRegistry()
        _, tool = registry.get_schema_and_tool("contract")
        assert tool["name"] == "extract_contract_structure"


def _contract_block(block_type: str = "paragraph") -> dict:
    return {
        "block_id": "c1",
        "type": block_type,
        "text": "Sample text.",
        "bbox": {"page_number": 1, "coordinates": [50, 50, 100, 80]},
    }


def _base_block() -> dict:
    return {
        "block_id": "b1",
        "type": "paragraph",
        "text": "Sample text.",
        "bbox": {"page_number": 1, "coordinates": [50, 50, 100, 80]},
    }


class TestValidate:
    def test_valid_baseline_core_passes(self, sample_block):
        registry = SchemaRegistry()
        payload = {
            "document_type": "baseline_core",
            "blocks": [sample_block],
        }
        registry.validate("baseline_core", payload)  # no exception

    def test_missing_blocks_raises(self):
        registry = SchemaRegistry()
        with pytest.raises(jsonschema.ValidationError):
            registry.validate("baseline_core", {"document_type": "baseline_core"})

    def test_invalid_block_type_raises(self):
        registry = SchemaRegistry()
        bad_block = {
            "block_id": "b1",
            "type": "invalid_type_xyz",
            "text": "hello",
            "bbox": {"page_number": 1, "coordinates": [0, 0, 10, 10]},
        }
        with pytest.raises(jsonschema.ValidationError):
            registry.validate(
                "baseline_core", {"document_type": "baseline_core", "blocks": [bad_block]}
            )

    def test_contract_paragraph_block_passes(self):
        registry = SchemaRegistry()
        payload = {"document_type": "contract", "blocks": [_contract_block("paragraph")]}
        registry.validate("contract", payload)  # no exception

    def test_contract_signature_block_type_accepted(self):
        registry = SchemaRegistry()
        payload = {"document_type": "contract", "blocks": [_contract_block("signature_block")]}
        registry.validate("contract", payload)  # no exception

    def test_contract_invalid_block_type_rejected(self):
        registry = SchemaRegistry()
        payload = {"document_type": "contract", "blocks": [_contract_block("invalid_type_xyz")]}
        with pytest.raises(jsonschema.ValidationError):
            registry.validate("contract", payload)


_ALL_DOC_TYPES = ["baseline_core", "invoice", "scientific_paper", "contract"]


class TestExtractionFlags:
    @pytest.mark.parametrize("doc_type", _ALL_DOC_TYPES)
    def test_extraction_flags_valid_flag_accepted(self, doc_type):
        registry = SchemaRegistry()
        block = {**_base_block(), "extraction_flags": ["ambiguous_type"]}
        registry.validate(doc_type, {"document_type": doc_type, "blocks": [block]})

    @pytest.mark.parametrize("doc_type", _ALL_DOC_TYPES)
    def test_extraction_flags_invalid_flag_rejected(self, doc_type):
        registry = SchemaRegistry()
        block = {**_base_block(), "extraction_flags": ["made_up_flag"]}
        with pytest.raises(jsonschema.ValidationError):
            registry.validate(doc_type, {"document_type": doc_type, "blocks": [block]})

    @pytest.mark.parametrize("doc_type", _ALL_DOC_TYPES)
    def test_extraction_flags_absent_passes(self, doc_type):
        registry = SchemaRegistry()
        registry.validate(doc_type, {"document_type": doc_type, "blocks": [_base_block()]})

    @pytest.mark.parametrize("doc_type", _ALL_DOC_TYPES)
    def test_extraction_flags_duplicate_flag_rejected(self, doc_type):
        registry = SchemaRegistry()
        block = {**_base_block(), "extraction_flags": ["ambiguous_type", "ambiguous_type"]}
        with pytest.raises(jsonschema.ValidationError):
            registry.validate(doc_type, {"document_type": doc_type, "blocks": [block]})
