from typing import List, Dict, Any, Tuple
from rank_bm25 import BM25Okapi
import re


def tokenize_for_bm25(text: str) -> List[str]:
    """Simple tokenization for BM25"""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text.split()


def build_bm25_index(chunks: List[Dict[str, Any]]) -> BM25Okapi:
    """
    Build BM25 index from chunks.
    
    Args:
        chunks: List of chunk dicts with 'text' field
    
    Returns:
        BM25Okapi index
    """
    tokenized_docs = [tokenize_for_bm25(chunk["text"]) for chunk in chunks]
    return BM25Okapi(tokenized_docs)


def score_chunks(
    bm25: BM25Okapi,
    query: str,
    threshold: float = 0.5
) -> List[int]:
    """
    Score chunks against query and return indices above threshold.
    
    Args:
        bm25: BM25 index
        query: Query string (task field)
        threshold: Minimum score threshold
    
    Returns:
        List of chunk indices above threshold
    """
    tokenized_query = tokenize_for_bm25(query)
    scores = bm25.get_scores(tokenized_query)
    
    indices_above_threshold = [
        idx for idx, score in enumerate(scores)
        if score >= threshold
    ]
    
    return indices_above_threshold


def filter_chunks_bm25(
    chunks: List[Dict[str, Any]],
    query: str,
    threshold: float = 0.1
) -> List[Dict[str, Any]]:
    """
    Filter chunks using BM25 scoring against query.
    FIX-1: Applies 2x stricter threshold to reference docs.
    
    Args:
        chunks: List of chunk dicts
        query: Query string for scoring
        threshold: Minimum score threshold
    
    Returns:
        Filtered chunks above threshold
    """
    if not chunks:
        return []
    
    bm25 = build_bm25_index(chunks)
    scores = bm25.get_scores(tokenize_for_bm25(query))
    
    filtered = []
    reference_chunks = 0
    reference_filtered = 0
    
    for i, (chunk, score) in enumerate(zip(chunks, scores)):
        # FIX-1: Apply 1.4x stricter threshold to reference docs (gentler nudge)
        chunk_threshold = threshold
        if chunk.get('doc_type') == 'reference':
            chunk_threshold = threshold * 1.4  # Was 2x, now 1.4x for softer filtering
            reference_chunks += 1
            if score < chunk_threshold:
                reference_filtered += 1
        
        if score >= chunk_threshold:
            filtered.append(chunk)
    
    # Debug logging for FIX-1
    if reference_chunks > 0:
        print(f"   FIX-1 Debug: {reference_chunks} reference chunks, {reference_filtered} filtered out ({reference_filtered/reference_chunks*100:.0f}%)")
    
    return filtered


def filter_by_length(
    chunks: List[Dict[str, Any]],
    min_tokens: int = 30
) -> List[Dict[str, Any]]:
    """
    Remove chunks below minimum token count (boilerplate filter).
    
    Args:
        chunks: List of chunk dicts
        min_tokens: Minimum tokens required
    
    Returns:
        Filtered chunks
    """
    return [chunk for chunk in chunks if chunk.get("token_count", 0) >= min_tokens]


def prefilter_chunks(
    chunks: List[Dict[str, Any]],
    query: str,
    bm25_threshold: float = 0.05,
    min_tokens: int = 30
) -> List[Dict[str, Any]]:
    """
    Apply all pre-filtering: BM25 + length filter.
    
    Args:
        chunks: Input chunks
        query: Query for BM25 scoring
        bm25_threshold: BM25 score threshold
        min_tokens: Minimum token count
    
    Returns:
        Filtered chunks
    """
    filtered = filter_by_length(chunks, min_tokens)
    
    if not filtered:
        return chunks[:15] if chunks else []
    
    filtered = filter_chunks_bm25(filtered, query, bm25_threshold)
    
    if len(filtered) == 0 and len(chunks) > 0:
        return chunks[:15]
    
    return filtered


def prefilter_chunks_with_stats(
    chunks: List[Dict[str, Any]],
    query: str,
    bm25_threshold: float = 0.5,
    min_tokens: int = 30
) -> Tuple[List[Dict[str, Any]], int, int, float]:
    """
    Apply pre-filtering and return stats for token reduction tracking.
    
    Args:
        chunks: Input chunks
        query: Query for BM25 scoring
        bm25_threshold: BM25 score threshold
        min_tokens: Minimum token count
    
    Returns:
        Tuple of (filtered_chunks, tokens_before, tokens_after, reduction_pct)
    """
    from pipeline.chunker import count_chunks_tokens
    
    tokens_before = count_chunks_tokens(chunks)
    
    filtered = filter_by_length(chunks, min_tokens)
    
    if not filtered:
        return (chunks[:15] if chunks else [], tokens_before, tokens_before, 0.0)
    
    # FIX-1 Debug: Log doc_type, threshold, and survival rate per document
    print(f"\n   🔍 FIX-1 Debug: Document Classification & Filter Survival")
    doc_types = {}
    for chunk in filtered:
        doc_id = chunk['doc_id']
        doc_type = chunk.get('doc_type', 'unknown')
        if doc_id not in doc_types:
            # FIX-1: Apply 1.0x multiplier to task docs, 1.4x to reference docs only
            effective_threshold = bm25_threshold * 1.4 if doc_type == 'reference' else bm25_threshold * 1.0
            doc_types[doc_id] = {
                'doc_type': doc_type,
                'threshold': effective_threshold,
                'chunks_before': 0,
                'chunks_after': 0
            }
        doc_types[doc_id]['chunks_before'] += 1
    
    # Apply BM25 filter and count survivors per doc
    filtered_result = filter_chunks_bm25(filtered, query, bm25_threshold)
    
    # FIX-4: Fallback loop - if fewer chunks survive than minimum required, relax threshold
    min_required = min(3 * len(doc_types), len(filtered))
    relaxed_threshold = bm25_threshold
    while len(filtered_result) < min_required and relaxed_threshold > 0.05:
        relaxed_threshold = max(0.05, relaxed_threshold - 0.25)
        filtered_result = filter_chunks_bm25(filtered, query, relaxed_threshold)
        if len(filtered_result) >= min_required:
            break
    
    for chunk in filtered_result:
        doc_id = chunk['doc_id']
        if doc_id in doc_types:
            doc_types[doc_id]['chunks_after'] += 1
    
    # Print per-document breakdown
    for doc_id, info in sorted(doc_types.items()):
        survival_rate = (info['chunks_after'] / info['chunks_before'] * 100) if info['chunks_before'] > 0 else 0
        print(f"     {doc_id}:")
        print(f"       doc_type: {info['doc_type']}")
        print(f"       BM25 threshold: {info['threshold']:.2f}x (base: {bm25_threshold})")
        print(f"       chunks: {info['chunks_before']} → {info['chunks_after']} ({survival_rate:.0f}% survive)")
    
    if len(filtered_result) == 0 and len(chunks) > 0:
        filtered_result = chunks[:15]
    
    tokens_after = count_chunks_tokens(filtered_result)
    
    if tokens_before > 0:
        reduction_pct = round((1 - tokens_after / tokens_before) * 100, 1)
    else:
        reduction_pct = 0.0
    
    return (filtered_result, tokens_before, tokens_after, reduction_pct)
