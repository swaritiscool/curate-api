import pytest
from pipeline.postprocess import (
    dedup_extractions, 
    normalize_priority, 
    attach_source_references,
    validate_against_schema,
    postprocess_extraction
)

def test_deduplication():
    """Duplicate tasks (identical task string) are deduplicated"""
    extractions = [
        {"task": "Update docs", "priority": "high", "source": "d1_c1"},
        {"task": "Update docs", "priority": "low", "source": "d1_c2"},
        {"task": "New task", "priority": "low", "source": "d1_c3"}
    ]
    deduped = dedup_extractions(extractions)
    assert len(deduped) == 2
    assert deduped[0]["task"] == "Update docs"

def test_priority_normalization():
    """Priority values are normalized to lowercase ("High" -> "high")"""
    assert normalize_priority("High") == "high"
    assert normalize_priority("URGENT") == "high"
    assert normalize_priority("medium") == "medium"
    assert normalize_priority(None) == "medium"

def test_source_attachment():
    """Every item in the output has a source field referencing a valid chunk ID"""
    extractions = [{"task": "Task without source"}]
    chunks = [{"doc_id": "doc1", "chunk_id": 5}]
    processed = attach_source_references(extractions, chunks)
    assert processed[0]["source"] == "doc1_chunk_5"

def test_schema_validation_success():
    """Final JSON passes schema validation before return"""
    data = {
        "tasks": [{"task": "T1", "priority": "high", "source": "s1"}],
        "summary": "Sum"
    }
    assert validate_against_schema(data, "tasks_v1") is True

def test_schema_validation_failure():
    """JSON that fails schema validation returns False"""
    data = {"wrong_key": "data"}
    assert validate_against_schema(data, "tasks_v1") is False

def test_postprocess_integration():
    """Meta-test for full post-processing logic"""
    raw_extraction = {
        "tasks": [
            {"task": "Do it", "priority": "High"},
            {"task": "Do it", "priority": "Low"}
        ],
        "summary": "Summary"
    }
    chunks = [{"doc_id": "d1", "chunk_id": 0}]
    processed = postprocess_extraction(raw_extraction, chunks, "tasks_v1")
    
    assert len(processed["tasks"]) == 1
    assert processed["tasks"][0]["priority"] == "high"
    assert "source" in processed["tasks"][0]
