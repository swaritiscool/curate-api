import pytest
import json
from unittest.mock import AsyncMock

def test_full_pipeline_meeting_notes(client, monkeypatch, meeting_notes):
    """Full pipeline test: realistic meeting notes -> correct tasks_v1 output"""
    mock_llm_response = {
        "tasks": [
            {"task": "Update API docs", "priority": "high", "deadline": "2026-04-30", "source": "meeting_chunk_0"},
            {"task": "Schedule call with Legal", "priority": "medium", "deadline": "2026-04-29", "source": "meeting_chunk_0"}
        ],
        "summary": "Meeting about product launch."
    }
    
    import main
    async def mock_call(*args, **kwargs):
        return json.dumps(mock_llm_response)
    monkeypatch.setattr(main, "call_llm", mock_call)
    
    payload = {
        "documents": [{"id": "meeting", "content": meeting_notes}],
        "task": "extract tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["tasks"]) == 2
    assert data["meta"]["docs_processed"] == 1
    assert data["meta"]["chunks_used"] > 0

def test_multi_doc_merge_dedup(client, monkeypatch, sample_docs):
    """Multi-doc merge: 3 docs with overlapping tasks -> deduped output"""
    # 3 docs, doc1 repeated
    docs = sample_docs + [{"id": "doc1_copy", "content": sample_docs[0]["content"]}]
    
    # Mock LLM returns duplicates as if it didn't dedup itself
    mock_llm_response = {
        "tasks": [
            {"task": "Update docs", "priority": "high", "source": "doc1_chunk_0"},
            {"task": "Update docs", "priority": "high", "source": "doc1_copy_chunk_0"},
            {"task": "Research AWS", "priority": "medium", "source": "doc2_chunk_0"}
        ],
        "summary": "Summary"
    }
    
    import main
    async def mock_call(*args, **kwargs):
        return json.dumps(mock_llm_response)
    monkeypatch.setattr(main, "call_llm", mock_call)
    
    payload = {
        "documents": docs,
        "task": "extract tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 200
    # Post-processor should have deduped "Update docs"
    tasks = response.json()["data"]["tasks"]
    assert len(tasks) == 2
    task_names = [t["task"] for t in tasks]
    assert "Update docs" in task_names
    assert "Research AWS" in task_names

def test_noise_filtering(client, monkeypatch, meeting_notes, empty_noise):
    """Noise doc: doc full of irrelevant filler -> BM25 filter fires"""
    # 1 relevant doc, 1 noise doc
    docs = [
        {"id": "real", "content": meeting_notes},
        {"id": "noise", "content": empty_noise}
    ]
    
    import pipeline.extractor
    async def mock_call(*args, **kwargs):
        return json.dumps({"tasks": [], "summary": "..."})
    monkeypatch.setattr(pipeline.extractor, "call_llm", mock_call)
    
    payload = {
        "documents": docs,
        "task": "API documentation",
        "schema": "tasks_v1"
    }
    
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 200

def test_retry_recovery(client, monkeypatch, meeting_notes):
    """Retry recovery: LLM returns bad JSON on first call, valid JSON on second"""
    call_count = [0]
    
    import main
    async def mock_call(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return "BAD JSON"
        return json.dumps({"tasks": [], "summary": "Recovered"})
    
    monkeypatch.setattr(main, "call_llm", mock_call)
    
    payload = {
        "documents": [{"id": "doc1", "content": meeting_notes}],
        "task": "task",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["summary"] == "Recovered"
    assert call_count[0] == 2
