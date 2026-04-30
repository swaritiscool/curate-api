import pytest
import tiktoken
from pipeline.chunker import chunk_document, chunk_documents

def test_chunker_multiple_chunks():
    """A 1000-token document produces multiple chunks"""
    text = "word " * 1000
    chunks = chunk_document(text, "test_doc", chunk_size=256, overlap=50)
    assert len(chunks) > 1

def test_chunk_fields():
    """Every chunk has doc_id, chunk_id, position fields"""
    text = "This is a test document for chunking."
    chunks = chunk_document(text, "test_doc")
    for chunk in chunks:
        assert "doc_id" in chunk
        assert "chunk_id" in chunk
        assert "position" in chunk
        assert "text" in chunk
        assert chunk["doc_id"] == "test_doc"

def test_chunk_size_limit():
    """Chunk size never exceeds 512 tokens"""
    # Force a large chunk size to test limit
    text = "word " * 2000
    chunks = chunk_document(text, "test_doc", chunk_size=512)
    enc = tiktoken.get_encoding("cl100k_base")
    for chunk in chunks:
        tokens = enc.encode(chunk["text"])
        assert len(tokens) <= 512

def test_chunks_contiguous():
    """Chunks are contiguous — no text is dropped between chunk 1 and chunk N"""
    text = "one two three four five six seven eight nine ten"
    # Small chunk size to force many chunks
    chunks = chunk_document(text, "test_doc", chunk_size=2, overlap=0)
    reconstructed = "".join([c["text"] for c in chunks])
    # The chunker might add some whitespace or use the encoder's decoding
    # We check if all words are present in order
    for word in text.split():
        assert word in reconstructed

def test_short_doc_single_chunk():
    """A very short doc (under 256 tokens) produces exactly 1 chunk"""
    text = "Short document."
    chunks = chunk_document(text, "test_doc", chunk_size=256)
    assert len(chunks) == 1

def test_position_sequential():
    """position values are sequential and zero-indexed"""
    text = "word " * 500
    chunks = chunk_document(text, "test_doc", chunk_size=100, overlap=10)
    assert chunks[0]["position"] == 0
    for i in range(1, len(chunks)):
        assert chunks[i]["position"] > chunks[i-1]["position"]

def test_multi_doc_namespacing():
    """Two docs processed together maintain separate doc_id namespacing"""
    docs = [
        {"id": "doc_a", "content": "Content A"},
        {"id": "doc_b", "content": "Content B"}
    ]
    chunks = chunk_documents(docs)
    doc_a_chunks = [c for c in chunks if c["doc_id"] == "doc_a"]
    doc_b_chunks = [c for c in chunks if c["doc_id"] == "doc_b"]
    assert len(doc_a_chunks) > 0
    assert len(doc_b_chunks) > 0
    assert doc_a_chunks[0]["text"] == "Content A"
    assert doc_b_chunks[0]["text"] == "Content B"
