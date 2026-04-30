import pytest
import json
from fastapi.testclient import TestClient
from auth import validate_api_key
import pipeline.extractor

@pytest.fixture
def app():
    """Create app instance with auth override"""
    from main import app as main_app
    main_app.dependency_overrides[validate_api_key] = lambda: "test-api-key"
    yield main_app
    main_app.dependency_overrides = {}

@pytest.fixture
def client(app):
    """FastAPI TestClient with default LLM mock"""
    async def default_mock(*args, **kwargs):
        return json.dumps({
            "tasks": [{"task": "Default", "priority": "medium", "source": "doc_0_chunk_0"}],
            "summary": "Default summary"
        })
    
    # Patch main.call_llm (the imported reference used by routes)
    import main
    original = main.call_llm
    main.call_llm = default_mock
    
    with TestClient(app) as c:
        yield c
    
    # Restore
    main.call_llm = original

@pytest.fixture
def mock_llm_success(monkeypatch):
    """Override default mock with successful LLM extraction."""
    mock_response = {
        "tasks": [
            {
                "task": "Update API documentation",
                "priority": "high",
                "deadline": "2026-04-30",
                "source": "doc1_chunk_0"
            }
        ],
        "summary": "Meeting to discuss product launch and dashboard integration."
    }
    
    async def mock_call(*args, **kwargs):
        return json.dumps(mock_response)
    
    import main
    monkeypatch.setattr(main, "call_llm", mock_call)

@pytest.fixture
def mock_llm_malformed(monkeypatch):
    """Override with malformed JSON response."""
    async def mock_call(*args, **kwargs):
        return "INVALID JSON { ..."
    
    import main
    monkeypatch.setattr(main, "call_llm", mock_call)

@pytest.fixture
def mock_llm_timeout(monkeypatch):
    """Override with timeout."""
    async def mock_call(*args, **kwargs):
        raise TimeoutError("LLM Request Timeout")
    
    import main
    monkeypatch.setattr(main, "call_llm", mock_call)

@pytest.fixture
def meeting_notes():
    with open("tests/fixtures/meeting_notes.txt", "r") as f:
        return f.read()

@pytest.fixture
def email_thread():
    with open("tests/fixtures/email_thread.txt", "r") as f:
        return f.read()

@pytest.fixture
def empty_noise():
    with open("tests/fixtures/empty_noise.txt", "r") as f:
        return f.read()

@pytest.fixture
def large_doc():
    with open("tests/fixtures/large_doc.txt", "r") as f:
        return f.read()

@pytest.fixture
def sample_docs(meeting_notes, email_thread):
    return [
        {"id": "doc1", "content": meeting_notes},
        {"id": "doc2", "content": email_thread}
    ]
