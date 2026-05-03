# AGENTS.md - Curate.ai Development Guide

**For AI Agents working on this codebase**

## Quick Context

Curate.ai is a **document transformation API** for AI agents. It takes messy multi-doc input → returns schema-locked JSON.

**Key differentiator**: BM25 pre-filtering reduces tokens by 60-80% BEFORE any LLM call.

**Performance tip**: Small docs (<500 tokens) skip expensive BM25 filtering, reducing pipeline time by 85%+.

## Project Structure

```
/home/imperinovus/Projects/API-Tools/Curate/
├── main.py                      # FastAPI app, /v1/transform, /v1/compress endpoints
├── requirements.txt             # Python dependencies
├── .env                         # LLM_API_KEY, OLLAMA_BASE_URL=ollama-cloud
├── .env.example                 # Template for .env
│
├── pipeline/                    # Core processing pipeline
│   ├── chunker.py               # Split docs into 256-token chunks with provenance
│   ├── filter.py                # BM25 pre-filtering + token stats
│   ├── ranker.py                # Task-specific relevance ranking
│   ├── extractor.py             # LLM calls (Ollama Cloud, minimax-m2.5)
│   └── postprocess.py           # Dedup, normalize, validate
│
├── schemas/                     # Pydantic models + JSON schemas
│   ├── models.py                # TransformRequest, TaskResponse, etc.
│   ├── tasks_v1.json
│   ├── summary_v1.json
│   └── entities_v1.json
│
├── tests/                       # 61 passing tests
│   ├── test_chunker.py
│   ├── test_filter.py
│   ├── test_ranker.py
│   ├── test_extractor.py
│   ├── test_postprocess.py
│   ├── test_endpoint.py
│   ├── test_integration.py
│   ├── test_compress.py
│   └── conftest.py              # Fixtures, mocks main.call_llm
│
├── docs.md                      # API documentation (for humans)
├── TOKEN_REDUCTION.md           # Token filtering guide
├── test_pipeline.py             # Pipeline tests without LLM
├── measure_reduction.py         # Token reduction measurement script
└── test_inputs/                 # Sample request payloads
```

## Core Pipeline Flow

```
POST /v1/transform
    ↓
1. chunker.chunk_documents() → List[chunk_with_doc_id, chunk_id, position, text, token_count]
    ↓
2. filter.prefilter_chunks_with_stats() → filtered_chunks, tokens_before, tokens_after, reduction_pct
    ↓
3. ranker.rank_chunks() → top 15 chunks by relevance
    ↓
4. extractor.call_llm() → JSON response (minimax-m2.5 via Ollama Cloud)
    ↓
5. postprocess.build_response() → final API response
```

## Compress Endpoint (Stages 1-3 Only)

```
POST /v1/compress
    ↓
1. chunker.chunk_documents() → List[chunk_with_doc_id, chunk_id, position, text, token_count]
    ↓
2. filter.prefilter_chunks_with_stats() → filtered_chunks, tokens_before, tokens_after, reduction_pct
    ↓
3. ranker.rank_chunks() → top 15 chunks by relevance
    ↓
Returns ranked chunks as plain text JSON (no LLM call)
```

## Key Files to Modify

### Adding a new schema type

1. **Add to `schemas/models.py`**:
   ```python
   class NewSchemaData(BaseModel):
       # fields...
   
   class NewSchemaResponse(BaseModel):
       status: Literal["success", "error"]
       data: NewSchemaData
       meta: Meta
   ```

2. **Add JSON schema** `schemas/new_schema_v1.json`

3. **Update `main.py`** TransformRequest:
   ```python
   schema_type: Literal["tasks_v1", "summary_v1", "entities_v1", "new_schema_v1"]
   ```

4. **Update `pipeline/ranker.py`** rank_chunks():
   ```python
   elif schema_type == "new_schema_v1":
       score = your_heuristic(text)
   ```

5. **Update `pipeline/postprocess.py`** build_response():
   ```python
   elif schema_type == "new_schema_v1":
       data = {"new_field": extraction.get("new_field", [])}
   ```

