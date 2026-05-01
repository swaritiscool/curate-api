from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import asyncio
import time
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add file handler for time.log (only if not already added)
time_handler = None
for handler in logger.handlers:
    if isinstance(handler, logging.FileHandler) and handler.baseFilename == 'time.log':
        time_handler = handler
        break

if time_handler is None:
    time_handler = logging.FileHandler('time.log')
    time_handler.setLevel(logging.INFO)
    time_format = logging.Formatter('%(asctime)s - %(message)s')
    time_handler.setFormatter(time_format)
    logger.addHandler(time_handler)

from schemas.models import (
    TransformRequest,
    TaskResponse,
    SummaryResponse,
    EntityResponse,
    Priority
)
from pipeline.chunker import chunk_documents, count_tokens, count_chunks_tokens
from pipeline.filter import prefilter_chunks_with_stats
from pipeline.ranker import rank_chunks
from pipeline.extractor import call_llm, build_extract_prompt, parse_llm_response, get_model
from pipeline.postprocess import (
    postprocess_extraction,
    validate_against_schema,
    build_response
)
from auth import (
    validate_api_key,
    init_api_key,
    get_usage_stats,
    ErrorCode
)

app = FastAPI(
    title="Curate.ai",
    description="Context structuring API for AI agents",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    init_api_key()


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up httpx client on shutdown"""
    from pipeline.extractor import cleanup_httpx_client
    cleanup_httpx_client()

MAX_DOCUMENTS = 20
MAX_DOC_TOKENS = 4000
MAX_LLM_CALLS = 1
MAX_PROCESSING_TIME = 60  # Increased from 15s to 60s for slower LLMs
TOP_CHUNKS_TO_LLM = 15
MAX_RETRIES = 1


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/v1/transform")
async def transform(request: TransformRequest, req: Request):
    """
    Transform messy multi-document input into structured JSON.
    
    Pipeline:
    1. Chunking with provenance
    2. BM25 pre-filter
    3. Relevance ranking
    4. LLM extraction (single call)
    5. Post-processing
    """
    await validate_api_key(req)
    
    start_time = time.time()
    logger.info(f"_pipeline_start - request_id={id(request)}")
    
    if len(request.documents) > MAX_DOCUMENTS:
        raise HTTPException(
            status_code=400,
            detail={"code": ErrorCode.DOCUMENT_LIMIT, "message": f"Maximum {MAX_DOCUMENTS} documents allowed per request"}
        )
    
    if not request.documents:
        raise HTTPException(
            status_code=400,
            detail={"code": ErrorCode.EMPTY_DOCUMENT, "message": "At least one document required"}
        )

    for doc in request.documents:
        if not doc.content.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": ErrorCode.EMPTY_DOCUMENT, "message": "Document content cannot be empty"}
            )
        if count_tokens(doc.content) > MAX_DOC_TOKENS:
            raise HTTPException(
                status_code=400,
                detail={"code": ErrorCode.DOCUMENT_LIMIT, "message": f"Document exceeds {MAX_DOC_TOKENS} token limit"}
            )
    
    try:
        # Stage 1: Chunking
        print(f"\n📊 [Pipeline Stage 1/5] Chunking {len(request.documents)} documents...")
        # Convert Pydantic Document objects to dicts for chunk_documents
        docs_as_dicts = [{"id": str(doc.id), "content": str(doc.content)} for doc in request.documents]
        
        # FIX-1 Debug: Log document classifications
        from pipeline.chunker import classify_doc_type
        for doc in docs_as_dicts:
            doc_type = classify_doc_type(doc['content'])
            doc['doc_type'] = doc_type
            print(f"   Document '{doc['id']}': {doc_type}")
        
        stage1_start = time.time()
        all_chunks = chunk_documents(docs_as_dicts, chunk_size=256, overlap=50)
        stage1_time = time.time() - stage1_start
        logger.info(f"stage1_chunking - time={stage1_time:.3f}s chunks={len(all_chunks)} request_id={id(request)}")
        print(f"   ✓ Created {len(all_chunks)} chunks")
        
        if not all_chunks:
            raise HTTPException(
                status_code=400,
                detail={"code": ErrorCode.EMPTY_DOCUMENT, "message": "No valid content found in documents"}
            )
        
        # Stage 2: BM25 Pre-filtering
        # Early exit for small documents (\u003c500 tokens) - BM25 overhead not worth it
        stage2_start = time.time()
        print(f"\n📊 [Pipeline Stage 2/5] BM25 pre-filtering (query: '{request.task[:50]}...')")
        
        from pipeline.chunker import count_chunks_tokens
        total_tokens_before = count_chunks_tokens(all_chunks)
        
        if total_tokens_before < 500:
            print(f"   🔍 Early exit: \u003c500 tokens, skipping BM25 filtering")
            filtered_chunks = all_chunks
            tokens_before = total_tokens_before
            tokens_after = total_tokens_before
            reduction_pct = 0.0
        else:
            # Dynamic BM25 threshold based on document count
            doc_count = len(request.documents)
            if doc_count <= 2:
                bm25_threshold = 1.5
                print(f"   🔍 Dynamic threshold: {bm25_threshold} (low doc count: {doc_count})")
            elif doc_count <= 5:
                bm25_threshold = 2.5
                print(f"   🔍 Dynamic threshold: {bm25_threshold} (med doc count: {doc_count})")
            else:
                bm25_threshold = 3.0
                print(f"   🔍 Dynamic threshold: {bm25_threshold} (high doc count: {doc_count})")
            
            filtered_chunks, tokens_before, tokens_after, reduction_pct = prefilter_chunks_with_stats(
                all_chunks,
                request.task,
                bm25_threshold=bm25_threshold,
                min_tokens=30
            )
        stage2_time = time.time() - stage2_start
        logger.info(f"stage2_filtering - time={stage2_time:.3f}s tokens_before={tokens_before} tokens_after={tokens_after} reduction_pct={reduction_pct:.1f}% request_id={id(request)}")
        print(f"   ✓ Tokens: {tokens_before} → {tokens_after} ({reduction_pct}% reduction)")
        print(f"   ✓ Chunks: {len(all_chunks)} → {len(filtered_chunks)}")
        
        # Stage 3: Relevance Ranking
        stage3_start = time.time()
        print(f"\n📊 [Pipeline Stage 3/5] Ranking chunks by relevance...")
        
        # Rank all chunks first
        ranked_chunks = rank_chunks(
            filtered_chunks,
            request.task,
            request.schema_type,
            top_n=TOP_CHUNKS_TO_LLM
        )
        
        # FIX-2: Apply per-document chunk allocation instead of global top-N
        from pipeline.ranker import select_top_chunks_per_doc
        doc_list = [{"id": str(doc.id), "content": str(doc.content), "token_count": count_tokens(str(doc.content))} 
                    for doc in request.documents]
        ranked_chunks = select_top_chunks_per_doc(ranked_chunks, doc_list, total_budget=TOP_CHUNKS_TO_LLM)
        stage3_time = time.time() - stage3_start
        logger.info(f"stage3_ranking - time={stage3_time:.3f}s chunks_selected={len(ranked_chunks)} request_id={id(request)}")
        
        if not ranked_chunks:
            ranked_chunks = all_chunks[:TOP_CHUNKS_TO_LLM]
            tokens_after = count_chunks_tokens(ranked_chunks)
            if tokens_before > 0:
                reduction_pct = round((1 - tokens_after / tokens_before) * 100, 1)
        
        print(f"   ✓ Selected top {len(ranked_chunks)} chunks for LLM (per-doc allocation)")
        
        total_tokens = tokens_after
        
        # Stage 4: LLM Extraction
        stage4_start = time.time()
        model = get_model(request.schema_type)
        print(f"\n📊 [Pipeline Stage 4/5] Calling LLM ({model})...")
        prompt = build_extract_prompt(ranked_chunks, request.task, request.schema_type)
        
        extraction_result = None
        retry_count = 0
        
        while retry_count <= MAX_RETRIES:
            try:
                llm_start = time.time()
                llm_response = await call_llm(prompt, request.schema_type, model=model)
                llm_time = time.time() - llm_start
                print(f"   ✓ LLM Response (attempt {retry_count + 1}): {llm_response[:200]}...")
                
                extraction_result = parse_llm_response(llm_response)
                print(f"   ✓ Parsed result keys: {extraction_result.keys() if isinstance(extraction_result, dict) else 'Not a dict'}")
                
                if validate_against_schema(extraction_result, request.schema_type):
                    print(f"   ✓ Schema validation passed")
                    break
                else:
                    print(f"   ✗ Schema validation failed. Got: {extraction_result}")
                    retry_count += 1
                    if retry_count > MAX_RETRIES:
                        raise HTTPException(
                            status_code=500,
                            detail={"code": ErrorCode.SCHEMA_MISMATCH, "message": f"LLM output failed schema validation after 1 retry. Got: {str(extraction_result)[:200]}"}
                        )
            except json.JSONDecodeError as e:
                print(f"   ✗ JSON decode error: {e}. Raw response: {llm_response[:200]}")
                retry_count += 1
                if retry_count > MAX_RETRIES:
                    raise HTTPException(
                        status_code=500,
                        detail={"code": ErrorCode.SCHEMA_MISMATCH, "message": f"LLM output was not valid JSON after 1 retry. Raw: {llm_response[:200]}"}
                    )
        
        stage4_time = time.time() - stage4_start
        logger.info(f"stage4_llm - time={stage4_time:.3f}s llm_only={llm_time:.3f}s attempt={retry_count + 1} request_id={id(request)}")
        
        # Stage 5: Post-processing
        stage5_start = time.time()
        print(f"\n📊 [Pipeline Stage 5/5] Post-processing results...")
        processed = postprocess_extraction(
            extraction_result,
            ranked_chunks,
            request.schema_type
        )
        stage5_time = time.time() - stage5_start
        logger.info(f"stage5_postprocess - time={stage5_time:.3f}s tasks={len(processed.get('tasks', []))} request_id={id(request)}")
        print(f"   ✓ Extracted {len(processed.get('tasks', []))} tasks")
        
        processing_time = time.time() - start_time
        logger.info(f"pipeline_complete - total_time={processing_time:.3f}s tokens={total_tokens} chunks={len(ranked_chunks)} request_id={id(request)}")
        if processing_time > MAX_PROCESSING_TIME:
            print(f"\n✗ TIMEOUT: Processing took {processing_time:.1f}s (limit: {MAX_PROCESSING_TIME}s)")
            raise HTTPException(
                status_code=504,
                detail={"code": ErrorCode.TIMEOUT, "message": f"Processing exceeded {MAX_PROCESSING_TIME}s timeout"}
            )
        
        # FIX-1: Add doc_type classifications to meta for debugging
        doc_classifications = {str(doc.id): doc_type for doc, doc_type in 
                              zip(request.documents, [classify_doc_type(str(doc.content)) for doc in request.documents])}
        
        response = build_response(
            processed,
            chunks_used=len(ranked_chunks),
            tokens_used=total_tokens,
            docs_processed=len(request.documents),
            schema_type=request.schema_type,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            reduction_pct=reduction_pct,
            doc_classifications=doc_classifications
        )
        
        print(f"\n✅ Pipeline completed in {processing_time:.2f}s")
        print(f"   Response: {len(ranked_chunks)} chunks, {total_tokens} tokens, {reduction_pct}% reduction\n")
        logger.info(f"pipeline_summary - total_time={processing_time:.3f}s tokens={total_tokens} chunks={len(ranked_chunks)} reduction_pct={reduction_pct:.1f}% request_id={id(request)}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": ErrorCode.PROCESSING_ERROR, "message": f"Processing failed: {str(e)}"}
        )


@app.get("/")
async def root():
    return {
        "name": "Curate.ai",
        "version": "1.0.0",
        "description": "Context structuring API for AI agents",
        "endpoints": {
            "transform": "POST /v1/transform",
            "health": "GET /health",
            "usage": "GET /v1/usage"
        }
    }


@app.get("/v1/usage")
async def get_usage(request: Request):
    """Get usage statistics (requires API key)"""
    api_key = await validate_api_key(request)
    
    if not api_key:
        return {"message": "API key not required"}
    
    stats = get_usage_stats(api_key)
    return stats


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
