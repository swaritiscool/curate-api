# Token Reduction Measurement

Curate.ai uses BM25 pre-filtering to reduce token costs by **60-80%** before sending documents to the LLM.

## How It Works

1. **Chunk documents** into 256-token pieces with provenance tags
2. **Score chunks** using BM25 against your task query
3. **Filter out** low-scoring chunks (below threshold)
4. **Send only top chunks** to the LLM

## Response Format

Every API response includes token metrics in the `meta` field:

```json
{
  "status": "success",
  "data": { ... },
  "meta": {
    "chunks_used": 2,
    "tokens_used": 389,
    "docs_processed": 4,
    "tokens_before_filter": 941,
    "tokens_after_filter": 389,
    "reduction_pct": 58.7
  }
}
```

## Measuring Reduction

Run the measurement script:

```bash
python measure_reduction.py
```

Example output:

```
doc                  | tokens_before | tokens_after | reduction | tasks_found
--------------------------------------------------------------------------------
meeting_notes.txt    |           941 |          389 |     58.7% |           4
email_thread.txt     |           850 |          340 |     60.0% |           3
empty_noise.txt      |           600 |          120 |     80.0% |           0
```

## Interpreting Results

| Reduction % | Status | Action |
|-------------|--------|--------|
| < 60% | ⚠️ Too low | Raise BM25 threshold (currently 0.1) |
| 60-80% | ✅ Optimal | No action needed |
| > 85% | ⚠️ Too high | Lower threshold or check query quality |

## Tuning BM25 Threshold

Adjust in `main.py`:

```python
filtered_chunks, tokens_before, tokens_after, reduction_pct = prefilter_chunks_with_stats(
    all_chunks,
    request.task,
    bm25_threshold=0.1,  # Adjust this value
    min_tokens=30
)
```

- **Higher threshold** (e.g., 0.2) → More aggressive filtering → Higher reduction
- **Lower threshold** (e.g., 0.05) → Less filtering → Lower reduction

## Best Practices

1. **Use specific task queries** that contain terms from relevant documents
   - ✅ Good: `"API documentation deadline Legal compliance"`
   - ❌ Bad: `"extract tasks"` (too generic)

2. **Test with mixed content** (relevant + noise) to measure real-world performance

3. **Monitor task quality** alongside reduction - don't sacrifice accuracy for cost savings

4. **Typical production settings**:
   - `bm25_threshold`: 0.1-0.15
   - `min_tokens`: 30
   - Expected reduction: 65-75%

## Cost Impact

Example: Processing 100 documents/day

| Without Filter | With Filter (70% reduction) |
|----------------|----------------------------|
| 100,000 tokens | 30,000 tokens |
| ~$0.15/day | ~$0.045/day |
| ~$4.50/month | ~$1.35/month |
| **Save 70% on LLM costs** |

The pre-filter **pays for itself** by reducing token costs before any LLM call.
