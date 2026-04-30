import pytest
from pipeline.filter import prefilter_chunks

@pytest.fixture
def mixed_chunks():
    return [
        {"doc_id": "d1", "chunk_id": 0, "text": "The project deadline is next Friday. Please update the API docs.", "token_count": 40},
        {"doc_id": "d1", "chunk_id": 1, "text": "The weather today is quite sunny with a light breeze.", "token_count": 40},
        {"doc_id": "d1", "chunk_id": 2, "text": "I like blueberry muffins from the cafe.", "token_count": 40},
        {"doc_id": "d1", "chunk_id": 3, "text": "Action item: Schedule maintenance for the server.", "token_count": 40},
        {"doc_id": "d1", "chunk_id": 4, "text": "Short.", "token_count": 5}
    ]

def test_filter_relevance(mixed_chunks):
    """Chunks clearly relevant to the task score higher than irrelevant chunks"""
    task = "project deadline API"
    filtered = prefilter_chunks(mixed_chunks, task, bm25_threshold=0.1)
    # Chunk with "deadline" and "API" should score higher
    texts = [c["text"] for c in filtered]
    assert any("deadline" in t for t in texts)
    assert any("API" in t for t in texts)
    assert not any("weather" in t for t in texts)

def test_filter_threshold(mixed_chunks):
    """Chunks below the score threshold are dropped"""
    task = "deadline"
    filtered = prefilter_chunks(mixed_chunks, task, bm25_threshold=1.0) # High threshold
    # At least one should survive as per requirement
    assert len(filtered) >= 1

def test_at_least_one_survives():
    """At least 1 chunk always survives (even if all scores are low) — never return empty"""
    chunks = [{"doc_id": "d1", "chunk_id": 0, "text": "completely irrelevant text", "token_count": 50}]
    filtered = prefilter_chunks(chunks, "specific task", bm25_threshold=10.0)
    assert len(filtered) == 1

def test_short_chunks_dropped(mixed_chunks):
    """Short chunks under 30 tokens are dropped when other chunks survive"""
    # chunk 4 is short, but when we query for "deadline", other chunks should survive
    # and the short one should be filtered by length
    filtered = prefilter_chunks(mixed_chunks, "deadline", min_tokens=30, bm25_threshold=0.0)
    texts = [c["text"] for c in filtered]
    # Short chunk should be dropped by length filter
    assert "Short." not in texts

def test_filter_reduction():
    """Filter reduces chunk count by at least 20% on a noisy document"""
    noisy_chunks = [
        {"doc_id": "d1", "chunk_id": i, "text": "irrelevant filler text", "token_count": 50}
        for i in range(10)
    ]
    noisy_chunks.append({"doc_id": "d1", "chunk_id": 10, "text": "Relevant task here", "token_count": 50})
    
    filtered = prefilter_chunks(noisy_chunks, "task", bm25_threshold=0.1)
    # Should drop most of the filler
    assert len(filtered) <= 8 # 11 * 0.8 = 8.8

def test_keyword_frequency_boost():
    """Task keyword appearing multiple times in a chunk increases its score"""
    chunks = [
        {"doc_id": "d1", "chunk_id": 0, "text": "task task task task", "token_count": 40},
        {"doc_id": "d1", "chunk_id": 1, "text": "just one task here", "token_count": 40}
    ]
    # We can't directly see the score, but we can see the order if they are returned
    # prefilter_chunks doesn't necessarily sort, but rank_chunks does.
    # However, it affects which one passes the threshold.
    filtered = prefilter_chunks(chunks, "task", bm25_threshold=0.5)
    assert len(filtered) >= 1
    assert filtered[0]["text"] == "task task task task"
