from src.state import merge_flat_blocks, merge_warnings


class TestMergeFlatBlocks:
    def test_append_to_empty(self, sample_block):
        assert merge_flat_blocks([], [sample_block]) == [sample_block]

    def test_append_to_existing(self, sample_block):
        block2 = {**sample_block, "block_id": "blk-002"}
        assert merge_flat_blocks([sample_block], [block2]) == [sample_block, block2]

    def test_none_resets_non_empty(self, sample_block):
        assert merge_flat_blocks([sample_block], None) == []

    def test_none_resets_empty(self):
        assert merge_flat_blocks([], None) == []


class TestMergeWarnings:
    def test_append_to_empty(self):
        assert merge_warnings([], ["w"]) == ["w"]

    def test_append_to_existing(self):
        assert merge_warnings(["w1"], ["w2"]) == ["w1", "w2"]

    def test_empty_new_preserves_existing(self):
        assert merge_warnings(["w1"], []) == ["w1"]

    def test_none_new_on_empty_existing(self):
        assert merge_warnings([], None) == []
