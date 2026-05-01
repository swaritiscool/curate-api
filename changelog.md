# Changelog

## 2026-04-30

### Added
- **Dynamic BM25 threshold** - Adjusts threshold based on doc count (1-2 docs: 1.5, 3-5 docs: 2.5, 6+: 3.0)
- **Early exit for small docs** - Skips BM25 filtering for documents <500 tokens (saves 5-25ms)
- **Schema-based LLM model selection** - Specific models per schema type (tasks, summary, entities)
- **HTTP connection pooling** - Reusable httpx client for 50-100ms savings
- **Chunk text trimming** - Reduces token count by 30-40% in prompts
- **Benchmark script** - Added `benchmark.py` for performance testing
- **Model config env vars** - `MODEL_TASKS`, `MODEL_SUMMARY`, `MODEL_ENTITIES`

### Changed
- **pipeline/extractor.py**:
  - Simplified prompt structure (30-40% token reduction)
  - Added more explicit entities format instructions
  - Added connection pooling with httpx client reuse
  - Model selection by schema type
  
- **pipeline/filter.py**:
  - BM25 scoring with cached regex patterns
  - Dynamic threshold support
  
- **pipeline/chunker.py**:
  - Token caching
  - Regex pre-compilation for faster chunking
  
- **pipeline/ranker.py**:
  - Uses `heapq.nlargest()` for O(n log k) performance
  - Score reuse and regex caching
  
- **pipeline/postprocess.py**:
  - Added `normalize_entities()` to handle flexible entity formats
  - Accepts both wrapped entities and raw list from LLM
  - Maps `entity` field → `name` field
  
- **AGENTS.md**:
  - Updated with recent optimizations
  - Performance results (48 passing tests, 85%+ time reduction for small docs)
  - Updated commands reference

### Fixed
- **Entities schema validation** - Properly validates full response and data-only formats
- **Entities extraction** - Handles LLM returning raw list instead of wrapped structure
- **Schema examples** - Updated to show clean format without wrapper for tasks

### Performance
- Small docs (<500 tokens): 85%+ pipeline time reduction (~8-15s → ~1.4-1.8s)
- Token reduction: Target 60-80% (68% at threshold 3.0)
- Tests: 48 passed, 1 skipped
