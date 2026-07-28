"""MMDocIR -> GoldenSet adapter: the id, selection and page-offset rules.

The page-offset conversion is the load-bearing one. MMDocIR labels pages 0-based
and this repo is 1-based everywhere, so an off-by-one here silently scores every
query against the wrong page while every count still looks right.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_mmdocir_golden import _categorize, _query_id
from scripts.fetch_mmdocir import _MAX_PAPER_ID_LEN, _paper_id, select_docs


def test_paper_id_strips_the_pdf_suffix() -> None:
    assert _paper_id("PH_2016.06.08_Economy-Final.pdf") == "PH_2016.06.08_Economy-Final"


def test_long_paper_id_is_truncated_but_stays_unique() -> None:
    a = _paper_id("A" * 90 + "-one.pdf")
    b = _paper_id("A" * 90 + "-two.pdf")
    assert len(a) <= _MAX_PAPER_ID_LEN
    assert len(b) <= _MAX_PAPER_ID_LEN
    assert a != b


def test_select_docs_applies_the_page_cap() -> None:
    rows = [
        {"doc_name": "small.pdf", "page_indices": [0, 10]},
        {"doc_name": "huge.pdf", "page_indices": [10, 900]},
    ]
    kept = select_docs(rows, page_cap=60, limit_docs=None)
    assert [r["doc_name"] for r in kept] == ["small.pdf"]


def test_select_docs_is_deterministic_under_limit() -> None:
    rows = [
        {"doc_name": "b.pdf", "page_indices": [0, 5]},
        {"doc_name": "a.pdf", "page_indices": [5, 10]},
    ]
    assert [r["doc_name"] for r in select_docs(rows, 60, 1)] == ["a.pdf"]


def test_categorize_covers_both_type_vocabularies() -> None:
    assert _categorize("['Chart']") == "figure"
    assert _categorize("['Figure', 'Pure-text (Plain-text)']") == "figure"
    assert _categorize("['Table']") == "table"
    assert _categorize("multimodal-f") == "figure"
    assert _categorize("multimodal-t") == "table"
    assert _categorize("text-only") == "factual"
    assert _categorize("meta-data") == "factual"


def test_figure_evidence_wins_over_table() -> None:
    assert _categorize("['Table', 'Chart']") == "figure"


def test_query_ids_are_unique_per_index() -> None:
    assert _query_id(0, "paper") != _query_id(1, "paper")


def test_golden_pages_are_one_based_and_range_checked(tmp_path: Path) -> None:
    """A 0-based label becomes 1-based; a label past the end of the doc is dropped."""
    annotations = tmp_path / "annotations.jsonl"
    annotations.write_text(
        json.dumps(
            {
                "doc_name": "doc.pdf",
                "domain": "News",
                "page_indices": [0, 3],
                "questions": [
                    {
                        "Q": "first page question",
                        "A": "yes",
                        "type": "['Chart']",
                        "page_id": [0],
                        "layout_mapping": [
                            {"page": 0, "bbox": [1, 2, 3, 4], "page_size": [612, 792]}
                        ],
                    },
                    {
                        "Q": "out of range question",
                        "A": "no",
                        "type": "text-only",
                        "page_id": [99],
                        "layout_mapping": [],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"docs": [{"paper_id": "doc", "n_pages": 3}]}), encoding="utf-8")
    out = tmp_path / "golden.yaml"
    layouts = tmp_path / "layouts.json"

    import sys

    from scripts.build_mmdocir_golden import main

    argv = sys.argv
    sys.argv = [
        "build_mmdocir_golden",
        "--annotations",
        str(annotations),
        "--manifest",
        str(manifest),
        "--output",
        str(out),
        "--layout-output",
        str(layouts),
    ]
    try:
        main()
    finally:
        sys.argv = argv

    import yaml

    golden = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert len(golden["queries"]) == 1
    query = golden["queries"][0]
    assert query["relevant_pages"] == [1]  # page_id 0 -> page 1
    assert query["category"] == "figure"

    layout_labels = json.loads(layouts.read_text(encoding="utf-8"))
    assert layout_labels[query["query_id"]][0]["page"] == 1
