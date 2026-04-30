from typing import List, Dict, Any
import tiktoken


def classify_doc_type(content: str) -> str:
    """
    FIX-1: Classify document as 'reference' or 'task'.
    Reference docs: technical runbooks, architecture docs, glossaries, specs
    Task docs: meeting notes, todo lists, emails, action item lists
    
    Returns:
        'reference' or 'task'
    """
    lines = content.strip().split('\n')
    
    # Check BOTH first 20% AND middle 20% to catch docs that start with tasks but are reference
    first_20_pct = lines[:max(5, int(len(lines) * 0.2))]
    middle_start = int(len(lines) * 0.4)
    middle_20_pct = lines[middle_start:middle_start + max(5, int(len(lines) * 0.2))]
    
    first_text = ' '.join(first_20_pct).lower()
    middle_text = ' '.join(middle_20_pct).lower()
    combined_text = first_text + ' ' + middle_text
    
    # Strong task indicators (ONLY meeting/conversation formats)
    strong_task_indicators = {
        'meeting', 'minutes', 'participants', 'attendees',
        'action item', 'action items',
        'agenda', 'sync', 'standup', 'retrospective',
        'sarah:', 'mike:', 'team:', 'rohan:', 'priya:',  # Common names in meetings
        'said', 'asked', 'replied', 'responded'  # Conversation markers
    }
    
    # General task indicators
    task_indicators = {
        'send', 'schedule', 'follow up', 'confirm', 'update', 
        'create', 'review', 'complete', 'assign', 'check',
        'coordinate', 'draft', 'ping', 'relay', 'chase',
        'own', 'write', 'flag', 'contact',
    }
    
    # Strong reference indicators (technical documentation titles/formats)
    strong_ref_indicators = {
        'runbook', 'specification', 'glossary', 'architecture',
        'technical documentation', 'api reference', 'user guide',
        'system design', 'infrastructure', 'deployment guide',
        'version:', 'v1.', 'v2.', 'v3.', 'v4.',  # Version numbers
        'table of contents', 'overview', 'introduction'
    }
    
    # General reference indicators (technical jargon density)
    reference_indicators = {
        'technical', 'implementation', 'deployed', 'configured',
        'service', 'microservice', 'kubernetes', 'docker', 'container',
        'module', 'component', 'infrastructure', 'system',
        'api', 'endpoint', 'authentication', 'authorization',
        'database', 'cache', 'queue', 'worker', 'gateway'
    }
    
    # Count indicators in combined text
    strong_task_count = sum(1 for indicator in strong_task_indicators if indicator in combined_text)
    task_count = sum(1 for indicator in task_indicators if indicator in combined_text)
    strong_ref_count = sum(1 for indicator in strong_ref_indicators if indicator in combined_text)
    ref_count = sum(1 for indicator in reference_indicators if indicator in combined_text)
    
    # Total counts with weighting
    total_task = strong_task_count * 3 + task_count
    total_ref = strong_ref_count * 3 + ref_count
    
    # FIX: Count total indicator occurrences, not just presence
    total_task_words = 0
    total_ref_words = 0
    for indicator in strong_task_indicators:
        if indicator in combined_text:
            total_task_words += combined_text.count(indicator) * 3
    for indicator in task_indicators:
        if indicator in combined_text:
            total_task_words += combined_text.count(indicator)
    for indicator in strong_ref_indicators:
        if indicator in combined_text:
            total_ref_words += combined_text.count(indicator) * 3
    for indicator in reference_indicators:
        if indicator in combined_text:
            total_ref_words += combined_text.count(indicator)
    
    # Check for list structure (bullets/numbers) - common in task lists
    has_list_structure = any(line.strip().startswith(('-', '*', '•')) 
                            for line in first_20_pct)
    
    # Check for dialogue/conversation format (meeting notes)
    # FIX-2: Only count dialogue if line contains actual conversation markers
    has_dialogue = any(
        ':' in line and len(line.split()) < 20 and 
        any(name in line.lower() for name in ['rohan', 'sarah', 'mike', 'team:', 'priya:', 'dev:', 'marcus:'])
        for line in first_20_pct[:10]
    )
    
    # Decision logic - require fewer task signals to classify as task
    # Strong meeting/conversation signals → task
    if strong_task_count >= 3 or (strong_task_count >= 2 and has_dialogue):
        return 'task'
    
    # Strong reference signals → reference
    if strong_ref_count >= 2:
        return 'reference'
    
    # High technical jargon density → reference
    if ref_count >= 8:
        return 'reference'
    
    # List structure with task verbs → task
    if has_list_structure and task_count >= 3:
        return 'task'
    
    # FIX-2: Use word count instead of indicator count for threshold
    # Only classify as task if we have at least 20 task-related word occurrences
    if total_task_words >= 20:
        return 'task'
    
    # Default to reference if ambiguous
    if total_task_words > total_ref_words * 1.5:  # Need 1.5x more task words
        return 'task'
    
    return 'reference'


def tokenize(text: str) -> List[str]:
    """Tokenize text using tiktoken"""
    encoder = tiktoken.get_encoding("cl100k_base")
    tokens = encoder.encode(text)
    return tokens


def count_tokens(text: str) -> int:
    """Count tokens in text"""
    encoder = tiktoken.get_encoding("cl100k_base")
    return len(encoder.encode(text))


def count_chunks_tokens(chunks: List[Dict[str, Any]]) -> int:
    """Count total tokens in a list of chunks"""
    return sum(chunk.get("token_count", 0) for chunk in chunks)


def chunk_document(
    text: str,
    doc_id: str,
    chunk_size: int = 256,
    overlap: int = 50,
    doc_type: str = None
) -> List[Dict[str, Any]]:
    """
    Split document into fixed-size chunks with provenance tags.
    
    Args:
        text: Document text
        doc_id: Unique document identifier
        chunk_size: Tokens per chunk (256-512 per PRD)
        overlap: Token overlap between chunks
        doc_type: Document type ('reference' or 'task') for FIX-1
    
    Returns:
        List of chunks with doc_id, chunk_id, position tags
    """
    encoder = tiktoken.get_encoding("cl100k_base")
    tokens = encoder.encode(text)
    
    chunks = []
    start = 0
    chunk_id = 0
    
    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        
        chunk_text = encoder.decode(chunk_tokens)
        
        if len(chunk_text.strip()) > 0:
            chunk = {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "position": start,
                "text": chunk_text,
                "token_count": len(chunk_tokens)
            }
            # FIX-1: Store doc_type on each chunk for later filtering
            if doc_type:
                chunk["doc_type"] = doc_type
            chunks.append(chunk)
            chunk_id += 1
        
        start += chunk_size - overlap
    
    return chunks


def chunk_documents(
    documents: List[Dict[str, str]],
    chunk_size: int = 256,
    overlap: int = 50
) -> List[Dict[str, Any]]:
    """
    Chunk multiple documents with provenance tracking.
    
    Args:
        documents: List of document dicts with 'id' and 'content'
        chunk_size: Tokens per chunk
        overlap: Token overlap between chunks
    
    Returns:
        All chunks from all documents with provenance
    """
    all_chunks = []
    
    for doc_idx, doc in enumerate(documents):
        # FIX-1: Classify document type before chunking
        doc_id = doc.get('id', f"doc_{doc_idx}")
        content = doc.get('content', doc) if isinstance(doc, dict) else doc
        doc_type = classify_doc_type(content)
        
        doc_chunks = chunk_document(content, doc_id, chunk_size, overlap, doc_type)
        all_chunks.extend(doc_chunks)
    
    return all_chunks
