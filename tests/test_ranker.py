import pytest
from pipeline.ranker import rank_chunks

@pytest.fixture
def ranking_chunks():
    return [
        {"doc_id": "d1", "chunk_id": 0, "position": 0, "text": "Schedule the meeting and update the report.", "token_count": 40}, # High verb density
        {"doc_id": "d1", "chunk_id": 1, "position": 10, "text": "The meeting was held on 2026-04-30 at the office with John Doe.", "token_count": 40}, # Entities
        {"doc_id": "d1", "chunk_id": 2, "position": 20, "text": "A descriptive paragraph about the history of the company and its various departments.", "token_count": 40}, # Summary/Filler
    ]

def test_ranker_tasks_verb_density(ranking_chunks):
    """For extract_tasks: chunks with high verb density rank higher"""
    ranked = rank_chunks(ranking_chunks, "extract tasks", "tasks_v1")
    assert "Schedule" in ranked[0]["text"]

def test_ranker_entities_signals(ranking_chunks):
    """For entities_v1: chunks with names, organizations, and dates rank higher"""
    ranked = rank_chunks(ranking_chunks, "extract entities", "entities_v1")
    assert "John Doe" in ranked[0]["text"]

def test_ranker_summary_density(ranking_chunks):
    """For summary_v1: chunks with high information density rank higher"""
    ranked = rank_chunks(ranking_chunks, "summarize", "summary_v1")
    # This depends on the heuristic, but let's assume it picks the descriptive one
    assert "history" in ranked[0]["text"]

def test_ranker_top_n_limit():
    """Top-N selection never returns more than 15 chunks"""
    many_chunks = [{"doc_id": "d1", "chunk_id": i, "text": "text", "token_count": 10} for i in range(20)]
    ranked = rank_chunks(many_chunks, "task", "tasks_v1", top_n=15)
    assert len(ranked) == 15

def test_ranker_preserves_metadata(ranking_chunks):
    """Ranker output preserves doc_id, chunk_id, position from input"""
    ranked = rank_chunks(ranking_chunks, "task", "tasks_v1")
    for chunk in ranked:
        assert "doc_id" in chunk
        assert "chunk_id" in chunk
        assert "position" in chunk

def test_ranker_no_padding():
    """If fewer than 15 chunks exist, return all of them (no padding)"""
    few_chunks = [{"doc_id": "d1", "chunk_id": 0, "text": "text", "token_count": 10}]
    ranked = rank_chunks(few_chunks, "task", "tasks_v1", top_n=15)
    assert len(ranked) == 1
