#!/usr/bin/env python3
"""
tuner.py - CLI tool for tuning BM25 threshold and other pipeline parameters.

Usage:
    python tuner.py --help
    python tuner.py --threshold 0.1 --min-tokens 30
    python tuner.py --test --verbose
"""

import argparse
import json
import asyncio
from typing import Dict, Any, List, Tuple
from rank_bm25 import BM25Okapi
import re

from pipeline.chunker import chunk_documents, classify_doc_type
from pipeline.filter import filter_chunks_bm25, prefilter_chunks, tokenize_for_bm25
from pipeline.ranker import rank_chunks
from pipeline.extractor import call_llm, build_extract_prompt, parse_llm_response
from schemas.models import TransformRequest, Document

def tokenize_for_bm25(text: str) -> List[str]:
    """Simple tokenization for BM25"""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text.split()


def build_bm25_index(chunks: List[Dict[str, Any]]) -> BM25Okapi:
    """Build BM25 index from chunks."""
    tokenized_docs = [tokenize_for_bm25(chunk["text"]) for chunk in chunks]
    return BM25Okapi(tokenized_docs)


def test_pipeline(
    documents: List[Dict[str, str]],
    task: str,
    schema: str,
    bm25_threshold: float,
    min_tokens: int,
    verbose: bool = False
) -> Dict[str, Any]:
    """Run the full pipeline with custom thresholds."""
    
    # Stage 1: Chunking
    docs_as_dicts = [{"id": doc.get("id", "doc"), "content": doc.get("content", "")} for doc in documents]
    
    for doc in docs_as_dicts:
        doc_type = classify_doc_type(doc['content'])
        doc['doc_type'] = doc_type
        if verbose:
            print(f"   Doc '{doc['id']}': {doc_type}")
    
    all_chunks = chunk_documents(docs_as_dicts, chunk_size=256, overlap=50)
    if verbose:
        print(f"   ✓ Created {len(all_chunks)} chunks")
    
    # Stage 2: Pre-filtering
    filtered = prefilter_chunks(all_chunks, task, bm25_threshold=bm25_threshold, min_tokens=min_tokens)
    
    # Per-doc stats
    doc_stats = {}
    for chunk in all_chunks:
        doc_id = chunk['doc_id']
        if doc_id not in doc_stats:
            doc_type = chunk.get('doc_type', 'unknown')
            doc_stats[doc_id] = {
                'doc_type': doc_type,
                'before': 0,
                'after': 0,
                'threshold': bm25_threshold * (1.4 if doc_type == 'reference' else 1.0)
            }
        doc_stats[doc_id]['before'] += 1
    
    for chunk in filtered:
        doc_id = chunk['doc_id']
        if doc_id in doc_stats:
            doc_stats[doc_id]['after'] += 1
    
    # Calculate token stats
    tokens_before = sum(c.get('token_count', 0) for c in all_chunks)
    tokens_after = sum(c.get('token_count', 0) for c in filtered)
    tokens_reduction = round((1 - tokens_after / tokens_before) * 100, 1) if tokens_before > 0 else 0
    
    if verbose:
        print(f"\n   BM25 Filter Stats:")
        print(f"   ------------------")
        for doc_id, stats in sorted(doc_stats.items()):
            rate = (stats['after'] / stats['before'] * 100) if stats['before'] > 0 else 0
            print(f"     {doc_id}: {stats['doc_type']} | threshold: {stats['threshold']:.2f}x | {stats['before']} → {stats['after']} ({rate:.0f}%)")
        print(f"\n   Tokens: {tokens_before} → {tokens_after} ({tokens_reduction}% reduction)")
        print(f"   Chunks: {len(all_chunks)} → {len(filtered)}")
    
    # Stage 3: Ranking
    ranked = rank_chunks(filtered, task, schema, top_n=15)
    if verbose:
        print(f"\n   ✓ Ranked {len(ranked)} chunks")
    
    # Stage 4: LLM Call (mock - just build prompt)
    prompt = build_extract_prompt(ranked, task, schema)
    prompt_tokens = len(prompt.split())
    
    if verbose:
        print(f"\n   Prompt length: ~{prompt_tokens} tokens")
    
    return {
        'chunks_before': len(all_chunks),
        'chunks_after': len(filtered),
        'tokens_before': tokens_before,
        'tokens_after': tokens_after,
        'tokens_reduction': tokens_reduction,
        'doc_stats': doc_stats
    }


