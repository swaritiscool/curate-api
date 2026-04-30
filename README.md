# Curate.ai

**Context structuring API for AI agents**

Transform messy multi-document input into clean, schema-locked JSON. No chat. No UI. Pure transformation pipeline.

```bash
POST messy multi-doc input → get back structured JSON
```

[📖 API Documentation](docs.md) | [📊 Token Reduction Guide](TOKEN_REDUCTION.md)

## Quick Start

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Ollama Cloud API key
# LLM_API_KEY=your-key
# OLLAMA_BASE_URL=https://cloud.ollama.com/v1/chat/completions

# Run server
python -m uvicorn main:app --reload --port 8000

# Test it
curl -X POST http://localhost:8000/v1/transform \
  -H "Content-Type: application/json" \
  -d '{"documents": [{"id": "doc1", "content": "Your text here"}], "task": "extract tasks", "schema": "tasks_v1"}' | jq
```

## What You Get

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
    "summary": "Meeting to discuss product launch."
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

## How It Works (Behind the Scenes)

Curate.ai isn't just an LLM wrapper. The real value is in the **pre-filtering pipeline** that happens before any LLM call:

```
┌─────────────────────────────────────────────────────────────────┐
│  Input: Messy multi-document text (1000s of tokens)             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: Chunking                                              │
│  - Split into 256-token chunks                                  │
│  - Tag each with doc_id, chunk_id, position                     │
│  - Never lose provenance                                        │
│                                                                  │
│  Output: 20-50 chunks with metadata                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: BM25 Pre-Filter (No LLM) ⭐                          │
│  - Score chunks against task query using BM25                   │
│  - Drop chunks below threshold (0.1 default)                    │
│  - Length filter removes boilerplate (<30 tokens)               │
│                                                                  │
│  Output: 6-15 chunks (60-80% reduction)                         │
│  💰 This is where you save money                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3: Relevance Ranking (No LLM)                            │
│  - Task-specific heuristics                                     │
│  - tasks_v1: Boost verb density                                 │
│  - entities_v1: Boost named entity signals                      │
│  - summary_v1: Boost information density                        │
│                                                                  │
│  Output: Top 15 chunks ranked by relevance                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 4: LLM Extraction (Single Call)                          │
│  - One structured prompt                                        │
│  - Strict schema injected as system instruction                 │
│  - JSON-only output (no prose, no markdown)                     │
│  - One retry if schema mismatch                                 │
│                                                                  │
│  Output: Structured JSON matching schema                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 5: Post-Processing                                       │
│  - Dedup identical extractions                                  │
│  - Normalize field values (lowercase priorities, ISO dates)     │
│  - Attach source chunk references                               │
│  - Validate final JSON against schema                           │
│                                                                  │
│  Output: Clean, validated JSON response                         │
└─────────────────────────────────────────────────────────────────┘
```

### Why the Pipeline Order Matters

If you skip stages 2-3 and just dump docs into the LLM, you're just a wrapper — no cost advantage, no differentiation. **The filtering is the product.**

**Without pre-filtering:**
- 10,000 tokens → LLM → $0.15
- Every chunk gets processed
- High latency, high cost

**With pre-filtering:**
- 10,000 tokens → BM25 → 2,000 tokens → LLM → $0.03
- 80% of tokens filtered before LLM call
- **5x cost reduction**

The non-LLM stages (chunking → BM25 filter → ranking) are where Curate.ai wins.

## Supported Schemas

### tasks_v1 (Default)
Extract actionable tasks with priorities and deadlines.

```json
{
  "tasks": [{"task": "...", "priority": "high", "deadline": "...", "source": "..."}],
  "summary": "..."
}
```

### summary_v1
Generate structured summaries with key points.

```json
{
  "summary": "...",
  "key_points": ["...", "..."]
}
```

### entities_v1
Extract named entities (people, orgs, dates, locations).

```json
{
  "entities": [{"name": "...", "type": "person", "source": "..."}]
}
```

## Hard Constraints

| Constraint | Value |
|------------|-------|
| Max documents | 20 per request |
| Max doc size | ~4,000 tokens |
| Max LLM calls | 1 per request |
| Max processing time | 15s hard timeout |
| Top chunks to LLM | 15 after filtering |
| JSON validation | Fail-fast after 1 retry |

## Token Reduction

BM25 pre-filtering typically achieves **60-80% token reduction**:

```
doc                 | tokens_before | tokens_after | reduction | tasks_found
--------------------|---------------|--------------|-----------|------------
meeting_notes.txt   | 941           | 389          | 58.7%     | 4
email_thread.txt    | 850           | 340          | 60.0%     | 3
mixed_docs.txt      | 2100          | 520          | 75.2%     | 5
```

**Measure your reduction:**
```bash
python measure_reduction.py
```

See [TOKEN_REDUCTION.md](TOKEN_REDUCTION.md) for details.

## Tech Stack

- **Framework:** FastAPI (Python)
- **Tokenization:** tiktoken (cl100k_base)
- **BM25:** rank_bm25
- **LLM:** Qwen 2.5 32B via Ollama (or OpenAI/Anthropic)
- **Validation:** Pydantic + JSON Schema

## Project Structure

```
curate-ai/
├── main.py                 # FastAPI app + route handlers
├── auth.py                 # API key auth + rate limiting
├── pipeline/
│   ├── chunker.py          # Document chunking with provenance
│   ├── filter.py           # BM25 pre-filtering + stats
│   ├── ranker.py           # Task-specific relevance ranking
│   ├── extractor.py        # LLM calls (Ollama/OpenAI/Anthropic)
│   └── postprocess.py      # Dedup, normalize, validate
├── schemas/
│   ├── models.py           # Pydantic models
│   ├── tasks_v1.json       # JSON schemas
│   ├── summary_v1.json
│   └── entities_v1.json
├── tests/
│   ├── test_chunker.py
│   ├── test_filter.py
│   ├── test_ranker.py
│   ├── test_extractor.py
│   ├── test_postprocess.py
│   ├── test_endpoint.py
│   ├── test_integration.py
│   └── conftest.py
├── test_inputs/            # Sample request payloads
├── requirements.txt
├── .env                    # API keys (never commit)
├── .env.example
├── README.md               # This file
├── docs.md                 # API documentation
└── TOKEN_REDUCTION.md      # Token reduction guide
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run pipeline tests
python test_pipeline.py