6. **Update `pipeline/extractor.py`** build_extract_prompt():
   ```python
   schema_examples["new_schema_v1"] = '''{...}'''
   ```

### Changing the LLM model

Edit `pipeline/extractor.py`:
```python
async def call_llm(..., model: str = None) -> str:
    if model is None:
        if schema_type == "summary_v1":
            model = "minimax-m2.5"  # or other model
        else:
            model = "minimax-m2.5"  # primary model
```

### Adjusting BM25 threshold

In `main.py` transform():
```python
filtered_chunks, tokens_before, tokens_after, reduction_pct = prefilter_chunks_with_stats(
    all_chunks,
    request.task,
    bm25_threshold=3.0,  # Adjust: 2.0=moderate, 4.0=aggressive
    min_tokens=30
)
```

Target: 50-70% reduction.

Use `tuner.py --test` to find optimal threshold for your documents.

| Threshold | Reduction | Chunks Survive |
|-----------|-----------|----------------|
| 2.0       | ~52%      | 22/48          |
| 2.5       | ~63%      | 17/48          |
| **3.0**   | **~68%**  | **15/48**      |
| 3.5       | ~72%      | 13/48          |
| 4.0       | ~80%      | 9/48           |

### Adding new token metrics

1. **Track in `pipeline/filter.py`** prefilter_chunks_with_stats()
2. **Pass through `main.py`** to build_response()
3. **Add to `pipeline/postprocess.py`** build_response() meta dict

## Testing Protocol

**Before committing changes:**

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

Must have **61 passing tests**.

**Test file purposes:**
- `test_chunker.py` - Chunking logic, provenance tags
- `test_filter.py` - BM25 filtering, token reduction
- `test_ranker.py` - Relevance ranking heuristics
- `test_extractor.py` - LLM prompt building, JSON parsing
- `test_postprocess.py` - Dedup, normalization, validation
- `test_endpoint.py` - API endpoint behavior (mocked LLM)
- `test_integration.py` - Full pipeline integration
- `test_compress.py` - /v1/compress endpoint tests (no LLM)

**Mocking pattern** (critical for endpoint tests):

Tests mock `main.call_llm` (not `pipeline.extractor.call_llm`) because main.py imports it directly:

```python
# In conftest.py or test file
import main

async def mock_call(*args, **kwargs):
    return json.dumps({"tasks": [], "summary": "test"})

monkeypatch.setattr(main, "call_llm", mock_call)
```

## Common Tasks

### Debug schema validation failures

Check server console logs - they show:
```
LLM Response (attempt 1): {raw JSON}...
Parsed result keys: dict_keys([...])
Schema validation failed. Got: {...}
```

If validation fails, the issue is usually:
1. Missing required keys in `data` field
2. `tasks` is not a list
3. Response wrapped in markdown code blocks (LLM error)

### Check token reduction

```bash
python measure_reduction.py
```

Look for 60-80% reduction. If lower, increase `bm25_threshold` in `main.py`.

### Test with real LLM

1. Set `.env`:
   ```bash
   LLM_API_KEY=your-ollama-cloud-key
   OLLAMA_BASE_URL=ollama-cloud
   ```

2. Run server: `python -m uvicorn main:app --reload --port 8000`

3. Test:
   ```bash
   curl -X POST http://localhost:8000/v1/transform \
     -H "Content-Type: application/json" \
     -d '{"documents": [{"id": "d1", "content": "test"}], "task": "extract tasks", "schema": "tasks_v1"}' | jq
   ```

## Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `LLM_API_KEY` | Ollama Cloud API key | `your-key-here` |
| `OLLAMA_BASE_URL` | Set to `ollama-cloud` for Ollama Cloud | `ollama-cloud` |
| `MODEL_TASKS` | Model for tasks extraction | `ministral-3:3b` (default) |
| `MODEL_SUMMARY` | Model for summary extraction | `minimax-m2.5` (default) |
| `MODEL_ENTITIES` | Model for entities extraction | `qwen3.5` (default) |

