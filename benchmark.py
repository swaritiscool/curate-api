#!/usr/bin/env python3
"""
Performance benchmark script for Curate.ai
Measures timing improvements from pipeline optimizations.
"""

import time
import asyncio
import json
from pathlib import Path

# Pipeline imports
from pipeline.chunker import chunk_documents, classify_doc_type, count_chunks_tokens
from pipeline.filter import prefilter_chunks_with_stats
from pipeline.ranker import rank_chunks
from pipeline.extractor import build_extract_prompt, parse_llm_response
from pipeline.postprocess import postprocess_extraction, validate_against_schema, dedup_extractions, attach_source_references

# Fixtures for testing
MEETING_NOTES = """Meeting Minutes: Product Launch Sync
Date: 2026-04-28
Participants: Sarah (PM), Mike (Eng), Elena (Design), David (Dev)

Agenda:
1. Product launch timeline
2. API documentation needs
3. Dashboard integration plans

Sarah: We need to update the API documentation before the launch. Can you ping Elena about the technical details?
Mike: Yes, I'll update the docs by April 30. Elena: can you review the API reference?

Elena: Yes, I'll review by May 2. Mike: also, we need to schedule maintenance this weekend.

Sarah: Right. Let's make sure that's communicated clearly. Okay, thanks everyone!
"""

SMALL_TEXT = "This is a small document with just a few words."

LARGE_TEXT = """Document 1: Technical Overview
This is a longer document that contains technical documentation about the system architecture. 
It covers various components like Kubernetes, Docker, microservices, and deployment strategies.
The document also mentions API endpoints, authentication, and authorization mechanisms.

Document 2: Meeting Notes
Meeting Minutes: Team Sync
Participants: John, Jane, Bob
Date: 2026-04-28

Action Items:
1. John needs to complete the API documentation
2. Jane should update the deployment guide
3. Bob will review the architecture diagrams

Document 3: Task List
- Fix critical bug in production
- Deploy new version by end of week
- Schedule follow-up meeting for next Monday
- Review security audit findings

Document 4: Reference Material
The system uses Kubernetes for orchestration. 
Each service runs in its own container.
API gateway handles authentication and rate limiting.
Database is PostgreSQL with read replicas.
"""

async def benchmark_pipeline():
    """Run benchmark on the pipeline"""
    try:
        import httpx
    except ImportError:
        print("httpx not installed. Run: pip install httpx")
        return
    
    from pipeline.chunker import count_chunks_tokens
    from pipeline.filter import prefilter_chunks_with_stats
    from pipeline.ranker import rank_chunks
    from pipeline.extractor import build_extract_prompt, parse_llm_response
    from pipeline.postprocess import build_response, validate_against_schema
    
    print("\n" + "="*80)
    print("CURATE.AI PERFORMANCE BENCHMARK")
    print("="*80)
    
    # Mock LLM call
    def mock_llm_call(*args, **kwargs):
        return json.dumps({
            "tasks": [
                {"task": "Update API documentation", "priority": "high", "deadline": "2026-04-30", "source": "doc1_chunk_0"},
                {"task": "Deploy new version", "priority": "high", "deadline": "2026-05-05", "source": "doc2_chunk_0"}
            ],
            "summary": "Meeting to discuss product launch and deployment."
        })
    
    async def mock_async_call(*args, **kwargs):
        return mock_llm_call(*args, **kwargs)
    
    # Test cases
    test_cases = [
        ("Small doc (single chunk, \u003c500 tokens)", SMALL_TEXT, 1),
        ("Medium doc (4 docs, \u003c500 tokens)", LARGE_TEXT, 4),
        ("Large doc (multiple chunks, \u003e500 tokens)", MEETING_NOTES, 1),
    ]
    
    for test_name, content, doc_count in test_cases:
        print(f"\n{'─'*80}")
        print(f"Test: {test_name}")
        print(f"{'─'*80}")
        
        # Prepare documents
        documents = [{"id": f"doc_{i}", "content": content} for i in range(doc_count)]
        
        # Stage 1: Chunking
        from pipeline.chunker import chunk_documents
        stage1_start = time.time()
        from pipeline.chunker import classify_doc_type
        for doc in documents:
            doc['doc_type'] = classify_doc_type(doc['content'])
        all_chunks = chunk_documents(documents, chunk_size=256, overlap=50)
        stage1_time = (time.time() - stage1_start) * 1000
        tokens_before = count_chunks_tokens(all_chunks)
        
        print(f"  Stage 1 (Chunking): {stage1_time:.2f}ms, {len(all_chunks)} chunks, {tokens_before} tokens")
        
        stage2_time = 0.0
        stage4_time = 0.0
        tokens_after = tokens_before
        reduction_pct = 0.0
        filtered_chunks = all_chunks
        
        # Stage 2: Early exit check
        if tokens_before < 500:
            print(f"  Stage 2 (Filtering): SKIPPED \u003c500 tokens")
            tokens_after = tokens_before
            reduction_pct = 0.0
            filtered_chunks = all_chunks
        else:
            # Stage 2: BM25 filtering
            stage2_start = time.time()
            filtered_chunks, tokens_before, tokens_after, reduction_pct = prefilter_chunks_with_stats(
                all_chunks, "extract tasks", bm25_threshold=3.0, min_tokens=30
            )
            stage2_time = (time.time() - stage2_start) * 1000
            print(f"  Stage 2 (Filtering): {stage2_time:.2f}ms, {tokens_before} \u2192 {tokens_after} tokens ({reduction_pct}% reduction)")
        
        # Stage 3: Ranking
        stage3_start = time.time()
        ranked_chunks = rank_chunks(filtered_chunks, "extract tasks", "tasks_v1", top_n=15)
        stage3_time = (time.time() - stage3_start) * 1000
        print(f"  Stage 3 (Ranking): {stage3_time:.2f}ms, {len(ranked_chunks)} chunks selected")
        
        # Stage 4: LLM call
        stage4_start = time.time()
        prompt = build_extract_prompt(ranked_chunks, "extract tasks", "tasks_v1")
        llm_response = await mock_async_call(prompt, "tasks_v1")
        stage4_time = (time.time() - stage4_start) * 1000
        print(f"  Stage 4 (LLM): {stage4_time:.2f}ms (mock, would be 5000-8000ms real)")
        
        # Parse and validate
        extraction = parse_llm_response(llm_response)
        is_valid = validate_against_schema(extraction, "tasks_v1")
        
        # Stage 5: Post-processing
        stage5_start = time.time()
        processed = postprocess_extraction(extraction, ranked_chunks, "tasks_v1")
        stage5_time = (time.time() - stage5_start) * 1000
        print(f"  Stage 5 (Postprocess): {stage5_time:.2f}ms")
        
        total_time = stage1_time + stage2_time + stage3_time + stage4_time + stage5_time
        print(f"{'─'*80}")
        print(f"  TOTAL PIPELINE TIME: {total_time:.2f}ms")
        print(f"  (Mock LLM: 0ms, Real LLM: ~{stage4_time + 6000:.0f}ms)")
        print(f"  Response tasks: {len(processed.get('tasks', []))}")
        print(f"  Schema valid: {is_valid}")
    
    print(f"\n{'='*80}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(benchmark_pipeline())
