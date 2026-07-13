import jsonschema
import pytest

from src.config import EXTRACTION_NOTE_MAX_LENGTH
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

    @pytest.mark.parametrize("doc_type", _ALL_DOC_TYPES)
    def test_extraction_note_with_flags_accepted(self, doc_type):
        registry = SchemaRegistry()
        block = {
            **_base_block(),
            "extraction_flags": ["low_legibility"],
            "extraction_note": "Text is faint due to low scan contrast.",
        }
        registry.validate(doc_type, {"document_type": doc_type, "blocks": [block]})

    @pytest.mark.parametrize("doc_type", _ALL_DOC_TYPES)
    def test_extraction_note_absent_passes(self, doc_type):
        registry = SchemaRegistry()
        registry.validate(doc_type, {"document_type": doc_type, "blocks": [_base_block()]})

    @pytest.mark.parametrize("doc_type", _ALL_DOC_TYPES)
    def test_extraction_note_too_long_rejected(self, doc_type):
        registry = SchemaRegistry()
        block = {
            **_base_block(),
            "extraction_flags": ["low_legibility"],
            "extraction_note": "x" * (EXTRACTION_NOTE_MAX_LENGTH + 1),
        }
        with pytest.raises(jsonschema.ValidationError):
            registry.validate(doc_type, {"document_type": doc_type, "blocks": [block]})


class TestStrictToolSchema:
    def test_tool_is_strict(self):
        _, tool = SchemaRegistry().get_schema_and_tool("invoice")
        assert tool["strict"] is True

    def test_every_object_has_additional_properties_false(self):
        _, tool = SchemaRegistry().get_schema_and_tool("invoice")

        def check(node, path="root"):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    assert node.get("additionalProperties") is False, path
                for k, v in node.items():
                    check(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    check(v, f"{path}[{i}]")

        check(tool["input_schema"])

    def test_unsupported_constraints_stripped_from_tool_only(self):
        schema, tool = SchemaRegistry().get_schema_and_tool("invoice")
        dumped = str(tool["input_schema"])
        assert "minItems" not in dumped
        assert "maxItems" not in dumped
        assert "maxLength" not in dumped
        assert "uniqueItems" not in dumped
        # the local validation schema keeps the full constraints
        coords = schema["properties"]["blocks"]["items"]["properties"]["bbox"]["properties"][
            "coordinates"
        ]
        assert coords["minItems"] == 4 and coords["maxItems"] == 4
        note = schema["properties"]["blocks"]["items"]["properties"]["extraction_note"]
        assert note["maxLength"] > 0

    def test_local_validation_still_enforces_stripped_constraints(self):
        import jsonschema
        import pytest

        bad = {
            "document_type": "invoice",
            "blocks": [
                {
                    "block_id": "b1",
                    "type": "paragraph",
                    "text": "x",
                    "bbox": {"page_number": 1, "coordinates": [1, 2, 3]},  # only 3 coords
                }
            ],
        }
        with pytest.raises(jsonschema.ValidationError):
            SchemaRegistry().validate("invoice", bad)

    def test_required_fields_unchanged(self):
        # optional block fields stay optional in the strict schema — strict
        # must not force the model to emit extraction_note on every block
        _, tool = SchemaRegistry().get_schema_and_tool("invoice")
        items = tool["input_schema"]["properties"]["blocks"]["items"]
        assert items["required"] == ["block_id", "type", "bbox", "text"]
