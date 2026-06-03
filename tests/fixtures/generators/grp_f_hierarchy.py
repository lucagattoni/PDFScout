"""Group F fixtures: pre-built block states for hierarchy narrow tests.

No PDF is generated — all inputs are Python dicts constructed in memory.
Not tracked in manifest.json.

Block coordinates are chosen so that geometric_pre_sorter (page ASC,
xmin // 50 ASC, ymin ASC) preserves the intended reading order:
  - All blocks on page 1 with xmin=70 (bucket 1) and monotonically
    increasing ymin values.
"""


def _block(block_id: str, btype: str, text: str, ymin: int) -> dict:
    return {
        "block_id": block_id,
        "type": btype,
        "text": text,
        "bbox": {"page_number": 1, "coordinates": [ymin, 70, ymin + 15, 500]},
    }


# F1: [heading, paragraph]
F1_BLOCKS = [
    _block("h1", "heading", "Section One", 50),
    _block("p1", "paragraph", "This paragraph falls under section one.", 70),
]

# F2: [heading, paragraph, paragraph, table]
F2_BLOCKS = [
    _block("h1", "heading", "Main Section", 50),
    _block("p1", "paragraph", "First paragraph under the heading.", 70),
    _block("p2", "paragraph", "Second paragraph under the heading.", 90),
    _block("t1", "table", "Col A | Col B | Col C", 110),
]

# F3: [title, heading, paragraph]
F3_BLOCKS = [
    _block("ti1", "title", "Document Title", 30),
    _block("h1", "heading", "1. Introduction", 55),
    _block("p1", "paragraph", "This paragraph belongs under the introduction heading.", 75),
]

# F4: [heading-A, para-A1, para-A2, heading-B, para-B1, para-B2]
F4_BLOCKS = [
    _block("hA", "heading", "First Heading", 30),
    _block("pA1", "paragraph", "First paragraph under first heading.", 50),
    _block("pA2", "paragraph", "Second paragraph under first heading.", 70),
    _block("hB", "heading", "Second Heading", 100),
    _block("pB1", "paragraph", "First paragraph under second heading.", 120),
    _block("pB2", "paragraph", "Second paragraph under second heading.", 140),
]

# F5: [page-1 is_continued paragraph, page-2 continuation paragraph]
# Verifies hierarchy Rule 2: is_continued=True → first page-2 block is its child.
F5_BLOCKS = [
    {
        "block_id": "p1c",
        "type": "paragraph",
        "text": "This text is cut off at the bottom of page one, and",
        "bbox": {"page_number": 1, "coordinates": [280, 70, 295, 500]},
        "is_continued": True,
    },
    {
        "block_id": "p2c",
        "type": "paragraph",
        "text": "continues at the top of page two.",
        "bbox": {"page_number": 2, "coordinates": [20, 70, 35, 500]},
    },
]


# F6: [orphan_para, heading, child_para] — orphan appears before any heading.
# Verifies hierarchy assigns parent_id=None for a pre-heading paragraph (Rule 3),
# and still correctly parents the post-heading paragraph (Rule 1).
F6_BLOCKS = [
    {
        "block_id": "orphan",
        "type": "paragraph",
        "text": "Preamble text that appears before any section heading.",
        "bbox": {"page_number": 1, "coordinates": [30, 70, 45, 500]},
    },
    {
        "block_id": "h1",
        "type": "heading",
        "text": "Section One",
        "bbox": {"page_number": 1, "coordinates": [60, 70, 75, 500]},
    },
    {
        "block_id": "p1",
        "type": "paragraph",
        "text": "This paragraph belongs under section one.",
        "bbox": {"page_number": 1, "coordinates": [90, 70, 105, 500]},
    },
]


def make_state(blocks: list, doc_type: str = "baseline_core") -> dict:
    """Build the minimal state dict required by layout_hierarchy_agent_node."""
    return {
        "document_type": doc_type,
        "pdf_hash": "f" * 64,
        "extracted_flat_blocks": blocks,
        "extraction_warnings": [],
    }
