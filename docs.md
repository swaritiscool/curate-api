# Curate.ai API Documentation

## Overview

Curate.ai is a context structuring API for AI agents. It transforms messy multi-document input into clean, schema-locked JSON output.

**Base URL:** `http://localhost:8000`

## Endpoints

### POST /v1/transform

Transform documents into structured JSON.

**Request Body:**
```json
{
  "documents": [
    {
      "id": "doc1",
      "content": "Your document text here..."
    }
  ],
  "task": "extract tasks with deadlines and priorities",
  "schema": "tasks_v1"
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `documents` | array | Yes | Array of document objects (max 20) |
| `documents[].id` | string | Yes | Unique document identifier |
| `documents[].content` | string | Yes | Document text (max ~4000 tokens) |
| `task` | string | Yes | Description of what to extract |
| `schema` | string | No | Output schema: `tasks_v1`, `summary_v1`, or `entities_v1` (default: `tasks_v1`) |

**Response (200 OK):**
```json
{
  "status": "success",
  "data": {
    "tasks": [
      {
        "task": "Update API documentation",
        "priority": "high",
        "deadline": "2026-04-30",
        "source": "doc1_chunk_0"
      }
    ],
    "summary": "Meeting to discuss product launch and dashboard integration."
  },
  "meta": {
    "chunks_used": 2,
    "tokens_used": 389,
    "docs_processed": 1,
    "tokens_before_filter": 941,
    "tokens_after_filter": 389,
    "reduction_pct": 58.7
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `success` or `error` |
| `data` | object | Extracted data matching schema |
| `data.tasks` | array | List of extracted tasks |
| `data.tasks[].task` | string | Task description |
| `data.tasks[].priority` | string | `low`, `medium`, or `high` |
| `data.tasks[].deadline` | string|null | ISO date or null |
| `data.tasks[].source` | string | Source chunk reference |
| `data.summary` | string | Brief summary |
| `meta` | object | Processing metadata |
| `meta.chunks_used` | number | Chunks sent to LLM |
| `meta.tokens_used` | number | Tokens in final request |
| `meta.docs_processed` | number | Documents processed |
| `meta.tokens_before_filter` | number | Tokens before BM25 filtering |
| `meta.tokens_after_filter` | number | Tokens after filtering |
| `meta.reduction_pct` | number | Percentage reduction (60-80% optimal) |

### POST /v1/compress

Compress documents by running pipeline stages 1-3 only (chunk → filter → rank). Returns filtered, ranked chunks as plain text. No LLM call.

**Request Body:** (identical to /v1/transform)
```json
{
  "documents": [
    {
      "id": "doc1",
      "content": "Your document text here..."
    }
  ],
  "task": "extract tasks with deadlines and priorities",
  "schema": "tasks_v1"
}
```

**Response (200 OK):**
```json
{
  "status": "success",
  "chunks": [
    {
      "chunk_id": "doc1_chunk_4",
      "doc_id": "doc1",
      "position": 4,
      "content": "Marcus needs to send the calendar invite for the QA sync by end of this week.",
      "score": 0.84,
      "doc_type": "task",
      "tokens": 156
    }
  ],
  "meta": {
    "chunks_returned": 12,
    "tokens_before_filter": 11829,
    "tokens_after_filter": 2547,
    "reduction_pct": 78.4,
    "docs_processed": 3,
    "processing_time_ms": 340
  }
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `success` or `error` |
| `chunks` | array | Ranked chunks (no LLM extraction) |
| `chunks[].chunk_id` | string | Chunk identifier (doc_id_chunk_N) |
| `chunks[].doc_id` | string | Source document ID |
| `chunks[].position` | number | Chunk position in document |
| `chunks[].content` | string | Raw chunk text (unchanged) |
| `chunks[].score` | number | BM25 relevance score (2 decimal places) |
| `chunks[].doc_type` | string | `task` or `reference` |
| `chunks[].tokens` | number | Token count for this chunk |
| `meta` | object | Processing metadata |
| `meta.chunks_returned` | number | Number of chunks returned |
| `meta.tokens_before_filter` | number | Tokens before BM25 filtering |
| `meta.tokens_after_filter` | number | Tokens after filtering |
| `meta.reduction_pct` | number | Percentage reduction |
| `meta.docs_processed` | number | Documents processed |
| `meta.processing_time_ms` | number | Total processing time |

**Rules:**
- Chunks ordered by score descending (highest relevance first)
- Content is raw text exactly as it appears in source (no modification)
- No LLM call is made
- No Ollama dependency

**Use cases:**
- Debugging BM25 filtering behavior
- Building custom extraction pipelines
- Quick document triage without LLM cost

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy"
}
```

## Output Schemas

### tasks_v1 (Default)

Extract actionable tasks with priorities and deadlines.

```json
{
  "status": "success",
  "data": {
    "tasks": [
      {
        "task": "string",
        "priority": "low|medium|high",
        "deadline": "ISO date string or null",
        "source": "doc_id_chunk_N"
      }
    ],
    "summary": "string"
  }
}
```

### summary_v1

Generate structured document summary.

```json
{
  "status": "success",
  "data": {
    "summary": "string",
    "key_points": ["string"]
  }
}
```

### entities_v1

Extract named entities.

```json
{
  "status": "success",
  "data": {
    "entities": [
      {
        "name": "string",
        "type": "person|organization|date|location|other",
        "source": "doc_id_chunk_N"
      }
    ]
  }
}
```

## Error Codes

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 400 | `VALIDATION_ERROR` | Invalid request format |
| 400 | `DOCUMENT_LIMIT` | More than 20 documents |
| 400 | `EMPTY_DOCUMENT` | Empty or whitespace-only content |
| 500 | `PROCESSING_ERROR` | Internal processing failed |
| 500 | `SCHEMA_MISMATCH` | LLM output didn't match schema |
| 504 | `TIMEOUT` | Processing exceeded timeout limit |

**Error Response Format:**
```json
{
  "detail": {
    "code": "PROCESSING_ERROR",
    "message": "Processing failed: description"
  }
}
```

## Usage Examples

### Example 1: Extract Tasks from Meeting Notes

```bash
curl -X POST http://localhost:8000/v1/transform \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "id": "meeting",
        "content": "Meeting Minutes: Product Launch Sync\nDate: 2026-04-28\n\nMike: The API integration needs to be done by April 30th. That'\''s high priority.\n\nDavid: We need to schedule a call with Legal about compliance. That'\''s urgent.\n\nSarah: Action item for me: Schedule user testing sessions."
      }
    ],
    "task": "extract tasks with deadlines and priorities",
    "schema": "tasks_v1"
  }' | jq
```

### Example 2: Process Multiple Documents

```bash
curl -X POST http://localhost:8000/v1/transform \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {"id": "doc1", "content": "..."},
      {"id": "doc2", "content": "..."},
      {"id": "doc3", "content": "..."}
    ],
    "task": "extract all action items",
    "schema": "tasks_v1"
  }' | jq
```

### Example 3: Extract Entities

```bash
curl -X POST http://localhost:8000/v1/transform \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "id": "article",
        "content": "John Smith from Acme Corp announced the merger on January 15, 2026 in New York."
      }
    ],
    "task": "extract people, organizations, and dates",
    "schema": "entities_v1"
  }' | jq
```

### Example 4: Generate Summary

```bash
curl -X POST http://localhost:8000/v1/transform \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {"id": "report", "content": "..."}
    ],
    "task": "summarize the key points",
    "schema": "summary_v1"
  }' | jq
```

### Example 5: Using with Python

```python
import httpx

payload = {
    "documents": [
        {
            "id": "meeting",
            "content": "Meeting notes content..."
        }
    ],
    "task": "extract tasks with deadlines",
    "schema": "tasks_v1"
}

response = httpx.post("http://localhost:8000/v1/transform", json=payload)
data = response.json()

print(f"Tasks found: {len(data['data']['tasks'])}")
print(f"Token reduction: {data['meta']['reduction_pct']}%")

for task in data['data']['tasks']:
    print(f"  - {task['task']} ({task['priority']})")
```

### Example 6: Check Token Reduction

```bash
python measure_reduction.py
```

Output:
```
doc                  | tokens_before | tokens_after | reduction | tasks_found
--------------------------------------------------------------------------------
meeting_notes.txt    |           941 |          389 |     58.7% |           4
email_thread.txt     |           850 |          340 |     60.0% |           3
```

## Hard Limits

| Constraint | Value |
|------------|-------|
| Max documents per request | 20 |
| Max document size | ~4,000 tokens |
| Max processing time | 60 seconds |
| Top chunks to LLM | 15 |
| LLM calls per request | 1 |

## Best Practices

### 1. Write Specific Task Queries

✅ Good:
```json
{
  "task": "API documentation deadline Legal compliance press release"
}
```

❌ Bad:
```json
{
  "task": "extract tasks"
}
```

Specific queries help BM25 filtering identify relevant chunks.

### 2. Monitor Token Reduction

Check `meta.reduction_pct` in responses:
- **60-80%**: ✅ Optimal
- **< 60%**: Consider raising BM25 threshold
- **> 85%**: May be dropping relevant content

### 3. Use Source Tracing for Debugging

Each extracted item includes a `source` field:
```json
{
  "task": "Update API docs",
  "source": "doc1_chunk_0"
}
```

This tells you exactly which document chunk produced each extraction.

### 4. Handle Errors Gracefully

```python
try:
    response = httpx.post(url, json=payload)
    response.raise_for_status()
    data = response.json()
    
    if data['status'] == 'success':
        # Process results
        pass
    else:
        # Handle error
        print(f"Error: {data['detail']['message']}")
        
except httpx.HTTPStatusError as e:
    print(f"HTTP Error: {e.response.status_code}")
except httpx.RequestError as e:
    print(f"Request failed: {e}")
```

### 5. Batch Related Documents

Instead of multiple API calls, send related documents together:
```json
{
  "documents": [
    {"id": "email1", "content": "..."},
    {"id": "email2", "content": "..."},
    {"id": "meeting_notes", "content": "..."}
  ],
  "task": "extract all action items"
}
```

The API will merge and deduplicate across all documents.

## Support

For issues or questions:
- Check logs: `tail -f uvicorn.log`
- Test endpoint: `curl http://localhost:8000/health`
- Review token reduction: `python measure_reduction.py`
