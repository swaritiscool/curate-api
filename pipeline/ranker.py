from typing import List, Dict, Any
import re
import heapq
from functools import lru_cache

# Pre-compile verb density patterns (run once at module load)
_VERB_PATTERNS = [
    r'\b(need|must|should|will|would|could|may|might)\b',
    r'\b(complete|finish|start|begin|end|submit|review|approve|finalize|wrap|close)\b',
    r'\b(create|update|delete|fix|build|deploy|test|implement|develop|code|refactor|merge|rollback)\b',
    r'\b(send|call|email|contact|meet|schedule|ping|notify|alert|inform|tell|ask|request)\b',
    r'\b(confirm|coordinate|check|chase|follow|follow-up|sync|align|pair|loop|escalate|flag|block)\b',
    r'\b(write|document|draft|prepare|update|record|log|note|report|present|share)\b',
    r'\b(check|verify|validate|investigate|debug|analyze|research|look|spike|audit|inspect)\b',
    r'\b(decide|choose|select|pick|confirm|approve|reject|accept|agree|commit)\b',
    r'\b(action|todo|task|ticket|blocker|blocked|pending|waiting|owner|due|deadline)\b',
]

_VERB_COMPILED = [re.compile(p, re.IGNORECASE) for p in _VERB_PATTERNS]


def select_top_chunks_per_doc(
    all_chunks: List[Dict[str, Any]],
    documents: List[Dict[str, Any]],
    total_budget: int = 15
) -> List[Dict[str, Any]]:
    """
    FIX-2: Allocate chunk budget proportionally across documents.
    Guarantees representation from every document.
    Minimum 3 chunks per document, remaining budget distributed by doc size.
    
    Args:
        all_chunks: All chunks from all documents
        documents: List of document dicts with 'id' and 'token_count'
        total_budget: Total number of chunks to select (default 15)
    
    Returns:
        Selected chunks with proportional representation
    """
    num_docs = len(documents)
    if num_docs == 0:
        return all_chunks[:total_budget]
    
    min_per_doc = 3
    base_allocation = min_per_doc
    remaining_budget = total_budget - (base_allocation * num_docs)
    
    # Calculate total tokens across all docs
    total_tokens = sum(doc.get('token_count', len(doc.get('content', '')) // 4) for doc in documents)
    if total_tokens == 0:
        total_tokens = 1
    
    selected = []
    for doc in documents:
        doc_id = doc.get('id', doc.get('doc_id', ''))
        doc_chunks = [c for c in all_chunks if c.get('doc_id') == doc_id]
        
        if not doc_chunks:
            continue
        
        # Proportional share of remaining budget
        doc_tokens = doc.get('token_count', len(doc.get('content', '')) // 4)
        proportion = doc_tokens / total_tokens
        extra = int(remaining_budget * proportion)
        allocation = base_allocation + extra
        
        # Take top-N by score for this doc using heapq.nlargest (faster than sort)
        top = heapq.nlargest(allocation, doc_chunks, key=lambda x: x.get('_score', 0))
        selected.extend(top)
    
    return selected


def calculate_verb_density(text: str) -> float:
    """
    Calculate verb density as proxy for action-oriented content.
    Simple heuristic: count common verb patterns using pre-compiled regex.
    """
    text_lower = text.lower()
    verb_count = 0
    for pattern in _VERB_COMPILED:
        verb_count += len(pattern.findall(text_lower))
    
    word_count = len(text.split())
    if word_count == 0:
        return 0.0
    
    return verb_count / word_count


def extract_named_entities(text: str) -> int:
    """
    Count named entity signals (capitalized words, dates, etc).
    Returns count as boost signal.
    """
    entity_count = 0
    
    capitalized_words = re.findall(r'\b[A-Z][a-z]+\b', text)
    entity_count += len(capitalized_words)
    
    date_patterns = re.findall(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b', text)
    entity_count += len(date_patterns)
    
    return entity_count


def rank_chunks(
    chunks: List[Dict[str, Any]],
    task: str,
    schema_type: str = "tasks_v1",
    top_n: int = 15
) -> List[Dict[str, Any]]:
    """
    Rank chunks by task-specific heuristics and return top-N.
    Prefers existing _score from BM25 filtering if present.
    Uses heapq.nlargest for O(n log k) instead of O(n log n) full sort.
    
    Args:
        chunks: Filtered chunks
        task: Task string for relevance
        schema_type: Schema type for ranking strategy
        top_n: Number of top chunks to return
    
    Returns:
        Top-N ranked chunks
    """
    scored_chunks = []
    
    for chunk in chunks:
        text = chunk["text"]
        
        # Use existing _score from BM25 filtering if available
        if '_score' in chunk:
            score = chunk['_score']
        else:
            # Calculate score if not present (for other pipeline stages)
            score = 0.0
            if schema_type == "tasks_v1":
                score = calculate_verb_density(text)
            elif schema_type == "entities_v1":
                score = extract_named_entities(text) * 0.01
            elif schema_type == "summary_v1":
                score = len(text) / 100.0
            else:
                score = 0.5
        
        scored_chunk = chunk.copy()
        scored_chunk["_score"] = score
        scored_chunks.append(scored_chunk)
    
    # Use heapq.nlargest for efficiency when top_n << len(chunks)
    # This is O(n log k) instead of O(n log n) for full sort
    top_chunks = heapq.nlargest(top_n, scored_chunks, key=lambda x: x.get('_score', 0))
    
    for chunk in top_chunks:
        chunk.pop("_score", None)
    
    return top_chunks