# Measure token reduction (requires running server)
python measure_reduction.py
```

**Test Results:**
```
============================== 49 passed in 0.71s ==============================
```

## Configuration

### Environment Variables (.env)

```bash
# LLM Configuration
LLM_API_KEY=ollama
OLLAMA_BASE_URL=http://localhost:11434

# Or use OpenAI
# LLM_API_KEY=sk-your-openai-key

# Or use Anthropic
# LLM_API_KEY=sk-ant-your-anthropic-key
# USE_ANTHROPIC=true

# API Authentication (optional)
# REQUIRED_API_KEY=your-secret-api-key
# API_KEY_HEADER=X-API-Key
```

### Tuning BM25 Filtering

Adjust in `main.py`:

```python
filtered_chunks, tokens_before, tokens_after, reduction_pct = prefilter_chunks_with_stats(
    all_chunks,
    request.task,
    bm25_threshold=0.1,  # Adjust: higher = more aggressive
    min_tokens=30
)
```

- **Threshold 0.05-0.1**: Lenient filtering (50-60% reduction)
- **Threshold 0.1-0.15**: Balanced (60-80% reduction) ✅
- **Threshold 0.15-0.2**: Aggressive (80-90% reduction)

## What Makes Curate.ai Different

### ✅ Pre-filtering kills 60-80% of tokens before LLM
Lower cost than calling the LLM directly on raw docs. The cheap filter IS the margin.

### ✅ Deterministic output schema
Agents can hardcode the response shape. No prompt engineering needed on the caller's side.

### ✅ Source tracing on every field
Debuggable. Agents and devs know exactly which doc chunk produced each result.

### ✅ Multi-doc merging with dedup
Signals from 20 docs collapsed into one clean object. Callers don't have to loop.

### ✅ Rigidity is the product
Vague or flexible schemas kill agent integrations. Output shape never shifts.

## What We Don't Do (By Design)

- ❌ No chat interface
- ❌ No UI
- ❌ No streaming (V1)
- ❌ No webhooks (V1)
- ❌ No multiple LLM calls per request
- ❌ No summarization modes beyond schema

Focus on the core transform until it's bulletproof.

## License

MIT

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Run tests: `python -m pytest tests/ -v`
5. Submit a PR

---

**Built for AI agents. Not for humans.**