def load_test_inputs(filepath: str) -> Tuple[List[Dict[str, str]], str, str]:
    """Load test inputs from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    documents = data.get('documents', [])
    task = data.get('task', 'extract tasks')
    schema = data.get('schema', 'tasks_v1')
    
    return documents, task, schema


def run_grid_search(
    documents: List[Dict[str, str]],
    task: str,
    schema: str,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """Run grid search across threshold values."""
    
    thresholds = [1.0, 2.0, 2.5, 3.0, 3.5, 4.0]
    min_tokens_values = [30, 50]
    
    results = []
    
    for mt in min_tokens_values:
        for thresh in thresholds:
            if verbose:
                print(f"\n{'='*60}")
                print(f"Testing: threshold={thresh}, min_tokens={mt}")
                print('='*60)
            
            result = test_pipeline(documents, task, schema, thresh, mt, verbose=verbose)
            results.append({
                'threshold': thresh,
                'min_tokens': mt,
                **result
            })
    
    return results


def print_grid_summary(results: List[Dict[str, Any]]) -> None:
    """Print summary of grid search results."""
    print("\n" + "="*80)
    print("GRID SEARCH RESULTS")
    print("="*80)
    print(f"{'Threshold':<10} {'MinTok':<8} {'Chunks':<10} {'Reduction':<12} {'Docs Surviving':<20}")
    print("-"*80)
    
    for r in results:
        surviving_docs = sum(1 for d in r['doc_stats'].values() if d['after'] > 0)
        doc_count = f"{surviving_docs}/{len(r['doc_stats'])}"
        print(f"{r['threshold']:<10.2f} {r['min_tokens']:<8} {r['chunks_after']:<10} {r['tokens_reduction']:<12.1f}% {doc_count:<20}")
    
    print("="*80)
    
    # Find optimal
    best = max(results, key=lambda x: x['tokens_reduction'] if x['chunks_after'] >= 10 else -1)
    print(f"\nRecommended: threshold={best['threshold']}, min_tokens={best['min_tokens']}")
    print(f"  → {best['tokens_reduction']}% token reduction, {best['chunks_after']} chunks")


def interactive_tuner(documents: List[Dict[str, str]], task: str, schema: str) -> None:
    """Interactive mode for tuning parameters."""
    print("\n" + "="*60)
    print("INTERACTIVE TUNER")
    print("="*60)
    print("Adjust BM25 threshold and min_tokens to find optimal filtering")
    print("Type 'q' to quit\n")
    
    threshold = 0.15
    min_tokens = 30
    
    while True:
        print(f"\nCurrent settings: threshold={threshold}, min_tokens={min_tokens}")
        result = test_pipeline(documents, task, schema, threshold, min_tokens, verbose=True)
        
        print(f"\nOptions:")
        print("  t [value] - Set BM25 threshold (e.g., 't 0.1')")
        print("  m [value] - Set min_tokens (e.g., 'm 50')")
        print("  h - Show this help")
        print("  q - Quit")
        
        cmd = input("\n> ").strip().lower()
        
        if cmd == 'q':
            break
        elif cmd == 'h':
            continue
        elif cmd.startswith('t '):
            try:
                threshold = float(cmd.split()[1])
            except (ValueError, IndexError):
                print("  Error: invalid threshold value")
        elif cmd.startswith('m '):
            try:
                min_tokens = int(cmd.split()[1])
            except (ValueError, IndexError):
                print("  Error: invalid min_tokens value")
        else:
            print(f"  Unknown command: {cmd}")


def main():
    parser = argparse.ArgumentParser(
        description="Tune BM25 threshold for better document filtering",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tuner.py --test                    # Run grid search
  python tuner.py --threshold 0.1           # Test single setting
  python tuner.py --interactive             # Interactive mode
        """
    )
    
    parser.add_argument('--threshold', type=float, default=None,
                        help='BM25 threshold to test')
    parser.add_argument('--min-tokens', type=int, default=30,
                        help='Minimum token count for chunks')
    parser.add_argument('--interactive', action='store_true',
                        help='Run in interactive tuning mode')
    parser.add_argument('--test', action='store_true',
                        help='Run grid search across multiple thresholds')
    parser.add_argument('--input', type=str, default='test_inputs/meeting_notes.json',
                        help='Input JSON file with test documents')
    parser.add_argument('--verbose', action='store_true',
                        help='Show detailed output')
    
    args = parser.parse_args()
    
    # Load test data
    documents, task, schema = load_test_inputs(args.input)
    
    if args.interactive:
        interactive_tuner(documents, task, schema)
    elif args.test:
        results = run_grid_search(documents, task, schema, verbose=args.verbose)
        print_grid_summary(results)
    elif args.threshold is not None:
        test_pipeline(documents, task, schema, args.threshold, args.min_tokens, verbose=args.verbose)
    else:
        # Default: run with recommended settings
        test_pipeline(documents, task, schema, 0.15, 30, verbose=True)


if __name__ == '__main__':
    main()
