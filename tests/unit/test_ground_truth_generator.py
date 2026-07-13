"""Unit tests for the golden ground-truth generator's consensus logic."""
import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "generate_real_ground_truth.py"
_spec = importlib.util.spec_from_file_location("generate_real_ground_truth", _SCRIPT)
_gen = importlib.util.module_from_spec(_spec)
sys.modules["generate_real_ground_truth"] = _gen
_spec.loader.exec_module(_gen)


def _run(blocks: list[dict]) -> dict:
    return {
        "document_type": "scientific_paper",
        "hierarchical_document_tree": {"structured_payload": blocks},
    }


def _title_block(title: str) -> dict:
    return {
        "block_id": "b1",
        "type": "title",
        "text": title,
        "bbox": {"page_number": 1, "coordinates": [0, 0, 10, 10]},
        "metadata": {"bibliographic": {"title": title}},
    }


class TestConsensusKey:
    def test_case_flicker_groups_together(self):
        a = "Physics-Informed Fourier Neural Operator"
        b = "Physics-informed Fourier Neural Operator"
        assert _gen._consensus_key(a) == _gen._consensus_key(b)

    def test_line_break_hyphenation_groups_together(self):
        assert _gen._consensus_key("task-specific model") == _gen._consensus_key(
            "taskspecific model"
        )

    def test_distinct_values_stay_distinct(self):
        assert _gen._consensus_key("BERT") != _gen._consensus_key("GPT")

    def test_author_lists(self):
        a = ["Jacob Devlin", "Ming-Wei Chang"]
        b = ["Jacob  Devlin", "ming-wei chang"]
        assert _gen._consensus_key(a) == _gen._consensus_key(b)


class TestMetadataConsensus:
    def test_case_flicker_no_longer_drops_key(self):
        # 5 runs: 3 with one casing, 2 with another — exact grouping made two
        # camps (3 < required_threshold 4) and dropped the key; normalized
        # grouping yields a 5-vote consensus.
        titles = [
            "Physics-Informed Fourier Neural Operator",
            "Physics-Informed Fourier Neural Operator",
            "Physics-Informed Fourier Neural Operator",
            "Physics-informed Fourier Neural Operator",
            "Physics-informed Fourier Neural Operator",
        ]
        runs = [_run([_title_block(t)]) for t in titles]
        golden = _gen._derive_golden("sp-x", "scientific_paper", runs, None, 5, None)
        assert "title" in golden["metadata_required"]
        # representative value is the most common raw form
        assert golden["metadata_required"]["title"] == (
            "Physics-Informed Fourier Neural Operator"
        )

    def test_genuinely_unstable_value_still_deferred_or_dropped(self):
        titles = ["Alpha Paper", "Beta Paper", "Gamma Paper", "Delta Paper", "Epsilon Paper"]
        runs = [_run([_title_block(t)]) for t in titles]
        golden = _gen._derive_golden("sp-x", "scientific_paper", runs, None, 5, None)
        assert "title" not in golden["metadata_required"]
