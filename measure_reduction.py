#!/usr/bin/env python3
"""
Token reduction measurement script for Curate.ai

Tests BM25 filtering effectiveness across fixture documents.
Expects reduction_pct between 60-80% for optimal filtering.
"""

import httpx
import asyncio
import json
from pathlib import Path

TEST_DOCS = [
    ("meeting_notes.txt", "API documentation press release Legal deadline"),
    ("email_thread.txt", "AWS research monitoring Graviton migration"),
    ("empty_noise.txt", "extract tasks"),
]

FIXTURES_DIR = Path("tests/fixtures")


async def test_token_reduction():
    print(f"\n{'doc':<20} | {'tokens_before':>13} | {'tokens_after':>12} | {'reduction':>9} | {'tasks_found':>11}")
    print("-" * 80)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for doc_name, task in TEST_DOCS:
            doc_path = FIXTURES_DIR / doc_name
            
            if not doc_path.exists():
                print(f"{doc_name:<20} | {'FILE NOT FOUND':>13} | {'':>12} | {'':>9} | {'':>11}")
                continue
            
            with open(doc_path, 'r') as f:
                content = f.read()
            
            payload = {
                "documents": [{"id": doc_name, "content": content}],
                "task": task,
                "schema": "tasks_v1"
            }
            
            try:
                response = await client.post("http://localhost:8000/v1/transform", json=payload)
                
                if response.status_code != 200:
                    print(f"{doc_name:<20} | {'ERROR':>13} | {response.status_code:>12} | {'':>9} | {'':>11}")
                    continue
                
                data = response.json()
                meta = data.get("meta", {})
                
                tokens_before = meta.get("tokens_before_filter", 0)
                tokens_after = meta.get("tokens_after_filter", 0)
                reduction_pct = meta.get("reduction_pct", 0)
                tasks_count = len(data.get("data", {}).get("tasks", []))
                
                reduction_str = f"{reduction_pct}%"
                
                color_ok = "\033[92m" if 60 <= reduction_pct <= 80 else "\033[93m"
                color_reset = "\033[0m"
                
                if reduction_pct < 60:
                    reduction_str = f"{color_ok}{reduction_pct}% (LOW){color_reset}"
                elif reduction_pct > 85:
                    reduction_str = f"{color_ok}{reduction_pct}% (HIGH){color_reset}"
                
                print(f"{doc_name:<20} | {tokens_before:>13} | {tokens_after:>12} | {reduction_str:>9} | {tasks_count:>11}")
                
            except httpx.ConnectError:
                print(f"{doc_name:<20} | {'SERVER OFFLINE':>13} | {'':>12} | {'':>9} | {'':>11}")
                print("\n⚠️  Make sure the server is running: python -m uvicorn main:app --reload")
                return
            except Exception as e:
                print(f"{doc_name:<20} | {'ERROR':>13} | {str(e):>12} | {'':>9} | {'':>11}")
    
    print("-" * 80)
    print("\nTarget reduction: 60-80%")
    print("  < 60%: BM25 threshold too loose — raise it")
    print("  > 85%: May be dropping relevant chunks — check task quality")


if __name__ == "__main__":
    print("\n🚀 Curate.ai Token Reduction Measurement\n")
    asyncio.run(test_token_reduction())
