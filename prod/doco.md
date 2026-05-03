# Curate.ai Go API Documentation

## Overview

The Curate.ai Go API transforms messy multi-document input into schema-locked JSON using BM25 pre-filtering and LLM extraction.

**Base URL**: `http://localhost:8000`

## Endpoints

### GET /v1/health

Health check endpoint.

**Response:**
```json
{
  "status": "ok"
}
```

### POST /v1/transform

Extracts structured data from documents based on a task prompt.

**Request Body:**
```json
{
  "documents": [
    {
      "id": "doc1",
      "content": "Your document text here...",
      "doc_type": "task"
    }
  ],
  "task": "Extract all action items and their priorities",
  "schema_type": "tasks_v1"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `documents` | array | Yes | 1-20 documents to process |
| `documents[].id` | string | Yes | Unique document identifier |
| `documents[].content` | string | Yes | Document text (max ~4000 tokens) |
| `documents[].doc_type` | string | No | `"task"` or `"reference"` |
| `task` | string | Yes | Natural language extraction task |
| `schema_type` | string | Yes | Output schema: `tasks_v1`, `summary_v1`, or `entities_v1` |

**Schema Types:**
- `tasks_v1` — Extracts action items with priority and deadline
- `summary_v1` — Generates a text summary
- `entities_v1` — Extracts named entities

**Response:**
```json
{
  "status": "success",
  "data": {
    "tasks": [
      {
        "task": "Review Q1 budget report",
        "priority": "high",
        "deadline": "2026-05-15",
        "source": "doc1"
      }
    ]
  },
  "meta": {
    "chunks_used": 5,
    "tokens_used": 842,
    "docs_processed": 1,
    "tokens_before_filter": 1200,
    "tokens_after_filter": 480,
    "reduction_pct": 60.0,
    "doc_classifications": {"doc1": "task"}
  }
}
```

## Example Usage

### cURL

```bash
curl -X POST http://localhost:8000/v1/transform \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {
        "id": "email1",
        "content": "Please review the API documentation by Friday. High priority.",
        "doc_type": "task"
      }
    ],
    "task": "Extract all tasks with their priorities and deadlines",
    "schema_type": "tasks_v1"
  }'
```

### Python

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/transform",
    json={
        "documents": [
            {
                "id": "email1",
                "content": "Please review the API documentation by Friday. High priority.",
                "doc_type": "task"
            }
        ],
        "task": "Extract all tasks with their priorities and deadlines",
        "schema_type": "tasks_v1"
    }
)
print(response.json())
```

### Go

```go
package main

import (
    "bytes"
    "encoding/json"
    "fmt"
    "net/http"
)

type Document struct {
    ID      string `json:"id"`
    Content string `json:"content"`
    DocType string `json:"doc_type"`
}

type TransformRequest struct {
    Documents  []Document `json:"documents"`
    Task       string     `json:"task"`
    SchemaType string     `json:"schema_type"`
}

func main() {
    reqBody := TransformRequest{
        Documents: []Document{
            {
                ID:      "email1",
                Content: "Please review the API documentation by Friday. High priority.",
                DocType: "task",
            },
        },
        Task:       "Extract all tasks with their priorities and deadlines",
        SchemaType: "tasks_v1",
    }

    body, _ := json.Marshal(reqBody)
    resp, err := http.Post(
        "http://localhost:8000/v1/transform",
        "application/json",
        bytes.NewBuffer(body),
    )
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()

    var result map[string]interface{}
    json.NewDecoder(resp.Body).Decode(&result)
    fmt.Println(result)
}
```

## Error Responses

| Code | Message | Cause |
|------|---------|-------|
| 400 | At least one document required | Empty documents array |
| 400 | Maximum 20 documents allowed | Too many documents |
| 400 | Task cannot be empty | Missing task field |
| 400 | Invalid schema type | Unknown schema |
| 400 | Document X exceeds 4000 token limit | Document too large |
| 500 | Internal server error | Pipeline failure |

**Error format:**
```json
{
  "status": "error",
  "message": "Invalid schema type",
  "code": 400
}
```

## Token Reduction

The API reports token usage in `meta`:
- `tokens_before_filter` — Total tokens before BM25 filtering
- `tokens_after_filter` — Tokens after filtering (sent to LLM)
- `reduction_pct` — Percentage reduction achieved

This helps track cost savings from the pre-filtering step.