### Recommended Model Configurations

| Schema Type | Fastest Model | Most Accurate | Recommended |
|-------------|---------------|---------------|-------------|
| Tasks extraction | `qwen3.5` | `ministral-3:3b` | `ministral-3:3b` |
| Summary extraction | `qwen3.5` | `minimax-m2.5` | `gemini-3-flash-preview` |
| Entities extraction | `qwen3.5` | `ministral-3:3b` | `gemini-3-flash-preview` |

## Hard Constraints (Never Change)

- Max 20 documents per request
- Max ~4000 tokens per document
- Max 15 chunks to LLM
- Max 15s processing time
- Max 1 LLM call per request (with 1 retry on schema mismatch)

## Current LLM Setup

- **Provider**: Ollama Cloud
- **Models** (schema-based selection via env vars):
  - `MODEL_TASKS`: `ministral-3:3b` (default)
  - `MODEL_SUMMARY`: `gemini-3-flash-preview` (default) 
  - `MODEL_ENTITIES`: `ministral-3:3b` (default)
- **Client**: Official `ollama` Python package + httpx client with connection pooling
- **Auth**: Bearer token via `LLM_API_KEY`

**Model Selection**: Edit `pipeline/extractor.py` or set environment variables in `.env`:
```bash
MODEL_TASKS=ministral-3:3b
MODEL_SUMMARY=minimax-m2.5
MODEL_ENTITIES=qwen3.5
```

## Known Issues / TODOs

- [ ] Improve BM25 threshold auto-tuning
- [ ] Add async batch processing (target: 0.7-1.3s LLM time with batching) (target: 0.7-1.3s LLM time with batching)

## Recent Changes (2026-05-03)

### New Endpoint Added:
- **POST /v1/compress**: Runs pipeline stages 1-3 only (chunk → filter → rank). Returns ranked chunks as plain text JSON. No LLM call, no Ollama dependency.

### Optimizations Completed:
1. **Early Exit for Small Docs**: Skip BM25 filtering for documents with <500 tokens (saves 5-25ms)
2. **Dynamic BM25 Threshold**: Adjust threshold based on doc count (1-2 docs: 1.5, 3-5 docs: 2.5, 6+: 3.0)
3. **Model Selection**: Schema-based LLM selection (ministral-3:3b, minimax-m2.5, qwen3.5)
4. **Prompt Optimization**: Simplified prompts + chunk text trimming (30-40% token reduction)
5. **Connection Pooling**: Reusable httpx client with connection pooling (50-100ms savings)

### Files Modified:
- `main.py` - Added /v1/compress endpoint
- `schemas/models.py` - Added CompressResponse, CompressChunk, CompressMeta models
- `tests/test_compress.py` - New test file with 13 tests
- `AGENTS.md` - This file

### Performance Results:
- **Small docs (<500 tokens)**: 85%+ pipeline time reduction (~8-15s → ~1.4-1.8s)
- **Tests**: 61 passed, 1 skipped
- **LLM Time**: Currently 1.3s-8.3s (target: 0.7-1.3s with batching)

### Token Reduction Optimization:
Run `python measure_reduction.py` for tuning recommendations. Target: 60-80% reduction.

## Commands Reference

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v
python -m pytest tests/test_filter.py -v  # specific file

# Run server
python -m uvicorn main:app --reload --port 8000

# Measure token reduction
python measure_reduction.py

# Check imports
python -c "from main import app; print('OK')"
```

## When You Get Stuck

1. **Check test logs**: `python -m pytest tests/ -xvs` for verbose output
2. **Check server logs**: Console shows LLM requests/responses
3. **Verify .env**: `cat .env` to check API key is set
4. **Test pipeline without LLM**: `python test_pipeline.py`

---

**Last Updated**: 2026-05-03
**Tests**: 61 passing
**LLM**: minimax-m2.5 via Ollama Cloud
