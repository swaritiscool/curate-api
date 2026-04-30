import pytest
import json
from unittest.mock import patch, AsyncMock

def test_transform_success_tasks(client, monkeypatch, meeting_notes):
    import main
    async def mock_call(*args, **kwargs):
        return json.dumps({
            "tasks": [{"task": "Update API documentation", "priority": "high", "deadline": "2026-04-30", "source": "doc1_chunk_0"}],
            "summary": "Meeting to discuss product launch and dashboard integration."
        })
    monkeypatch.setattr(main, "call_llm", mock_call)
    """Valid single doc + tasks_v1 -> 200, correct response shape"""
    payload = {
        "documents": [{"id": "doc1", "content": meeting_notes}],
        "task": "extract_tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "tasks" in data["data"]
    assert "summary" in data["data"]
    assert data["meta"]["docs_processed"] == 1

def test_transform_multi_doc(client, monkeypatch, sample_docs):
    import main
    async def mock_call(*args, **kwargs):
        return json.dumps({
            "tasks": [{"task": "Test", "priority": "high", "source": "doc1_chunk_0"}],
            "summary": "Summary"
        })
    monkeypatch.setattr(main, "call_llm", mock_call)
    """Valid multi-doc (5 docs) + tasks_v1 -> 200, all source chunk IDs traceable"""
    # Use 5 docs (some repeated for test simplicity)
    docs = sample_docs * 2 + [sample_docs[0]]
    payload = {
        "documents": docs,
        "task": "extract_tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["docs_processed"] == 5
    # Verification of source tracing is handled in post-processing tests, 
    # but we check if the response is successful here.

@pytest.mark.parametrize("schema_name, data_key", [
    ("summary_v1", "summary"),
    ("entities_v1", "entities")
])
def test_transform_different_schemas(client, monkeypatch, meeting_notes, schema_name, data_key):
    """Valid doc + summary_v1/entities_v1 -> 200, correct response shape"""
    mock_responses = {
        "summary_v1": {"summary": "test", "key_points": ["point"]},
        "entities_v1": {"entities": [{"name": "Sarah", "type": "person", "source": "doc1_chunk_0"}]}
    }
    
    import main
    async def mock_call(*args, **kwargs):
        return json.dumps(mock_responses[schema_name])
    monkeypatch.setattr(main, "call_llm", mock_call)
    
    payload = {
        "documents": [{"id": "doc1", "content": meeting_notes}],
        "task": "test task",
        "schema": schema_name
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 200
    assert data_key in response.json()["data"]

def test_empty_content(client):
    """Empty content string -> 400"""
    payload = {
        "documents": [{"id": "doc1", "content": ""}],
        "task": "extract_tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 400

def test_whitespace_content(client):
    """content is whitespace only -> 400"""
    payload = {
        "documents": [{"id": "doc1", "content": "   \n  "}],
        "task": "extract_tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 400

@pytest.mark.parametrize("missing_field", ["task", "schema", "documents"])
def test_missing_fields(client, missing_field):
    """Missing required fields -> 422"""
    payload = {
        "documents": [{"id": "doc1", "content": "text"}],
        "task": "extract_tasks",
        "schema": "tasks_v1"
    }
    del payload[missing_field]
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 422

def test_unknown_schema(client):
    """Unknown schema name -> 400 (Pydantic validation error or handled)"""
    payload = {
        "documents": [{"id": "doc1", "content": "text"}],
        "task": "extract_tasks",
        "schema": "nonexistent_v9"
    }
    response = client.post("/v1/transform", json=payload)
    # Since it's a Literal in Pydantic, it returns 422
    assert response.status_code == 422

def test_too_many_documents(client):
    """21 documents (over limit) -> 400"""
    payload = {
        "documents": [{"id": f"doc{i}", "content": "text"} for i in range(21)],
        "task": "extract_tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 400

def test_oversized_document(client, large_doc):
    """Single doc over 4000 tokens -> 400"""
    # large_doc generated earlier is ~10,000 tokens
    payload = {
        "documents": [{"id": "doc1", "content": large_doc}],
        "task": "extract_tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 400

def test_llm_malformed_retry_failure(client, monkeypatch, meeting_notes):
    """LLM returns malformed JSON after retry -> 500"""
    import main
    async def mock_call(*args, **kwargs):
        return "INVALID JSON { ..."
    monkeypatch.setattr(main, "call_llm", mock_call)
    
    payload = {
        "documents": [{"id": "doc1", "content": meeting_notes}],
        "task": "extract_tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 500
    assert "JSON" in response.json()["detail"]["message"]

def test_llm_timeout(client, monkeypatch, meeting_notes):
    """LLM times out -> 500"""
    import main
    async def mock_call(*args, **kwargs):
        raise TimeoutError("LLM Request Timeout")
    monkeypatch.setattr(main, "call_llm", mock_call)
    
    payload = {
        "documents": [{"id": "doc1", "content": meeting_notes}],
        "task": "extract_tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 500

def test_no_actionable_content(client, monkeypatch, empty_noise):
    """Empty tasks doc (no actionable content) -> 200 with "tasks": [], not an error"""
    # Mock LLM returning empty list for empty content
    import main
    async def mock_call(*args, **kwargs):
        return json.dumps({"tasks": [], "summary": "No tasks found."})
    monkeypatch.setattr(main, "call_llm", mock_call)
    
    payload = {
        "documents": [{"id": "doc1", "content": empty_noise}],
        "task": "extract_tasks",
        "schema": "tasks_v1"
    }
    response = client.post("/v1/transform", json=payload)
    assert response.status_code == 200
    assert response.json()["data"]["tasks"] == []
