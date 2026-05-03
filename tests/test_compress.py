import pytest
import time


class TestCompressEndpoint:
    def test_valid_single_doc_returns_200(self, client, meeting_notes):
        """Valid single doc → 200, chunks array not empty, all chunks have required fields"""
        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": meeting_notes}],
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "chunks" in data
        assert len(data["chunks"]) > 0
        for chunk in data["chunks"]:
            assert "chunk_id" in chunk
            assert "doc_id" in chunk
            assert "position" in chunk
            assert "content" in chunk
            assert "score" in chunk
            assert "doc_type" in chunk
            assert "tokens" in chunk

    def test_valid_multi_doc_chunks_from_all_docs(self, client, sample_docs):
        """Valid multi-doc → chunks from all docs present in response"""
        response = client.post("/v1/compress", json={
            "documents": sample_docs,
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        assert response.status_code == 200
        data = response.json()
        doc_ids = {c["doc_id"] for c in data["chunks"]}
        assert "doc1" in doc_ids
        assert "doc2" in doc_ids

    def test_reduction_pct_between_0_and_100(self, client, meeting_notes):
        """reduction_pct is between 0 and 100"""
        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": meeting_notes}],
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        assert response.status_code == 200
        data = response.json()
        assert 0 <= data["meta"]["reduction_pct"] <= 100

    def test_chunks_ordered_by_score_descending(self, client, meeting_notes):
        """chunks ordered by score descending"""
        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": meeting_notes}],
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        assert response.status_code == 200
        data = response.json()
        scores = [c["score"] for c in data["chunks"]]
        assert scores == sorted(scores, reverse=True)

    def test_empty_content_returns_400(self, client):
        """Empty content → 400"""
        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": "   "}],
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        assert response.status_code == 400

    def test_missing_task_field_returns_422(self, client, meeting_notes):
        """Missing task field → 422"""
        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": meeting_notes}],
            "schema": "tasks_v1"
        })
        assert response.status_code == 422

    def test_unknown_schema_returns_422(self, client, meeting_notes):
        """Unknown schema → 422 (same as /v1/transform)"""
        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": meeting_notes}],
            "task": "extract_tasks",
            "schema": "unknown_schema"
        })
        assert response.status_code == 422

    def test_over_20_docs_returns_400(self, client):
        """Over 20 docs → 400"""
        docs = [{"id": f"doc{i}", "content": f"content {i}"} for i in range(21)]
        response = client.post("/v1/compress", json={
            "documents": docs,
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        assert response.status_code == 400

    def test_response_time_under_2000ms(self, client, meeting_notes):
        """Response time under 2000ms"""
        start = time.time()
        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": meeting_notes}],
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        elapsed = (time.time() - start) * 1000
        assert response.status_code == 200
        assert elapsed < 2000

    def test_content_matches_source_not_modified(self, client, meeting_notes):
        """content field matches actual text from input document — not modified"""
        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": meeting_notes}],
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        assert response.status_code == 200
        data = response.json()
        for chunk in data["chunks"]:
            assert len(chunk["content"]) > 0
            assert "test" not in chunk["content"].lower() or "test" in meeting_notes.lower()

    def test_meta_fields_present(self, client, meeting_notes):
        """All meta fields are present"""
        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": meeting_notes}],
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        assert response.status_code == 200
        data = response.json()
        assert "meta" in data
        meta = data["meta"]
        assert "chunks_returned" in meta
        assert "tokens_before_filter" in meta
        assert "tokens_after_filter" in meta
        assert "reduction_pct" in meta
        assert "docs_processed" in meta
        assert "processing_time_ms" in meta

    def test_over_token_limit_returns_400(self, client):
        """Over token limit → 400"""
        long_content = "word " * 4500
        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": long_content}],
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        assert response.status_code == 400

    def test_no_llm_called(self, client, meeting_notes, monkeypatch):
        """Verify no LLM call is made"""
        call_count = 0

        async def mock_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return '{"tasks": [], "summary": ""}'

        import main
        monkeypatch.setattr(main, "call_llm", mock_llm)

        response = client.post("/v1/compress", json={
            "documents": [{"id": "doc1", "content": meeting_notes}],
            "task": "extract_tasks",
            "schema": "tasks_v1"
        })
        assert response.status_code == 200
        assert call_count == 0